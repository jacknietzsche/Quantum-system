# S06 — 工作流引擎

## 6.1 LangGraph工作流定义

```python
from langgraph.graph import StateGraph, START, END

def build_trading_graph(llm_client: AsyncLLMClient) -> StateGraph:
    graph = StateGraph(AgentState)

    # === 分析师团队（4个独立节点） ===
    graph.add_node("market_analyst", create_market_analyst(llm_client))
    graph.add_node("fundamentals_analyst", create_fundamentals_analyst(llm_client))
    graph.add_node("news_analyst", create_news_analyst(llm_client))
    graph.add_node("sentiment_analyst", create_sentiment_analyst(llm_client))

    # === 分析师并行入口 ===
    graph.add_conditional_edges(
        START,
        route_to_analysts,               # 并行分发
        {
            "parallel": "market_analyst", # 首个节点，其余通过Send并行
            "single": "market_analyst",   # 快速模式：只执行市场分析
        }
    )

    # === 分析师汇聚 → 消息清理 ===
    graph.add_node("aggregate_analysts", aggregate_analyst_results)
    graph.add_node("clear_messages_1", create_msg_delete())

    graph.add_edge("market_analyst", "aggregate_analysts")
    graph.add_edge("fundamentals_analyst", "aggregate_analysts")
    graph.add_edge("news_analyst", "aggregate_analysts")
    graph.add_edge("sentiment_analyst", "aggregate_analysts")
    graph.add_edge("aggregate_analysts", "clear_messages_1")

    # === 多空辩论（条件循环） ===
    graph.add_edge("clear_messages_1", "bull_researcher")
    graph.add_conditional_edges(
        "bull_researcher",
        should_continue_investment_debate,
        {"continue": "bear_researcher", "end": "research_manager"}
    )
    graph.add_conditional_edges(
        "bear_researcher",
        should_continue_investment_debate,
        {"continue": "bull_researcher", "end": "research_manager"}
    )

    # === 研究经理 → 交易员 ===
    graph.add_edge("research_manager", "trader")

    # === 消息清理 → 风险团队 ===
    graph.add_node("clear_messages_2", create_msg_delete())
    graph.add_edge("trader", "clear_messages_2")
    graph.add_edge("clear_messages_2", "aggressive_analyst")

    # === 三方风险辩论（条件循环） ===
    graph.add_conditional_edges(
        "aggressive_analyst", should_continue_risk_debate,
        {"continue": "conservative_analyst", "end": "portfolio_manager"}
    )
    graph.add_conditional_edges(
        "conservative_analyst", should_continue_risk_debate,
        {"continue": "neutral_analyst", "end": "portfolio_manager"}
    )
    graph.add_conditional_edges(
        "neutral_analyst", should_continue_risk_debate,
        {"continue": "aggressive_analyst", "end": "portfolio_manager"}
    )

    # === 组合经理 → [可选]大师视角 → 最终输出 ===
    graph.add_node("master_layer", create_master_layer(llm_client))
    graph.add_conditional_edges(
        "portfolio_manager",
        route_after_pm,
        {"with_masters": "master_layer", "final": END}
    )
    graph.add_edge("master_layer", END)

    return graph.compile()
```

## 6.2 并行执行实现

### 方案A: LangGraph Send API（推荐）

LangGraph原生支持并行节点分发：

```python
from langgraph.types import Send

def route_to_analysts(state: AgentState) -> list[Send]:
    """并行分发4个分析师"""
    if state.get("fast_mode"):
        return [Send("market_analyst", state)]  # 快速模式只执行1个

    return [
        Send("market_analyst", state),
        Send("fundamentals_analyst", state),
        Send("news_analyst", state),
        Send("sentiment_analyst", state),
    ]

def aggregate_analyst_results(state: AgentState) -> dict:
    """汇聚4个分析师结果（LangGraph自动合并）"""
    # 4个节点的返回值已通过Send机制自动合并到state
    # 此节点只负责后处理
    return {
        "messages": [],  # 清空分析师的消息
    }
```

### 方案B: AsyncIO（备选）

如果LangGraph版本不支持Send API：

```python
import asyncio

async def parallel_analysis(state: AgentState) -> AgentState:
    """4个分析师并行执行"""
    tasks = [
        market_analyst_node(state),
        fundamentals_analyst_node(state),
        news_analyst_node(state),
        sentiment_analyst_node(state),
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    merged = {}
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            # 单个分析师失败，用默认值
            merged[ANALYST_KEYS[i]] = DEFAULTS["analyst"]()
        else:
            merged.update(result)
    return merged
```

## 6.3 条件路由实现

### 辩论终止判断

