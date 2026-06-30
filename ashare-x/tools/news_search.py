"""新闻搜索工具。

设计依据: S04 §4.6, S05 §5.11。
通过DatabaseFirstDataBus获取数据（数据库优先 → API → 存库 → 返回）。
"""

from __future__ import annotations

import logging

from providers.data_bus import DatabaseFirstDataBus

logger = logging.getLogger(__name__)

_bus = DatabaseFirstDataBus()


def get_news(code: str, days: int = 7) -> list[dict]:
    """
    获取股票新闻（数据库优先）。
    返回: [{title, source, date, content, url}]
    """
    return _bus.get_news(code, days)


def get_global_news() -> list[dict]:
    """获取宏观经济新闻（央视新闻联播财经摘要）。"""
    news_list: list[dict] = []

    try:
        import akshare as ak
        from datetime import datetime, timedelta

        # akshare 的 news_cctv 需要 YYYYMMDD 格式日期，留 None 在部分版本会报错
        date_str = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")
        df = ak.news_cctv(date=date_str)
        if df is not None and not df.empty:
            for _, row in df.head(20).iterrows():
                news_list.append({
                    "title": str(row.get("title", "")),
                    "content": str(row.get("content", ""))[:500],
                    "source": "央视新闻",
                    "date": str(row.get("date", ""))[:10],
                    "url": "",
                })

        logger.info("获取宏观新闻%d条", len(news_list))

    except ImportError:
        logger.warning("akshare未安装")
    except Exception as e:
        logger.warning("获取宏观新闻失败: %s", e)

    return news_list
