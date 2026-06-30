"""每日交易计划生成器 — 端到端流水线。

流程: 数据更新 → 全市场扫描 → 深度分析 → 仓位决策 → 模拟交易 → 计划保存。
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from core.config import Config
from services.market_perception import get_market_overview
from services.market_scanner import MarketScanner
from services.paper_portfolio import PaperPortfolio
from services.position_engine import PositionDecision, PositionEngine

logger = logging.getLogger("ashare-x.services.daily_plan")


class DailyPlanGenerator:
    """每日交易计划生成器。"""

    def __init__(self, config: Config | None = None):
        self.config = config or Config()
        self.db_path = self.config.get("runtime.db_path", "runtime/investment.db")
        self.portfolio = PaperPortfolio(self.db_path, self.config)
        self.scanner = MarketScanner(self.db_path, self.config)
        self.engine = PositionEngine(self.config)
        self.daily_batch = self.config.get("trading_plan.daily_analysis_batch", 5)
        self.auto_trade = self.config.get("trading_plan.auto_trade", True)

    def generate(self, fast_mode: bool = True) -> dict:
        """
        生成每日交易计划（完整流水线）。
        """
        today = datetime.now().strftime("%Y-%m-%d")
        plan: dict = {
            "date": today,
            "market_state": "NEUTRAL",
            "market_overview": {},
            "actions": [],
            "holdings_status": [],
            "watchlist": [],
            "summary": "",
            "errors": [],
        }

        logger.info("═══ 开始生成每日交易计划 %s ═══", today)

        # Step 1: 更新市场数据
        try:
            from services.updater import DailyUpdater

            updater = DailyUpdater(self.db_path)
            update_stats = updater.run_daily_update()
            plan["data_update"] = {
                "kline": update_stats.get("kline_updated", 0),
                "stock_info": update_stats.get("stock_info_updated", 0),
                "fundamentals": update_stats.get("fundamentals_updated", 0),
                "errors": len(update_stats.get("errors", [])),
            }
            logger.info("Step 1: 数据更新完成")
        except Exception as e:
            plan["errors"].append(f"数据更新失败: {e}")
            logger.warning("数据更新失败: %s", e)

        # Step 2: 市场状态
        try:
            overview = get_market_overview()
            plan["market_overview"] = overview
            plan["market_state"] = overview.get("market_state", "NEUTRAL")
            logger.info("Step 2: 市场状态=%s", plan["market_state"])
        except Exception as e:
            plan["errors"].append(f"市场状态获取失败: {e}")
            logger.warning("市场状态获取失败: %s", e)

        # Step 3: 全市场扫描
        try:
            scan_results = self.scanner.scan_full_market(top_n=50)
            self.scanner.update_watchlist(scan_results)
            plan["scan_count"] = len(scan_results)
            logger.info("Step 3: 全市场扫描完成, %d只候选", len(scan_results))
        except Exception as e:
            plan["errors"].append(f"市场扫描失败: {e}")
            scan_results = []
            logger.warning("市场扫描失败: %s", e)

        # Step 4: 更新持仓价格 + 清除T+1冻结
        try:
            self.portfolio.update_prices()
        except Exception as e:
            logger.warning("更新持仓价格失败: %s", e)

        # Step 5: 获取账户状态
        account = self.portfolio.get_account()
        holdings = self.portfolio.get_holdings()
        market_state = plan["market_state"]

        # Step 6: 深度分析 — 持仓股（每日必须）
        for h in holdings:
            try:
                analysis = self._run_analysis(h["stock_code"], fast_mode=fast_mode)
                if analysis:
                    analysis["ticker"] = h["stock_code"]
                    analysis["stock_name"] = h["stock_name"]
                    decision = self.engine.decide(
                        analysis_result=analysis,
                        current_holding=h,
                        account=account,
                        market_state=market_state,
                        holding_count=len(holdings),
                    )
                    plan["actions"].append(decision.to_dict())
                    # 执行模拟交易
                    if self.auto_trade:
                        trade_result = self._execute_paper_trade(decision)
                        if not trade_result.get("ok"):
                            err = trade_result.get("error", "unknown")
                            plan["errors"].append(
                                f"模拟交易失败 {h['stock_code']}: {err}"
                            )
            except Exception as e:
                plan["errors"].append(f"分析{h['stock_code']}失败: {e}")
                logger.warning("分析持仓 %s 失败: %s", h["stock_code"], e)

        # Step 7: 深度分析 — 观察名单Top N（轮换）
        watchlist = self.scanner.get_watchlist()
        to_analyze = self._select_analysis_batch(watchlist, self.daily_batch)
        for stock in to_analyze:
            try:
                analysis = self._run_analysis(stock["stock_code"], fast_mode=fast_mode)
                if analysis:
                    analysis["ticker"] = stock["stock_code"]
                    analysis["stock_name"] = stock.get("stock_name", "")
                    decision = self.engine.decide(
                        analysis_result=analysis,
                        current_holding=None,
                        account=account,
                        market_state=market_state,
                        holding_count=len(holdings),
                    )
                    if decision.action != "WATCH":
                        plan["actions"].append(decision.to_dict())
                        if self.auto_trade:
                            trade_result = self._execute_paper_trade(decision)
                            if not trade_result.get("ok"):
                                err = trade_result.get("error", "unknown")
                                plan["errors"].append(
                                    f"模拟交易失败 {stock['stock_code']}: {err}"
                                )
                    # 标记已分析
                    self.scanner.mark_analyzed(stock["stock_code"])
            except Exception as e:
                plan["errors"].append(f"分析{stock['stock_code']}失败: {e}")
                logger.warning("分析观察股 %s 失败: %s", stock["stock_code"], e)

        # Step 8: 持仓状态更新
        plan["holdings_status"] = self.portfolio.get_holdings()
        plan["account"] = self.portfolio.get_account()
        plan["watchlist"] = watchlist[:10]

        # Step 9: 生成摘要
        plan["summary"] = self._generate_summary(plan)

        # Step 10: 保存
        self._save_plan(plan)
        self._save_markdown_report(plan)

        logger.info("═══ 每日交易计划生成完成 ═══")
        logger.info("操作建议: %d项, 持仓: %d只",
                    len(plan["actions"]), len(plan["holdings_status"]))

        return plan

    def get_today_plan(self) -> dict | None:
        """获取今日交易计划。"""
        today = datetime.now().strftime("%Y-%m-%d")
        conn = sqlite3.connect(self.db_path)
        row = conn.execute(
            "SELECT plan_json FROM daily_plans WHERE id = ?", (today,)
        ).fetchone()
        conn.close()
        if row:
            result: dict[str, Any] = json.loads(row[0])
            return result
        return None

    def get_plan_history(self, limit: int = 30) -> list[dict]:
        """获取历史计划。"""
        conn = sqlite3.connect(self.db_path)
        rows = conn.execute(
            "SELECT id, date, actions_count, buy_count, sell_count, hold_count, created_at "
            "FROM daily_plans ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        conn.close()
        return [
            {
                "id": r[0], "date": r[1], "actions_count": r[2],
                "buy_count": r[3], "sell_count": r[4], "hold_count": r[5],
                "created_at": r[6],
            }
            for r in rows
        ]

    def _run_analysis(self, ticker: str, fast_mode: bool = True) -> dict | None:
        """调用LangGraph工作流分析单只股票。"""
        try:
            from core.llm_client import LLMClient
            from core.state import make_initial_state
            from graph.trading_graph import build_trading_graph

            config = self.config
            api_key = config.get("llm.deepseek.api_key", "")
            if not api_key:
                import os
                api_key = os.getenv("DEEPSEEK_API_KEY", "")
            if not api_key:
                logger.warning("未配置API Key，跳过LLM分析: %s", ticker)
                return None

            llm_client = LLMClient(config)
            graph = build_trading_graph(llm_client)

            state = make_initial_state(ticker=ticker, mode="fast" if fast_mode else "full")
            state["config"] = {
                "debate": {
                    "investment": {"max_rounds": 1 if fast_mode else 2},
                    "risk": {"max_rounds": 1 if fast_mode else 2},
                },
                "features": {"enable_masters": False},
            }

            date_tag = datetime.now().strftime("%Y%m%d")
            thread_config = {"configurable": {"thread_id": f"daily-{ticker}-{date_tag}"}}
            final_state = graph.invoke(state, config=thread_config)

            return self._parse_analysis(final_state, ticker)
        except Exception as e:
            logger.error("分析 %s 失败: %s", ticker, e)
            return None

    @staticmethod
    def _parse_analysis(final_state: dict, ticker: str) -> dict:
        """从LangGraph最终状态解析分析结果。"""
        import re

        result: dict = {"ticker": ticker, "action": "Hold", "confidence": 50}

        pm_report = final_state.get("portfolio_manager_report", "")
        if pm_report:
            try:
                # Handle nested JSON by finding the outermost balanced braces
                flat = pm_report.replace("\n", " ")
                # Try finding a JSON object that may contain nested braces
                start = flat.find("{")
                if start >= 0:
                    depth = 0
                    end = -1
                    for i, ch in enumerate(flat[start:], start):
                        if ch == "{":
                            depth += 1
                        elif ch == "}":
                            depth -= 1
                            if depth == 0:
                                end = i + 1
                                break
                    if end > start:
                        decision = json.loads(flat[start:end])
                        result["action"] = decision.get("rating", "Hold")
                        result["confidence"] = decision.get("confidence", 50)
                        result["entry_price"] = decision.get("entry_price")
                        result["stop_loss"] = decision.get("stop_loss")
                        result["take_profit"] = decision.get("take_profit")
                        result["position_pct"] = decision.get("position_pct", 5.0)
                        result["executive_summary"] = decision.get("executive_summary", "")
            except (json.JSONDecodeError, AttributeError):
                result["thesis"] = pm_report[:500]

        result.setdefault("thesis", result.get("executive_summary", "分析完成"))
        return result

    def _select_analysis_batch(self, watchlist: list[dict], max_count: int) -> list[dict]:
        """轮换选择今日分析的观察名单股票。优先: 从未分析 > 最久未分析。"""
        # 过滤掉已是持仓的
        holdings_codes = {h["stock_code"] for h in self.portfolio.get_holdings()}
        candidates = [w for w in watchlist if w["stock_code"] not in holdings_codes]

        # 从未分析过的优先
        never_analyzed = [w for w in candidates if not w.get("last_analysis_date")]
        analyzed = [w for w in candidates if w.get("last_analysis_date")]
        analyzed.sort(key=lambda w: w.get("last_analysis_date", ""))

        return (never_analyzed + analyzed)[:max_count]

    def _execute_paper_trade(self, decision: PositionDecision) -> dict:
        """根据决策执行模拟交易，返回执行结果。"""
        try:
            if decision.action == "INITIAL_BUY" and decision.target_shares > 0:
                return self.portfolio.buy(
                    decision.stock_code, decision.stock_name,
                    decision.target_price or decision.current_price,
                    decision.target_shares, decision.reasoning,
                )
            if decision.action == "ADD" and decision.target_shares > 0:
                return self.portfolio.add(
                    decision.stock_code, decision.stock_name,
                    decision.target_price or decision.current_price,
                    decision.target_shares, decision.reasoning,
                )
            if decision.action == "REDUCE" and decision.target_shares > 0:
                return self.portfolio.reduce(
                    decision.stock_code,
                    decision.target_price or decision.current_price,
                    decision.target_shares, decision.reasoning,
                )
            if decision.action == "CLEAR":
                return self.portfolio.clear(
                    decision.stock_code,
                    decision.target_price or decision.current_price,
                    decision.reasoning,
                )
        except Exception as e:
            logger.warning("模拟交易执行失败 %s: %s", decision.stock_code, e)
            return {"ok": False, "error": str(e)}
        return {"ok": True, "skipped": True}

    @staticmethod
    def _generate_summary(plan: dict) -> str:
        """生成文字摘要。"""
        actions = plan.get("actions", [])
        buy_count = sum(1 for a in actions if a["action"] in ("INITIAL_BUY", "ADD"))
        sell_count = sum(1 for a in actions if a["action"] in ("REDUCE", "CLEAR"))
        hold_count = sum(1 for a in actions if a["action"] == "HOLD")
        watch_count = sum(1 for a in actions if a["action"] == "WATCH")

        account = plan.get("account", {})
        total_assets = account.get("total_assets", 0)
        pnl = account.get("pnl", 0)
        pnl_pct = account.get("pnl_pct", 0)
        market_state = plan.get("market_state", "NEUTRAL")

        summary = (
            f"市场状态: {market_state}。"
            f"总资产¥{total_assets:,.0f}，盈亏¥{pnl:,.0f}({pnl_pct:+.1f}%)。"
            f"今日操作: 买入{buy_count}笔，卖出{sell_count}笔，"
            f"持有{hold_count}只，观察{watch_count}只。"
        )
        if plan.get("errors"):
            summary += f" 错误{len(plan['errors'])}项。"
        return summary

    def _save_plan(self, plan: dict):
        """保存到daily_plans表。"""
        today = plan.get("date", datetime.now().strftime("%Y-%m-%d"))
        actions = plan.get("actions", [])
        buy_count = sum(1 for a in actions if a["action"] in ("INITIAL_BUY", "ADD"))
        sell_count = sum(1 for a in actions if a["action"] in ("REDUCE", "CLEAR"))
        hold_count = sum(1 for a in actions if a["action"] == "HOLD")

        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "INSERT OR REPLACE INTO daily_plans "
            "(id, date, plan_json, actions_count, buy_count, sell_count, hold_count) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (today, today, json.dumps(plan, ensure_ascii=False, default=str),
             len(actions), buy_count, sell_count, hold_count),
        )
        conn.commit()
        conn.close()
        logger.info("计划已保存到数据库: %s", today)

    def _save_markdown_report(self, plan: dict):
        """生成Markdown报告。"""
        reports_dir = Path(self.config.get("runtime.reports_dir", "reports"))
        reports_dir.mkdir(parents=True, exist_ok=True)
        today = plan.get("date", datetime.now().strftime("%Y-%m-%d"))
        filepath = reports_dir / f"daily_plan_{today}.md"

        md = f"# 每日交易计划 — {today}\n\n"
        md += f"**市场状态**: {plan.get('market_state', 'N/A')}\n\n"

        account = plan.get("account", {})
        if account:
            md += "## 账户概览\n\n"
            md += f"- 总资产: ¥{account.get('total_assets', 0):,.2f}\n"
            md += f"- 现金: ¥{account.get('cash', 0):,.2f}\n"
            md += f"- 持仓市值: ¥{account.get('holdings_value', 0):,.2f}\n"
            md += f"- 盈亏: ¥{account.get('pnl', 0):,.2f} ({account.get('pnl_pct', 0):+.1f}%)\n"
            md += f"- 持仓数: {account.get('holding_count', 0)}\n\n"

        actions = plan.get("actions", [])
        if actions:
            md += "## 今日操作建议\n\n"
            for a in actions:
                action_emoji = {
                    "INITIAL_BUY": "📈", "ADD": "⬆", "REDUCE": "⬇",
                    "CLEAR": "🔴", "HOLD": "⚪", "WATCH": "👀",
                }.get(a["action"], "•")
                md += f"### {action_emoji} {a['action']} — {a['stock_code']} {a['stock_name']}\n\n"
                if a.get("target_shares"):
                    md += f"- 建议股数: {a['target_shares']}股\n"
                if a.get("target_price"):
                    md += f"- 建议价格: ¥{a['target_price']:.2f}\n"
                if a.get("stop_loss"):
                    md += f"- 止损: ¥{a['stop_loss']:.2f}\n"
                if a.get("take_profit"):
                    md += f"- 止盈: ¥{a['take_profit']:.2f}\n"
                md += f"- 置信度: {a.get('confidence', 0)}%\n"
                md += f"- 理由: {a.get('reasoning', 'N/A')}\n\n"

        holdings = plan.get("holdings_status", [])
        if holdings:
            md += "## 当前持仓\n\n"
            md += "| 代码 | 名称 | 持仓 | 成本 | 现价 | 盈亏% |\n"
            md += "|------|------|------|------|------|-------|\n"
            for h in holdings:
                md += (
                    f"| {h['stock_code']} | {h['stock_name']} | "
                    f"{h['shares']} | ¥{h['avg_cost']:.2f} | "
                    f"¥{h.get('current_price', 0):.2f} | "
                    f"{h.get('pnl_pct', 0):+.1f}% |\n"
                )
            md += "\n"

        watchlist = plan.get("watchlist", [])
        if watchlist:
            md += "## 观察名单\n\n"
            md += "| 代码 | 名称 | 评分 | 上次分析 |\n"
            md += "|------|------|------|----------|\n"
            for w in watchlist:
                md += (
                    f"| {w['stock_code']} | {w.get('stock_name', '')} | "
                    f"{w.get('score', 0):.1f} | {w.get('last_analysis_date', '未分析')} |\n"
                )
            md += "\n"

        md += f"\n---\n*摘要: {plan.get('summary', '')}*\n"

        filepath.write_text(md, encoding="utf-8")
        logger.info("Markdown报告已保存: %s", filepath)
