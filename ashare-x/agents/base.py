"""Agent工厂基类。

设计依据: S04 §4.3, experiments exp4.1-exp4.3。
每个Agent通过工厂函数创建，接收LLM，返回节点函数。
Agent执行前自动获取相关数据注入prompt，确保LLM基于真实数据进行分析。
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from core.llm_client import LLMClient
from core.state import AgentState
from skills.engine import SkillEngine

logger = logging.getLogger(__name__)

# 全局SkillEngine单例（懒加载）
_skill_engine: SkillEngine | None = None


def _get_skill_engine() -> SkillEngine:
    """获取全局SkillEngine单例。"""
    global _skill_engine  # noqa: PLW0603
    if _skill_engine is None:
        _skill_engine = SkillEngine()
        _skill_engine.discover()
        logger.info(
            "SkillEngine已加载 %d 个技能: %s",
            len(_skill_engine.registry),
            list(_skill_engine.registry.keys()),
        )
    return _skill_engine

# 每个分析师Agent对应的数据获取函数
_DATA_PROVIDERS: dict[str, str] = {
    "market_analyst": "technical",
    "fundamentals_analyst": "fundamentals",
    "news_analyst": "news",
    "sentiment_analyst": "sentiment",
}

# 分析师Agent对应的量化预信号计算函数
_QUANT_SIGNALS: dict[str, str] = {
    "market_analyst": "technical",
    "fundamentals_analyst": "fundamentals",
    "news_analyst": "news",
    "sentiment_analyst": "sentiment",
}


def _gather_technical_data(ticker: str) -> str:
    """获取技术指标数据，格式化为文本。"""
    try:
        from tools.stock_data import get_stock_data

        data = get_stock_data(ticker, days=120)
        kline = data.get("kline")
        indicators = data.get("indicators")

        if not kline:
            return "⚠ 暂无K线数据"

        # 取最近5天K线
        recent = kline[-5:] if isinstance(kline, list) else []
        kline_text = "\n".join(
            f"  {row.get('trade_date', '')}: 开{row.get('open', 0):.2f} "
            f"高{row.get('high', 0):.2f} 低{row.get('low', 0):.2f} "
            f"收{row.get('close', 0):.2f} 量{row.get('volume', 0):.0f}"
            for row in recent
        )

        ind_text = ""
        if indicators:
            ind_text = (
                f"  MA5={indicators.get('ma5', 'N/A')}, "
                f"MA20={indicators.get('ma20', 'N/A')}, "
                f"MA60={indicators.get('ma60', 'N/A')}\n"
                f"  MACD={indicators.get('macd', 'N/A')}, "
                f"DIF={indicators.get('dif', 'N/A')}, "
                f"DEA={indicators.get('dea', 'N/A')}\n"
                f"  RSI14={indicators.get('rsi_14', 'N/A')}, "
                f"BOLL上轨={indicators.get('boll_upper', 'N/A')}, "
                f"BOLL下轨={indicators.get('boll_lower', 'N/A')}\n"
                f"  ATR14={indicators.get('atr_14', 'N/A')}"
            )

        return f"## 技术指标数据\n### 最近5日K线\n{kline_text}\n### 技术指标\n{ind_text}"
    except Exception as e:
        logger.warning("获取技术指标失败 %s: %s", ticker, e)
        return f"⚠ 技术指标数据获取失败: {e}"


def _gather_fundamentals_data(ticker: str) -> str:
    """获取基本面数据，格式化为文本。"""
    try:
        from tools.fundamentals import get_fundamentals

        fund = get_fundamentals(ticker)
        if not fund:
            return "⚠ 暂无基本面数据"

        lines = ["## 基本面数据"]
        if fund.get("stock_name"):
            lines.append(f"股票名称: {fund['stock_name']}")
        if fund.get("industry"):
            lines.append(f"行业: {fund['industry']}")

        lines.append("\n### 估值指标")
        lines.append(f"  PE(动态): {fund.get('pe_ratio', 'N/A')}")
        lines.append(f"  PB: {fund.get('pb_ratio', 'N/A')}")
        lines.append(f"  最新价: {fund.get('latest_price', 'N/A')}")
        lines.append(f"  涨跌幅: {fund.get('change_pct', 'N/A')}%")

        lines.append("\n### 盈利能力")
        lines.append(f"  ROE: {fund.get('roe', 'N/A')}%")
        lines.append(f"  ROA: {fund.get('roa', 'N/A')}%")
        lines.append(f"  毛利率: {fund.get('gross_margin', 'N/A')}%")
        lines.append(f"  净利率: {fund.get('net_margin', 'N/A')}%")

        lines.append("\n### 成长性")
        lines.append(f"  营收同比: {fund.get('revenue_yoy', 'N/A')}%")
        lines.append(f"  净利润同比: {fund.get('net_income_yoy', 'N/A')}%")

        lines.append("\n### 财务健康")
        lines.append(f"  资产负债率: {fund.get('debt_to_equity', 'N/A')}%")
        lines.append(f"  营收: {fund.get('revenue', 'N/A')}")
        lines.append(f"  净利润: {fund.get('net_income', 'N/A')}")

        if fund.get("report_period"):
            lines.append(f"\n报告期: {fund['report_period']}")

        return "\n".join(lines)
    except Exception as e:
        logger.warning("获取基本面数据失败 %s: %s", ticker, e)
        return f"⚠ 基本面数据获取失败: {e}"


def _gather_news_data(ticker: str) -> str:
    """获取新闻数据，格式化为文本。"""
    try:
        from tools.news_search import get_global_news, get_news

        news = get_news(ticker, days=7)
        global_news = get_global_news()

        lines = ["## 新闻数据"]

        if news:
            lines.append(f"\n### 个股新闻 ({len(news)}条)")
            for n in news[:10]:
                lines.append(
                    f"  [{n.get('date', '')}] {n.get('title', '')[:60]}"
                )
                if n.get("source"):
                    lines.append(f"    来源: {n['source']}")
        else:
            lines.append("\n### 个股新闻: 暂无")

        if global_news:
            lines.append(f"\n### 宏观新闻 ({len(global_news)}条)")
            for n in global_news[:5]:
                lines.append(
                    f"  [{n.get('date', '')}] {n.get('title', '')[:60]}"
                )

        return "\n".join(lines)
    except Exception as e:
        logger.warning("获取新闻数据失败 %s: %s", ticker, e)
        return f"⚠ 新闻数据获取失败: {e}"


def _gather_sentiment_data(ticker: str) -> str:
    """获取情绪数据，格式化为文本。"""
    try:
        from tools.social_sentiment import get_social_sentiment

        sent = get_social_sentiment(ticker)

        lines = ["## 情绪数据"]

        if sent.get("turnover_rate"):
            lines.append(f"  换手率: {sent['turnover_rate']}%")
        if sent.get("latest_price"):
            lines.append(f"  最新价: {sent.get('latest_price')}")
            lines.append(f"  涨跌幅: {sent.get('change_pct', 'N/A')}%")
        if sent.get("amount"):
            lines.append(f"  成交额: {sent.get('amount'):,.0f}")

        if sent.get("dragon_tiger"):
            dt = sent["dragon_tiger"]
            lines.append("\n### 龙虎榜")
            lines.append(f"  日期: {dt.get('date', 'N/A')}")
            lines.append(f"  原因: {dt.get('reason', 'N/A')}")
            lines.append(f"  净买额: {dt.get('net_buy', 'N/A')}")
            lines.append(f"  买入额: {dt.get('buy_amount', 'N/A')}")
            lines.append(f"  卖出额: {dt.get('sell_amount', 'N/A')}")

        if sent.get("fund_flow"):
            ff = sent["fund_flow"]
            lines.append("\n### 资金流向")
            lines.append(f"  主力净流入: {ff.get('main_net_inflow', 'N/A')}")
            lines.append(f"  主力净占比: {ff.get('main_net_pct', 'N/A')}%")
            lines.append(f"  超大单净流入: {ff.get('super_large_net', 'N/A')}")
            lines.append(f"  大单净流入: {ff.get('large_net', 'N/A')}")
            lines.append(f"  中单净流入: {ff.get('medium_net', 'N/A')}")
            lines.append(f"  小单净流入: {ff.get('small_net', 'N/A')}")

        if sent.get("north_flow") is not None:
            lines.append(f"\n### 北向资金\n  持股: {sent['north_flow']}")

        return "\n".join(lines) if len(lines) > 1 else "⚠ 暂无情绪数据"
    except Exception as e:
        logger.warning("获取情绪数据失败 %s: %s", ticker, e)
        return f"⚠ 情绪数据获取失败: {e}"


_DATA_GATHERERS = {
    "technical": _gather_technical_data,
    "fundamentals": _gather_fundamentals_data,
    "news": _gather_news_data,
    "sentiment": _gather_sentiment_data,
}


def _compute_quant_signal(agent_name: str, data_text: str) -> str:
    """对数据文本做量化预分析，生成可解释的预信号。"""
    try:
        from agents.analysts.quant_signals import (
            compute_fundamental_signal,
            compute_news_signal,
            compute_sentiment_signal,
            compute_technical_signal,
        )

        signal_type = _QUANT_SIGNALS.get(agent_name)
        if signal_type == "technical":
            # 从文本中提取关键指标（简化解析）
            import re

            indicators: dict[str, float | None] = {}
            tech_keys = [
                "ma5", "ma20", "ma60", "macd", "dif", "dea",
                "rsi_14", "boll_upper", "boll_lower", "atr_14",
            ]
            for key in tech_keys:
                pattern = rf"{key.replace('_', r'[_/]?')}=([^,\n]+)"
                m = re.search(pattern, data_text, re.IGNORECASE)
                if m:
                    try:
                        val = m.group(1).strip()
                        indicators[key] = float(val) if val not in ("N/A", "None", "") else None
                    except (ValueError, TypeError):
                        indicators[key] = None
            sig = compute_technical_signal(indicators)
        elif signal_type == "fundamentals":
            fund: dict[str, float | None] = {}
            fund_keys = [
                "pe_ratio", "pb_ratio", "roe", "gross_margin",
                "revenue_yoy", "net_income_yoy", "debt_to_equity",
            ]
            for key in fund_keys:
                pattern = rf"{key.replace('_', ' ')}[:：]?\s*([0-9.\-]+)"
                m = re.search(pattern, data_text, re.IGNORECASE)
                if m:
                    try:
                        fund[key] = float(m.group(1))
                    except (ValueError, TypeError):
                        fund[key] = None
            sig = compute_fundamental_signal(fund)
        elif signal_type == "news":
            news: list[dict[str, str]] = []
            for line in data_text.splitlines():
                m = re.search(r"\[([^\]]+)\]\s*(.+)", line)
                if m:
                    news.append({"date": m.group(1), "title": m.group(2)})
            sig = compute_news_signal(news)
        elif signal_type == "sentiment":
            sent: dict[str, Any] = {}
            for key in ["主力净流入", "主力净占比", "北向资金"]:
                m = re.search(rf"{key}[:：]?\s*([0-9.\-]+)", data_text)
                if m:
                    try:
                        if key == "主力净流入":
                            sent.setdefault("fund_flow", {})["main_net_inflow"] = float(
                                m.group(1)
                            )
                        elif key == "主力净占比":
                            sent.setdefault("fund_flow", {})["main_net_pct"] = float(m.group(1))
                        elif key == "北向资金":
                            sent["north_flow"] = float(m.group(1))
                    except (ValueError, TypeError):
                        pass
            sig = compute_sentiment_signal(sent)
        else:
            return ""

        return (
            f"## 量化预信号\n"
            f"  方向: {sig['signal']}\n"
            f"  得分: {sig['confidence']}/100\n"
            f"  依据: {sig['reason']}"
        )
    except Exception as e:
        logger.debug("量化预信号计算失败 %s: %s", agent_name, e)
        return ""


def _gather_prior_reports(state: AgentState, agent_name: str) -> str:
    """从state中收集前序Agent的报告，注入给后续Agent。"""
    report_keys = {
        "market_analyst": "market_analyst_report",
        "fundamentals_analyst": "fundamentals_analyst_report",
        "news_analyst": "news_analyst_report",
        "sentiment_analyst": "sentiment_analyst_report",
        "bull_researcher": "bull_researcher_report",
        "bear_researcher": "bear_researcher_report",
        "research_manager": "research_manager_report",
        "trader": "trader_report",
        "aggressive_analyst": "aggressive_analyst_report",
        "conservative_analyst": "conservative_analyst_report",
        "neutral_analyst": "neutral_analyst_report",
    }

    # 根据当前Agent决定需要收集哪些前序报告
    report_order = [
        "market_analyst",
        "fundamentals_analyst",
        "news_analyst",
        "sentiment_analyst",
        "bull_researcher",
        "bear_researcher",
        "research_manager",
        "trader",
        "aggressive_analyst",
        "conservative_analyst",
        "neutral_analyst",
    ]

    # 收集当前Agent之前的所有报告
    found_current = False
    reports: list[str] = []
    for name in report_order:
        if name == agent_name:
            found_current = True
            break
        key = report_keys.get(name)
        if key and state.get(key):
            reports.append(f"### {name}\n{state[key]}")  # type: ignore[typeddict-item, literal-required, index]

    if not found_current or not reports:
        return ""

    return "## 前序Agent报告\n" + "\n\n".join(reports)


def _gather_memory(ticker: str) -> str:
    """获取历史决策记忆（兼容旧接口，代理到MemoryManager）。"""
    try:
        from memory.layered import get_memory_manager

        mm = get_memory_manager()
        return mm.get_mid_term(ticker)
    except Exception:
        return ""


def _gather_rag_context(ticker: str, agent_name: str) -> str:
    """从向量库检索相关历史分析（RAG，长期记忆）。"""
    try:
        from memory.layered import get_memory_manager

        mm = get_memory_manager()
        return mm.get_long_term(ticker, query=f"{ticker} {agent_name}")
    except Exception:
        return ""


def _gather_short_term_memory(state: AgentState) -> str:
    """从当前AgentState提取短期记忆摘要。"""
    try:
        from memory.layered import get_memory_manager

        mm = get_memory_manager()
        mm.set_short_term(dict(state))
        return mm.short_term_summary()
    except Exception:
        return ""


def create_agent(
    agent_name: str,
    system_prompt: str,
    llm_client: LLMClient,
    tools: list | None = None,
    mode: str = "inject",
) -> Callable[[AgentState], dict]:
    """
    Agent工厂：创建Agent节点函数。

    执行流程:
    1. 根据agent_name自动获取相关数据（技术指标/基本面/新闻/情绪）
    2. 收集前序Agent报告（供辩论/决策Agent使用）
    3. 注入分层记忆（短期+中期+长期）
    4. 构建数据增强的prompt
    5. 调用LLM获取分析结果

    Args:
        agent_name: Agent名称
        system_prompt: 系统提示词
        llm_client: LLM客户端
        tools: 可用工具列表
        mode: Agent模式
              "inject" (默认): 数据注入模式，代码决定给LLM什么数据
              "react": ReAct模式，LLM自主调用工具获取数据

    Returns:
        节点函数: (state) -> dict
    """

    # ReAct模式委托给react.py
    if mode == "react":
        from agents.react import create_react_agent

        return create_react_agent(agent_name, system_prompt, llm_client)

    def agent_node(state: AgentState) -> dict:
        ticker = state.get("ticker", "")

        # 构建数据增强的user message
        user_parts: list[str] = [f"请分析股票: {ticker}"]

        # 0. 注入投资技能（SkillEngine）
        effective_prompt = system_prompt
        try:
            engine = _get_skill_engine()
            skills = engine.get_for_agent(agent_name)
            if skills:
                skill_text = "\n\n".join(
                    f"## 投资技能: {s.metadata.name}\n{s.prompt[: s.metadata.max_tokens]}"
                    for s in skills
                )
                effective_prompt = f"{system_prompt}\n\n---\n# 可用投资技能\n{skill_text}"
        except Exception as e:
            logger.warning("技能注入失败 %s: %s", agent_name, e)

        # 1. 获取实时数据（仅分析师Agent需要）
        data_type = _DATA_PROVIDERS.get(agent_name)
        if data_type:
            gatherer = _DATA_GATHERERS.get(data_type)
            if gatherer:
                data_text = gatherer(ticker)
                user_parts.append(data_text)
                # 1.1 量化预信号：基于原始数据计算先验信号注入LLM
                quant_signal = _compute_quant_signal(agent_name, data_text)
                if quant_signal:
                    user_parts.append(quant_signal)

        # 2. 收集前序Agent报告（辩论/风险/决策Agent需要）
        prior_reports = _gather_prior_reports(state, agent_name)
        if prior_reports:
            user_parts.append(prior_reports)

        # 2.1 大师评审节点传入的汇总前序上下文
        master_context = state.get("master_prior_context", "")
        if master_context:
            user_parts.append(f"## 前序Agent报告摘要\n{master_context}")

        # 3. 分层记忆注入（短期+中期+长期）
        short_term = _gather_short_term_memory(state)
        if short_term:
            user_parts.append(f"## 短期记忆（当前会话）\n{short_term}")

        memory_text = _gather_memory(ticker)
        if memory_text:
            user_parts.append(memory_text)

        rag_text = _gather_rag_context(ticker, agent_name)
        if rag_text:
            user_parts.append(rag_text)

        user_content = "\n\n".join(user_parts)

        # 构建prompt
        messages = [
            {"role": "system", "content": effective_prompt},
            {"role": "user", "content": user_content},
        ]

        # 调用LLM
        try:
            response = llm_client.complete(
                messages=messages,
                agent_name=agent_name,
                ticker=ticker,
            )
            result: dict[str, Any] = {f"{agent_name}_report": response.content}
        except Exception as e:
            logger.error("Agent %s 执行失败: %s", agent_name, e)
            result = {f"{agent_name}_report": f"分析失败: {e}"}

        # 辩论节点自动递增轮次，防止条件路由无限循环
        if agent_name in ("bull_researcher", "bear_researcher"):
            result["investment_debate_rounds"] = (
                state.get("investment_debate_rounds", 0) + 1
            )
        elif agent_name in ("aggressive_analyst", "conservative_analyst", "neutral_analyst"):
            result["risk_debate_rounds"] = (
                state.get("risk_debate_rounds", 0) + 1
            )

        return result

    return agent_node
