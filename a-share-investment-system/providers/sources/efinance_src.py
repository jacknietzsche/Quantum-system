"""efinance 数据源适配器

依赖 efinance 三方包, 提供实时行情、K线、基本面。
"""

import logging

from providers.source_base import SourceAdapter, classify_error
from shared.logging import emit_log

logger = logging.getLogger(__name__)


class EFinanceAdapter(SourceAdapter):
    name = "efinance"
    priority = 60
    timeout = 10.0

    # ── 实时行情 ──

    def fetch_stock_spot(self):
        try:
            import efinance as ef

            return ef.stock.get_realtime_quotes()
        except Exception as e:
            raise classify_error(e, self.name) from e

    # ── K线 ──

    def fetch_kline(self, code: str, days: int = 90):
        try:
            import efinance as ef

            df = ef.stock.get_quote_history(code, klt=101)
            return df.tail(days) if df is not None and not df.empty else df
        except Exception as e:
            raise classify_error(e, self.name) from e

    # ── 基本面 ──

    def fetch_basic(self, code: str) -> dict | None:
        try:
            import efinance as ef

            info = ef.stock.get_base_info(code)
            return info if isinstance(info, dict) else {}
        except Exception as e:
            raise classify_error(e, self.name) from e

    # ── 连接测试 ──

    def test_connect(self) -> bool:
        try:
            import efinance as ef

            df = ef.stock.get_realtime_quotes()
            return df is not None and not df.empty
        except Exception as e:
            emit_log("WARNING", "efinance_src", f"Operation failed: {str(e)[:100]}")
            return False
