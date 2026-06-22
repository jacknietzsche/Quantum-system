import logging
from datetime import datetime

from services.base import BaseService
from shared.logging import emit_log

logger = logging.getLogger(__name__)


class IndicatorRefresher(BaseService):
    def __init__(self, provider):
        super().__init__()
        self._provider = provider

    @property
    def provider(self):
        return self._provider

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

        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = {executor.submit(_fetch_one, code): code for code in targets}
            for i, future in enumerate(as_completed(futures)):
                if i > 0 and i % 25 == 0:
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
        if not result:
            emit_log("WARNING", "data_init", "[Industry] fetch_industry_batch returned no data")
            return {"status": "no_data", "updated": 0}

        # result is a plain dict mapping stock_code -> industry_name
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

    def _default_stock_pool(self) -> list:
        return self.get_hot_stock_pool()
