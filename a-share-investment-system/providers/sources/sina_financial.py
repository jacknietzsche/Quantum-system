"""Sina 财报数据适配器 — 资产负债表/利润表

通过 AKShare 的 stock_financial_report_sina 接口获取。
返回中文列名,由 _normalize_fields 在 data_initializer 中映射。
"""

import contextlib
import logging
from typing import ClassVar

from providers.source_base import SourceAdapter
from shared.logging import emit_log

logger = logging.getLogger(__name__)


class SinaFinancialAdapter(SourceAdapter):
    name = "sina_financial"
    priority = 30  # After EastMoney(10) and Tencent(10), before Baostock(15) as fallback
    timeout = 15.0

    IDX_MAP: ClassVar[dict[str, tuple[str, ...]]] = {
        "sh": ("6", "9"),
        "sz": ("0", "3", "2"),
        "bj": ("4", "8"),
    }

    def _to_sina_symbol(self, code: str) -> str:
        code = code.replace(".SH", "").replace(".SZ", "").replace(".BJ", "")
        for prefix, codes in self.IDX_MAP.items():
            if code.startswith(codes):
                return f"{prefix}{code}"
        return f"sz{code}"

    def fetch_balance_sheet(self, code: str) -> dict | None:
        """Fetch balance sheet via AKShare sina financial report API"""
        try:
            import akshare as ak

            symbol = self._to_sina_symbol(code)
            df = ak.stock_financial_report_sina(stock=symbol, symbol="资产负债表")
            if df is None or df.empty:
                return None

            latest = df.iloc[0].to_dict()
            result = {"stock_code": code, "report_date": str(latest.get("REPORT_DATE", ""))[:10]}

            field_map = {
                "流动资产合计": "current_assets",
                "货币资金": "cash",
                "应收账款": "accounts_receivable",
                "存货": "inventory",
                "负债合计": "total_liabilities",
                "流动负债": "current_liabilities",
                "非流动资产合计": "non_current_assets",
                "资产总计": "total_assets",
                "所有者权益合计": "total_equity",
            }

            for cn_name, en_name in field_map.items():
                val = latest.get(cn_name)
                if val is not None:
                    with contextlib.suppress(ValueError, TypeError):
                        result[en_name] = float(val)

            return result
        except Exception as e:
            raise self._classify_error(e) from e

    def fetch_income_sheet(self, code: str) -> dict | None:
        """Fetch income statement"""
        try:
            import akshare as ak

            symbol = self._to_sina_symbol(code)
            df = ak.stock_financial_report_sina(stock=symbol, symbol="利润表")
            if df is None or df.empty:
                return None

            latest = df.iloc[0].to_dict()
            result = {"stock_code": code, "report_date": str(latest.get("REPORT_DATE", ""))[:10]}

            field_map = {
                "营业收入": "revenue",
                "营业利润": "operating_profit",
                "利润总额": "total_profit",
                "净利润": "net_income",
                "营业成本": "cost_of_revenue",
            }

            for cn_name, en_name in field_map.items():
                val = latest.get(cn_name)
                if val is not None:
                    with contextlib.suppress(ValueError, TypeError):
                        result[en_name] = float(val)

            return result
        except Exception as e:
            raise self._classify_error(e) from e

    def fetch_basic(self, code: str) -> dict | None:
        """Implements the fetch_basic interface: returns current_assets, total_liabilities,
        cash, net_income, revenue"""
        bs = self.fetch_balance_sheet(code)
        inc = self.fetch_income_sheet(code)

        if not bs and not inc:
            return None

        result = {}
        if bs:
            result.update(bs)
        if inc:
            result.update(inc)

        try:
            import akshare as ak

            info = ak.stock_individual_info_em(symbol=code)
            if info is not None:
                info_dict = {str(r["item"]): r["value"] for _, r in info.iterrows()}
                total_shares = info_dict.get("总股本")
                if total_shares:
                    result["shares_outstanding"] = float(total_shares)
        except Exception as e:
            emit_log("WARNING", "sina_financial", f"Operation failed: {str(e)[:100]}")

        # Drop zero/None fields (avoid _save_stock_info overwrite with 0)
        for k in list(result.keys()):
            if k in ("stock_code", "stock_name", "report_date"):
                continue
            v = result.get(k)
            if v is None or v in {0}:
                with contextlib.suppress(KeyError):
                    del result[k]

        return result

    def test_connect(self) -> bool:
        try:
            result = self.fetch_balance_sheet("000001")
            return result is not None and "current_assets" in result
        except Exception as e:
            emit_log("WARNING", "sina_financial", f"Operation failed: {str(e)[:100]}")
            return False

    def _classify_error(self, e: Exception) -> Exception:
        from providers.source_base import DataSourceError, RateLimitError

        msg = str(e).lower()
        if "timeout" in msg or "read timed out" in msg:
            return DataSourceError(f"sina_financial timeout: {e}")
        if "429" in msg or "too many" in msg:
            return RateLimitError(f"sina_financial rate limit: {e}")
        return DataSourceError(f"sina_financial: {e}")
