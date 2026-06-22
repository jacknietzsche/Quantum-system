"""数据库优先数据总线 - SQLite缓存层 + API降级 + 自动回填"""

import contextlib
import json
import logging
import threading
from datetime import datetime
from typing import Any

from services.base import BaseService, ServiceResult
from shared.logging import emit_log

logger = logging.getLogger(__name__)

# ── TTL配置 ──
CACHE_TTL = {
    "indices": 300,  # 指数: 5分钟(盘中高频更新)
    "north_flow": 300,  # 北向资金: 5分钟
    "sectors": 600,  # 板块排行: 10分钟
    "kline_daily": 86400,  # 日K线: 24小时(收盘后更新)
    "stock_basic": 86400,  # 基本面: 24小时
    "stock_quote": 300,  # 实时行情: 5分钟
}


class DatabaseBackedDataBus(BaseService):
    """数据库优先数据总线 - 读缓存→API降级→自动回填"""

    def __init__(self, db_path: str = "data/investment.db"):
        super().__init__()
        self.db_path = db_path
        self._provider: Any = None  # 延迟加载 MarketDataProvider
        self._lock = threading.Lock()
        self._stats = {"db_hits": 0, "api_calls": 0, "api_failures": 0, "stale_served": 0}

    @property
    def provider(self):
        """延迟加载 MarketDataProvider,避免循环导入和缺失依赖"""
        if self._provider is None:
            from providers.market_data import MarketDataProvider

            self._provider = MarketDataProvider()
        return self._provider

    @contextlib.contextmanager
    def _db_session(self):
        from shared.models import get_session

        session = get_session(self.db_path)
        try:
            yield session
        finally:
            session.close()

    # ════════════════════════════════════════════
    #  公开接口(与 super_workflow 兼容)
    # ════════════════════════════════════════════

    def get_market_indices(self) -> dict:
        """获取市场指数 → DB优先"""
        return self._get_or_fetch(
            snapshot_type="indices",
            fetch_fn=self.provider.get_indices,
            ttl=CACHE_TTL["indices"],
        )

    def get_market_breadth(self) -> dict:
        """获取市场广度 → 从 indices 的 breadth 提取"""
        result = self.get_market_indices()
        return result.get("breadth", {})

    def get_north_flow(self) -> dict:
        """获取北向资金 → DB优先"""
        return self._get_or_fetch(
            snapshot_type="north_flow",
            fetch_fn=self.provider.get_north_flow,
            ttl=CACHE_TTL["north_flow"],
        )

    def get_sector_ranking(self, top_n: int = 10) -> list[dict]:
        """获取板块排行 → DB优先"""
        result = self._get_or_fetch(
            snapshot_type="sectors",
            fetch_fn=self._fetch_sectors_raw,
            ttl=CACHE_TTL["sectors"],
        )
        if isinstance(result, list):
            return result[:top_n]
        return []

    def get_stock_quote(self, stock_code: str) -> dict:
        """获取个股行情 → StockInfo表优先"""
        return self._get_stock_quote_cached(stock_code)

    def get_stocks_quote(self, stock_codes: list[str]) -> list[dict]:
        """批量获取个股行情 — 单次DB查询 + 并行API回填"""
        if not stock_codes:
            return []

        quotes: dict[str, dict] = {}
        missing: list[str] = []

        # 1. 批量读缓存
        try:
            from shared.models import StockInfo

            with self._db_session() as session:
                infos = session.query(StockInfo).filter(StockInfo.stock_code.in_(stock_codes)).all()
                cached_codes = {info.stock_code for info in infos}
                for info in infos:
                    if info.latest_price and info.latest_price > 0:
                        age = (datetime.now() - (info.updated_at or datetime.min)).total_seconds()
                        if age < CACHE_TTL["stock_quote"]:
                            quotes[info.stock_code] = {
                                "stock_code": info.stock_code,
                                "stock_name": info.stock_name,
                                "price": info.latest_price,
                                "change_pct": info.change_pct or 0,
                                "turnover_rate": info.turnover_rate or 0,
                                "volume": info.volume or 0,
                                "amount": info.amount or 0,
                                "pe_ratio": info.pe_ratio or 0,
                                "pb_ratio": info.pb_ratio or 0,
                                "market_cap": info.total_market_cap or 0,
                            }
                            continue
                    missing.append(info.stock_code)

            for code in stock_codes:
                if code not in cached_codes:
                    missing.append(code)
        except Exception:
            missing = list(stock_codes)

        # 2. 并行API回填缺失数据
        if missing:
            from concurrent.futures import ThreadPoolExecutor, as_completed

            def fetch_one(code: str) -> tuple[str, dict]:
                try:
                    return code, self._fetch_stock_quote_api(code)
                except Exception as e:
                    self._stats["api_failures"] += 1
                    emit_log("WARNING", "data_bus", f"fetch quote {code}: {str(e)[:80]}")
                    return code, {"stock_code": code, "price": 0}

            with ThreadPoolExecutor(max_workers=3) as executor:
                futures = [executor.submit(fetch_one, c) for c in set(missing)]
                for future in as_completed(futures):
                    code, quote = future.result()
                    quotes[code] = quote

        return [quotes.get(c, {"stock_code": c, "price": 0}) for c in stock_codes]

    def get_stock_kline(self, stock_code: str, days: int = 60) -> Any | None:
        """获取个股K线 → KlineCache表优先"""
        return self._get_kline_cached(stock_code, days)

    def get_stock_basic(self, stock_code: str) -> dict:
        """获取个股基本面 → StockInfo表优先"""
        return self._get_stock_basic_cached(stock_code)

    # ════════════════════════════════════════════
    #  缓存读取核心
    # ════════════════════════════════════════════

    def _get_or_fetch(self, snapshot_type: str, fetch_fn, ttl: int) -> Any:
        """通用 DB优先+API降级 模式"""
        # Step 1: 读取数据库缓存
        cached = self._read_snapshot(snapshot_type, ttl)
        if cached is not None:
            self._stats["db_hits"] += 1
            return cached

        # Step 2: API获取
        try:
            self._stats["api_calls"] += 1
            fresh = fetch_fn()
            if fresh:
                self._write_snapshot(snapshot_type, fresh)
            return fresh or cached  # API失败但有旧缓存 → 用旧数据
        except Exception as e:
            self._stats["api_failures"] += 1
            emit_log("ERROR", "data_bus", f"[{snapshot_type}] API failed: {str(e)[:100]}")
            # Step 3: API失败 → 返回过期缓存
            stale = self._read_snapshot(snapshot_type, ttl=None)  # 不过滤TTL
            if stale is not None:
                self._stats["stale_served"] += 1
                # 每5次告警一次,避免日志淹没
                if self._stats["stale_served"] % 5 == 1:
                    logger.warning(
                        "serving stale cache for %s (stale count: %d, api failures: %d)",
                        snapshot_type,
                        self._stats["stale_served"],
                        self._stats["api_failures"],
                    )
            return stale

    def _read_snapshot(self, snapshot_type: str, ttl: int | None = None) -> Any | None:
        """Read MarketSnapshot cache with retry on locked"""
        import time as _time

        for attempt in range(3):
            try:
                from shared.models import MarketSnapshot

                with self._db_session() as session:
                    row = (
                        session.query(MarketSnapshot).filter_by(snapshot_type=snapshot_type).first()
                    )

                if row and row.data_json:
                    if ttl is not None:
                        age = (datetime.now() - row.updated_at).total_seconds()
                        if age > ttl:
                            return None
                    return json.loads(row.data_json)
                return None
            except Exception as e:
                if "locked" in str(e).lower() and attempt < 2:
                    _time.sleep(0.2 * (attempt + 1))
                    continue
                emit_log(
                    "WARNING",
                    "data_bus",
                    f"Read {snapshot_type}: {type(e).__name__}: {str(e)[:80]}",
                )
        return None

    def _write_snapshot(self, snapshot_type: str, data: Any):
        """Write MarketSnapshot with 5x retry + auto rollback"""
        import time as _time

        data_json = json.dumps(data, ensure_ascii=False, default=str)
        now = datetime.now()
        for attempt in range(5):
            session = None
            try:
                from shared.models import MarketSnapshot, get_session

                with self._lock:
                    session = get_session(self.db_path)
                    try:
                        row = (
                            session.query(MarketSnapshot)
                            .filter_by(snapshot_type=snapshot_type)
                            .first()
                        )
                        if row:
                            row.data_json = data_json
                            row.updated_at = now
                        else:
                            session.add(
                                MarketSnapshot(
                                    snapshot_type=snapshot_type,
                                    data_json=data_json,
                                    updated_at=now,
                                )
                            )
                        session.commit()
                    except Exception:
                        session.rollback()
                        raise
                    finally:
                        session.close()
                return  # success
            except Exception as e:
                err_str = str(e).lower()
                if ("locked" in err_str or "busy" in err_str) and attempt < 4:
                    _time.sleep(0.3 * (attempt + 1))
                    continue
                if attempt >= 4:
                    logger.warning(
                        "DataBus write gave up after 5 attempts [%s]: %s", snapshot_type, e
                    )
                else:
                    logger.warning("DataBus write error [%s]: %s", snapshot_type, e)
                emit_log(
                    "WARNING",
                    "data_bus",
                    f"Write {snapshot_type} failed(attempt={attempt}): {str(e)[:80]}",
                )

    def _get_stock_quote_cached(self, stock_code: str) -> dict:
        """从 StockInfo 表读取个股行情"""
        try:
            from shared.models import StockInfo

            with self._db_session() as session:
                info = session.query(StockInfo).filter_by(stock_code=stock_code).first()

            if info and info.latest_price and info.latest_price > 0:
                age = (datetime.now() - (info.updated_at or datetime.min)).total_seconds()
                if age < CACHE_TTL["stock_quote"]:
                    self._stats["db_hits"] += 1
                    return {
                        "stock_code": stock_code,
                        "stock_name": info.stock_name,
                        "price": info.latest_price,
                        "change_pct": info.change_pct or 0,
                        "turnover_rate": info.turnover_rate or 0,
                        "volume": info.volume or 0,
                        "amount": info.amount or 0,
                        "pe_ratio": info.pe_ratio or 0,
                        "pb_ratio": info.pb_ratio or 0,
                        "market_cap": info.total_market_cap or 0,
                    }
        except Exception:
            pass

        # 缓存未命中 → API
        return self._fetch_stock_quote_api(stock_code)

    def _fetch_stock_quote_api(self, stock_code: str) -> dict:
        """API获取个股行情 → 回填 StockInfo"""
        try:
            self._stats["api_calls"] += 1
            basic = self.provider.get_stock_basic(stock_code)
            if basic:
                self._upsert_stock_info(stock_code, basic)
                return {
                    "stock_code": stock_code,
                    "stock_name": basic.get("stock_name", basic.get("name", "")),
                    "price": basic.get("latest_price", basic.get("price", 0)),
                    "change_pct": basic.get("change_pct", 0),
                    "pe_ratio": basic.get("pe_ratio", 0),
                    "pb_ratio": basic.get("pb_ratio", 0),
                    "market_cap": basic.get("total_market_cap", 0),
                }
        except Exception:
            self._stats["api_failures"] += 1
        return {"stock_code": stock_code, "price": 0}

    def _get_kline_cached(self, stock_code: str, days: int = 60) -> Any | None:
        """从 KlineCache 表读取K线"""
        try:
            from shared.models import KlineCache

            with self._db_session() as session:
                rows = (
                    session.query(KlineCache)
                    .filter_by(stock_code=stock_code)
                    .order_by(KlineCache.trade_date.desc())
                    .limit(days)
                    .all()
                )

            if rows and len(rows) >= min(20, days):
                newest = rows[0].trade_date
                age_hours: float = 0.0
                with contextlib.suppress(Exception):
                    age_hours = (
                        datetime.now() - datetime.strptime(newest, "%Y-%m-%d")
                    ).total_seconds() / 3600

                if age_hours < 24:
                    # 24小时内有效
                    self._stats["db_hits"] += 1
                    return [
                        {
                            "date": r.trade_date,
                            "open": r.open,
                            "high": r.high,
                            "low": r.low,
                            "close": r.close,
                            "volume": r.volume,
                            "amount": r.amount,
                            "change_pct": r.change_pct,
                        }
                        for r in reversed(rows)
                    ]
        except Exception:
            pass

        # 缓存未命中 → API
        return self._fetch_kline_api(stock_code, days)

    def _fetch_kline_api(self, stock_code: str, days: int = 60) -> Any | None:
        """API获取K线 → 回填 KlineCache"""
        try:
            self._stats["api_calls"] += 1
            df = self.provider.get_stock_kline(stock_code, days)
            if df is not None and not df.empty:
                self._upsert_klines(stock_code, df)
                return df
        except Exception:
            self._stats["api_failures"] += 1
        return None

    def _get_stock_basic_cached(self, stock_code: str) -> dict:
        """从 StockInfo 表读取基本面"""
        try:
            from shared.models import StockInfo

            with self._db_session() as session:
                info = session.query(StockInfo).filter_by(stock_code=stock_code).first()

            if info and info.updated_at:
                age = (datetime.now() - info.updated_at).total_seconds()
                if age < CACHE_TTL["stock_basic"]:
                    self._stats["db_hits"] += 1
                    return {
                        "stock_code": stock_code,
                        "stock_name": info.stock_name,
                        "industry": info.industry,
                        "pe_ratio": info.pe_ratio,
                        "pb_ratio": info.pb_ratio,
                        "roe": info.roe,
                        "gross_margin": info.gross_margin,
                        "net_margin": info.net_margin,
                        "total_market_cap": info.total_market_cap,
                        "ma5": info.ma5,
                        "ma10": info.ma10,
                        "ma20": info.ma20,
                        "ma60": info.ma60,
                        "rsi": info.rsi_14,
                        "macd": info.macd,
                        "trend": info.trend,
                        "volatility": info.volatility_20d,
                        "max_dd": info.max_drawdown_60d,
                    }
        except Exception:
            pass

        return self._fetch_stock_basic_api(stock_code)

    def _fetch_stock_basic_api(self, stock_code: str) -> dict:
        """API获取基本面 → 回填 StockInfo"""
        try:
            self._stats["api_calls"] += 1
            basic = self.provider.get_stock_basic(stock_code)
            if basic:
                self._upsert_stock_info(stock_code, basic)
                return basic
        except Exception:
            self._stats["api_failures"] += 1
        return {}

    # ════════════════════════════════════════════
    #  数据回填
    # ════════════════════════════════════════════

    def _upsert_stock_info(self, stock_code: str, data: dict):
        """Update StockInfo table with retry"""
        import time as _time

        for attempt in range(3):
            try:
                from shared.models import StockInfo, get_session

                session = None
                try:
                    session = get_session(self.db_path)
                    info = session.query(StockInfo).filter_by(stock_code=stock_code).first()
                    if not info:
                        stock_name = data.get("stock_name", data.get("name", ""))
                        info = StockInfo(stock_code=stock_code, stock_name=stock_name)
                        session.add(info)

                    for field in [
                        "latest_price",
                        "change_pct",
                        "pe_ratio",
                        "pb_ratio",
                        "roe",
                        "gross_margin",
                        "net_margin",
                        "total_market_cap",
                        "industry",
                    ]:
                        if data.get(field) is not None:
                            setattr(info, field, data[field])

                    info.updated_at = datetime.now()
                    session.commit()
                except Exception:
                    if session:
                        session.rollback()
                    raise
                finally:
                    if session:
                        session.close()
                return
            except Exception as e:
                if "locked" in str(e).lower() and attempt < 2:
                    _time.sleep(0.3 * (attempt + 1))
                    continue
                logger.warning("DataBus upsert_stock_info error [%s]: %s", stock_code, e)
                emit_log("WARNING", "data_bus", f"upsert_stock_info {stock_code}: {str(e)[:80]}")

    def _upsert_klines(self, stock_code: str, df) -> None:
        """Batch update KlineCache with retry — O(N) query 优化为 O(1) 批量查重"""
        import time as _time

        if df is None or df.empty:
            return

        for attempt in range(3):
            session = None
            try:
                from shared.models import KlineCache, get_session

                session = get_session(self.db_path)
                # 一次性查询该股票所有已存在的 trade_date,避免 N+1 查询
                existing_dates = {
                    row[0]
                    for row in session.query(KlineCache.trade_date)
                    .filter(KlineCache.stock_code == stock_code)
                    .all()
                }

                new_rows = []
                for _, row in df.iterrows():
                    trade_date = str(row.get("date", row.name))[:10]
                    if not trade_date or trade_date in existing_dates:
                        continue
                    existing_dates.add(trade_date)
                    new_rows.append(
                        KlineCache(
                            stock_code=stock_code,
                            trade_date=trade_date,
                            open=float(row.get("open", 0) or 0),
                            high=float(row.get("high", 0) or 0),
                            low=float(row.get("low", 0) or 0),
                            close=float(row.get("close", 0) or 0),
                            volume=float(row.get("volume", 0) or 0),
                            amount=float(row.get("amount", 0) or 0),
                            change_pct=float(row.get("change_pct", 0) or 0),
                        )
                    )

                if new_rows:
                    session.add_all(new_rows)
                    session.commit()
                return
            except Exception as e:
                if session:
                    with contextlib.suppress(Exception):
                        session.rollback()
                if "locked" in str(e).lower() and attempt < 2:
                    _time.sleep(0.3 * (attempt + 1))
                    continue
                logger.warning("DataBus upsert_klines error [%s]: %s", stock_code, e)
                emit_log("WARNING", "data_bus", f"upsert_klines {stock_code}: {str(e)[:80]}")
            finally:
                if session:
                    with contextlib.suppress(Exception):
                        session.close()

    def _fetch_sectors_raw(self) -> list[dict]:
        """获取板块排行原始数据"""
        try:
            sectors = self.provider.get_hot_stocks(sort="change_pct", limit=50)
            return sectors if sectors else []
        except Exception:
            return []

    # ════════════════════════════════════════════
    #  状态查询
    # ════════════════════════════════════════════

    def get_stats(self) -> ServiceResult:
        """获取缓存命中统计"""
        total = self._stats["db_hits"] + self._stats["api_calls"]
        hit_rate = self._stats["db_hits"] / max(total, 1)
        return ServiceResult.ok(
            data={
                **self._stats,
                "total_requests": total,
                "db_hit_rate": round(hit_rate, 3),
                "cache_tables": ["MarketSnapshot", "StockInfo", "KlineCache"],
                "cache_ttls": CACHE_TTL,
            }
        )

    def preload_stock_data(self, stock_codes: list[str]):
        """预加载股票数据到缓存(批量API调用→回填DB)"""
        from concurrent.futures import ThreadPoolExecutor, as_completed

        def load_one(code):
            self.get_stock_quote(code)
            self.get_stock_kline(code, days=60)
            self.get_stock_basic(code)

        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(load_one, c) for c in stock_codes]
            for _ in as_completed(futures):
                pass

        return self.get_stats()

    def invalidate_cache(self, cache_type: str | None = None):
        """清除缓存"""
        try:
            from shared.models import MarketSnapshot

            with self._db_session() as session:
                if cache_type:
                    session.query(MarketSnapshot).filter_by(snapshot_type=cache_type).delete()
                else:
                    session.query(MarketSnapshot).delete()
                session.commit()
        except Exception as e:
            logger.warning("DataBus error: %s", e)
