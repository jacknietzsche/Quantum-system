"""涨停/跌停/炸板数据源适配器

提供涨停池、强势股池、炸板池数据,基于 AKShare 接口。
"""

import logging

import pandas as pd

from providers.source_base import SourceAdapter, classify_error
from shared.logging import emit_log

logger = logging.getLogger(__name__)


class ZTPoolAdapter(SourceAdapter):
    name = "zt_pool"
    priority = 45
    timeout = 15.0

    def _normalize_date(self, date_str: str) -> str:
        """将日期格式从 YYYY-MM-DD 转换为 YYYYMMDD"""
        return date_str.replace("-", "")

    def fetch_zt_pool(self, date: str) -> pd.DataFrame | None:
        """获取涨停板池

        Args:
            date: 日期,格式 YYYY-MM-DD

        Returns:
            DataFrame: 涨停板数据
        """
        try:
            import akshare as ak
        except ImportError:
            return None

        try:
            date_key = self._normalize_date(date)
            df = ak.stock_zt_pool_em(date=date_key)
            return df if df is not None and not df.empty else None
        except Exception as e:
            raise classify_error(e, self.name) from e

    def fetch_strong_pool(self, date: str) -> pd.DataFrame | None:
        """获取强势股池

        Args:
            date: 日期,格式 YYYY-MM-DD

        Returns:
            DataFrame: 强势股数据
        """
        try:
            import akshare as ak
        except ImportError:
            return None

        try:
            date_key = self._normalize_date(date)
            df = ak.stock_strong_pool_em(date=date_key)
            return df if df is not None and not df.empty else None
        except Exception as e:
            raise classify_error(e, self.name) from e

    def fetch_zhaban_pool(self, date: str) -> pd.DataFrame | None:
        """获取炸板池

        Args:
            date: 日期,格式 YYYY-MM-DD

        Returns:
            DataFrame: 炸板数据
        """
        try:
            import akshare as ak
        except ImportError:
            return None

        try:
            date_key = self._normalize_date(date)
            df = ak.stock_zhaban_pool_em(date=date_key)
            return df if df is not None and not df.empty else None
        except Exception as e:
            raise classify_error(e, self.name) from e

    def test_connect(self) -> bool:
        try:
            import akshare as ak

            df = ak.stock_zt_pool_em(date="20250102")
            return df is not None and not df.empty
        except Exception as e:
            emit_log("WARNING", "zt_pool", f"Operation failed: {str(e)[:100]}")
            return False
