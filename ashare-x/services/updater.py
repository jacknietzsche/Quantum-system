"""每日数据更新服务。

设计依据: S06 §6.5。
每日收盘后更新数据库中的K线、指数、财务数据。
所有数据通过DatabaseFirstDataBus获取（数据库优先 → API → 存库 → 返回）。
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TypedDict

from providers.data_bus import DatabaseFirstDataBus

logger = logging.getLogger("ashare-x.services.updater")


class _DailyUpdateStats(TypedDict, total=False):
    started_at: str
    completed_at: str
    kline_updated: int
    stock_info_updated: int
    fundamentals_updated: int
    news_updated: int
    sentiment_updated: int
    market_breadth_updated: bool
    errors: list[str]


class _IncrementalStats(TypedDict, total=False):
    started_at: str
    completed_at: str
    total: int
    skipped: int
    updated: int
    failed: int
    details: list[dict[str, object]]


class DailyUpdater:
    """每日数据更新器。"""

    def __init__(self, db_path: str = "runtime/investment.db"):
        self.db_path = db_path
        self.bus = DatabaseFirstDataBus(db_path)

    def run_daily_update(self, stock_codes: list[str] | None = None) -> _DailyUpdateStats:
        """
        每日收盘后执行数据更新。
        所有数据遵循: 数据库优先 → API获取 → 存入数据库 → 返回。

        Args:
            stock_codes: 需要更新的股票代码列表。若为None则更新活跃股票。

        Returns:
            更新结果统计
        """
        logger.info("开始每日数据更新")
        stats: _DailyUpdateStats = {
            "started_at": datetime.now().isoformat(),
            "kline_updated": 0,
            "stock_info_updated": 0,
            "fundamentals_updated": 0,
            "news_updated": 0,
            "sentiment_updated": 0,
            "market_breadth_updated": False,
            "errors": [],
        }

        # 确定需要更新的股票列表
        if not stock_codes:
            stock_codes = self._get_active_stocks()
            if not stock_codes:
                # 默认更新几个蓝筹股
                stock_codes = [
                    "600519",  # 贵州茅台
                    "000858",  # 五粮液
                    "601318",  # 中国平安
                    "000333",  # 美的集团
                    "600036",  # 招商银行
                ]

        logger.info("待更新股票: %d只", len(stock_codes))

        # 1. 更新K线数据
        for code in stock_codes:
            try:
                kline = self.bus.get_kline(code, days=365)
                if kline:
                    stats["kline_updated"] += 1
            except Exception as e:
                stats["errors"].append(f"K线 {code}: {e}")
                logger.warning("更新K线失败 %s: %s", code, e)

        # 2. 更新股票基础信息
        for code in stock_codes:
            try:
                info = self.bus.get_stock_info(code)
                if info:
                    stats["stock_info_updated"] += 1
            except Exception as e:
                stats["errors"].append(f"股票信息 {code}: {e}")
                logger.warning("更新股票信息失败 %s: %s", code, e)

        # 3. 更新基本面数据
        for code in stock_codes:
            try:
                fund = self.bus.get_fundamentals(code)
                if fund:
                    stats["fundamentals_updated"] += 1
            except Exception as e:
                stats["errors"].append(f"基本面 {code}: {e}")
                logger.warning("更新基本面失败 %s: %s", code, e)

        # 4. 更新新闻数据
        for code in stock_codes:
            try:
                news = self.bus.get_news(code, days=7)
                if news:
                    stats["news_updated"] += 1
            except Exception as e:
                stats["errors"].append(f"新闻 {code}: {e}")
                logger.warning("更新新闻失败 %s: %s", code, e)

        # 5. 更新情绪数据
        for code in stock_codes:
            try:
                sent = self.bus.get_social_sentiment(code)
                if sent and any(v is not None for v in sent.values()):
                    stats["sentiment_updated"] += 1
            except Exception as e:
                stats["errors"].append(f"情绪 {code}: {e}")
                logger.warning("更新情绪失败 %s: %s", code, e)

        # 6. 更新市场广度
        try:
            breadth = self.bus.get_market_breadth()
            if breadth and breadth.get("total", 0) > 0:
                stats["market_breadth_updated"] = True
        except Exception as e:
            stats["errors"].append(f"市场广度: {e}")
            logger.warning("更新市场广度失败: %s", e)

        # 7. 更新市场概览
        try:
            self.bus.get_market_overview()
        except Exception as e:
            stats["errors"].append(f"市场概览: {e}")
            logger.warning("更新市场概览失败: %s", e)

        stats["completed_at"] = datetime.now().isoformat()
        logger.info(
            "每日数据更新完成: K线%d/信息%d/基本面%d/新闻%d/情绪%d, 错误%d",
            stats["kline_updated"],
            stats["stock_info_updated"],
            stats["fundamentals_updated"],
            stats["news_updated"],
            stats["sentiment_updated"],
            len(stats["errors"]),
        )
        return stats

    def _get_active_stocks(self) -> list[str]:
        """从数据库获取活跃股票列表（有持仓或最近分析过的）。"""
        import sqlite3

        codes: list[str] = []
        try:
            conn = sqlite3.connect(self.db_path)
            # 从stock_info表获取所有已缓存的股票
            cursor = conn.execute("SELECT DISTINCT stock_code FROM stock_info LIMIT 50")
            codes = [row[0] for row in cursor.fetchall()]
            conn.close()
        except Exception:
            pass
        return codes

    def update_single_stock(self, code: str) -> dict:
        """更新单只股票的所有数据。"""
        logger.info("更新单只股票: %s", code)
        stats = {
            "code": code,
            "kline": False,
            "stock_info": False,
            "fundamentals": False,
            "news": False,
            "sentiment": False,
        }

        try:
            if self.bus.get_kline(code, days=365):
                stats["kline"] = True
        except Exception as e:
            logger.warning("更新K线失败 %s: %s", code, e)

        try:
            if self.bus.get_stock_info(code):
                stats["stock_info"] = True
        except Exception as e:
            logger.warning("更新股票信息失败 %s: %s", code, e)

        try:
            if self.bus.get_fundamentals(code):
                stats["fundamentals"] = True
        except Exception as e:
            logger.warning("更新基本面失败 %s: %s", code, e)

        try:
            if self.bus.get_news(code, days=7):
                stats["news"] = True
        except Exception as e:
            logger.warning("更新新闻失败 %s: %s", code, e)

        try:
            sent = self.bus.get_social_sentiment(code)
            if sent and any(v is not None for v in sent.values()):
                stats["sentiment"] = True
        except Exception as e:
            logger.warning("更新情绪失败 %s: %s", code, e)

        return stats

    def incremental_refresh(self, days: int = 60) -> _IncrementalStats:
        """
        增量刷新近N日数据。

        逐股检查kline_daily表中近days天的数据完整性:
        - 数据完整的跳过（已有交易日数 >= 预期的80%）
        - 不完整的调用bus.get_kline补充
        - 同时更新stock_info（如果过期）

        Returns:
            统计: skipped, updated, failed, total, details
        """
        import sqlite3
        from datetime import datetime, timedelta

        logger.info("开始增量刷新近%d日数据", days)
        stats: _IncrementalStats = {
            "started_at": datetime.now().isoformat(),
            "total": 0,
            "skipped": 0,
            "updated": 0,
            "failed": 0,
            "details": [],
        }

        # 获取所有需要检查的股票
        stock_codes = self._get_stocks_to_check()
        stats["total"] = len(stock_codes)
        logger.info("待检查股票: %d只", len(stock_codes))

        # 预期交易日数（days天去除周末）
        expected_trading_days = int(days * 5 / 7)
        min_required = int(expected_trading_days * 0.8)  # 80%完整即跳过
        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

        conn = sqlite3.connect(self.db_path)
        for code in stock_codes:
            try:
                # 检查kline_daily中近days天的记录数
                cursor = conn.execute(
                    "SELECT COUNT(*) FROM kline_daily "
                    "WHERE stock_code = ? AND trade_date >= ?",
                    (code, start_date),
                )
                row_count = cursor.fetchone()[0]

                if row_count >= min_required:
                    # 数据完整，跳过
                    stats["skipped"] += 1
                    stats["details"].append({
                        "code": code, "status": "skipped",
                        "existing_days": row_count,
                    })
                    logger.debug("跳过 %s: 已有%d条K线", code, row_count)
                else:
                    # 数据不完整，补充
                    kline = self.bus.get_kline(code, days=days)
                    if kline:
                        stats["updated"] += 1
                        stats["details"].append({
                            "code": code, "status": "updated",
                            "previous_days": row_count,
                            "new_days": len(kline),
                        })
                        logger.info(
                            "更新 %s: %d条 -> %d条",
                            code, row_count, len(kline),
                        )
                    else:
                        stats["failed"] += 1
                        stats["details"].append({
                            "code": code, "status": "failed",
                            "existing_days": row_count,
                        })
                        logger.warning("更新失败 %s: 无数据", code)
            except Exception as e:
                stats["failed"] += 1
                stats["details"].append({
                    "code": code, "status": "failed", "error": str(e),
                })
                logger.warning("检查/更新 %s 失败: %s", code, e)

        conn.close()

        stats["completed_at"] = datetime.now().isoformat()
        logger.info(
            "增量刷新完成: 共%d只, 跳过%d, 更新%d, 失败%d",
            stats["total"], stats["skipped"], stats["updated"], stats["failed"],
        )
        return stats

    def _get_stocks_to_check(self) -> list[str]:
        """获取需要检查数据完整性的股票列表。

        来源: stock_info表 + paper_holdings + watchlist（去重）
        """
        import sqlite3

        codes: set[str] = set()
        conn = sqlite3.connect(self.db_path)
        try:
            # stock_info表中的所有股票
            cursor = conn.execute("SELECT DISTINCT stock_code FROM stock_info")
            codes.update(row[0] for row in cursor.fetchall())

            # 模拟持仓
            cursor = conn.execute("SELECT stock_code FROM paper_holdings")
            codes.update(row[0] for row in cursor.fetchall())

            # 观察名单
            cursor = conn.execute("SELECT stock_code FROM watchlist")
            codes.update(row[0] for row in cursor.fetchall())
        except Exception:
            pass
        finally:
            conn.close()

        if not codes:
            # 如果数据库为空，使用默认蓝筹股
            codes = {
                "600519", "000858", "601318",
                "000333", "600036",
            }

        return sorted(codes)
