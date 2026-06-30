"""ReAct模式Agent工厂 — LLM自主选择工具调用。

Phase 8.3: 对标 TradingAgents/FinRobot 的 ReAct (Reasoning + Acting) 架构。
LLM通过 OpenAI function calling 自主决定调用哪些工具获取数据，
而非被动接收注入的prompt数据。

两种模式:
  - "inject" (默认): 数据注入模式，由代码决定给LLM什么数据
  - "react": ReAct模式，LLM自主调用工具获取数据

向后兼容: 现有Agent无需修改，默认使用inject模式。
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import Any

from core.llm_client import LLMClient
from core.state import AgentState

logger = logging.getLogger("ashare-x.agents.react")

# ── 工具定义（OpenAI function calling格式） ──

TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_stock_data",
            "description": "获取A股K线数据和技术指标(MA/MACD/RSI/BOLL)",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "6位股票代码，如 600519",
                    },
                    "days": {
                        "type": "integer",
                        "description": "获取最近N天数据，默认120",
                        "default": 120,
                    },
                },
                "required": ["code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_fundamentals",
            "description": "获取基本面数据(PE/PB/ROE/营收/利润等)",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "6位股票代码"},
                },
                "required": ["code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_news",
            "description": "获取个股相关新闻",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "6位股票代码"},
                    "days": {
                        "type": "integer",
                        "description": "获取最近N天新闻",
                        "default": 7,
                    },
                },
                "required": ["code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_global_news",
            "description": "获取宏观经济新闻(央视新闻联播财经摘要)",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_social_sentiment",
            "description": "获取情绪数据(龙虎榜/北向资金/换手率/资金流向)",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "6位股票代码"},
                },
                "required": ["code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_market_breadth",
            "description": "获取市场广度数据(全市场涨跌家数/涨停跌停数)",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]


def _execute_tool(name: str, args: dict[str, Any]) -> str:  # noqa: PLR0911  # 工具分发返回多
    """执行工具调用，返回结果文本。"""
    try:
        if name == "get_stock_data":
            from tools.stock_data import get_stock_data

            data = get_stock_data(args.get("code", ""), days=args.get("days", 120))
            kline = data.get("kline", [])
            indicators = data.get("indicators", {})
            kline_list = kline if isinstance(kline, list) else []
            recent = kline_list[-5:] if len(kline_list) > 5 else kline_list
            kline_text = "; ".join(
                f"{r.get('trade_date', '')}: 收{r.get('close', 0):.2f}"
                for r in recent
            ) if recent else "无数据"
            ind_text = json.dumps(indicators, ensure_ascii=False) if indicators else "{}"
            return f"K线(最近5日): {kline_text}\n指标: {ind_text}"

        if name == "get_fundamentals":
            from tools.fundamentals import get_fundamentals

            result = get_fundamentals(args.get("code", ""))
            return json.dumps(result, ensure_ascii=False, default=str) if result else "无基本面数据"

        if name == "get_news":
            from tools.news_search import get_news

            news = get_news(args.get("code", ""), days=args.get("days", 7))
            if not news:
                return "暂无新闻"
            titles = [f"[{n.get('date', '')}] {n.get('title', '')[:50]}" for n in news[:10]]
            return "\n".join(titles)

        if name == "get_global_news":
            from tools.news_search import get_global_news

            news = get_global_news()
            if not news:
                return "暂无宏观新闻"
            titles = [f"[{n.get('date', '')}] {n.get('title', '')[:50]}" for n in news[:5]]
            return "\n".join(titles)

        if name == "get_social_sentiment":
            from tools.social_sentiment import get_social_sentiment

            result = get_social_sentiment(args.get("code", ""))
            return json.dumps(result, ensure_ascii=False, default=str) if result else "无情绪数据"

        if name == "get_market_breadth":
            from tools.social_sentiment import get_market_breadth

            result = get_market_breadth()
            if result:
                return json.dumps(result, ensure_ascii=False, default=str)
            return "无市场广度数据"

        return f"未知工具: {name}"
    except Exception as e:
        logger.warning("工具调用失败 %s(%s): %s", name, args, e)
        return f"工具调用失败: {e}"


def run_react_agent(
    system_prompt: str,
    llm_client: LLMClient,
    ticker: str,
    agent_name: str = "unknown",
    prior_reports: str = "",
    memory_text: str = "",
    max_tool_calls: int = 5,
) -> str:
    """ReAct模式：LLM自主调用工具获取数据，再生成分析。

    执行流程:
    1. 给LLM工具定义 + 初始prompt（含前序报告和记忆）
    2. LLM返回tool_calls，执行对应工具
    3. 将工具结果反馈给LLM，重复2-3直到LLM生成最终文本
    4. 最多循环max_tool_calls次防止无限调用

    Args:
        system_prompt: Agent系统提示词
        llm_client: LLM客户端
        ticker: 股票代码
        agent_name: Agent名称
        prior_reports: 前序Agent报告文本
        memory_text: 分层记忆文本
        max_tool_calls: 最大工具调用次数

    Returns:
        LLM最终分析结果文本
    """
    # 构建初始消息
    user_content = f"请分析股票: {ticker}"
    if prior_reports:
        user_content += f"\n\n{prior_reports}"
    if memory_text:
        user_content += f"\n\n{memory_text}"
    user_content += (
        "\n\n你可以使用以下工具获取数据。请先调用需要的工具，"
        "获取数据后给出你的分析结论。"
    )

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]

    tool_call_count = 0

    while tool_call_count < max_tool_calls:
        try:
            # 调用LLM（带工具定义）
            provider = llm_client.config.get("llm.quick_think.provider", "deepseek")
            model = llm_client.config.get("llm.quick_think.model", "deepseek-chat")
            # Fallback to the config keys that llm_client.complete actually uses
            if not llm_client.config.get("llm.quick_think.model"):
                provider = llm_client.config.get("llm.quick.provider", provider)
                model = llm_client.config.get("llm.quick.model", model)
            client = llm_client._get_client(provider)

            response = client.chat.completions.create(
                model=model,
                messages=messages,
                tools=TOOL_DEFINITIONS,
            )

            message = response.choices[0].message

            # 如果LLM没有调用工具，返回最终文本
            if not message.tool_calls:
                logger.info(
                    "ReAct Agent %s 完成，%d次工具调用",
                    agent_name, tool_call_count,
                )
                return message.content or ""

            # 处理工具调用
            messages.append({
                "role": "assistant",
                "content": message.content or "",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in message.tool_calls
                ],
            })

            # 执行每个工具调用
            for tc in message.tool_calls:
                tool_name = tc.function.name
                try:
                    tool_args = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    tool_args = {}

                logger.info(
                    "ReAct工具调用 %s.%s(%s)",
                    agent_name, tool_name, tool_args,
                )

                result = _execute_tool(tool_name, tool_args)

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result[:2000],
                })

                # 记录token消耗
                usage = response.usage
                if usage:
                    llm_client.counter.record(
                        agent_name, ticker, usage.total_tokens
                    )

                tool_call_count += 1

                if tool_call_count >= max_tool_calls:
                    messages.append({
                        "role": "user",
                        "content": "已达到工具调用上限，请基于已有数据给出最终分析。",
                    })
                    break

        except Exception as e:
            logger.error("ReAct Agent %s 执行失败: %s", agent_name, e)
            # 降级到无工具模式
            break

    # 最终调用（不带工具）
    try:
        if "client" not in dir() or client is None:
            provider = llm_client.config.get("llm.quick.provider", "deepseek")
            model = llm_client.config.get("llm.quick.model", "deepseek-chat")
            client = llm_client._get_client(provider)
        response = client.chat.completions.create(
            model=model,
            messages=messages,
        )
        usage = response.usage
        if usage:
            llm_client.counter.record(agent_name, ticker, usage.total_tokens)
        return response.choices[0].message.content or ""
    except Exception as e:
        logger.error("ReAct Agent最终调用失败: %s", e)
        return f"分析失败: {e}"


def create_react_agent(
    agent_name: str,
    system_prompt: str,
    llm_client: LLMClient,
) -> Callable[[AgentState], dict]:
    """创建ReAct模式Agent节点函数。

    与create_agent()接口一致，但LLM可自主调用工具。
    """

    def react_node(state: AgentState) -> dict:
        ticker = state.get("ticker", "")

        # 收集前序报告和记忆（复用base.py的逻辑）
        from agents.base import _gather_memory, _gather_prior_reports, _gather_rag_context

        prior_reports = _gather_prior_reports(state, agent_name)
        memory_text = _gather_memory(ticker)
        rag_text = _gather_rag_context(ticker, agent_name)

        combined_memory = ""
        if memory_text:
            combined_memory += memory_text + "\n"
        if rag_text:
            combined_memory += rag_text

        # 执行ReAct循环
        result = run_react_agent(
            system_prompt=system_prompt,
            llm_client=llm_client,
            ticker=ticker,
            agent_name=agent_name,
            prior_reports=prior_reports,
            memory_text=combined_memory,
        )

        return {f"{agent_name}_report": result}

    return react_node
