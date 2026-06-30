"""股票代码标准化。

设计依据: S05 §5.13, experiments exp14.2。
不同数据源用不同格式，需要统一转换层。
"""

from __future__ import annotations


class StockCodeNormalizer:
    """股票代码标准化。"""

    @staticmethod
    def to_db(code: str) -> str:
        """统一转为数据库格式: 600519"""
        code = code.strip()
        for prefix in ["sh.", "sz.", "bj."]:
            if code.startswith(prefix):
                return code[3:]
        if "." in code:
            return code.split(".")[0]
        return code

    @staticmethod
    def to_baostock(code: str) -> str:
        """转为BaoStock格式: sh.600519"""
        code = StockCodeNormalizer.to_db(code)
        if code.startswith("6"):
            return f"sh.{code}"
        if code.startswith(("0", "3")):
            return f"sz.{code}"
        if code.startswith(("4", "8", "92")):
            return f"bj.{code}"
        return f"sh.{code}"

    @staticmethod
    def to_yfinance(code: str) -> str:
        """转为yfinance格式: 600519.SS"""
        code = StockCodeNormalizer.to_db(code)
        if code.startswith("6"):
            return f"{code}.SS"
        if code.startswith(("0", "3")):
            return f"{code}.SZ"
        return f"{code}.SS"

    @staticmethod
    def get_exchange(code: str) -> str:
        """获取交易所: SH/SZ/BJ"""
        code = StockCodeNormalizer.to_db(code)
        if code.startswith("6"):
            return "SH"
        if code.startswith(("0", "3")):
            return "SZ"
        if code.startswith(("4", "8", "92")):
            return "BJ"
        return "SH"
