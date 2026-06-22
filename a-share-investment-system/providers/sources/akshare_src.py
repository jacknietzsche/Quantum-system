"""AKShare 数据源适配器

AKShare 是最全面的 A 股数据源, 依赖 akshare 三方包。
包含东财/新浪/腾讯多重内部降级。
参考: quant-agents daily_stock_analysis/data_provider/akshare_fetcher.py
"""

import logging

from providers.source_base import RateLimiter, SourceAdapter, classify_error
from shared.logging import emit_log

logger = logging.getLogger(__name__)

# AKShare 限流器: 全局最多5个并发
_AK_LOCK = RateLimiter(total=5, acquire_timeout=20.0, name="akshare")


class AKShareAdapter(SourceAdapter):
    name = "akshare"
    priority = 50
    timeout = 15.0

    # ── 指数 ──

    def fetch_indices(self) -> dict | None:
        try:
            import akshare as ak
        except ImportError:
            return None

        result = {
            "indices": {},
            "breadth": {
                "total": 0,
                "up": 0,
                "down": 0,
                "flat": 0,
                "limit_up": 0,
                "limit_down": 0,
                "up_ratio": 0,
            },
            "sectors": [],
            "data_time": __import__("time").strftime("%Y-%m-%d %H:%M"),
        }
        try:
            for name, code in [
                ("上证指数", "sh000001"),
                ("深证成指", "sz399001"),
                ("创业板指", "sz399006"),
                ("中证500", "sh000905"),
            ]:
                df = ak.stock_zh_index_daily(symbol=code)
                if df is not None and not df.empty:
                    latest = df.iloc[-1]
                    result["indices"][name] = {
                        "price": float(latest.get("close", 0)),
                        "change_pct": round(float(latest.get("pct_chg", 0) or 0), 2),
                        "amount": float(latest.get("amount", 0) or 0),
                    }
        except Exception as e:
            logger.debug(f"[AKShare] 指数获取部分失败: {e}")

        try:
            spot = ak.stock_zh_a_spot_em()
            if spot is not None and not spot.empty and "涨跌幅" in spot.columns:
                pct = spot["涨跌幅"]
                result["breadth"] = {
                    "total": len(spot),
                    "up": int((pct > 0).sum()),
                    "down": int((pct < 0).sum()),
                    "flat": int((pct == 0).sum()),
                    "limit_up": int((pct >= 9.5).sum()),
                    "limit_down": int((pct <= -9.5).sum()),
                    "up_ratio": round(int((pct > 0).sum()) / max(len(spot), 1) * 100, 1),
                }
        except Exception as e:
            logger.debug(f"[AKShare] 广度获取失败: {e}")

        try:
            for fn_name in ["stock_board_industry_name_em", "stock_board_concept_name_em"]:
                fn = getattr(ak, fn_name, None)
                if fn:
                    df = fn()
                    if df is not None and not df.empty:
                        sc = "涨跌幅" if "涨跌幅" in df.columns else df.columns[-1]
                        top = df.nlargest(10, sc)
                        field_map = {
                            "板块名称": "name",
                            "涨跌幅": "change_pct",
                            "换手率": "turnover",
                            "排名": "rank",
                            "最新价": "price",
                            "成交额": "amount",
                        }
                        result["sectors"] = [
                            {field_map.get(k, k): v for k, v in row.items()}
                            for _, row in top.iterrows()
                        ]
                        break
        except Exception as e:
            logger.debug(f"[AKShare] 板块获取失败: {e}")

        return result if result["indices"] else None

    # ── 北向资金 ──

    def fetch_north_flow(self) -> dict | None:
        try:
            import akshare as ak
        except ImportError:
            return None

        for fn_name in ["stock_hsgt_north_net_flow_in_em", "stock_em_hsgt_north_net_flow_in"]:
            try:
                fn = getattr(ak, fn_name, None)
                if fn:
                    df = fn(symbol="北上")
                    if df is not None and not df.empty:
                        latest = df.iloc[-1]
                        return {
                            "date": str(latest.get("date", "")),
                            "net_buy_amount": float(latest.get("value", 0) or 0),
                        }
            except Exception:
                logger.debug("Suppressed error in loop")
                continue
        return None

    # ── 实时行情 ──

    def fetch_stock_spot(self):
        try:
            import akshare as ak
        except ImportError:
            return None

        if not _AK_LOCK.acquire():
            return None
        try:
            return ak.stock_zh_a_spot_em()
        except Exception as e:
            raise classify_error(e, self.name) from e
        finally:
            _AK_LOCK.release()

    # ── K线 ──

    def fetch_kline(self, code: str, days: int = 90):
        try:
            import akshare as ak
        except ImportError:
            return None

        try:
            symbol = (
                f"sh{code}"
                if code.isdigit() and code.startswith(("6", "9"))
                else f"sz{code}"
                if code.isdigit()
                else code
            )
            # Try stock_zh_a_daily (Sina-based, more reliable) first
            try:
                df = ak.stock_zh_a_daily(symbol=symbol, adjust="qfq")
                if df is not None and not df.empty:
                    return df.tail(days)
            except Exception:
                pass
            # Fallback to stock_zh_a_hist (eastmoney-based)
            df = ak.stock_zh_a_hist(symbol=symbol, period="daily", adjust="qfq")
            return df.tail(days) if df is not None and not df.empty else None
        except Exception as e:
            raise classify_error(e, self.name) from e

    # ── 基本面 ──

    def fetch_basic(self, code: str) -> dict | None:
        try:
            import akshare as ak
        except ImportError:
            return None

        try:
            info = ak.stock_individual_info_em(symbol=code)
            if info is not None:
                return {str(row["item"]): row["value"] for _, row in info.iterrows()}
        except Exception as e:
            raise classify_error(e, self.name) from e
        return None

    # ── 连接测试 ──

    def test_connect(self) -> bool:
        try:
            import akshare as ak

            df = ak.stock_zh_index_daily(symbol="sh000001")
            return df is not None and not df.empty
        except Exception as e:
            emit_log("WARNING", "akshare_src", f"Operation failed: {str(e)[:100]}")
            return False