```python
from typing import Literal

def should_continue_investment_debate(state: AgentState) -> Literal["continue", "end"]:
    """
    多空辩论终止条件（TradingAgents的ConditionalLogic模式）：
    1. 达到最大轮次 → 结束
    2. Token超预算 → 紧急结束
    3. 连续2个Agent观点一致 → 共识终止
    """
    debate = state.get("investment_debate_state", {})
    count = debate.get("count", 0)
    max_rounds = state.get("config", {}).get("debate", {}).get("investment", {}).get("max_rounds", 2)

    # 条件1: 达到最大轮次
    if count >= max_rounds * 2:  # 每轮2次发言（bull + bear）
        return "end"

    # 条件2: Token超预算
    if state.get("token_counter", {}).should_fast_mode():
        return "end"

    # 条件3: 共识终止（最近2个Agent观点一致）
    history = debate.get("history", [])
    if len(history) >= 2:
        last_two = history[-2:]
        if all(m.get("signal") == last_two[0].get("signal") for m in last_two):
            return "end"

    return "continue"

def should_continue_risk_debate(state: AgentState) -> Literal["continue", "end"]:
    """
    风险辩论终止条件：
    1. 达到最大轮次 → 结束
    2. Token超预算 → 紧急结束
    """
    debate = state.get("risk_debate_state", {})
    count = debate.get("count", 0)
    max_rounds = state.get("config", {}).get("debate", {}).get("risk", {}).get("max_rounds", 2)

    if count >= max_rounds * 3:  # 3方 × 轮次
        return "end"

    if state.get("token_counter", {}).should_fast_mode():
        return "end"

    return "continue"

def route_after_pm(state: AgentState) -> Literal["with_masters", "final"]:
    """组合经理决策后，是否进入大师视角"""
    if state.get("config", {}).get("enable_masters", False):
        return "with_masters"
    return "final"
```

## 6.4 检查点与恢复

```python
from langgraph.checkpoint.sqlite import SqliteSaver

def create_checkpointer(ticker: str) -> SqliteSaver:
    """每个股票一个检查点数据库"""
    return SqliteSaver.from_conn_string(f"runtime/checkpoints/{ticker}.db")

def run_analysis(
    graph,
    ticker: str,
    initial_state: dict,
    resume: bool = False,
):
    """
    执行分析，支持检查点恢复。
    - resume=True: 从上次中断处继续
    - resume=False: 从头开始
    """
    checkpointer = create_checkpointer(ticker)
    thread_id = f"{ticker}:{datetime.now().strftime('%Y-%m-%d')}"

    config = {"configurable": {"thread_id": thread_id}}

    if resume:
        # 从检查点恢复
        return graph.invoke(None, config=config, checkpointer=checkpointer)
    else:
        return graph.invoke(initial_state, config=config, checkpointer=checkpointer)
```

### 检查点策略

| 节点 | 是否检查点 | 原因 |
|------|-----------|------|
| 分析师 | ✅ | 每个分析师独立，可单独恢复 |
| 消息清理 | ❌ | 无状态操作，无需恢复 |
| 辩论轮次 | ✅ | 每轮保存，避免重复辩论 |
| 研究经理 | ✅ | 决策节点，需要保存 |
| 交易员 | ✅ | 决策节点，需要保存 |
| 风险辩论 | ✅ | 每轮保存 |
| 组合经理 | ✅ | 最终决策，必须保存 |
| 大师层 | ✅ | 可选但需保存 |

## 6.5 超时中断机制

```python
import asyncio

class WorkflowTimeout:
    """工作流级别超时控制"""

    def __init__(self, total_timeout: int = 600):  # 默认10分钟
        self.total_timeout = total_timeout

    async def run_with_timeout(self, graph, state, config):
        """带超时的执行"""
        try:
            result = await asyncio.wait_for(
                graph.ainvoke(state, config),
                timeout=self.total_timeout,
            )
            return result
        except asyncio.TimeoutError:
            # 超时：返回当前状态的快照
            return {
                "error": "WORKFLOW_TIMEOUT",
                "message": f"分析超过{self.total_timeout}秒，已中断",
                "partial_result": state,  # 返回已有的部分结果
            }
```

### 超时配置

| 超时类型 | 默认值 | 说明 |
|----------|--------|------|
| 单个Agent | 60秒 | 分析师/研究员/风险分析师 |
| 研究经理 | 90秒 | 综合判断需要更多时间 |
| 交易员 | 45秒 | 按固定步骤，不需要太久 |
| 组合经理 | 120秒 | 最终决策，最复杂 |
| 辩论单轮 | 120秒 | 一轮辩论（bull + bear） |
| 全局 | 600秒 | 整个分析流程 |

## 6.6 进度事件推送

```python
class ProgressEmitter:
    """通过SSE推送Agent执行进度"""

    def __init__(self, job_id: str, sse_manager):
        self.job_id = job_id
        self.sse = sse_manager

    def emit_agent_status(self, agent: str, status: str, message: str = ""):
        """推送Agent状态变更"""
        self.sse.send(self.job_id, {
            "type": "agent.status",
            "agent": agent,
            "status": status,
            "message": message,
        })

    def emit_agent_message(self, agent: str, content: str, round: int = None, role: str = None):
        """推送Agent消息（辩论发言）"""
        self.sse.send(self.job_id, {
            "type": "agent.message",
            "agent": agent,
            "content": content,
            "round": round,
            "role": role,
        })

    def emit_token_usage(self, agent: str, tokens: int, total: int):
        """推送token使用量"""
        self.sse.send(self.job_id, {
            "type": "agent.token",
            "agent": agent,
            "tokens": tokens,
            "total_tokens": total,
        })

    def emit_report_chunk(self, section: str, content: str):
        """推送报告片段（打字机效果）"""
        self.sse.send(self.job_id, {
            "type": "report.chunk",
            "section": section,
            "content": content,
        })
```

