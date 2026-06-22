import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

from services.base import BaseService, ServiceResult
from shared.logging import emit_log

logger = logging.getLogger(__name__)


class StockPopulator(BaseService):
    def __init__(self, provider):
        super().__init__()
        self._provider = provider

    @property
    def provider(self):
        return self._provider

    @staticmethod
    def _normalize_codes(codes: list) -> list[str]:
        """Ensure codes are strings, extracting from dicts if needed."""
        result = []
        for c in codes:
            if isinstance(c, dict):
                result.append(str(c.get("stock_code", c.get("code", ""))))
            else:
                result.append(str(c))
        return [c for c in result if c]

    def populate_stock_list(self, codes: list | None = None, get_pool_fn=None) -> ServiceResult:
        if codes is None:
            codes = get_pool_fn() if get_pool_fn else []
        codes = self._normalize_codes(codes)
        return self._populate_batch(codes, "数据填充")

    def _populate_batch(self, codes: list, label: str) -> ServiceResult:
        """核心批量填充 - DB→API→DB→return。前20只全失败+所有源down→终止"""
        # Soft-reset circuit breakers: raise failure threshold to avoid false trips
        # (some stocks e.g. BSE 872xxx have no data in primary APIs, which is not an API failure)
        try:
            from providers.sources import get_all_adapters

            for a in get_all_adapters():
                a.cb.reset()
                a.cb.failure_threshold = 20
        except Exception:
            pass

        from services.trading_calendar import TradingCalendar
        from shared.logging import emit_log

        tc = TradingCalendar()
        effective_date = tc.effective_data_date()
        if tc.is_market_closed_today():
            emit_log("INFO", "data_init", f"盘后模式: 使用今日数据 {effective_date}")
        elif not tc.is_trading_day():
            emit_log("INFO", "data_init", f"非交易日,使用最近交易日数据: {effective_date}")

        total = len(codes)
        emit_log("INFO", "data_init", f"[{label}] 开始填充 {total} 只 (数据日期: {effective_date})")
        success = 0
        failed = 0
        consecutive_fails = 0

        batch_size = 5 if total > 50 else 10
        for i in range(0, total, batch_size):
            batch = codes[i : i + batch_size]
            if total > 50 and i % 50 == 0:
                emit_log("INFO", "data_init", f"[{label}] 进度: {i}/{total}")

            with ThreadPoolExecutor(max_workers=1) as executor:
                futures = {executor.submit(self._populate_one, code): code for code in batch}
                for future in as_completed(futures):
                    try:
                        if future.result():
                            success += 1
                            consecutive_fails = 0
                        else:
                            failed += 1
                            consecutive_fails += 1
                    except Exception:
                        failed += 1
                        consecutive_fails += 1

            # 前20只全失败 + 所有源不可用 → 快速终止（阈值提高防止多线程误判）
            if success == 0 and consecutive_fails >= min(20, total) and failed >= min(20, total):
                status = self.provider.get_source_status()
                available = [n for n, s in status.items() if s.get("available")]
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

        emit_log("INFO", "data_init", f"[{label}] 完成: 成功{success} 失败{failed} / 共{total}")
        return ServiceResult.ok(data={"total": total, "success": success, "failed": failed})

    def _populate_one(self, code: str) -> bool:
        """DB优先: 检查StockInfo+KlineCache是否已有近期数据,有则跳过API"""
        try:
            from shared.models import KlineCache, StockInfo, get_session

            session = get_session()
            try:
                info = session.query(StockInfo).filter_by(stock_code=code).first()
                kline_count = session.query(KlineCache).filter_by(stock_code=code).count()
            finally:
                session.close()

            age_hours = 999
            if info and info.updated_at:
                age_hours = (datetime.now() - info.updated_at).total_seconds() / 3600

            if (
                info
                and info.latest_price
                and info.latest_price > 0
                and age_hours < 24
                and kline_count >= 20
            ):
                return True
        except Exception as e:
            emit_log("WARNING", "data_init", f"{type(e).__name__}: {str(e)[:100]}")

        # 确保StockInfo行存在 (即使basic API失败)
        self._ensure_stock_row(code)

        has_data = False
        try:
            basic = self.provider.get_stock_basic(code)
            if basic:
                self._save_stock_info(code, basic)
                if basic.get("stock_name"):
                    has_data = True
        except Exception as e:
            emit_log("WARNING", "data_init", f"{type(e).__name__}: {str(e)[:100]}")
        try:
            df = self.provider.get_stock_kline(code, days=90)
            if df is not None and not df.empty:
                self._save_klines(code, df)
                self._update_indicators(code, df)
                has_data = True
        except Exception as e:
            emit_log("WARNING", "data_init", f"{type(e).__name__}: {str(e)[:100]}")
        return has_data

    def _ensure_stock_row(self, code: str):
        """确保StockInfo表中存在该股票行"""
        try:
            from shared.models import StockInfo, get_session

            session = get_session()
            try:
                exists = session.query(StockInfo).filter_by(stock_code=code).first()
                if not exists:
                    session.add(StockInfo(stock_code=code, stock_name=code))
                    session.commit()
            finally:
                session.close()
        except Exception as e:
            emit_log("WARNING", "data_init", f"{type(e).__name__}: {str(e)[:100]}")

    def _save_stock_info(self, code: str, data: dict):
        try:
            from shared.models import StockInfo, get_session

            session = get_session()
            try:
                info = session.query(StockInfo).filter_by(stock_code=code).first()
                if not info:
                    info = StockInfo(stock_code=code)
                    session.add(info)
                info.stock_name = data.get("stock_name", data.get("名称", data.get("name", code)))
                info.industry = data.get(
                    "industry", data.get("行业", data.get("industry_name", ""))
                )
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
                if info.total_market_cap > 1e9:
                    info.total_market_cap = round(info.total_market_cap / 100_000_000.0, 2)
                info.turnover_rate = float(data.get("turnover_rate", data.get("换手率", 0)) or 0)
                info.volume = float(data.get("volume", data.get("成交量", 0)) or 0)
                info.amount = float(data.get("amount", data.get("成交额", 0)) or 0)
                info.eps = float(data.get("eps", data.get("每股收益", 0)) or 0)
                info.bvps = float(data.get("bvps", data.get("每股净资产", 0)) or 0)
                info.debt_to_equity = float(data.get("debt_to_equity", 0) or 0)
                info.net_income = float(data.get("net_income", 0) or 0)
                info.shares_outstanding = float(data.get("shares_outstanding", 0) or 0)
                if (
                    info.shares_outstanding == 0
                    and info.total_market_cap > 0
                    and info.latest_price > 0
                ):
                    info.shares_outstanding = info.total_market_cap * 1e8 / info.latest_price
                info.current_ratio = float(data.get("current_ratio", 0) or 0)
                info.operating_margin = float(data.get("operating_margin", 0) or 0)
                info.free_cash_flow = float(data.get("free_cash_flow", 0) or 0)
                info.revenue_growth_3y = float(data.get("revenue_growth_3y", 0) or 0)
                info.cash_ratio = float(data.get("cash_ratio", 0) or 0)
                info.updated_at = datetime.now()
                session.commit()
            finally:
                session.close()
        except Exception as e:
            emit_log("WARNING", "data_init", f"{type(e).__name__}: {str(e)[:100]}")

    def _save_klines(self, code: str, df):
        from shared.models import KlineCache, get_session

        session = get_session()
        try:
            for _, row in df.tail(90).iterrows():
                trade_date = str(row.get("date", row.name))[:10]
                if not trade_date or not trade_date[0].isdigit():
                    continue
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
        except Exception as e:
            session.rollback()
            emit_log("WARNING", "data_init", f"{type(e).__name__}: {str(e)[:100]}")
        finally:
            session.close()

    def _update_indicators(self, code: str, df):
        """Update latest_price from kline close data."""
        try:
            close = df["close"].astype(float)
            latest_price = float(close.iloc[-1])
            from shared.models import StockInfo, get_session

            session = get_session()
            try:
                info = session.query(StockInfo).filter_by(stock_code=code).first()
                if info:
                    info.latest_price = latest_price
                    info.updated_at = datetime.now()
                    session.commit()
            finally:
                session.close()
        except Exception as e:
            emit_log("WARNING", "data_init", f"{type(e).__name__}: {str(e)[:100]}")
