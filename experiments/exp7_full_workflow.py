# -*- coding: utf-8 -*-
"""
实验7: LangGraph完整Agent工作流
目标: 验证 4分析师并行→消息清理→多空辩论→研究经理→交易员 的完整流程
"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import time
import asyncio
from typing import TypedDict, Annotated, Literal
from langgraph.graph import StateGraph, START, END
import operator

print("=" * 60)
print("实验7: LangGraph完整Agent工作流")
print("=" * 60)

# ========== 实验7.1: 完整多Agent工作流 ==========
print("\n" + "=" * 60)
print("实验7.1: 完整多Agent工作流（简化版）")
print("=" * 60)

try:
    class FullAgentState(TypedDict):
        ticker: str
        # 分析师输出
        market_report: str
        fundamentals_report: str
        news_report: str
        sentiment_report: str
        # 研究员输出
        bull_argument: str
        bear_argument: str
        debate_history: Annotated[list[str], operator.add]
        investment_plan: str
        # 交易员输出
        trading_proposal: str
        # 风险团队输出
        risk_assessment: str
        final_decision: str
        # 元数据
        iteration: int

    # 分析师节点（模拟LLM输出）
    def market_analyst(state: FullAgentState) -> dict:
        ticker = state["ticker"]
        return {"market_report": f"{ticker} 技术面：MA5>MA20，MACD金叉，RSI=55中性偏强"}

    def fundamentals_analyst(state: FullAgentState) -> dict:
        ticker = state["ticker"]
        return {"fundamentals_report": f"{ticker} 基本面：PE=25，ROE=18%，营收增长15%"}

    def news_analyst(state: FullAgentState) -> dict:
        ticker = state["ticker"]
        return {"news_report": f"{ticker} 新闻：政策利好，行业景气度上升"}

    def sentiment_analyst(state: FullAgentState) -> dict:
        ticker = state["ticker"]
        return {"sentiment_report": f"{ticker} 情绪：北向资金流入，融资余额增加"}

    # 消息清理节点
    def clear_messages_1(state: FullAgentState) -> dict:
        return {"iteration": 0}

    # 看涨研究员
    def bull_researcher(state: FullAgentState) -> dict:
        iteration = state.get("iteration", 0) + 1
        arg = f"Round {iteration}: 看涨 - {state['market_report']}，{state['fundamentals_report']}"
        return {
            "iteration": iteration,
            "bull_argument": arg,
            "debate_history": [arg]
        }

    # 看跌研究员
    def bear_researcher(state: FullAgentState) -> dict:
        arg = f"Round {state['iteration']}: 看跌 - 估值偏高，风险因素需关注"
        return {
            "bear_argument": arg,
            "debate_history": [arg]
        }

    # 辩论终止判断
    def should_continue_debate(state: FullAgentState) -> Literal["continue", "end"]:
        if state.get("iteration", 0) >= 2:
            return "end"
        return "continue"

    # 研究经理
    def research_manager(state: FullAgentState) -> dict:
        plan = f"综合辩论结果：看涨{state['bull_argument'][:30]}...，看跌{state['bear_argument'][:30]}...。建议：买入"
        return {"investment_plan": plan}

    # 交易员
    def trader(state: FullAgentState) -> dict:
        proposal = f"交易提案：{state['investment_plan'][:50]}...，入场价1500，止损1425，止盈1650，仓位5%"
        return {"trading_proposal": proposal}

    # 风险管理
    def risk_manager(state: FullAgentState) -> dict:
        assessment = f"风险评估：通过。{state['trading_proposal'][:50]}..."
        return {"risk_assessment": assessment}

    # 组合经理
    def portfolio_manager(state: FullAgentState) -> dict:
        decision = f"最终决策：买入 {state['ticker']}。{state['risk_assessment'][:50]}..."
        return {"final_decision": decision}

    # 构建图
    graph = StateGraph(FullAgentState)

    # 添加节点
    graph.add_node("market_analyst", market_analyst)
    graph.add_node("fundamentals_analyst", fundamentals_analyst)
    graph.add_node("news_analyst", news_analyst)
    graph.add_node("sentiment_analyst", sentiment_analyst)
    graph.add_node("clear_messages_1", clear_messages_1)
    graph.add_node("bull_researcher", bull_researcher)
    graph.add_node("bear_researcher", bear_researcher)
    graph.add_node("research_manager", research_manager)
    graph.add_node("trader", trader)
    graph.add_node("risk_manager", risk_manager)
    graph.add_node("portfolio_manager", portfolio_manager)

    # 添加边
    # 分析师阶段（顺序执行，模拟并行）
    graph.add_edge(START, "market_analyst")
    graph.add_edge("market_analyst", "fundamentals_analyst")
    graph.add_edge("fundamentals_analyst", "news_analyst")
    graph.add_edge("news_analyst", "sentiment_analyst")
    graph.add_edge("sentiment_analyst", "clear_messages_1")

    # 辩论阶段
    graph.add_edge("clear_messages_1", "bull_researcher")
    graph.add_conditional_edges(
        "bull_researcher",
        should_continue_debate,
        {"continue": "bear_researcher", "end": "research_manager"}
    )
    graph.add_conditional_edges(
        "bear_researcher",
        should_continue_debate,
        {"continue": "bull_researcher", "end": "research_manager"}
    )

    # 决策阶段
    graph.add_edge("research_manager", "trader")
    graph.add_edge("trader", "risk_manager")
    graph.add_edge("risk_manager", "portfolio_manager")
    graph.add_edge("portfolio_manager", END)

    app = graph.compile()

    # 执行
    start_time = time.time()
    result = app.invoke({
        "ticker": "600519",
        "market_report": "",
        "fundamentals_report": "",
        "news_report": "",
        "sentiment_report": "",
        "bull_argument": "",
        "bear_argument": "",
        "debate_history": [],
        "investment_plan": "",
        "trading_proposal": "",
        "risk_assessment": "",
        "final_decision": "",
        "iteration": 0,
    })
    elapsed = time.time() - start_time

    print(f"执行时间: {elapsed:.3f}秒")
    print(f"\n--- 分析师报告 ---")
    print(f"市场: {result['market_report']}")
    print(f"基本面: {result['fundamentals_report']}")
    print(f"新闻: {result['news_report']}")
    print(f"情绪: {result['sentiment_report']}")
    print(f"\n--- 辩论记录 ---")
    for msg in result['debate_history']:
        print(f"  {msg}")
    print(f"\n--- 决策 ---")
    print(f"投资计划: {result['investment_plan']}")
    print(f"交易提案: {result['trading_proposal']}")
    print(f"风险评估: {result['risk_assessment']}")
    print(f"最终决策: {result['final_decision']}")

    print("\n[PASS] 完整多Agent工作流成功")
except Exception as e:
    print(f"[FAIL] 完整多Agent工作流失败: {e}")
    import traceback
    traceback.print_exc()

# ========== 实验7.2: 工作流执行时间统计 ==========
print("\n" + "=" * 60)
print("实验7.2: 工作流执行时间统计")
print("=" * 60)

try:
    # 运行10次取平均
    times = []
    for i in range(10):
        start = time.time()
        result = app.invoke({
            "ticker": f"60051{i}",
            "market_report": "", "fundamentals_report": "",
            "news_report": "", "sentiment_report": "",
            "bull_argument": "", "bear_argument": "",
            "debate_history": [], "investment_plan": "",
            "trading_proposal": "", "risk_assessment": "",
            "final_decision": "", "iteration": 0,
        })
        times.append(time.time() - start)

    avg_time = sum(times) / len(times)
    print(f"10次执行统计:")
    print(f"  平均: {avg_time*1000:.1f}ms")
    print(f"  最快: {min(times)*1000:.1f}ms")
    print(f"  最慢: {max(times)*1000:.1f}ms")

    print("\n[PASS] 执行时间统计成功")
except Exception as e:
    print(f"[FAIL] 执行时间统计失败: {e}")

print("\n" + "=" * 60)
print("实验7完成")
print("=" * 60)