### 集成到Agent节点

```python
def create_market_analyst(llm_client, progress: ProgressEmitter):
    def market_analyst_node(state):
        ticker = state["company_of_interest"]

        progress.emit_agent_status("market_analyst", "in_progress", "获取K线数据")
        # ... 获取数据

        progress.emit_agent_status("market_analyst", "in_progress", "计算技术指标")
        # ... 计算指标

        progress.emit_agent_status("market_analyst", "in_progress", "生成报告")
        response = llm_client.complete(...)

        progress.emit_token_usage("market_analyst", response.token_usage.total_tokens, llm_client.counter.daily_used)
        progress.emit_agent_status("market_analyst", "completed")

        return {"market_report": response.content}

    return market_analyst_node
```

## 6.7 快速模式路径

当token预算达到90%时，系统自动切换到快速模式：

```python
def route_to_analysts(state: AgentState) -> list[Send]:
    """根据预算决定执行路径"""
    counter = state.get("token_counter")
    if counter and counter.should_fast_mode():
        state["fast_mode"] = True
        # 快速模式：只执行市场分析师（最重要的技术面）
        return [Send("market_analyst", state)]

    # 正常模式：4个分析师并行
    return [
        Send("market_analyst", state),
        Send("fundamentals_analyst", state),
        Send("news_analyst", state),
        Send("sentiment_analyst", state),
    ]
```

### 快速模式 vs 正常模式

| 维度 | 正常模式 | 快速模式 |
|------|----------|----------|
| 分析师 | 4个并行 | 仅市场分析师 |
| 多空辩论 | 2轮 | 跳过 |
| 研究经理 | ✅ | 跳过 |
| 交易员 | ✅ | ✅ |
| 风险辩论 | 2轮(3方) | 跳过 |
| 组合经理 | ✅ | ✅ |
| 大师视角 | 可选 | 跳过 |
| 预估token | ~17,500/只 | ~5,000/只 |

## 6.8 Graph可视化调试（借鉴AI Hedge Fund）

AI Hedge Fund提供`save_graph_as_png`导出LangGraph流程图，便于调试和文档：

```python
def save_graph_as_png(graph, filepath: str = "logs/trading_graph.png"):
    """导出LangGraph流程图为PNG"""
    try:
        png_data = graph.get_graph().draw_mermaid_png()
        with open(filepath, "wb") as f:
            f.write(png_data)
        print(f"Graph saved to {filepath}")
    except Exception as e:
        print(f"Could not save graph: {e}")
        # Fallback: 导出为文本格式
        print(graph.get_graph().draw_ascii())
```

### 调试命令

```bash
# 导出流程图
python -c "from graph.trading_graph import build_trading_graph; save_graph_as_png(build_trading_graph())"

# 打印ASCII流程图
python -c "from graph.trading_graph import build_trading_graph; print(build_trading_graph().get_graph().draw_ascii())"
```

## 6.9 多Ticker批处理（借鉴AI Hedge Fund）

AI Hedge Fund支持一次分析多只股票，我们采用同样的模式：

```python
async def run_batch_analysis(
    tickers: list[str],
    config: dict,
    fast_mode: bool = False,
) -> list[AnalysisResult]:
    """
    批量分析多只股票。
    - 每只股票独立执行完整工作流
    - 可选并行（受LLM并发限制）
    - 共享token预算
    """
    results = []
    llm_client = create_llm_client_from_config(config)
    graph = build_trading_graph(llm_client)

    # 并发控制：最多同时分析N只股票
    semaphore = asyncio.Semaphore(config.get("batch", {}).get("max_concurrent", 3))

    async def analyze_one(ticker: str) -> AnalysisResult:
        async with semaphore:
            state = create_initial_state(ticker, config, fast_mode)
            result = await graph.ainvoke(state)
            return parse_result(result)

    # 并行执行
    tasks = [analyze_one(ticker) for ticker in tickers]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # 处理异常
    final_results = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            final_results.append(AnalysisResult(
                ticker=tickers[i], error=str(result), status="failed"
            ))
        else:
            final_results.append(result)

    return final_results
```

### 批处理配置

```yaml
# config.yaml
batch:
  max_concurrent: 3                     # 最多同时分析3只股票
  per_stock_timeout: 300                # 单股超时5分钟
  total_timeout: 1800                   # 批量总超时30分钟
```

### CLI使用

```bash
# 分析多只股票
ashare-x analyze 600519,000858,601318

# 每日分析Top 10
ashare-x daily -n 10

# 指定股票池
ashare-x daily --tickers 600519,000858,601318,002594,600036
```

---

**依赖**: S3(架构), S4(Agent), S5(数据), S15(LLM层)
**被依赖**: S9(记忆), S10(前端), S14(API)
