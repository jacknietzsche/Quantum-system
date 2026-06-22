"""日频复盘引擎

对比昨日推荐 vs 今日实际表现, 更新 Agent 历史准确率, 生成反思.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timedelta
from typing import Any

from services.screening.daily_memory import DB_PATH, DailyMemory
from shared.db_session import db_session
from shared.logging import emit_log

logger = logging.getLogger(__name__)


class DailyReview:
    """日频复盘: 对比昨日推荐 vs 今日实际表现"""

    def __init__(self, llm_client: Any | None = None):
        self._memory = DailyMemory()
        self._llm = llm_client

    def review_yesterday(self, force_trade_date: str | None = None) -> dict:
        """复盘昨日推荐

        1. 从 daily_memory 读取昨日 picks
        2. 从 DB 读取今日实际价格/涨跌幅
        3. 计算命中率/平均收益/最大回撤
        4. 更新 agent_stats 表（每个Agent的历史准确率）
        5. 生成 AI 反思（有LLM时）

        Args:
            force_trade_date: 指定复盘日期（默认昨日）

        Returns:
            dict: 复盘结果
        """
        yesterday = force_trade_date or self._get_yesterday()
        today = datetime.now().strftime("%Y-%m-%d")

        try:
            # 1. 读取昨日记忆
            recent = self._memory.get_recent(days=7)
            yesterday_record = next((r for r in recent if r["trade_date"] == yesterday), None)

            if not yesterday_record:
                return {
                    "ok": False,
                    "error": f"未找到 {yesterday} 的推荐记录",
                    "trade_date": yesterday,
                }

            picks = yesterday_record.get("picks", [])
            if not picks:
                return {
                    "ok": False,
                    "error": f"{yesterday} 无推荐记录",
                    "trade_date": yesterday,
                }

            # 2. 查询今日实际表现
            actual_results = self._query_actual_performance(picks)

            # 3. 计算统计指标
            stats = self._compute_stats(actual_results)

            # 4. 更新 agent_stats
            agent_hits = self._compute_agent_hits(picks, actual_results)
            self._update_agent_stats(yesterday, agent_hits)

            # 5. 生成反思
            reflection = self._generate_reflection(yesterday, stats, agent_hits)

            # 6. 保存复盘结果到 daily_memory
            self._memory.update_result(
                yesterday,
                {
                    "review_date": today,
                    "stats": stats,
                    "agent_hits": agent_hits,
                    "reflection": reflection,
                },
            )

            emit_log(
                "INFO",
                "daily_review",
                f"复盘 {yesterday}: {stats.get('total', 0)} 只, "
                f"命中 {stats.get('hits', 0)}, "
                f"收益 {stats.get('avg_return', 0):.1f}%",
            )

            return {
                "ok": True,
                "trade_date": yesterday,
                "stats": stats,
                "agent_hits": agent_hits,
                "reflection": reflection,
            }

        except Exception as e:
            logger.exception("DailyReview failed")
            return {"ok": False, "error": str(e), "trade_date": yesterday}

    def calculate_accuracy(self, days: int = 30) -> dict:
        """计算最近N天各Agent的推荐准确率

        Args:
            days: 回溯天数

        Returns:
            dict: {agent_name: {accuracy, total_picks, correct, avg_return}}
        """
        try:
            # 从 daily_memory 获取近期记录
            recent = self._memory.get_recent(days=days)

            agent_stats: dict[str, dict] = {}
            for record in recent:
                picks = record.get("picks", [])
                for pick in picks:
                    agent_name = pick.get("agent_name", "unknown")
                    correct = pick.get("correct", pick.get("hit", False))
                    ret = pick.get("return_pct", pick.get("change_pct", 0))

                    if agent_name not in agent_stats:
                        agent_stats[agent_name] = {
                            "total_picks": 0,
                            "correct": 0,
                            "total_return": 0.0,
                        }
                    agent_stats[agent_name]["total_picks"] += 1
                    if correct:
                        agent_stats[agent_name]["correct"] += 1
                    agent_stats[agent_name]["total_return"] += float(ret or 0)

            # 从 agent_stats 表补充
            try:
                db_stats = self._memory.get_agent_stats()
                for s in db_stats:
                    name = s.get("agent_name", "")
                    if name and name not in agent_stats:
                        agent_stats[name] = {
                            "total_picks": int(s.get("total_picks", 0)),
                            "correct": int(s.get("correct", 0)),
                            "total_return": 0.0,
                        }
            except Exception:
                pass

            result = {}
            for name, s in agent_stats.items():
                total = s["total_picks"]
                correct = s["correct"]
                result[name] = {
                    "accuracy": round(correct / max(total, 1), 4),
                    "total_picks": total,
                    "correct": correct,
                    "avg_return": round(s["total_return"] / max(total, 1), 2),
                }
            return result

        except Exception as e:
            logger.warning("calculate_accuracy failed: %s", e)
            return {}

    # ── 内部方法 ──

    def _get_yesterday(self) -> str:
        """获取昨交易日字符串"""
        from services.trading_calendar import TradingCalendar

        cal = TradingCalendar()
        return cal.previous_trading_day() or (datetime.now() - timedelta(days=1)).strftime(
            "%Y-%m-%d"
        )

    def _query_actual_performance(self, picks: list[dict]) -> list[dict]:
        """查询今日实际涨跌幅"""
        from shared.models import StockInfo

        results = []
        with db_session() as session:
            for pick in picks:
                code = pick.get("stock_code", "")
                if not code:
                    continue
                stock = session.query(StockInfo).filter(StockInfo.stock_code == code).first()
                if stock and stock.latest_price and stock.latest_price > 0:
                    results.append(
                        {
                            "stock_code": code,
                            "stock_name": pick.get("stock_name", ""),
                            "agent_name": pick.get("agent_name", "unknown"),
                            "recommended_price": pick.get("price", pick.get("latest_price", 0)),
                            "actual_price": stock.latest_price,
                            "change_pct": float(stock.change_pct or 0),
                            "hit": float(stock.change_pct or 0) > 0,
                            "score": pick.get("score", 50),
                            "signal": pick.get("signal", "neutral"),
                        }
                    )
                else:
                    results.append(
                        {
                            "stock_code": code,
                            "stock_name": pick.get("stock_name", ""),
                            "agent_name": pick.get("agent_name", "unknown"),
                            "recommended_price": pick.get("price", 0),
                            "actual_price": 0,
                            "change_pct": 0,
                            "hit": False,
                            "score": pick.get("score", 50),
                            "signal": pick.get("signal", "neutral"),
                            "error": "no_price_data",
                        }
                    )
        return results

    def _compute_stats(self, actual_results: list[dict]) -> dict:
        """计算统计指标"""
        total = len(actual_results)
        if total == 0:
            return {
                "total": 0,
                "hits": 0,
                "hit_rate": 0,
                "avg_return": 0,
                "max_return": 0,
                "min_return": 0,
                "total_positive": 0,
                "total_negative": 0,
            }

        with_data = [r for r in actual_results if not r.get("error")]
        hits = sum(1 for r in with_data if r.get("hit"))
        returns = [float(r.get("change_pct", 0)) for r in with_data]

        avg_ret = sum(returns) / max(len(returns), 1)
        max_ret = max(returns) if returns else 0
        min_ret = min(returns) if returns else 0
        pos = sum(1 for r in returns if r > 0)
        neg = sum(1 for r in returns if r < 0)

        return {
            "total": total,
            "with_data": len(with_data),
            "hits": hits,
            "hit_rate": round(hits / max(len(with_data), 1), 4),
            "avg_return": round(avg_ret, 2),
            "max_return": round(max_ret, 2),
            "min_return": round(min_ret, 2),
            "total_positive": pos,
            "total_negative": neg,
        }

    def _compute_agent_hits(self, picks: list[dict], actual: list[dict]) -> list[dict]:
        """按Agent汇总命中情况"""
        code_map: dict[str, dict] = {}
        for a in actual:
            code = a.get("stock_code", "")
            if code:
                code_map[code] = a

        agent_map: dict[str, dict] = {}
        for pick in picks:
            code = pick.get("stock_code", "")
            agent_name = pick.get("agent_name", "unknown")
            actual_data = code_map.get(code, {})

            if agent_name not in agent_map:
                agent_map[agent_name] = {
                    "agent_name": agent_name,
                    "picks_count": 0,
                    "correct_count": 0,
                    "total_return": 0.0,
                }
            agent_map[agent_name]["picks_count"] += 1
            if actual_data.get("hit"):
                agent_map[agent_name]["correct_count"] += 1
            agent_map[agent_name]["total_return"] += float(actual_data.get("change_pct", 0))

        return list(agent_map.values())

    def _update_agent_stats(self, trade_date: str, agent_hits: list[dict]) -> None:
        """更新 agent_stats 表"""
        try:
            conn = sqlite3.connect(DB_PATH)
            for ah in agent_hits:
                count = ah.get("picks_count", 0)
                correct = ah.get("correct_count", 0)
                avg_ret = ah["total_return"] / max(count, 1) if count > 0 else 0
                conn.execute(
                    """INSERT OR REPLACE INTO agent_stats
                       (agent_name, trade_date, picks_count, correct_count, avg_return)
                       VALUES (?, ?, ?, ?, ?)""",
                    (ah["agent_name"], trade_date, count, correct, round(avg_ret, 2)),
                )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning("update_agent_stats failed: %s", e)

    def _generate_reflection(
        self,
        trade_date: str,
        stats: dict,
        agent_hits: list[dict],
    ) -> str:
        """生成复盘反思"""
        if self._llm:
            return self._ai_reflection(trade_date, stats, agent_hits)
        return self._rule_reflection(trade_date, stats, agent_hits)

    def _rule_reflection(
        self,
        trade_date: str,
        stats: dict,
        agent_hits: list[dict],
    ) -> str:
        """生成规则反思"""
        hit_rate = stats.get("hit_rate", 0)
        avg_return = stats.get("avg_return", 0)
        total = stats.get("total", 0)

        parts = [f"复盘 {trade_date}：推荐 {total} 只股票。"]

        if total == 0:
            parts.append("无推荐记录，无需复盘。")
            return " ".join(parts)

        parts.append(f"命中率 {hit_rate:.0%}，平均收益 {avg_return:.1f}%。")

        if hit_rate >= 0.6:
            parts.append("整体表现良好，策略有效。")
        elif hit_rate >= 0.4:
            parts.append("表现中等，需关注策略细节。")
        else:
            parts.append("表现不佳，建议重新评估选股策略。")

        if avg_return < -2:
            parts.append("市场环境偏弱，可考虑降低仓位。")
        elif avg_return > 2:
            parts.append("市场情绪偏暖，可适当提高仓位。")

        # Agent 表现
        if agent_hits:

            def _agent_acc(x):
                return x.get("correct_count", 0) / max(x.get("picks_count", 1), 1)

            best = max(agent_hits, key=_agent_acc)
            worst = min(agent_hits, key=_agent_acc)
            best_acc = best.get("correct_count", 0) / max(best.get("picks_count", 0), 1)
            worst_acc = worst.get("correct_count", 0) / max(worst.get("picks_count", 0), 1)
            parts.append(
                f"最佳 Agent: {best['agent_name']} ({best_acc:.0%}), "
                f"待改进 Agent: {worst['agent_name']} ({worst_acc:.0%})."
            )

        return " ".join(parts)

    def _ai_reflection(
        self,
        trade_date: str,
        stats: dict,
        agent_hits: list[dict],
    ) -> str:
        """调用 LLM 生成反思"""
        try:
            prompt = (
                f"你是A股量化投研系统的复盘分析师。"
                f"请对以下 {trade_date} 的选股复盘结果进行分析和反思。\n\n"
                f"## 统计概览\n"
                f"推荐股票数: {stats.get('total', 0)}\n"
                f"命中率: {stats.get('hit_rate', 0):.0%}\n"
                f"平均收益: {stats.get('avg_return', 0):.1f}%\n"
                f"最大收益: {stats.get('max_return', 0):.1f}%\n"
                f"最小收益: {stats.get('min_return', 0):.1f}%\n"
                f"上涨: {stats.get('total_positive', 0)} / "
                f"下跌: {stats.get('total_negative', 0)}\n\n"
                f"## Agent 表现\n"
            )
            for ah in agent_hits:
                count = ah.get("picks_count", 0)
                correct = ah.get("correct_count", 0)
                prompt += (
                    f"- {ah['agent_name']}: {correct}/{count} 正确"
                    f" ({correct / max(count, 1):.0%})\n"
                )

            prompt += (
                "\n## 要求\n"
                "请输出一段不超过200字的复盘反思，包括：\n"
                "1. 今日策略整体评价\n"
                "2. 表现突出的 Agent 及原因\n"
                "3. 明日建议（调仓方向、参数调整）\n"
            )

            response = self._llm.chat(prompt)
            text = str(response).strip()
            return text[:500]
        except Exception as e:
            logger.warning("AI reflection failed: %s", e)
            return self._rule_reflection(trade_date, stats, agent_hits)
