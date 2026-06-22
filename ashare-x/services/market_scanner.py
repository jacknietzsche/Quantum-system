"""全市场扫描服务 — 不调用LLM，纯量化筛选。

从DataBus获取5000+只A股快照，多因子打分排名，维护观察名单。
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime

from core.config import Config
from providers.data_bus import DatabaseFirstDataBus
from services.screening import compute_stock_score, hard_filter

logger = logging.getLogger("ashare-x.services.market_scanner")


class MarketScanner:
    """全市场扫描器。"""

    def __init__(self, db_path: str | None = None, config: Config | None = None):
        self.config = config or Config()
        if db_path is None:
            db_path = self.config.get("runtime.db_path", "runtime/investment.db")
        self.db_path = db_path
        self.bus = DatabaseFirstDataBus(db_path)
        self.watchlist_size = self.config.get("trading_plan.watchlist_size", 30)
        self.scan_top_n = self.config.get("trading_plan.scan_top_n", 50)

    def scan_full_market(self, style: str = "balanced", top_n: int | None = None) -> list[dict]:
        """
        全市场扫描:
        1. 获取5000+只股票快照
        2. 过滤ST、停牌、流动性不足
        3. 多因子打分
        4. 返回Top N
        """
        if top_n is None:
            top_n = self.scan_top_n

        stocks = self._get_spot_universe()
        if not stocks:
            logger.warning("全市场快照为空，尝试刷新...")
            stocks = self._refresh_and_get_universe()

        if not stocks:
            logger.error("无法获取全市场数据")
            return []

        logger.info("全市场快照: %d只股票", len(stocks))

        # 过滤 + 打分
        filtered = []
        for s in stocks:
            stock = self._normalize_spot(s)
            if hard_filter(stock):
                stock["score"] = compute_stock_score(stock, style)
                filtered.append(stock)

        # 排序
        ranked = sorted(filtered, key=lambda x: x["score"], reverse=True)
        result = ranked[:top_n]

        logger.info("筛选后: %d只 → Top %d", len(filtered), len(result))
        return result

    def update_watchlist(self, scan_results: list[dict], max_size: int | None = None):
        """更新观察名单。高分新入选加入，跌出范围移除。"""
        if max_size is None:
            max_size = self.watchlist_size

        conn = sqlite3.connect(self.db_path)
        today = datetime.now().strftime("%Y-%m-%d")

        # 获取当前观察名单中的代码集合
        cursor = conn.execute("SELECT stock_code FROM watchlist")
        existing_codes = {row[0] for row in cursor.fetchall()}

        # 新入选的代码
        new_codes = {s["stock_code"] for s in scan_results[:max_size]}

        # 添加新入选的
        added = 0
        for stock in scan_results[:max_size]:
            code = stock["stock_code"]
            if code not in existing_codes:
                conn.execute(
                    "INSERT OR IGNORE INTO watchlist "
                    "(stock_code, stock_name, score, style, added_date, priority) "
                    "VALUES (?, ?, ?, ?, ?, 0)",
                    (code, stock.get("stock_name", ""), stock.get("score", 0),
                     stock.get("style", "balanced"), today),
                )
                added += 1

        # 更新已有观察名单的评分
        for stock in scan_results[:max_size]:
            conn.execute(
                "UPDATE watchlist SET score = ?, stock_name = ? WHERE stock_code = ?",
                (stock.get("score", 0), stock.get("stock_name", ""), stock["stock_code"]),
            )

        # 移除跌出范围的（不在Top max_size*2的）
        keep_codes = {s["stock_code"] for s in scan_results[:max_size * 2]}
        # 不移除持仓股（priority=1）
        if keep_codes:
            placeholders = ",".join("?" * len(keep_codes))
            conn.execute(
                f"DELETE FROM watchlist WHERE stock_code NOT IN ({placeholders}) "  # noqa: S608
                f"AND priority = 0",
                tuple(keep_codes),
            )
        else:
            conn.execute("DELETE FROM watchlist WHERE priority = 0")

        conn.commit()
        conn.close()

        logger.info("观察名单更新: 新增%d, 保留%d", added, len(new_codes))

    def get_watchlist(self) -> list[dict]:
        """获取当前观察名单。"""
        conn = sqlite3.connect(self.db_path)
        rows = conn.execute(
            "SELECT stock_code, stock_name, score, added_date, "
            "last_analysis_date, analysis_count, priority "
            "FROM watchlist ORDER BY priority DESC, score DESC"
        ).fetchall()
        conn.close()
        return [
            {
                "stock_code": r[0], "stock_name": r[1], "score": r[2],
                "added_date": r[3], "last_analysis_date": r[4],
                "analysis_count": r[5], "priority": r[6],
            }
            for r in rows
        ]

    def mark_analyzed(self, code: str):
        """标记某股票已分析。"""
        conn = sqlite3.connect(self.db_path)
        today = datetime.now().strftime("%Y-%m-%d")
        conn.execute(
            "UPDATE watchlist SET last_analysis_date = ?, analysis_count = analysis_count + 1 "
            "WHERE stock_code = ?",
            (today, code),
        )
        conn.commit()
        conn.close()

    def set_priority(self, code: str, priority: int):
        """设置观察名单优先级。0=观察, 1=持仓, 2=待分析。"""
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "UPDATE watchlist SET priority = ? WHERE stock_code = ?",
            (priority, code),
        )
        conn.commit()
        conn.close()

    def _get_spot_universe(self) -> list[dict]:
        """获取全量快照数据。"""
        cache = DatabaseFirstDataBus._spot_cache
        if cache and len(cache) > 100:
            return [{"stock_code": code, **data} for code, data in cache.items()]
        return []

    def _refresh_and_get_universe(self) -> list[dict]:
        """刷新快照缓存并获取。"""
        # 调用 get_market_breadth 会触发 stock_zh_a_spot_em 并缓存
        self.bus.get_market_breadth()
        return self._get_spot_universe()

    @staticmethod
    def _normalize_spot(spot: dict) -> dict:
        """将spot缓存数据标准化为screening兼容格式。"""
        return {
            "stock_code": spot.get("stock_code", ""),
            "stock_name": spot.get("stock_name", ""),
            "pe_ratio": spot.get("pe_ratio") or 50,
            "pb_ratio": spot.get("pb_ratio") or 5,
            "dividend_yield": spot.get("dividend_yield", 0),
            "latest_price": spot.get("latest_price", 0),
            "change_pct": spot.get("change_pct", 0),
            "change_pct_20d": spot.get("change_pct", 0),  # 近似用日涨幅
            "volume": spot.get("volume", 0),
            "amount": spot.get("amount", 0),
            "turnover_rate": spot.get("turnover_rate", 0),
            "rsi_14": 50,  # 快照无RSI，默认中性
            "roe": 0,  # 快照无ROE
            "revenue_growth": 0,
            "profit_growth": 0,
            "is_st": "ST" in spot.get("stock_name", ""),
            "is_suspended": False,
            "listing_days": 999,
        }
