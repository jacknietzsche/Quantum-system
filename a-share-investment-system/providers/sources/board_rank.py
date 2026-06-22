"""板块排行榜数据源适配器

提供行业板块和概念板块排名数据,基于 AKShare 接口。
"""

import logging

from providers.source_base import SourceAdapter, classify_error
from shared.logging import emit_log

logger = logging.getLogger(__name__)


class BoardRankAdapter(SourceAdapter):
    name = "board_rank"
    priority = 35
    timeout = 15.0

    def fetch_industry_rank(self) -> list | None:
        """获取行业板块排名

        Returns:
            list[dict]: 行业板块列表
        """
        try:
            import akshare as ak
        except ImportError:
            return None

        try:
            df = ak.stock_board_industry_name_em()
            if df is None or df.empty:
                return None
            result = []
            for _, row in df.iterrows():
                entry = {}
                for col in df.columns:
                    val = row[col]
                    if hasattr(val, "item"):
                        val = val.item()
                    entry[str(col)] = val
                result.append(entry)
            return result
        except Exception as e:
            raise classify_error(e, self.name) from e

    def fetch_concept_rank(self) -> list | None:
        """获取概念板块排名

        Returns:
            list[dict]: 概念板块列表
        """
        try:
            import akshare as ak
        except ImportError:
            return None

        try:
            df = ak.stock_board_concept_name_em()
            if df is None or df.empty:
                return None
            result = []
            for _, row in df.iterrows():
                entry = {}
                for col in df.columns:
                    val = row[col]
                    if hasattr(val, "item"):
                        val = val.item()
                    entry[str(col)] = val
                result.append(entry)
            return result
        except Exception as e:
            raise classify_error(e, self.name) from e

    def test_connect(self) -> bool:
        try:
            import akshare as ak

            df = ak.stock_board_industry_name_em()
            return df is not None and not df.empty
        except Exception as e:
            emit_log("WARNING", "board_rank", f"Operation failed: {str(e)[:100]}")
            return False
