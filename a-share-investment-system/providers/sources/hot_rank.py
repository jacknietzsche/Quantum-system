"""热门排行榜数据源适配器

提供热门股票排名和热门搜索数据,基于 AKShare 接口。
"""

import logging

from providers.source_base import SourceAdapter, classify_error

logger = logging.getLogger(__name__)


class HotRankAdapter(SourceAdapter):
    name = "hot_rank"
    priority = 15
    timeout = 15.0

    def fetch_hot_rank(self) -> list | None:
        """获取热门股票排名

        Returns:
            list[dict]: 热门股票列表,每项包含 code, name, price, change_pct, hot_score
        """
        try:
            import akshare as ak
        except ImportError:
            return None

        try:
            df = ak.stock_hot_rank_em()
            if df is None or df.empty:
                return None
            result = []
            for _, row in df.iterrows():
                result.append(
                    {
                        "code": str(row.get("代码", "")),
                        "name": str(row.get("名称", "")),
                        "price": float(row.get("最新价", 0) or 0),
                        "change_pct": float(row.get("涨跌幅", 0) or 0),
                        "hot_score": float(row.get("热度", 0) or 0),
                    }
                )
            return result
        except Exception as e:
            raise classify_error(e, self.name) from e

    def fetch_hot_search(self) -> list | None:
        """获取热门搜索

        Returns:
            list[dict]: 热门搜索列表
        """
        try:
            import akshare as ak
        except ImportError:
            return None

        try:
            df = ak.stock_hot_search_em()
            if df is None or df.empty:
                return None
            result = []
            for _, row in df.iterrows():
                entry = {}
                for col in df.columns:
                    entry[str(col)] = row[col]
                result.append(entry)
            return result
        except Exception as e:
            raise classify_error(e, self.name) from e
