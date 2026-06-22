"""数据初始化器 - 多源填充 StockInfo+KlineCache,全市场+热榜双模式"""

import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

from services.base import BaseService, ServiceResult
from shared.logging import emit_log


class DataInitializer(BaseService):
    """多源数据填充器 - 全市场初始加载 + 热榜增量刷新"""

    def __init__(self):
        super().__init__()
        self._provider = None

    @property
    def provider(self):
        if self._provider is None:
            from providers.market_data import MarketDataProvider

            self._provider = MarketDataProvider()
        return self._provider

    def is_db_empty(self) -> bool:
        from shared.logging import emit_log

        try:
            from shared.models import StockInfo, get_session

            session = get_session()
            count = session.query(StockInfo).filter(StockInfo.latest_price > 0).count()
            session.close()
            return count == 0
        except Exception as e:
            emit_log("ERROR", "data_initializer", f"Operation failed: {str(e)[:100]}")
            return True

    # ════════════════════════════════════════════
    # ════════════════════════════════════════════

    def get_full_universe(self, force_refresh: bool = False) -> list:
        """全A股标的列表(股票+ETF+LOF)
        DB优先 → AkShare → StockInfo表兜底 → 热榜池 → 蓝筹"""
        from shared.logging import emit_log

        # 1. DB缓存 (24h内有效)
        if not force_refresh:
            codes = self._get_full_universe_from_cache()
            if codes and len(codes) >= 100:
                return codes

        # 2. AkShare 全市场快照
        codes = []
        try:
            df = self.provider.get_full_market_spot()
            if df is not None and not df.empty:
                for _, r in df.iterrows():
                    code = str(r.get("代码", ""))
                    if code and len(code) == 6:
                        cat = (
                            "ETF"
                            if code.startswith(("51", "58", "15", "16"))
                            else ("LOF" if code.startswith("16") else "股票")
                        )
                        codes.append(
                            {"code": code, "name": str(r.get("名称", "")), "category": cat}
                        )
        except Exception as e:
            emit_log("WARNING", "data_init", f"{type(e).__name__}: {str(e)[:100]}")

        if len(codes) >= 1000:
            self._cache_full_universe(codes)
            return codes

        # 3. API失败 → StockInfo表兜底
        emit_log("WARNING", "data_init", "全市场API不可用, 从StockInfo表获取已有股票")
        db_codes = self._get_pool_from_stockinfo()
        if db_codes and len(db_codes) >= 50:
            emit_log("INFO", "data_init", f"StockInfo兜底: {len(db_codes)}只")
            return [{"code": c, "name": c, "category": "股票"} for c in db_codes]

        # 4. 热榜池兜底
        hot_codes = self.get_hot_stock_pool()
        if hot_codes and len(hot_codes) >= 50:
            emit_log("INFO", "data_init", f"热榜池兜底: {len(hot_codes)}只")
            return [{"code": c, "name": c, "category": "股票"} for c in hot_codes]

        # 5. 蓝筹终极兜底
        emit_log("WARNING", "data_init", "全市场数据不可用, 使用98只蓝筹兜底")
        return [{"code": c, "name": c, "category": "股票"} for c in self._fallback_bluechips()]

    def _get_full_universe_from_cache(self) -> list:
        try:
            from shared.models import MarketSnapshot, get_session

            session = get_session()
            row = session.query(MarketSnapshot).filter_by(snapshot_type="full_universe").first()
            session.close()
            if row and row.data_json:
                data = json.loads(row.data_json)
                age = (datetime.now() - row.updated_at).total_seconds()
                if age < 86400:
                    codes = data.get("codes", [])
                    if codes:
                        return codes
        except Exception as e:
            emit_log("WARNING", "data_init", f"{type(e).__name__}: {str(e)[:100]}")
        return []

    def _cache_full_universe(self, codes: list):
        try:
            from shared.models import MarketSnapshot, get_session

            session = get_session()
            row = session.query(MarketSnapshot).filter_by(snapshot_type="full_universe").first()
            payload = json.dumps(
                {
                    "codes": [c["code"] for c in codes],
                    "details": codes,
                    "total": len(codes),
                    "updated": datetime.now().isoformat(),
                },
                ensure_ascii=False,
            )
            if row:
                row.data_json = payload
                row.updated_at = datetime.now()
            else:
                session.add(
                    MarketSnapshot(
                        snapshot_type="full_universe", data_json=payload, updated_at=datetime.now()
                    )
                )
            session.commit()
            session.close()
        except Exception as e:
            emit_log("WARNING", "data_init", f"{type(e).__name__}: {str(e)[:100]}")

    def get_hot_stock_pool(self) -> list:
        """热榜股票池
        0. 确认数据日期(交易日当天/最近交易日)
        1. DB查 2. API获取 3. 存DB 4. 返回"""
        from services.trading_calendar import TradingCalendar

        tc = TradingCalendar()
        data_date = tc.effective_data_date()

        from shared.logging import emit_log

        if not tc.is_trading_day():
            emit_log("INFO", "data_init", f"非交易日 → 获取最近交易日({data_date})数据")
        elif tc.is_market_closed_today():
            emit_log("INFO", "data_init", f"盘后模式 → 获取今日({data_date})数据")

        codes = self._get_pool_from_cache(data_date)
        if not codes or len(codes) < 50:
            codes = self._get_pool_from_nearby_dates(data_date, 10)
        if codes and len(codes) >= 50:
            emit_log("INFO", "data_init", f"DB命中 {len(codes)}只 → 零API调用")
            return codes

        api_codes = self.provider.get_hot_stocks_eastmoney(100) or []
        if len(api_codes) >= 50:
            emit_log("INFO", "data_init", f"API获取 {len(api_codes)}只 → 存入DB → 返回")
            self._cache_pool(f"hot_stock_pool_{data_date}", api_codes, "hot_stocks")
            return api_codes

        merged = list(dict.fromkeys(codes + api_codes + self.get_lhb_stock_pool()))
        if len(merged) < 50:
            merged = list(dict.fromkeys(merged + self._get_pool_from_stockinfo()))
        if len(merged) < 20:
            merged = list(dict.fromkeys(merged + self._fallback_bluechips()))

        return merged[:100] if len(merged) >= 20 else self._fallback_bluechips()

    def _get_pool_from_cache(self, data_date: str, prefix: str = "hot_stock") -> list:
        try:
            from shared.models import MarketSnapshot, get_session

            session = get_session()
            cache_key = f"{prefix}_pool_{data_date}"
            row = session.query(MarketSnapshot).filter_by(snapshot_type=cache_key).first()
            session.close()
            if row and row.data_json:
                data = json.loads(row.data_json)
                codes = data.get("codes", [])
                if codes:
                    return codes
        except Exception as e:
            emit_log("WARNING", "data_init", f"{type(e).__name__}: {str(e)[:100]}")
        return []

    def _get_pool_from_nearby_dates(self, data_date: str, lookback: int) -> list:
        from datetime import timedelta

        dt = datetime.strptime(data_date, "%Y-%m-%d")
        from services.trading_calendar import TradingCalendar

        tc = TradingCalendar()
        seen = set()
        all_codes = []
        for _ in range(lookback):
            codes = self._get_pool_from_cache(dt.strftime("%Y-%m-%d"))
            for c in codes:
                key = str(c.get("stock_code", c)) if isinstance(c, dict) else str(c)
                if key not in seen:
                    seen.add(key)
                    all_codes.append(c)
            if len(all_codes) >= 50:
                break
            dt -= timedelta(days=1)
            while not tc.is_trading_day(dt.strftime("%Y-%m-%d")) and _ < lookback - 1:
                dt -= timedelta(days=1)
        return all_codes

    def _get_pool_from_stockinfo(self) -> list:
        try:
            from shared.models import StockInfo, get_session

            session = get_session()
            rows = (
                session.query(StockInfo.stock_code)
                .filter(StockInfo.latest_price > 0)
                .order_by(StockInfo.total_market_cap.desc())
                .all()
            )
            session.close()
            return [r[0] for r in rows]
        except Exception as e:
            emit_log("ERROR", "data_initializer", f"Operation failed: {str(e)[:100]}")
            return []

    def get_lhb_stock_pool(self) -> list:
        """龙虎榜股票池 - DB优先 → API → DB回存 → 返回"""
        from services.trading_calendar import TradingCalendar

        tc = TradingCalendar()
        data_date = tc.effective_data_date()

        codes = self._get_pool_from_cache(data_date, prefix="lhb")
        if codes:
            return codes

        try:
            import akshare as ak

            df = ak.stock_sina_lhb_detail_daily(date=data_date.replace("-", ""))
            if df is not None and not df.empty and "code" in df.columns:
                codes = list(df["code"].dropna().astype(str).unique())[:100]
        except Exception as e:
            emit_log("WARNING", "data_init", f"{type(e).__name__}: {str(e)[:100]}")

        if codes:
            try:
                zt_df = None
                try:
                    import akshare as ak

                    zt_df = ak.stock_zt_pool_em(date=data_date.replace("-", ""))
                except Exception as e:
                    emit_log("WARNING", "data_init", f"{type(e).__name__}: {str(e)[:100]}")
                if zt_df is not None and not zt_df.empty:
                    codes = list(
                        dict.fromkeys(codes + [str(c) for c in zt_df["代码"].tolist() if str(c)])
                    )
            except Exception as e:
                emit_log("WARNING", "data_init", f"{type(e).__name__}: {str(e)[:100]}")
            self._cache_pool(f"lhb_pool_{data_date}", codes, "lhb")
        return codes

    def _cache_pool(self, cache_key: str, codes: list, source: str):
        try:
            from shared.models import MarketSnapshot, get_session

            session = get_session()
            row = session.query(MarketSnapshot).filter_by(snapshot_type=cache_key).first()
            payload = json.dumps(
                {
                    "codes": codes,
                    "source": source,
                    "count": len(codes),
                    "updated": datetime.now().isoformat(),
                },
                ensure_ascii=False,
            )
            if row:
                row.data_json = payload
                row.updated_at = datetime.now()
            else:
                session.add(
                    MarketSnapshot(
                        snapshot_type=cache_key, data_json=payload, updated_at=datetime.now()
                    )
                )
            session.commit()
            session.close()
        except Exception as e:
            emit_log("WARNING", "data_init", f"{type(e).__name__}: {str(e)[:100]}")

    def _fallback_bluechips(self) -> list:
        return [
            "601398",
            "601939",
            "601288",
            "601328",
            "600036",
            "000001",
            "002142",
            "600000",
            "601318",
            "601628",
            "601601",
            "600030",
            "600519",
            "000858",
            "000568",
            "600887",
            "002714",
            "000895",
            "600809",
            "603288",
            "600690",
            "002304",
            "600132",
            "000596",
            "600779",
            "002568",
            "300750",
            "002475",
            "000725",
            "688981",
            "002415",
            "300059",
            "002230",
            "688111",
            "300124",
            "002049",
            "603501",
            "600745",
            "300782",
            "688012",
            "002371",
            "603986",
            "300661",
            "688008",
            "600031",
            "000338",
            "601012",
            "600585",
            "000651",
            "002050",
            "601100",
            "600406",
            "300274",
            "600150",
            "000425",
            "600875",
            "601615",
            "002202",
            "600276",
            "000538",
            "300015",
            "300760",
            "300122",
            "002007",
            "603259",
            "600196",
            "300347",
            "000963",
            "002001",
            "300529",
            "601857",
            "600028",
            "601088",
            "600900",
            "601225",
            "600188",
            "000983",
            "600489",
            "603993",
            "002460",
            "600048",
            "001979",
            "601668",
            "600585",
            "000002",
            "600383",
            "601800",
            "601390",
            "601111",
            "600029",
            "601006",
            "002352",
            "600233",
            "603128",
            "002714",
            "000876",
            "600438",
            "002311",
        ]

    # ════════════════════════════════════════════
    #  数据填充
    # ════════════════════════════════════════════

    def refresh_hot_stocks(self) -> ServiceResult:
        t0 = __import__("time").time()
        pool = self.get_hot_stock_pool()
        emit_log("INFO", "data_init", f"[热榜] 原始池大小: {len(pool)}")
        filtered = []
        for c in pool:
            code = str(c.get("stock_code", c)) if isinstance(c, dict) else str(c)
            if code.startswith(
                ("000", "001", "002", "003", "300", "600", "601", "603", "605", "688")
            ):
                filtered.append(c)
        emit_log("INFO", "data_init", f"[热榜] 过滤后: {len(filtered)}只(取前30)")
        result = self._populate_batch(filtered[:30], "热榜刷新")
        emit_log("INFO", "data_init", f"[热榜] 总耗时{round(__import__('time').time() - t0, 1)}s")
        return result

    def refresh_full_universe(
        self, max_stocks: int = 500, force_refresh: bool = False
    ) -> ServiceResult:
        t0 = __import__("time").time()
        universe = self.get_full_universe(force_refresh=force_refresh)
        codes = [c["code"] if isinstance(c, dict) else c for c in universe[:max_stocks]]
        emit_log("INFO", "data_init", f"[全市场] 获{len(universe)}只标的, 取前{len(codes)}只")
        result = self._populate_batch(codes, "全市场刷新")
        self.compute_derived_fields()
        elapsed = round(__import__("time").time() - t0, 1)
        emit_log("INFO", "data_init", f"[全市场] 总耗时{elapsed}s")
        return result

    def populate_stock_list(self, codes: list | None = None) -> ServiceResult:
        if codes is None:
            codes = self.get_hot_stock_pool()
            emit_log("INFO", "data_init", f"[填充] 无指定代码, 使用热榜池{len(codes)}只")
        else:
            emit_log("INFO", "data_init", f"[填充] 指定{len(codes)}只")
        return self._populate_batch(codes, "数据填充")

    def _populate_batch(self, codes: list, label: str) -> ServiceResult:
        """核心批量填充 - DB→API→DB→return。前20只全失败+所有源down→终止"""
        t0 = __import__("time").time()
        from services.trading_calendar import TradingCalendar
        from shared.logging import emit_log

        # 规范化代码: dict→string
        raw = []
        for c in codes:
            if isinstance(c, dict):
                raw.append(str(c.get("stock_code", c.get("code", ""))))
            else:
                raw.append(str(c))
        codes = [c for c in raw if c]
        if not codes:
            emit_log("WARNING", "data_init", f"[{label}] 代码列表为空, 跳过填充")
            return ServiceResult.ok(data={"total": 0, "success": 0, "failed": 0})

        # 重置断路器
        try:
            from providers.sources import get_all_adapters

            for a in get_all_adapters():
                a.cb.reset()
                a.cb.failure_threshold = 20
        except Exception as e:
            emit_log("WARNING", "data_init", f"断路器重置失败: {e}")

        tc = TradingCalendar()
        effective_date = tc.effective_data_date()
        if tc.is_market_closed_today():
            emit_log("INFO", "data_init", f"[{label}] 盘后模式: 使用今日数据 {effective_date}")
        elif not tc.is_trading_day():
            emit_log(
                "INFO", "data_init", f"[{label}] 非交易日,使用最近交易日数据: {effective_date}"
            )

        # 记录数据源状态
        try:
            src_status = self.provider.get_source_status()
            available = [n for n, s in src_status.items() if s.get("available")]
            cb_states = {n: s.get("state", "?") for n, s in src_status.items()}
            emit_log("INFO", "data_init", f"[{label}] 数据源状态: {cb_states}, 可用: {available}")
        except Exception as e:
            emit_log("WARNING", "data_init", f"[{label}] 获取数据源状态失败: {e}")

        total = len(codes)
        emit_log("INFO", "data_init", f"[{label}] 开始填充 {total} 只 (数据日期: {effective_date})")
        success = 0
        failed = 0
        consecutive_fails = 0
        fail_reasons: dict[str, int] = {}

        batch_size = 5 if total > 50 else 10
        for i in range(0, total, batch_size):
            batch = codes[i : i + batch_size]
            if total > 50 and i % 50 == 0:
                elapsed = round(__import__("time").time() - t0, 1)
                emit_log(
                    "INFO",
                    "data_init",
                    f"[{label}] 进度: {i}/{total} (成功{success} 失败{failed} 耗时{elapsed}s)",
                )

            with ThreadPoolExecutor(max_workers=1) as executor:
                futures = {executor.submit(self._populate_one, code): code for code in batch}
                for future in as_completed(futures):
                    code = futures[future]
                    try:
                        ok = future.result()
                        if ok:
                            success += 1
                            consecutive_fails = 0
                        else:
                            failed += 1
                            consecutive_fails += 1
                            if consecutive_fails <= 3:
                                emit_log(
                                    "WARNING",
                                    "data_init",
                                    f"[{label}] {code}: 填充失败(连续{consecutive_fails}次)",
                                )
                    except Exception as e:
                        failed += 1
                        consecutive_fails += 1
                        reason = type(e).__name__
                        fail_reasons[reason] = fail_reasons.get(reason, 0) + 1

            # 前20只全失败 + 所有源不可用 → 快速终止
            if success == 0 and consecutive_fails >= min(20, total) and failed >= min(20, total):
                status = self.provider.get_source_status()
                available = [n for n, s in status.items() if s.get("available")]
                cb_states = {n: s.get("state", "?") for n, s in status.items()}
                emit_log(
                    "WARNING", "data_init", f"[{label}] 连续{failed}只失败, 断路器状态: {cb_states}"
                )
                if not available:
                    emit_log(
                        "ERROR",
                        "data_init",
                        f"[{label}] 所有数据源不可用 → 终止 (已尝试{failed}只, 0成功)",
                    )
                    return ServiceResult.ok(
                        data={
                            "total": total,
                            "success": 0,
                            "failed": failed,
                            "aborted": True,
                            "reason": "所有数据源不可用(周末/网络故障)",
                        }
                    )

            time.sleep(1)

        elapsed = round(__import__("time").time() - t0, 1)
        emit_log(
            "INFO",
            "data_init",
            f"[{label}] 完成: 成功{success} 失败{failed} / 共{total} 耗时{elapsed}s, 异常类型: {fail_reasons or '无'}",
        )
        return ServiceResult.ok(data={"total": total, "success": success, "failed": failed})

    def _check_completeness(self, code: str) -> tuple[bool, list[str]]:
        """检查股票数据的完整度, 返回 (是否完整, 缺失字段列表)"""
        missing = []
        try:
            from shared.models import StockInfo as _SI
            from shared.models import get_session as _GS

            _s = _GS()
            _info = _s.query(_SI).filter_by(stock_code=code).first()
            _s.close()
            if not _info:
                return False, ["DB无记录"]
            if not _info.latest_price or _info.latest_price <= 0:
                missing.append("价格")
            if not _info.pe_ratio or _info.pe_ratio <= 0:
                missing.append("PE")
            if not _info.roe or _info.roe <= 0:
                missing.append("ROE")
            if not _info.eps or _info.eps <= 0:
                missing.append("EPS")
            if not _info.dividend_yield or _info.dividend_yield <= 0:
                missing.append("股息率")
            if not _info.total_market_cap or _info.total_market_cap <= 0:
                missing.append("市值")
            if not _info.turnover_rate or _info.turnover_rate <= 0:
                missing.append("换手率")
            if not _info.industry:
                missing.append("行业")
        except Exception:
            return False, ["检查异常"]
        return len(missing) == 0, missing

    def _populate_one(self, code: str) -> bool:
        """完整填充单只股票: 每个源尝试3次→检查完整度→未完整切下一源→报告缺失"""
        import time as _t

        def _try_src(src_name: str, max_retry: int = 3) -> dict | None:
            """尝试源获取数据, 对不可恢复错误(限速/不支持/导入失败)不重试"""
            for a in range(1, max_retry + 1):
                try:
                    if src_name == "tencent":
                        d = self.provider._source_tencent("fetch_basic", code)
                    elif src_name == "sina":
                        d = self.provider._source_sina("fetch_basic", code)
                    elif src_name == "akshare":
                        d = self.provider._source_akshare("fetch_basic", code)
                    elif src_name == "tushare":
                        d = self.provider._source_tushare("fetch_basic", code)
                    elif src_name == "yfinance":
                        from providers.sources.yfinance_src import YFinanceAdapter

                        d = YFinanceAdapter().fetch_basic(code)
                    elif src_name == "zzshare":
                        from providers.sources.zzshare_src import ZZShareAdapter

                        d = ZZShareAdapter().fetch_basic(code)
                    else:
                        d = None
                    if d and d.get("stock_name"):
                        return d
                except Exception as e:
                    ename = type(e).__name__
                    emit_log("DEBUG", "data_init", f"[{code}] {src_name}[{a}/{max_retry}]: {ename}")
                    # 限速/不支持/导入失败 → 不重试,立即跳过
                    if ename in ("RateLimitError", "TransientError", "ImportError"):
                        emit_log("DEBUG", "data_init", f"[{code}] {src_name} {ename}→跳过剩余重试")
                        break
                _t.sleep(0.5)
            return None

        try:
            from shared.models import KlineCache, get_session

            _s = get_session()
            _kc = _s.query(KlineCache).filter_by(stock_code=code).count()
            _s.close()
            _c, _ = self._check_completeness(code)
            if _c and _kc >= 20:
                emit_log("DEBUG", "data_init", f"[{code}] 跳过: DB已完整(k线={_kc})")
                return True
        except Exception:
            pass

        self._ensure_stock_row(code)
        has_data = False

        for src in ["tencent", "sina", "akshare", "tushare", "yfinance", "zzshare"]:
            data = _try_src(src)
            if data:
                self._save_stock_info(code, data)
                has_data = True
                _ok, _miss = self._check_completeness(code)
                if _ok:
                    emit_log("INFO", "data_init", f"[{code}] ✅ {src}已补齐全部字段")
                    break
                emit_log("DEBUG", "data_init", f"[{code}] {src}后仍缺{_miss}→下一源")
                _t.sleep(0.5)

        for src in ["tencent", "sina", "akshare", "tushare", "zzshare"]:
            for a in range(1, 4):
                try:
                    df = None
                    if src == "tencent":
                        df = self.provider._source_tencent("fetch_kline", code, 90)
                    elif src == "sina":
                        df = self.provider._source_sina("fetch_kline", code, 90)
                    elif src == "akshare":
                        df = self.provider._source_akshare("fetch_kline", code, 90)
                    elif src == "tushare":
                        df = self.provider._source_tushare("fetch_kline", code, 90)
                    elif src == "zzshare":
                        from providers.sources.zzshare_src import ZZShareAdapter

                        df = ZZShareAdapter().fetch_kline(code, 90)
                    if df is not None and hasattr(df, "empty") and not df.empty:
                        _dr = (
                            f"{df['date'].iloc[0]}~{df['date'].iloc[-1]}"
                            if "date" in df.columns
                            else "?"
                        )
                        emit_log("DEBUG", "data_init", f"[{code}] K线({src}): {len(df)}条 ({_dr})")
                        self._save_klines(code, df)
                        self._compute_and_save_indicators(code, df)
                        has_data = True
                        break
                except Exception as e:
                    emit_log(
                        "DEBUG", "data_init", f"[{code}] K线({src})[{a}/3]: {type(e).__name__}"
                    )
                _t.sleep(0.5)

        _ok, _miss = self._check_completeness(code)
        if _ok:
            emit_log("INFO", "data_init", f"[{code}] ✅ 数据完整")
        else:
            emit_log("INFO", "data_init", f"[{code}] ⚠️ 仍缺: {_miss}")
        return has_data

    def _ensure_stock_row(self, code: str):
        """确保StockInfo表中存在该股票行"""
        try:
            from shared.models import StockInfo, get_session

            session = get_session()
            exists = session.query(StockInfo).filter_by(stock_code=code).first()
            if not exists:
                session.add(StockInfo(stock_code=code, stock_name=code))
                session.commit()
            session.close()
        except Exception as e:
            emit_log("WARNING", "data_init", f"{type(e).__name__}: {str(e)[:100]}")

    def _save_stock_info(self, code: str, data: dict):
        try:
            from shared.models import StockInfo, get_session

            session = get_session()
            info = session.query(StockInfo).filter_by(stock_code=code).first()
            if not info:
                info = StockInfo(stock_code=code)
                session.add(info)
                emit_log("DEBUG", "data_init", f"[{code}] 新建StockInfo行")

            new_name = str(data.get("stock_name", data.get("名称", data.get("name", code))) or code)
            if new_name:
                old_name = info.stock_name or ""
                old_has_cn = bool(re.search(r"[一-鿿]", old_name))
                new_has_cn = bool(re.search(r"[一-鿿]", new_name))
                if not old_has_cn or new_has_cn:
                    info.stock_name = new_name
                elif old_has_cn and not new_has_cn:
                    pass  # 保留已有中文名, 不覆盖
            info.industry = data.get("industry", data.get("行业", data.get("industry_name", "")))
            info.latest_price = float(data.get("latest_price", data.get("price", 0)) or 0)
            info.change_pct = float(data.get("change_pct", data.get("涨跌幅", 0)) or 0)
            info.pe_ratio = float(data.get("pe_ratio", data.get("peTTM", 0)) or 0)
            pb_raw = data.get("pb_ratio", data.get("pbMRQ", data.get("市净率", 0)))
            info.pb_ratio = float(pb_raw or 0)
            info.roe = float(data.get("roe", 0) or 0)
            info.gross_margin = float(data.get("gross_margin", data.get("毛利率", 0)) or 0)
            info.net_margin = float(data.get("net_margin", data.get("净利率", 0)) or 0)
            mcap = data.get("total_market_cap", data.get("总市值", 0))
            info.total_market_cap = float(mcap or 0)
            info.turnover_rate = float(data.get("turnover_rate", data.get("换手率", 0)) or 0)
            info.volume = float(data.get("volume", data.get("成交量", 0)) or 0)
            info.amount = float(data.get("amount", data.get("成交额", 0)) or 0)
            info.eps = float(data.get("eps", data.get("每股收益", 0)) or 0)
            info.bvps = float(data.get("bvps", data.get("每股净资产", 0)) or 0)
            info.debt_to_equity = float(data.get("debt_to_equity", 0) or 0)
            info.net_income = float(data.get("net_income", 0) or 0)
            info.shares_outstanding = float(data.get("shares_outstanding", 0) or 0)
            # Fallback: compute shares_outstanding from market cap if missing
            if info.shares_outstanding == 0 and info.total_market_cap > 0 and info.latest_price > 0:
                info.shares_outstanding = info.total_market_cap * 1e8 / info.latest_price
            info.current_ratio = float(data.get("current_ratio", 0) or 0)
            info.operating_margin = float(data.get("operating_margin", 0) or 0)
            info.free_cash_flow = float(data.get("free_cash_flow", 0) or 0)
            info.revenue_growth_3y = float(data.get("revenue_growth_3y", 0) or 0)
            info.cash_ratio = float(data.get("cash_ratio", 0) or 0)
            info.updated_at = datetime.now()
            session.commit()
            session.close()
        except Exception as e:
            emit_log("WARNING", "data_init", f"{type(e).__name__}: {str(e)[:100]}")

    def _save_klines(self, code: str, df):
        try:
            from shared.models import KlineCache, get_session

            session = get_session()
            for _, row in df.tail(90).iterrows():
                trade_date = str(row.get("date", row.name))[:10]
                if not trade_date or not trade_date[0].isdigit():
                    continue
                # Normalize date: accept YYYYMMDD or YYYY-MM-DD, reject garbage
                if len(trade_date) == 8 and trade_date.isdigit():
                    trade_date = f"{trade_date[:4]}-{trade_date[4:6]}-{trade_date[6:]}"
                if len(trade_date) != 10 or trade_date[4] != "-" or trade_date[7] != "-":
                    continue
                existing = (
                    session.query(KlineCache)
                    .filter_by(stock_code=code, trade_date=trade_date)
                    .first()
                )
                if existing:
                    continue
                session.add(
                    KlineCache(
                        stock_code=code,
                        trade_date=trade_date,
                        open=float(row.get("open", 0) or 0),
                        high=float(row.get("high", 0) or 0),
                        low=float(row.get("low", 0) or 0),
                        close=float(row.get("close", 0) or 0),
                        volume=float(row.get("volume", 0) or 0),
                        amount=float(row.get("amount", 0) or 0),
                        change_pct=float(row.get("change_pct", row.get("pct_chg", 0)) or 0),
                    )
                )
            session.commit()
            session.close()
        except Exception as e:
            emit_log("WARNING", "data_init", f"{type(e).__name__}: {str(e)[:100]}")

    def _compute_and_save_indicators(self, code: str, df):
        try:
            close = df["close"].astype(float)
            ma5 = float(close.rolling(5).mean().iloc[-1])
            ma10 = float(close.rolling(10).mean().iloc[-1])
            ma20 = float(close.rolling(20).mean().iloc[-1])
            ma60 = float(close.rolling(60).mean().iloc[-1]) if len(close) >= 60 else ma20
            delta = close.diff()
            gain = delta.where(delta > 0, 0.0).rolling(14).mean().iloc[-1]
            loss = (-delta.where(delta < 0, 0.0)).rolling(14).mean().iloc[-1]
            rsi = float(100 - 100 / (1 + gain / max(loss, 0.0001)))
            # MACD
            ema12 = close.ewm(span=12, adjust=False).mean()
            ema26 = close.ewm(span=26, adjust=False).mean()
            macd_dif = ema12 - ema26
            macd_signal = macd_dif.ewm(span=9, adjust=False).mean()
            macd_val = float((macd_dif - macd_signal).iloc[-1] * 2)
            # Change pct fields
            chg_5d = float(close.pct_change(5).iloc[-1] * 100) if len(close) >= 5 else 0
            chg_20d = float(close.pct_change(20).iloc[-1] * 100) if len(close) >= 20 else 0
            chg_60d = float(close.pct_change(60).iloc[-1] * 100) if len(close) >= 60 else 0
            # Volume ratio
            vol_series = df["volume"].astype(float) if "volume" in df.columns else close * 0
            vol_ratio_5d = (
                float(vol_series.iloc[-1] / vol_series.rolling(5).mean().iloc[-1])
                if vol_series.rolling(5).mean().iloc[-1] > 0
                else 1.0
            )
            returns = close.pct_change()
            vol = (
                float(returns.rolling(20).std().iloc[-1] * (252**0.5)) if len(returns) >= 20 else 0
            )
            cummax = close.cummax()
            max_dd = float(((close - cummax) / cummax).min())
            trend = "上升" if ma5 > ma10 > ma20 else ("下降" if ma5 < ma10 < ma20 else "震荡")
            alignment = (
                "多头"
                if ma5 > ma10 > ma20 > ma60
                else ("空头" if ma5 < ma10 < ma20 < ma60 else "交叉")
            )

            from shared.models import StockInfo, get_session

            session = get_session()
            info = session.query(StockInfo).filter_by(stock_code=code).first()
            if info:
                info.latest_price = float(close.iloc[-1])
                info.ma5 = ma5
                info.ma10 = ma10
                info.ma20 = ma20
                info.ma60 = ma60
                info.rsi_14 = rsi
                info.macd = macd_val
                info.change_pct_5d = chg_5d
                info.change_pct_20d = chg_20d
                info.change_pct_60d = chg_60d
                info.volume_ratio = vol_ratio_5d
                info.volatility_20d = vol
                info.max_drawdown_60d = max_dd
                info.trend = trend
                info.ma_alignment = alignment
                info.updated_at = datetime.now()
                session.commit()
            session.close()
        except Exception as e:
            emit_log("WARNING", "data_init", f"{type(e).__name__}: {str(e)[:100]}")

    def refresh_indicators_batch(self, max_stocks: int = 5000) -> dict:
        """Batch refresh technical indicators from existing kline data (no API calls)"""
        import pandas as pd

        from shared.models import KlineCache, StockInfo, get_session

        session = get_session()
        try:
            # Find stocks with kline data but missing MACD
            stocks = (
                session.query(StockInfo)
                .filter(
                    StockInfo.latest_price > 0,
                    StockInfo.macd == 0,
                )
                .limit(max_stocks)
                .all()
            )
            session.close()

            success = 0
            failed = 0
            for info in stocks:
                code = info.stock_code
                try:
                    session2 = get_session()
                    klines = (
                        session2.query(KlineCache)
                        .filter_by(stock_code=code)
                        .order_by(KlineCache.trade_date.asc())
                        .all()
                    )
                    session2.close()

                    if len(klines) < 20:
                        continue

                    df = pd.DataFrame(
                        [
                            {
                                "close": k.close,
                                "high": k.high,
                                "low": k.low,
                                "open": k.open,
                                "volume": k.volume,
                                "amount": k.amount,
                            }
                            for k in klines
                        ]
                    )

                    self._compute_and_save_indicators(code, df)
                    success += 1
                except Exception:
                    failed += 1

            return {"success": success, "failed": failed, "total": len(stocks)}
        except Exception as e:
            session.close()
            return {"success": 0, "failed": 0, "error": str(e)}

    def refresh_klines_batch(self, max_stocks: int = 5000, days: int = 90) -> dict:
        """Bulk refresh klines for stocks with stale/missing data using MarketDataProvider.
        Uses sequential fetching with delays to avoid circuit breaker trips."""
        import time as _time

        from shared.logging import emit_log
        from shared.models import KlineCache, StockInfo, get_session

        session = get_session()
        try:
            from datetime import timedelta

            cutoff_date = (datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d")

            stocks_with_recent = (
                session.query(KlineCache.stock_code)
                .filter(KlineCache.trade_date >= cutoff_date)
                .distinct()
                .subquery()
            )

            # Skip ETF/LOF/fund codes (start with 15, 16, 51, 58) - no individual klines
            from sqlalchemy import not_ as _not

            targets = (
                session.query(StockInfo.stock_code)
                .filter(
                    StockInfo.latest_price > 0,
                    ~StockInfo.stock_code.in_(session.query(stocks_with_recent.c.stock_code)),
                    _not(StockInfo.stock_code.startswith("15")),
                    _not(StockInfo.stock_code.startswith("16")),
                    _not(StockInfo.stock_code.startswith("51")),
                    _not(StockInfo.stock_code.startswith("58")),
                )
                .limit(max_stocks)
                .all()
            )
            session.close()

            target_codes = [r[0] for r in targets]
            total = len(target_codes)
            emit_log(
                "INFO",
                "data_init",
                f"[Kline Refresh] {total} stocks need kline update (cutoff={cutoff_date})",
            )

            if total == 0:
                return {
                    "success": 0,
                    "failed": 0,
                    "total": 0,
                    "message": "All stocks have recent klines",
                }

            success = 0
            failed = 0

            for i, code in enumerate(target_codes):
                try:
                    df = self.provider.get_stock_kline(code, days=days)
                    if df is not None and not df.empty:
                        self._save_klines(code, df)
                        self._compute_and_save_indicators(code, df)
                        success += 1
                    else:
                        failed += 1
                except Exception:
                    failed += 1

                if (i + 1) % 100 == 0:
                    emit_log(
                        "INFO",
                        "data_init",
                        f"[Kline Refresh] Progress: {i + 1}/{total} ({success} ok)",
                    )

                _time.sleep(0.3)

            emit_log(
                "INFO",
                "data_init",
                f"[Kline Refresh] Done: {success} ok, {failed} failed / {total}",
            )
            return {"success": success, "failed": failed, "total": total}
        except Exception as e:
            session.close()
            return {"success": 0, "failed": 0, "error": str(e)}

    def compute_derived_fields(self) -> dict:
        """Compute shares_outstanding from market_cap for all stocks missing it."""
        import sqlite3

        from shared.logging import emit_log
        from shared.models import get_session

        _s = get_session()
        db_path = str(_s.bind.url).replace("sqlite:///", "")
        _s.close()
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Compute shares_outstanding from total_market_cap (亿元) / latest_price (元)
        cursor.execute("""
            UPDATE stock_info
            SET shares_outstanding = total_market_cap * 100000000.0 / latest_price
            WHERE total_market_cap > 0 AND latest_price > 0
              AND (shares_outstanding = 0 OR shares_outstanding IS NULL)
        """)
        shares_updated = cursor.rowcount

        conn.commit()
        conn.close()
        emit_log(
            "INFO", "data_init", f"[Derived] shares_outstanding: {shares_updated} stocks updated"
        )
        return {"shares_outstanding_updated": shares_updated}

    def batch_enrich_from_tushare(self) -> dict:
        """批量填充 PE/PB/换手率/市值/股息率 — Tushare daily_basic 一次调用覆盖5514只

        只需一次API调用(~7s), 不触发限速 (daily_basic 200次/分钟)。
        """
        import sqlite3
        from datetime import datetime

        from shared.logging import emit_log

        emit_log("INFO", "data_init", "[TushareBatch] Starting daily_basic batch fill...")
        try:
            from providers.sources.tushare import TushareAdapter
        except ImportError:
            return {"status": "error", "error": "tushare not installed"}

        _d = datetime.now()
        if _d.weekday() == 5:
            _d = _d.replace(day=_d.day - 1)
        elif _d.weekday() == 6:
            _d = _d.replace(day=_d.day - 2)
        trade_date = _d.strftime("%Y%m%d")

        try:
            adapter = TushareAdapter()
            df = adapter.fetch_daily_basic(trade_date=trade_date)
            if df is None or df.empty:
                return {"status": "no_data", "error": f"daily_basic empty for {trade_date}"}
        except Exception as e:
            emit_log("ERROR", "data_init", f"[TushareBatch] daily_basic call failed: {e}")
            return {"status": "error", "error": str(e)[:80]}

        from shared.models import get_session

        _s = get_session()
        db_path = str(_s.bind.url).replace("sqlite:///", "")
        _s.close()

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        updated = {"pe": 0, "pb": 0, "turnover": 0, "mv": 0, "dividend": 0}
        total = len(df)

        for _, row in df.iterrows():
            ts_code = str(row.get("ts_code", ""))
            if not ts_code:
                continue
            code = ts_code.split(".", maxsplit=1)[0]

            pe = float(row.get("pe", 0) or 0)
            pb = float(row.get("pb", 0) or 0)
            turnover = float(row.get("turnover_rate", 0) or 0)
            total_mv = float(row.get("total_mv", 0) or 0) / 1e8
            dv_ratio = float(row.get("dv_ratio", 0) or 0) / 10

            sets = []
            vals = []
            if 0 < pe < 9999:
                sets.append("pe_ratio = ?")
                vals.append(pe)
            if pb > 0:
                sets.append("pb_ratio = ?")
                vals.append(pb)
            if turnover > 0:
                sets.append("turnover_rate = ?")
                vals.append(turnover)
            if total_mv > 0:
                sets.append("total_market_cap = ?")
                vals.append(total_mv)
            if dv_ratio > 0:
                sets.append("dividend_yield = ?")
                vals.append(dv_ratio)

            if sets:
                vals.append(code)
                # sets 的列名来自本函数内部硬编码映射，非用户输入
                cursor.execute(
                    f"UPDATE stock_info SET {', '.join(sets)} WHERE stock_code = ?",  # noqa: S608
                    vals,
                )
                if cursor.rowcount > 0:
                    if pe > 0:
                        updated["pe"] += 1
                    if pb > 0:
                        updated["pb"] += 1
                    if turnover > 0:
                        updated["turnover"] += 1
                    if total_mv > 0:
                        updated["mv"] += 1
                    if dv_ratio > 0:
                        updated["dividend"] += 1

        conn.commit()
        conn.close()
        emit_log(
            "INFO",
            "data_init",
            f"[TushareBatch] Done: {total} stocks, "
            f"PE={updated['pe']}, PB={updated['pb']}, "
            f"turnover={updated['turnover']}, MV={updated['mv']}, dividend={updated['dividend']}",
        )
        return {"status": "ok", "total": total, **updated}

    def enrich_financial_data(self, max_stocks: int = 200) -> dict:
        """Batch enrich stock_info with financial metrics from akshare.
        Uses concurrent fetching (3 workers) for speed."""
        import sqlite3
        from concurrent.futures import ThreadPoolExecutor, as_completed

        from shared.logging import emit_log

        emit_log("INFO", "data_init", f"[Enrich] Starting for up to {max_stocks} stocks...")
        try:
            import akshare as ak  # noqa: F401
        except ImportError:
            return {"success": 0, "failed": 0, "error": "akshare not installed"}

        from shared.models import get_session

        _s = get_session()
        db_path = str(_s.bind.url).replace("sqlite:///", "")
        _s.close()
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT stock_code FROM stock_info
            WHERE latest_price > 0 AND (
                eps = 0 OR eps IS NULL OR
                cash_ratio = 0 OR cash_ratio IS NULL OR
                debt_to_equity = 0 OR debt_to_equity IS NULL OR
                roe = 0 OR roe IS NULL OR
                gross_margin = 0 OR gross_margin IS NULL OR
                current_ratio = 0 OR current_ratio IS NULL OR
                operating_margin = 0 OR operating_margin IS NULL OR
                dividend_yield = 0 OR dividend_yield IS NULL
            )
            ORDER BY total_market_cap DESC LIMIT ?
        """,
            (max_stocks,),
        )
        targets = [r[0] for r in cursor.fetchall()]
        conn.close()

        def _fetch_one(code):
            try:
                import akshare as _ak

                df = _ak.stock_financial_analysis_indicator(symbol=code, start_year="2023")
                if df is None or df.empty:
                    return None
                row = df.iloc[0]

                def _v(key):
                    val = row.get(key, 0)
                    try:
                        return float(val) if val and str(val) not in ("nan", "None", "") else 0
                    except (ValueError, TypeError):
                        return 0

                return {
                    "code": code,
                    "eps": _v("\u644a\u8584\u6bcf\u80a1\u6536\u76ca(\u5143)"),
                    "bvps": _v("\u6bcf\u80a1\u51c0\u8d44\u4ea7_\u8c03\u6574\u524d(\u5143)"),
                    "roe": _v("\u51c0\u8d44\u4ea7\u6536\u76ca\u7387(%)"),
                    "gpm": _v("\u4e3b\u8425\u4e1a\u52a1\u5229\u6da6\u7387(%)"),
                    "opm": _v("\u8425\u4e1a\u5229\u6da6\u7387(%)"),
                    "npm": _v("\u9500\u552e\u51c0\u5229\u7387(%)"),
                    "debt_eq": _v(
                        "\u8d1f\u503a\u4e0e\u6240\u6709\u8005\u6743\u76ca\u6bd4\u7387(%)"
                    ),
                    "cr": _v("\u6d41\u52a8\u6bd4\u7387"),
                    "eg": _v("\u51c0\u5229\u6da6\u589e\u957f\u7387(%)"),
                    "rg": _v("\u4e3b\u8425\u4e1a\u52a1\u6536\u5165\u589e\u957f\u7387(%)"),
                    "cash": _v("\u73b0\u91d1\u6bd4\u7387(%)"),
                    "dpr": _v("\u80a1\u606f\u53d1\u653e\u7387(%)"),
                }
            except Exception as e:
                emit_log("ERROR", "data_initializer", f"Operation failed: {str(e)[:100]}")
                return None

        success = 0
        failed = 0
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = {executor.submit(_fetch_one, code): code for code in targets}
            for i, future in enumerate(as_completed(futures)):
                if i > 0 and i % 50 == 0:
                    emit_log("INFO", "data_init", f"[Enrich] {i}/{len(targets)} ({success} ok)")
                    conn.commit()
                data = future.result()
                if not data:
                    failed += 1
                    continue
                code = data["code"]
                updates = {}
                for key, db_key in [
                    ("eps", "eps"),
                    ("bvps", "bvps"),
                    ("roe", "roe"),
                    ("gpm", "gross_margin"),
                    ("opm", "operating_margin"),
                    ("npm", "net_margin"),
                    ("debt_eq", "debt_to_equity"),
                    ("cr", "current_ratio"),
                    ("eg", "earnings_growth_3y"),
                    ("rg", "revenue_growth_3y"),
                    ("cash", "cash_ratio"),
                    ("dpr", "dividend_yield"),
                ]:
                    if data.get(key, 0) != 0:
                        updates[db_key] = data[key]
                if updates:
                    set_c = ", ".join(f"{k} = ?" for k in updates)
                    # updates 的键来自本函数内部硬编码映射，非用户输入
                    cursor.execute(
                        f"UPDATE stock_info SET {set_c} WHERE stock_code = ?",  # noqa: S608
                        [*list(updates.values()), code],
                    )
                    if data.get("bvps", 0) > 0:
                        cursor.execute(
                            "UPDATE stock_info SET pb_ratio = latest_price / ? WHERE stock_code = ? AND latest_price > 0",
                            (data["bvps"], code),
                        )
                    success += 1
                else:
                    failed += 1

        conn.commit()
        conn.close()
        emit_log(
            "INFO",
            "data_init",
            f"[Enrich] Done: {success} ok, {failed} failed / {len(targets)}",
        )
        return {"success": success, "failed": failed, "total": len(targets)}

    def refresh_industry_data(self) -> dict:
        """Batch refresh industry data from EastMoney."""
        import sqlite3

        from providers.market_data import MarketDataProvider
        from shared.logging import emit_log

        emit_log("INFO", "data_init", "[Industry] Starting industry data refresh...")
        provider = MarketDataProvider()
        result = provider.fetch_industry_batch(max_pages=60)
        if not result or not result.get("success"):
            emit_log("WARNING", "data_init", "[Industry] fetch_industry_batch returned no data")
            return {"status": "no_data", "updated": 0}

        # result is a dict mapping stock_code -> industry_name
        industry_map = result.get("data", result)
        if not isinstance(industry_map, dict):
            # result might be the map directly
            industry_map = result

        try:
            from shared.models import get_session

            _s = get_session()
            db_path = str(_s.bind.url).replace("sqlite:///", "")
            _s.close()
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            updated = 0
            for code, industry in industry_map.items():
                if industry and isinstance(industry, str) and len(industry) > 0:
                    cursor.execute(
                        "UPDATE stock_info SET industry = ? WHERE stock_code = ? AND (industry IS NULL OR industry = '')",
                        (industry, code),
                    )
                    updated += cursor.rowcount
            conn.commit()
            conn.close()
            emit_log("INFO", "data_init", f"[Industry] Done: {updated} stocks updated")
            return {"status": "ok", "updated": updated, "total_fetched": len(industry_map)}
        except Exception as e:
            emit_log("ERROR", "data_init", f"[Industry] Failed: {e}")
            return {"status": "error", "error": str(e)}

    # ════════════════════════════════════════════════════════════
    #  ZZShare 数据 → MarketSnapshot 存储 (方案A)
    # ════════════════════════════════════════════════════════════

    def refresh_zzshare_snapshots(self) -> dict:
        """获取 zzshare 的热门/涨停/板块排行数据, 存入 MarketSnapshot

        使用 zzshare 模块级免费接口 (无需 token):
          - ths_hot_top()    同花顺热搜 Top N
          - uplimit_stocks() 涨停股票
          - plates_rank()    板块排行 (17=概念, 14=行业)
        """
        results = {}

        try:
            import zzshare
        except ImportError:
            return {"error": "zzshare not installed"}

        from datetime import timedelta

        _d = datetime.now()
        # 周末回退到周五, 否则用今天
        if _d.weekday() == 5:  # 周六
            _d -= timedelta(days=1)
        elif _d.weekday() == 6:  # 周日
            _d -= timedelta(days=2)
        date_str = _d.strftime("%Y%m%d")

        snapshots = [
            ("hot_stocks_ths", lambda: zzshare.ths_hot_top(date1=date_str, top_n=50)),
            ("uplimit_stocks", lambda: zzshare.uplimit_stocks(date1=date_str)),
            (
                "sector_rank_concept",
                lambda: zzshare.plates_rank(plate_type=17, date1=date_str, limit=20),
            ),
            (
                "sector_rank_industry",
                lambda: zzshare.plates_rank(plate_type=14, date1=date_str, limit=20),
            ),
        ]

        for snap_type, fetch_fn in snapshots:
            try:
                data = fetch_fn()
                if data and isinstance(data, list) and len(data) > 0:
                    self._save_market_snapshot(
                        snap_type, json.dumps(data, ensure_ascii=False, default=str)
                    )
                    results[snap_type] = f"ok ({len(data)} entries)"
                    emit_log(
                        "INFO", "zzshare", f"[{snap_type}] saved {len(data)} entries ({date_str})"
                    )
                else:
                    results[snap_type] = "no_data"
                    emit_log("DEBUG", "zzshare", f"[{snap_type}] no data for {date_str}")
            except Exception as e:
                results[snap_type] = f"error: {str(e)[:80]}"
                emit_log("WARNING", "zzshare", f"[{snap_type}] failed: {e}")

        return results

    def _save_market_snapshot(self, snap_type: str, payload: str):
        """保存快照到 MarketSnapshot 表"""
        try:
            from shared.models import MarketSnapshot, get_session

            session = get_session()
            row = session.query(MarketSnapshot).filter_by(snapshot_type=snap_type).first()
            if row:
                row.data_json = payload
                row.trade_date = datetime.now().strftime("%Y-%m-%d")
                row.updated_at = datetime.now()
            else:
                session.add(
                    MarketSnapshot(
                        snapshot_type=snap_type,
                        trade_date=datetime.now().strftime("%Y-%m-%d"),
                        data_json=payload,
                    )
                )
            session.commit()
            session.close()
        except Exception as e:
            emit_log("WARNING", "data_init", f"_save_market_snapshot({snap_type}): {e}")

    # ════════════════════════════════════════════════════════════
    #  批量修正英文股票名 → 中文名
    # ════════════════════════════════════════════════════════════

    def fix_english_names(self, max_stocks: int = 500) -> dict:
        """批量修正英文股票名 — 通过 Tencent/Sina/AKShare 获取中文名覆盖"""
        import time as _t

        from providers.market_data import MarketDataProvider
        from shared.models import StockInfo, get_session

        provider = MarketDataProvider()
        session = get_session()

        # 找到英文名股票 (在 Python 侧过滤, 避免 SQLite GLOB 兼容问题)
        all_stocks = session.query(StockInfo).all()
        session.close()

        all_eng = [
            s for s in all_stocks if s.stock_name and re.search(r"[a-zA-Z]{3,}", s.stock_name)
        ]

        total = len(all_eng)
        fixed = 0
        skipped = 0
        errors = 0

        for i, info in enumerate(all_eng[:max_stocks]):
            code = info.stock_code
            old_name = info.stock_name

            # 跳过已有中文名的
            if re.search(r"[一-鿟]", old_name):
                skipped += 1
                continue

            # 按优先级尝试各源获取中文名
            found_cn = False
            for src in ["tencent", "sina", "akshare"]:
                try:
                    d = None
                    if src == "tencent":
                        d = provider._source_tencent("fetch_basic", code)
                    elif src == "sina":
                        d = provider._source_sina("fetch_basic", code)
                    elif src == "akshare":
                        d = provider._source_akshare("fetch_basic", code)

                    if d:
                        cn_name = str(d.get("stock_name", d.get("名称", d.get("name", ""))) or "")
                        if cn_name and re.search(r"[一-鿟]", cn_name):
                            self._save_stock_info(code, {"stock_name": cn_name})
                            fixed += 1
                            found_cn = True
                            if fixed <= 5 or fixed % 50 == 0:
                                emit_log(
                                    "INFO",
                                    "fix_names",
                                    f"[{code}] {old_name[:20]} -> {cn_name[:10]}",
                                )
                            break
                except Exception as e:
                    emit_log("DEBUG", "fix_names", f"名称修复失败({code}): {e}")
                _t.sleep(0.1)

            if not found_cn:
                errors += 1
                if errors <= 5:
                    emit_log("DEBUG", "fix_names", f"[{code}] no Chinese name found")

            if (i + 1) % 100 == 0:
                emit_log("INFO", "fix_names", f"Progress: {i + 1}/{min(total, max_stocks)}")

        emit_log(
            "INFO",
            "fix_names",
            f"Done: fixed={fixed}, skipped(had cn)={skipped}, not_found={errors}, total_checked={min(total, max_stocks)}",
        )
        return {
            "fixed": fixed,
            "skipped": skipped,
            "not_found": errors,
            "total": min(total, max_stocks),
        }

    def _default_stock_pool(self) -> list:
        return self.get_hot_stock_pool()
