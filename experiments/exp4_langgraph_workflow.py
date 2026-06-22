# -*- coding: utf-8 -*-
"""
实验4: LangGraph工作流验证
目标: 验证LangGraph构建多Agent工作流的可行性
"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from typing import TypedDict, Annotated, Literal
from langgraph.graph import StateGraph, START, END
import time

print("=" * 60)
print("实验4: LangGraph工作流验证")
print("=" * 60)

# ========== 实验4.1: 简单线性工作流 ==========
print("\n" + "=" * 60)
print("实验4.1: 简单线性工作流")
print("=" * 60)

try:
    class SimpleState(TypedDict):
        ticker: str
        market_report: str
        investment_plan: str
        trading_decision: str

    def market_analyst(state: SimpleState) -> dict:
        ticker = state["ticker"]
        return {"market_report": f"{ticker} 技术面分析报告：趋势向上，MA5>MA20"}

    def investment_researcher(state: SimpleState) -> dict:
        report = state["market_report"]
        return {"investment_plan": f"基于{report}，建议买入"}

    def risk_manager(state: SimpleState) -> dict:
        plan = state["investment_plan"]
        return {"trading_decision": f"风险评估通过：{plan}"}

    graph = StateGraph(SimpleState)
    graph.add_node("market_analyst", market_analyst)
    graph.add_node("investment_researcher", investment_researcher)
    graph.add_node("risk_manager", risk_manager)

    graph.add_edge(START, "market_analyst")
    graph.add_edge("market_analyst", "investment_researcher")
    graph.add_edge("investment_researcher", "risk_manager")
    graph.add_edge("risk_manager", END)

    app = graph.compile()

    result = app.invoke({"ticker": "600519"})
    print(f"输入: 600519")
    print(f"市场报告: {result['market_report']}")
    print(f"投资计划: {result['investment_plan']}")
    print(f"交易决策: {result['trading_decision']}")
    print("[PASS] 简单线性工作流成功")
except Exception as e:
    print(f"[FAIL] 简单线性工作流失败: {e}")

# ========== 实验4.2: 条件分支工作流 ==========
print("\n" + "=" * 60)
print("实验4.2: 条件分支工作流")
print("=" * 60)

try:
    class ConditionalState(TypedDict):
        ticker: str
        signal: str
        confidence: int
        decision: str

    def analyst(state: ConditionalState) -> dict:
        ticker = state["ticker"]
        if "600519" in ticker:
            return {"signal": "bullish", "confidence": 80}
        else:
            return {"signal": "bearish", "confidence": 60}

    def bull_action(state: ConditionalState) -> dict:
        return {"decision": f"买入 {state['ticker']}"}

    def bear_action(state: ConditionalState) -> dict:
        return {"decision": f"卖出 {state['ticker']}"}

    def route_decision(state: ConditionalState) -> Literal["bull", "bear"]:
        if state["signal"] == "bullish":
            return "bull"
        return "bear"

    graph = StateGraph(ConditionalState)
    graph.add_node("analyst", analyst)
    graph.add_node("bull_action", bull_action)
    graph.add_node("bear_action", bear_action)

    graph.add_edge(START, "analyst")
    graph.add_conditional_edges(
        "analyst",
        route_decision,
        {"bull": "bull_action", "bear": "bear_action"}
    )
    graph.add_edge("bull_action", END)
    graph.add_edge("bear_action", END)

    app = graph.compile()

    result1 = app.invoke({"ticker": "600519"})
    print(f"600519 -> 信号: {result1['signal']}, 决策: {result1['decision']}")

    result2 = app.invoke({"ticker": "000001"})
    print(f"000001 -> 信号: {result2['signal']}, 决策: {result2['decision']}")

    print("[PASS] 条件分支工作流成功")
except Exception as e:
    print(f"[FAIL] 条件分支工作流失败: {e}")

# ========== 实验4.3: 循环辩论工作流 ==========
print("\n" + "=" * 60)
print("实验4.3: 循环辩论工作流（模拟多空辩论）")
print("=" * 60)

try:
    import operator

    class DebateState(TypedDict):
        ticker: str
        round: int
        max_rounds: int
        bull_argument: str
        bear_argument: str
        history: Annotated[list[str], operator.add]

    def bull_researcher(state: DebateState) -> dict:
        round_num = state["round"] + 1
        arg = f"Round {round_num}: 看涨论据 - 基本面强劲"
        return {
            "round": round_num,
            "bull_argument": arg,
            "history": [arg]
        }

    def bear_researcher(state: DebateState) -> dict:
        arg = f"Round {state['round']}: 看跌论据 - 估值偏高"
        return {
            "bear_argument": arg,
            "history": [arg]
        }

    def should_continue(state: DebateState) -> Literal["continue", "end"]:
        if state["round"] >= state["max_rounds"]:
            return "end"
        return "continue"

    graph = StateGraph(DebateState)
    graph.add_node("bull", bull_researcher)
    graph.add_node("bear", bear_researcher)

    graph.add_edge(START, "bull")
    graph.add_conditional_edges(
        "bull",
        should_continue,
        {"continue": "bear", "end": END}
    )
    graph.add_conditional_edges(
        "bear",
        should_continue,
        {"continue": "bull", "end": END}
    )

    app = graph.compile()

    result = app.invoke({
        "ticker": "600519",
        "round": 0,
        "max_rounds": 2,
        "bull_argument": "",
        "bear_argument": "",
        "history": []
    })

    print(f"辩论轮次: {result['round']}")
    print(f"辩论记录:")
    for msg in result["history"]:
        print(f"  - {msg}")
    print("[PASS] 循环辩论工作流成功")
except Exception as e:
    print(f"[FAIL] 循环辩论工作流失败: {e}")

# ========== 实验4.4: 并行执行 ==========
print("\n" + "=" * 60)
print("实验4.4: 并行执行验证")
print("=" * 60)

try:
    import asyncio

    async def parallel_analysts(state: dict) -> dict:
        async def market():
            await asyncio.sleep(0.1)
            return {"market": "技术面看涨"}

        async def fundamentals():
            await asyncio.sleep(0.1)
            return {"fundamentals": "基本面良好"}

        async def news():
            await asyncio.sleep(0.1)
            return {"news": "新闻偏正面"}

        async def sentiment():
            await asyncio.sleep(0.1)
            return {"sentiment": "情绪偏乐观"}

        results = await asyncio.gather(
            market(), fundamentals(), news(), sentiment()
        )

        merged = {}
        for r in results:
            merged.update(r)
        return merged

    start = time.time()
    result = asyncio.run(parallel_analysts({}))
    elapsed = time.time() - start

    print(f"4个分析师并行结果: {result}")
    print(f"耗时: {elapsed:.3f}秒（4个0.1秒任务并行，理论最少0.1秒）")
    print("[PASS] 并行执行成功")
except Exception as e:
    print(f"[FAIL] 并行执行失败: {e}")

print("\n" + "=" * 60)
print("实验4完成")
print("=" * 60)
