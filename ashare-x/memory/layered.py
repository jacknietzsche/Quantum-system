"""FinMem式分层记忆系统。

Phase 8.2: 对标 FinMem (ICLR 2024) 的三层记忆架构。
    - 短期记忆: 当前分析会话的AgentState（由LangGraph checkpointer管理）
    - 中期记忆: 最近N次同股票分析结论（SQLite，DecisionLog已有）
    - 长期记忆: 向量库中的历史研报/新闻embedding（chromadb，VectorStore已有）

MemoryManager 统一三层记忆的读取和注入，替代碎片化的 injection.py。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from memory.decision_log import DecisionLog
    from memory.vectorstore import VectorStore

logger = logging.getLogger("ashare-x.memory.layered")

_memory_manager: MemoryManager | None = None


class MemoryManager:
    """三层记忆管理器（FinMem架构）。"""

    def __init__(
        self,
        short_term: dict[str, Any] | None = None,
        mid_term_limit: int = 5,
        long_term_limit: int = 3,
    ):
        self._short_term: dict[str, Any] = short_term or {}
        self._mid_term_limit = mid_term_limit
        self._long_term_limit = long_term_limit

        # 延迟初始化持久化组件
        self._decision_log: DecisionLog | None = None
        self._vectorstore: VectorStore | None = None

    def _ensure_decision_log(self):
        if self._decision_log is None:
            try:
                from memory.decision_log import DecisionLog

                self._decision_log = DecisionLog()
            except Exception:
                self._decision_log = None

    def _ensure_vectorstore(self):
        if self._vectorstore is None:
            try:
                from memory.vectorstore import get_vectorstore

                self._vectorstore = get_vectorstore()
            except Exception:
                self._vectorstore = None

    # ── 短期记忆：当前分析会话状态 ──

    def set_short_term(self, state: dict[str, Any]):
        """更新短期记忆（当前AgentState的引用）。"""
        self._short_term = state

    def get_short_term(self) -> dict[str, Any]:
        """获取短期记忆。"""
        return self._short_term

    def short_term_summary(self) -> str:
        """从短期记忆提取关键信息摘要。"""
        if not self._short_term:
            return ""

        parts: list[str] = []
        ticker = self._short_term.get("ticker", "")
        if ticker:
            parts.append(f"当前分析: {ticker}")

        # 已有分析师信号
        signals = self._short_term.get("analyst_signals", {})
        if signals:
            bull = sum(1 for s in signals.values() if s.get("signal") == "bullish")
            bear = sum(1 for s in signals.values() if s.get("signal") == "bearish")
            parts.append(f"已收集信号: 看多{bull} | 看空{bear}")

        # 已完成的报告数量
        reports_done = sum(
            1 for k, v in self._short_term.items()
            if k.endswith("_report") and isinstance(v, str) and v
        )
        if reports_done:
            parts.append(f"已完成Agent: {reports_done}")

        # 辩论进度
        inv_rounds = self._short_term.get("investment_debate_rounds", 0)
        risk_rounds = self._short_term.get("risk_debate_rounds", 0)
        if inv_rounds or risk_rounds:
            parts.append(f"辩论进度: 多空{inv_rounds}轮, 风险{risk_rounds}轮")

        return "\n".join(parts) if parts else ""

    # ── 中期记忆：最近N次分析结论 ──

    def get_mid_term(self, ticker: str) -> str:
        """获取中期记忆（历史决策日志）。"""
        self._ensure_decision_log()
        if not self._decision_log:
            return ""

        history = self._decision_log.get_history(ticker, limit=self._mid_term_limit)
        if not history:
            return ""

        lines = [f"## 中期记忆（最近{len(history)}次决策）"]
        for h in history:
            action = h.get("action", "N/A")
            confidence = h.get("confidence", 0)
            date = h.get("date", h.get("created_at", "N/A"))
            thesis = (h.get("thesis") or "")[:100]
            reflection = h.get("reflection", "")

            lines.append(f"- [{date}] {action} (置信度: {confidence}%)")
            if thesis:
                lines.append(f"  论据: {thesis}")
            if reflection:
                lines.append(f"  反思: {reflection[:100]}")

        return "\n".join(lines)

    # ── 长期记忆：向量库语义检索 ──

    def get_long_term(self, ticker: str, query: str = "") -> str:
        """获取长期记忆（向量库历史研报检索）。"""
        self._ensure_vectorstore()
        if not self._vectorstore or not self._vectorstore.available:
            return ""

        search_query = query or f"{ticker} 分析报告"
        results = self._vectorstore.search(
            query=search_query,
            n_results=self._long_term_limit,
            ticker=ticker,
            doc_type="analysis",
        )

        if not results:
            return ""

        lines = [f"## 长期记忆（向量库检索 {len(results)}条）"]
        for i, r in enumerate(results, 1):
            content = r["content"][:300]
            date = r["metadata"].get("date", "")
            relevance = 1 - r.get("distance", 0)
            lines.append(f"### 参考{i} ({date}, 相关度: {relevance:.0%})")
            lines.append(content)
            lines.append("")

        return "\n".join(lines)

    # ── 统一注入接口 ──

    def inject_all(self, ticker: str, agent_name: str = "") -> str:
        """统一注入三层记忆到Agent prompt。

        Args:
            ticker: 股票代码
            agent_name: 当前Agent名称

        Returns:
            合并的记忆文本（Markdown格式）
        """
        parts: list[str] = []

        # 短期记忆
        short = self.short_term_summary()
        if short:
            parts.append(f"## 短期记忆（当前会话）\n{short}")

        # 中期记忆
        mid = self.get_mid_term(ticker)
        if mid:
            parts.append(mid)

        # 长期记忆
        long_term = self.get_long_term(ticker, query=f"{ticker} {agent_name}")
        if long_term:
            parts.append(long_term)

        return "\n\n".join(parts)

    # ── 记忆写入接口 ──

    def record_decision(
        self,
        ticker: str,
        action: str,
        confidence: float,
        thesis: str = "",
        date: str = "",
    ):
        """记录决策到中期记忆（DecisionLog）。"""
        self._ensure_decision_log()
        if not self._decision_log:
            return

        try:
            self._decision_log.add_entry(
                ticker=ticker,
                date=date,
                action=action,
                confidence=confidence,
                thesis=thesis,
            )
        except Exception as e:
            logger.warning("记录决策失败: %s", e)

    def store_analysis(self, ticker: str, report_text: str, date: str = ""):
        """存储分析报告到长期记忆（向量库）。"""
        self._ensure_vectorstore()
        if not self._vectorstore or not self._vectorstore.available:
            return

        try:
            self._vectorstore.add_report(
                ticker=ticker,
                report_text=report_text,
                report_type="analysis",
                date=date,
            )
        except Exception as e:
            logger.warning("存储分析报告失败: %s", e)

    def store_news(self, ticker: str, title: str, content: str, date: str = ""):
        """存储新闻到长期记忆。"""
        self._ensure_vectorstore()
        if not self._vectorstore or not self._vectorstore.available:
            return

        try:
            self._vectorstore.add_news(
                ticker=ticker,
                title=title,
                content=content,
                date=date,
            )
        except Exception as e:
            logger.warning("存储新闻失败: %s", e)

    def stats(self) -> dict[str, Any]:
        """返回记忆系统统计信息。"""
        self._ensure_vectorstore()
        vector_count = 0
        if self._vectorstore and self._vectorstore.available:
            vector_count = self._vectorstore.count()

        return {
            "short_term_active": bool(self._short_term),
            "mid_term_available": self._decision_log is not None,
            "long_term_available": self._vectorstore is not None
            and self._vectorstore.available,
            "long_term_count": vector_count,
        }


def get_memory_manager() -> MemoryManager:
    """获取全局MemoryManager实例（单例）。"""
    global _memory_manager  # noqa: PLW0603
    if _memory_manager is None:
        _memory_manager = MemoryManager()
    return _memory_manager
