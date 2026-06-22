# S4 — Agent体系设计

> **设计依据**: 参考 TradingAgents(TauricResearch)、AI Hedge Fund(virattt)、AlphaAnalyst(kbhujbal)、
> OpenViking(字节跳动)、CrewAI、Microsoft Agent Framework、OpenAI Swarm、MetaGPT、Swarms(kyegomez)、
> Agency Swarm(VRSEN) 十个成熟开源项目。

## 4.1 设计模式来源

| 模式 | 来源项目 | 核心思想 | 我们采用 |
|------|----------|----------|----------|
| Agent工厂模式 | TradingAgents | `create_xxx(llm)` 返回节点函数，延迟绑定LLM | ✅ 全部Agent |
| 结构化输出+渲染 | TradingAgents | Pydantic schema + `render_xxx()` 转markdown | ✅ 决策Agent |
| 信号架构 | AI Hedge Fund | 每个Agent输出 `signal + confidence + reasoning` | ✅ 分析师 |
| 默认降级 | AI Hedge Fund | `default_factory` 提供fallback输出 | ✅ 全部Agent |
| 确定性约束+LLM决策 | AI Hedge Fund | 风险管理用纯量化计算，组合经理在约束内决策 | ✅ 风险+组合 |
| 角色定义 | CrewAI | Agent有 role/goal/backstory 三要素 | ✅ Prompt设计 |
| SOP驱动 | MetaGPT | `Code = SOP(Team)`，工作流即标准流程 | ✅ 辩论流程 |
| Handoff机制 | Swarm | Agent通过返回另一个Agent来转移控制 | ✅ 辩论路由 |
| 错误分层 | Swarms | AgentError/LLMError/ToolError/MemoryError分层处理 | ✅ 4.18节 |
| 上下文压缩 | Swarms | ContextCompressor压缩长对话，保留关键信息 | ✅ 4.19节 |
| 通信流控制 | Agency Swarm | communication_flows显式定义Agent间通信方向 | ✅ 4.20节 |
| 状态机模式 | MetaGPT | REACT/BY_ORDER/PLAN_AND_ACT三种执行模式 | ✅ 4.21节 |
| 记忆分层 | MetaGPT+TradingAgents | 长期记忆+工作记忆+消息缓冲+决策日志 | ✅ 4.22节 |
| 线程持久化 | Agency Swarm | load/save callbacks + LangGraph检查点 | ✅ 4.23节 |
| 重试退避 | Swarms | 可配置重试次数+指数退避+超时控制 | ✅ 4.24节 |
| LLM是写手不是知识库 | AlphaAnalyst | 数字来自API，LLM只负责组织语言 | ✅ 4.26节 |
| 引用验证 | AlphaAnalyst | 每个数字标注数据来源 | ✅ 4.27节 |
| 纯Python估值 | AlphaAnalyst | decimal.Decimal，LLM不碰算术 | ✅ S08 |
| Devil's Advocate | AlphaAnalyst | 反方用不同模型族，确保独立性 | ✅ 4.28节 |

## 4.2 Agent团队结构

执行方向：**从下往上**（分析师 → 研究员 → 交易员 → 风险团队 → 组合经理）

```
                        ┌─────────────────┐
                        │   Portfolio      │
                        │   Manager        │ ← 最终决策者（确定性约束+LLM）
                        └────────┬────────┘
                                 │
                    ┌────────────┼────────────┐
                    │            │            │
              ┌─────┴─────┐ ┌───┴───┐ ┌─────┴─────┐
              │ Aggressive│ │Neutral│ │Conservative│ ← 三方风险辩论
              │ (激进)    │ │(中性) │ │ (保守)     │
              └─────┬─────┘ └───┬───┘ └─────┬─────┘
                    │           │            │
                    └───────────┼────────────┘
                                │
                        ┌───────┴───────┐
                        │    Trader      │ ← 交易计划生成（结构化输出）
                        └───────┬───────┘
                                │
                        ┌───────┴───────┐
                        │ Research Mgr   │ ← 辩论裁判（结构化输出）
                        └───────┬───────┘
                                │
                    ┌───────────┼───────────┐
                    │                       │
              ┌─────┴─────┐          ┌─────┴─────┐
              │    Bull    │          │    Bear    │ ← 多空辩论（Handoff）
              │  (看涨)    │◄────────►│  (看跌)    │
              └─────┬─────┘          └─────┬─────┘
                    │                       │
              ┌─────┴───────────────────────┴─────┐
              │                                   │
        ┌─────┴─────┐ ┌─────┴─────┐ ┌─────┴─────┐ ┌─────┴─────┐
        │  Market   │ │Fundamental│ │   News    │ │Sentiment  │ ← 分析师（信号架构）
        │ (市场)    │ │ (基本面)  │ │ (新闻)    │ │ (情绪)    │
        └───────────┘ └───────────┘ └───────────┘ └───────────┘

执行顺序: 分析师(并行) → 消息清理 → 多空辩论(2轮) → 研究经理 → 交易员 → 消息清理 → 风险辩论(2轮) → 组合经理(初步决策) → [可选]大师视角 → 组合经理(最终决策)
```

## 4.3 Agent工厂模式（借鉴TradingAgents）

每个Agent通过工厂函数创建，接收LLM实例，返回LangGraph节点函数：

```python
# tradingagents/agents/analysts/market_analyst.py 的模式
def create_market_analyst(llm):
    """工厂函数：接收LLM，返回节点函数"""

    def market_analyst_node(state):
        # 1. 从state提取上下文
        current_date = state["trade_date"]
        ticker = state["company_of_interest"]

        # 2. 定义工具
        tools = [get_stock_data, get_indicators]

        # 3. 构建prompt（system + tools + context）
        system_message = """You are a market analyst..."""
        prompt = ChatPromptTemplate.from_messages([
            ("system", system_message),
            MessagesPlaceholder(variable_name="messages"),
        ])

        # 4. 绑定工具并调用LLM
        chain = prompt | llm.bind_tools(tools)
        result = chain.invoke(state["messages"])

        # 5. 提取报告（当没有tool_calls时，content就是最终报告）
        report = ""
        if len(result.tool_calls) == 0:
            report = result.content

        # 6. 返回更新后的state
        return {
            "messages": [result],
            "market_report": report,  # 结构化字段
        }

    return market_analyst_node
```

**关键设计**:
- 工厂模式允许同一Agent类用不同LLM实例化（快速模型/深度模型）
- 节点函数签名统一：`(state) -> dict`，返回值合并到LangGraph state
- 工具通过 `llm.bind_tools()` 绑定，LLM自主决定调用哪些工具
- 当 `tool_calls` 为空时，`content` 就是最终报告

## 4.4 结构化输出与渲染（借鉴TradingAgents）

决策Agent使用Pydantic schema确保输出一致，render函数转markdown供下游消费：

```python
# tradingagents/agents/schemas.py 的模式
from enum import Enum
from pydantic import BaseModel, Field

class PortfolioRating(str, Enum):
    BUY = "Buy"
    OVERWEIGHT = "Overweight"
    HOLD = "Hold"
    UNDERWEIGHT = "Underweight"
    SELL = "Sell"

class ResearchPlan(BaseModel):
    """研究经理的投资计划"""
    recommendation: PortfolioRating = Field(
        description="投资建议。Buy/Overweight/Hold/Underweight/Sell"
    )
    rationale: str = Field(
        description="辩论双方关键论点总结，以及哪个论点导致了这个建议"
    )
    strategic_actions: str = Field(
        description="给交易员的具体执行步骤，包括仓位建议"
    )

def render_research_plan(plan: ResearchPlan) -> str:
    """渲染为markdown，供存储和下游prompt使用"""
    return "\n".join([
        f"**Recommendation**: {plan.recommendation.value}",
        f"**Rationale**: {plan.rationale}",
        f"**Strategic Actions**: {plan.strategic_actions}",
    ])
```

**所有决策Agent的Schema**:

| Agent | Schema | 关键字段 |
|-------|--------|----------|
| 研究经理 | `ResearchPlan` | recommendation, rationale, strategic_actions |
| 交易员 | `TraderProposal` | action, reasoning, entry_price, stop_loss, position_sizing |
| 投资组合经理 | `PortfolioDecision` | rating, executive_summary, investment_thesis, price_target, time_horizon |

## 4.5 信号架构（借鉴AI Hedge Fund）

分析师Agent使用统一的信号格式输出：

```python
# ai-hedge-fund/src/agents/warren_buffett.py 的模式
class AnalystSignal(BaseModel):
    signal: Literal["bullish", "bearish", "neutral"]
    confidence: int = Field(description="Confidence 0-100")
    reasoning: str = Field(description="Reasoning for the decision")
```

**每个分析师输出**: `signal + confidence + reasoning`
**下游消费**: 只传递 `{agent: {sig, conf}}` 给决策Agent，节省token

```python
# 紧凑信号格式（AI Hedge Fund的_compact_signals模式）
def compact_signals(analyst_signals: dict) -> dict:
    """只保留 {agent: {sig, conf}}，丢弃冗余"""
    out = {}
    for agent, payload in analyst_signals.items():
        sig = payload.get("signal")
        conf = payload.get("confidence")
        if sig is not None and conf is not None:
            out[agent] = {"sig": sig, "conf": conf}
    return out
```

## 4.6 分析师团队（4个Agent）

每个分析师：工厂模式 + 信号架构 + 工具调用

**市场分析师 (Market Analyst)**
- 工具：`get_stock_data(code, period)`, `get_indicators(code, indicators)`
- 输出：`{signal, confidence, reasoning}` + 技术指标详情
- 指标：MA5/MA20/MA60、MACD、RSI(14)、KDJ、Bollinger(20,2)、ATR(14)、成交量趋势、OBV

**基本面分析师 (Fundamentals Analyst)**
- 工具：`get_fundamentals(code)`, `get_balance_sheet(code)`, `get_cashflow(code)`, `get_income_statement(code)`
- 输出：`{signal, confidence, reasoning}` + 财务指标详情
- A股特色：扣非净利润、经营现金流/净利润比、应收账款周转天数

**新闻分析师 (News Analyst)**
- 工具：`get_news(code)`, `get_global_news()`, `get_insider_transactions(code)`
- 输出：`{signal, confidence, reasoning}` + 事件影响评估
- 数据源：AKShare封装的巨潮资讯公告、东方财富新闻

**情绪分析师 (Sentiment Analyst)**
- 工具：`get_news(code)`, `get_social_sentiment(code)`
- 输出：`{signal, confidence, reasoning}` + 情绪指标
- A股特色：龙虎榜数据、北向资金、融资融券余额变化

## 4.7 研究员团队（3个Agent）

**看涨研究员 (Bull Researcher)**
- 输入：所有分析师信号 + 看跌研究员的最新论点
- 任务：构建看涨论据，直接反驳看跌研究员
- 输出：结构化看涨论证（包含数据引用和逻辑链）

**看跌研究员 (Bear Researcher)**
- 输入：所有分析师信号 + 看涨研究员的最新论点
- 任务：构建看跌论据，直接反驳看涨研究员
- 输出：结构化看跌论证（包含风险点和反例）

**研究经理 (Research Manager)**
- 输入：多轮辩论记录
- 任务：作为裁判，综合双方观点，形成投资计划
- 输出：`ResearchPlan`（结构化） + `render_research_plan()`（渲染为markdown）

## 4.8 交易员（1个Agent）

**交易员 (Trader)**
- 输入：研究经理的 `ResearchPlan`
- 任务：转化为具体可执行的交易指令
- 输出：`TraderProposal`（结构化）

```python
class TraderProposal(BaseModel):
    action: TraderAction                    # Buy/Hold/Sell
    reasoning: str                          # 2-4句话的理由
    entry_price: Optional[float]            # 建议入场价
    stop_loss: Optional[float]              # 止损价
    position_sizing: Optional[str]          # "5% of portfolio"
```

## 4.9 风险管理（纯量化，不调用LLM）

**借鉴AI Hedge Fund的risk_manager.py**: 风险管理是纯量化计算，不需要LLM。

```python
# AI Hedge Fund的风险管理模式
def risk_management_agent(state):
    """纯量化风险计算，无LLM调用"""
    # 1. 获取价格数据，计算波动率
    for ticker in all_tickers:
        prices = get_prices(ticker, start_date, end_date)
        volatility_metrics = calculate_volatility_metrics(prices_df)

    # 2. 计算相关性矩阵
    correlation_matrix = returns_df.corr()

    # 3. 波动率调整仓位上限
    vol_adjusted_limit = calculate_volatility_adjusted_limit(annualized_vol)
    # 低波动(<15%): 25% | 中波动(15-30%): 15-20% | 高波动(>30%): 10-15%

    # 4. 相关性调整
    corr_multiplier = calculate_correlation_multiplier(avg_correlation)
    # 高相关(>=0.8): 0.7x | 中相关(0.4-0.6): 1.0x | 低相关(<0.2): 1.1x

    # 5. 输出每个ticker的仓位限制
    return {
        "remaining_position_limit": max_position_size,
        "current_price": current_price,
        "volatility_metrics": {...},
        "correlation_metrics": {...},
    }
```

**三方风险辩论**（LLM参与，但基于量化数据）：

| Agent | 角色 | 关注点 | 论证风格 |
|-------|------|--------|----------|
| 激进分析师 | 高风险高回报 | 机会成本、上涨潜力、动量信号 | "如果错过这个机会..." |
| 保守分析师 | 资本保全 | 下行风险、波动性、流动性 | "如果最坏情况发生..." |
| 中性分析师 | 平衡视角 | 风险收益比、概率分布 | "综合来看..." |

## 4.10 投资组合经理（确定性约束+LLM决策）

**借鉴AI Hedge Fund的portfolio_manager.py**: 先计算确定性约束，再让LLM在约束内决策。

```python
# AI Hedge Fund的组合经理模式
def portfolio_management_agent(state):
    # 1. 确定性约束计算（不经过LLM）
    allowed_actions = compute_allowed_actions(
        tickers, current_prices, max_shares, portfolio
    )
    # 每个ticker的允许操作和最大数量

    # 2. 预填充纯hold（无法交易的直接跳过LLM）
    prefilled = {}
    for t in tickers:
        if only_hold_allowed(t):
            prefilled[t] = PortfolioDecision(
                action="hold", quantity=0, confidence=100,
                reasoning="No valid trade available"
            )

    # 3. 只把可交易的ticker发给LLM
    llm_out = call_llm(
        prompt=minimal_prompt(signals, allowed),
        pydantic_model=PortfolioManagerOutput,
        default_factory=create_default_output,  # 降级fallback
    )

    # 4. 合并结果
    merged = {**prefilled, **llm_out.decisions}
```

**投资组合经理输出**：

```python
class PortfolioDecision(BaseModel):
    rating: PortfolioRating
    confidence: float              # 0-100%
    executive_summary: str         # 入场策略、仓位、关键风险、时间框架
    investment_thesis: str         # 基于辩论证据的详细推理
    entry_price: Optional[float]   # 建议入场价
    stop_loss: Optional[float]     # 止损价
    take_profit: Optional[float]   # 止盈价
    position_pct: Optional[float]  # 占总资金比例
    price_target: Optional[float]
    time_horizon: Optional[str]
    key_factors: list[str]         # 关键因素
    risks: list[str]               # 主要风险
    invalidation: str              # 论据失效条件
    source_agents: list[str]       # 参与决策的Agent
    debate_summary: str            # 辩论摘要
```

> 此schema与S08的`TradingPlan`对齐，确保输出包含可直接执行的交易参数（入场价/止损/止盈/仓位）。

## 4.11 大师视角层（可选，7个Agent）

**集成点**: 在投资组合经理做出初步决策后，大师视角层独立评估，投资组合经理参考大师意见做出最终决策。

**大师选择逻辑**: 根据股票特征自动选择最相关的3个大师（而非全部7个）：

```python
def select_masters(stock_profile: dict) -> list[str]:
    """
    根据股票特征选择最相关的3个大师
    stock_profile: {pe_ratio, roe, volatility, growth}
    """
    pe = stock_profile.get("pe_ratio", 20)
    roe = stock_profile.get("roe", 15)
    volatility = stock_profile.get("volatility", 0.3)
    growth = stock_profile.get("revenue_growth", 0.1)

    scores = {}

    # 巴菲特: 低PE + 高ROE + 低波动
    scores["buffett"] = 0
    if pe < 25: scores["buffett"] += 2
    if roe > 15: scores["buffett"] += 2
    if volatility < 0.3: scores["buffett"] += 1

    # 芒格: 高ROE + 合理PE + 稳定增长
    scores["munger"] = 0
    if roe > 20: scores["munger"] += 2
    if 10 < pe < 30: scores["munger"] += 1
    if 0.05 < growth < 0.3: scores["munger"] += 1

    # 林奇: 成长性 + 合理估值
    scores["lynch"] = 0
    if growth > 0.2: scores["lynch"] += 2
    if pe < growth * 100: scores["lynch"] += 2  # PEG < 1

    # 伯里: 高波动 + 低PE
    scores["burry"] = 0
    if volatility > 0.4: scores["burry"] += 2
    if pe < 15: scores["burry"] += 2

    # 伍德: 高成长 + 高波动
    scores["wood"] = 0
    if growth > 0.3: scores["wood"] += 2
    if volatility > 0.35: scores["wood"] += 1

    # 达利欧: 中等波动 + 稳定增长
    scores["druckenmiller"] = 0
    if 0.2 < volatility < 0.4: scores["druckenmiller"] += 2
    if growth > 0.1: scores["druckenmiller"] += 1

    # 费雪: 高成长 + 高ROE
    scores["fisher"] = 0
    if growth > 0.25: scores["fisher"] += 2
    if roe > 20: scores["fisher"] += 1

    # 按分数排序，取前3
    sorted_masters = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return [name for name, score in sorted_masters[:3] if score > 0]
```

**实验验证结果**:
- 贵州茅台(PE=25, ROE=30%, 波动=0.2): 推荐 munger, buffett, druckenmiller
- 宁德时代(PE=50, ROE=20%, 波动=0.45): 推荐 wood, buffett, lynch
- 中国平安(PE=8, ROE=12%, 波动=0.35): 推荐 buffett, burry, druckenmiller

每个大师Agent遵循AI Hedge Fund的信号模式：

```python
class MasterSignal(BaseModel):
    signal: Literal["bullish", "bearish", "neutral"]
    confidence: int = Field(description="Confidence 0-100")
    reasoning: str = Field(description="Short reasoning")
```

## 4.12 Agent间通信机制

Agent间通过LangGraph状态字典通信：

```python
class AgentState(TypedDict):
    # 输入
    company_of_interest: str     # 股票代码（与TradingAgents一致）
    trade_date: str

    # 分析师输出（信号格式）
    market_report: str
    fundamentals_report: str
    news_report: str
    sentiment_report: str

    # 研究员输出（辩论状态，独立dict）
    investment_debate_state: dict  # {history, bear_history, bull_history, count, judge_decision}
    investment_plan: dict

    # 交易员输出
    trader_proposal: dict

    # 风险团队输出
    risk_debate_state: dict       # {history, count, risk_analysis}
    risk_level: str
    final_decision: dict

    # 大师视角（可选）
    master_views: dict

    # 元数据
    messages: list[BaseMessage]
    iteration: int
    token_usage: int
```

## 4.13 消息清理机制

消息清理按阶段执行（TradingAgents模式：分析师之间清理，辩论中保留）：

| 阶段转换 | 清理策略 | 原因 |
|----------|----------|------|
| 分析师 → 研究员 | **清理** | 报告已提取到state字段 |
| 多空辩论过程中 | **保留** | 辩论需要引用对方论点 |
| 辩论结束 → 研究经理 | **保留** | 研究经理需要完整辩论记录 |
| 研究经理 → 交易员 | **清理** | 投资计划已提取到state字段 |
| 交易员 → 风险团队 | **清理** | 交易提案已提取到state字段 |
| 风险辩论过程中 | **保留** | 辩论需要引用对方论点 |
| 风险辩论结束 → 组合经理 | **保留** | 组合经理需要完整风险辩论记录 |

```python
def create_msg_delete():
    """TradingAgents的消息清理模式"""
    def delete_messages(state: AgentState):
        return {"messages": [HumanMessage(content="Continue")]}
    return delete_messages
```

## 4.14 默认降级机制（借鉴AI Hedge Fund）

每个Agent都有 `default_factory`，LLM失败时提供安全fallback：

```python
# AI Hedge Fund的call_llm模式
def call_llm(prompt, pydantic_model, agent_name, state, default_factory):
    """调用LLM，失败时返回默认值"""
    try:
        result = llm.invoke(prompt)
        return pydantic_model.model_validate_json(result.content)
    except Exception:
        return default_factory()  # 降级：返回安全默认值

# 各Agent的默认值
DEFAULTS = {
    "analyst": lambda: AnalystSignal(signal="neutral", confidence=0, reasoning="数据获取失败"),
    "research_manager": lambda: ResearchPlan(
        recommendation="Hold", rationale="辩论数据不足", strategic_actions="等待更多信息"
    ),
    "trader": lambda: TraderProposal(
        action="Hold", reasoning="数据不足，建议观望"
    ),
    "portfolio_manager": lambda: PortfolioDecision(
        rating="Hold", confidence=0,
        executive_summary="系统降级，建议持有",
        investment_thesis="数据不足，无法做出有信心的判断",
        key_factors=[], risks=["数据不足"], invalidation="N/A",
        source_agents=[], debate_summary="无"
    ),
}
```

## 4.15 Agent超时与重试

```python
class AgentConfig:
    timeout_seconds: int = 60       # 单个Agent最多60秒
    max_retries: int = 2            # 失败重试2次
    retry_delay: float = 2.0        # 重试间隔2秒
    fallback_output: str = ""       # 失败时的默认输出
```

**超时处理**:
- 分析师超时 → 该字段设为 `"[数据获取超时]"`，后续Agent可识别并跳过引用
- 辩论Agent超时 → 该轮辩论跳过，使用已有辩论记录
- 风险团队超时 → 使用保守默认（rating="Hold", risk_level="HIGH"）

## 4.16 辩论轮次配置

```yaml
# config.yaml
debate:
  investment:
    max_rounds: 2                   # Bull→Bear→Bull→Bear
    min_rounds: 1
    termination: "consensus_or_max"
  risk:
    max_rounds: 2                   # 3方×2轮=6次发言
    min_rounds: 1
    participants: ["aggressive", "conservative", "neutral"]
```

**辩论终止条件**（TradingAgents的ConditionalLogic模式）:
- 达成共识：连续2个Agent观点一致
- 达到最大轮次：强制停止，由裁判决策
- Token超预算：紧急停止，直接进入下一阶段

## 4.17 进度追踪（借鉴AI Hedge Fund）

```python
# AI Hedge Fund的progress.update_status模式
from src.utils.progress import progress

def market_analyst_node(state):
    ticker = state["company_of_interest"]
    progress.update_status("market_analyst", ticker, "Fetching stock data")
    # ... 获取数据
    progress.update_status("market_analyst", ticker, "Calculating indicators")
    # ... 计算指标
    progress.update_status("market_analyst", ticker, "Generating report")
    # ... 生成报告
    progress.update_status("market_analyst", ticker, "Done", analysis=report)
```

前端通过SSE订阅进度更新，实时显示每个Agent的状态。

## 4.18 错误分层体系（借鉴Swarms）

Swarms定义了完整的Agent异常层级，每个层级对应不同的处理策略：

```python
# swarms/structs/agent.py 的错误层级
class AgentError(Exception):
    """Agent异常基类"""

class AgentLLMError(AgentError):
    """LLM调用失败（超时、限流、认证）"""

class AgentToolError(AgentError):
    """工具调用失败"""

class AgentToolExecutionError(AgentToolError):
    """工具执行失败"""

class AgentMemoryError(AgentError):
    """记忆系统异常"""

class AgentRunError(AgentError):
    """Agent运行时异常"""
```

**我们的映射**:

| 异常类型 | 触发场景 | 处理策略 |
|----------|----------|----------|
| `AgentLLMError` | LLM超时/限流/认证失败 | 重试2次 → 降级为free-text → default_factory |
| `AgentToolError` | 数据源API不可用 | 跳过该工具 → LLM基于已有信息继续 |
| `AgentToolExecutionError` | 工具执行异常 | 记录日志 → 返回空结果 → LLM标注"数据不可用" |
| `AgentMemoryError` | 记忆读写失败 | 降级为无记忆模式，继续执行 |

## 4.19 上下文压缩（借鉴Swarms）

Swarms的`ContextCompressor`解决了长对话上下文溢出问题：

```python
# swarms/agents/context_compressor.py 的模式
class ContextCompressor:
    """当token接近上限时，压缩历史上下文"""

    def __init__(self, llm, max_tokens: int = 4000):
        self.llm = llm
        self.max_tokens = max_tokens

    def compress(self, messages: list) -> list:
        """压缩消息列表，保留关键信息"""
        current_tokens = count_tokens(messages)
        if current_tokens < self.max_tokens * 0.8:
            return messages  # 无需压缩

        # 策略1: 保留最近N轮对话
        # 策略2: 对早期对话生成摘要
        # 策略3: 保留工具调用结果，压缩纯文本
        summary = self.llm.invoke(f"Summarize this conversation: {early_messages}")
        return [SystemMessage(summary)] + recent_messages
```

**在辩论中的应用**:
- 多空辩论超过3轮时，自动压缩早期轮次为摘要
- 保留最近1轮的完整对话，确保辩论连贯性
- 风险辩论同理

## 4.20 通信流控制（借鉴Agency Swarm）

Agency Swarm的`communication_flows`显式定义Agent间通信方向：

```python
# agency-swarm的Agency通信流定义
agency = Agency(
    agents=[ceo, researcher, analyst],
    communication_flows={
        ceo: [researcher, analyst],      # CEO可以发消息给researcher和analyst
        researcher: [analyst],            # researcher只能发消息给analyst
        analyst: [],                      # analyst不能主动发消息
    }
)
```

**在我们的系统中**:

```python
# 显式通信流定义
COMMUNICATION_FLOWS = {
    "market_analyst": [],                # 分析师不主动通信，只输出到state
    "fundamentals_analyst": [],
    "news_analyst": [],
    "sentiment_analyst": [],
    "bull_researcher": ["bear_researcher"],  # 只能发给bear
    "bear_researcher": ["bull_researcher"],  # 只能发给bull
    "research_manager": ["trader"],           # 裁判→交易员
    "trader": [],                             # 交易员不主动通信
    "aggressive_analyst": ["conservative_analyst", "neutral_analyst"],
    "conservative_analyst": ["aggressive_analyst", "neutral_analyst"],
    "neutral_analyst": ["aggressive_analyst", "conservative_analyst"],
    "portfolio_manager": [],              # 最终决策者不主动通信
}
```

## 4.21 状态机模式（借鉴MetaGPT）

MetaGPT的`RoleReactMode`定义了Agent的三种执行模式：

```python
# metagpt/roles/role.py 的模式
class RoleReactMode(str, Enum):
    REACT = "react"           # 思考→行动→观察 循环
    BY_ORDER = "by_order"     # 按预定义顺序执行
    PLAN_AND_ACT = "plan_and_act"  # 先规划再执行
```

**映射到我们的Agent**:

| Agent | 推荐模式 | 原因 |
|-------|----------|------|
| 分析师 | `REACT` | 需要思考→调用工具→观察结果→继续 |
| 研究员 | `REACT` | 辩论需要动态响应对方论点 |
| 研究经理 | `PLAN_AND_ACT` | 先综合所有信息，再做出判断 |
| 交易员 | `BY_ORDER` | 按固定步骤转化投资计划 |
| 风险分析师 | `REACT` | 辩论需要动态响应 |
| 组合经理 | `PLAN_AND_ACT` | 先评估约束，再决策 |

## 4.22 记忆分层（借鉴MetaGPT + TradingAgents）

MetaGPT区分了三种记忆，TradingAgents实现了决策日志：

```python
# metagpt的三层记忆 + TradingAgents的决策日志
class MemorySystem:
    def __init__(self):
        # MetaGPT模式：三层记忆
        self.memory = Memory()              # 长期记忆：所有历史消息
        self.working_memory = Memory()       # 工作记忆：当前任务相关
        self.msg_buffer = MessageQueue()     # 消息缓冲：待处理消息

        # TradingAgents模式：决策日志
        self.decision_log = TradingMemoryLog()  # 追加式markdown日志

    def get_context(self, ticker: str) -> str:
        """注入历史记忆到Agent prompt"""
        # 同一股票的历史决策（最近5条）
        same_ticker = self.decision_log.get_past_context(ticker, n_same=5)
        # 跨股票的经验教训（最近3条）
        cross_ticker = self.decision_log.get_past_context(ticker, n_cross=3)
        return f"{same_ticker}\n\n{cross_ticker}"
```

**TradingAgents的决策日志格式**:
```
[2026-06-13 | 600519 | Buy | +5.2% | +3.1% | 30d]

DECISION:
**Rating**: Buy
**Rationale**: 茅台Q2营收超预期...
**Strategic Actions**: 建议在1500附近建仓...

REFLECTION:
方向判断正确，alpha+3.1%。但入场时机偏早，
如果等到回调到1450再入，收益会更高。下次注意
在RSI>70时不要急于入场。
```

## 4.23 线程持久化（借鉴Agency Swarm）

Agency Swarm的`load_threads_callback`/`save_threads_callback`支持会话持久化：

```python
# agency-swarm的线程持久化模式
agency = Agency(
    agents=[...],
    load_threads_callback=load_from_db,    # 从SQLite加载
    save_threads_callback=save_to_db,       # 保存到SQLite
)

# 与LangGraph检查点结合
# TradingAgents的检查点模式
from langgraph.checkpoint.sqlite import SqliteSaver
checkpointer = SqliteSaver.from_conn_string(f"data/checkpoints/{ticker}.db")
```

**我们的实现**: LangGraph检查点 + SQLite决策日志，双重持久化。

## 4.24 重试与退避（借鉴Swarms）

Swarms的Agent内置重试机制：

```python
# swarms/structs/agent.py 的重试模式
class Agent:
    def __init__(self, ..., retry_attempts: int = 3, retry_interval: int = 1):
        self.retry_attempts = retry_attempts
        self.retry_interval = retry_interval

    def _execute_with_retry(self, fn):
        for attempt in range(self.retry_attempts):
            try:
                return fn()
            except AgentLLMError as e:
                if attempt < self.retry_attempts - 1:
                    time.sleep(self.retry_interval * (attempt + 1))  # 线性退避
                    continue
                raise
```

**我们的配置**:

```yaml
# config.yaml
agent:
  retry:
    max_attempts: 2              # 最多重试2次
    base_delay: 2.0              # 基础延迟2秒
    backoff_multiplier: 2.0      # 指数退避
    max_delay: 30.0              # 最大延迟30秒
  timeout:
    analyst: 60                  # 分析师60秒
    researcher: 120              # 研究员120秒（辩论可能多轮）
    trader: 45                   # 交易员45秒
    risk_analyst: 60             # 风险分析师60秒
    portfolio_manager: 90        # 组合经理90秒
```

## 4.25 数据契约（Agent间接口定义）

所有Agent间传递的数据结构，确保接口一致性。

### AnalystSignal（分析师输出）

```python
class AnalystSignal(BaseModel):
    """所有4个分析师的统一输出格式"""
    signal: Literal["bullish", "bearish", "neutral"]
    confidence: int = Field(ge=0, le=100)  # 0-100
    reasoning: str                         # 分析理由（Markdown）

class MarketAnalystOutput(AnalystSignal):
    """市场分析师特有字段"""
    indicators: dict                       # 技术指标详情
    trend: str                             # 趋势判断
    support_resistance: dict               # 支撑/阻力位

class FundamentalsAnalystOutput(AnalystSignal):
    """基本面分析师特有字段"""
    financial_metrics: dict                # 财务指标
    valuation: dict                        # 估值数据
    quality_score: Optional[float]         # 质量评分

class NewsAnalystOutput(AnalystSignal):
    """新闻分析师特有字段"""
    events: list[dict]                     # 关键事件列表
    event_impact: str                      # 事件影响评估

class SentimentAnalystOutput(AnalystSignal):
    """情绪分析师特有字段"""
    sentiment_metrics: dict                # 情绪指标
    fund_flow: Optional[dict]              # 资金流向
```

### DebateMessage（辩论消息）

```python
class DebateMessage(BaseModel):
    """辩论中每条发言的消息结构"""
    speaker: str                           # Agent内部名（如 "bull_researcher"）
    role: Literal["bull", "bear", "aggressive", "conservative", "neutral"]
    round: int                             # 轮次（从1开始）
    content: str                           # Markdown格式发言内容
    signal: Optional[Literal["bullish", "bearish", "neutral"]]  # 发言者的立场信号
    timestamp: str                         # ISO 8601
    token_usage: Optional[int]             # 该条消息消耗的token数
```

### InvestmentDebateState（多空辩论状态）

```python
class InvestmentDebateState(BaseModel):
    """多空辩论的完整状态（存储在AgentState中）"""
    history: list[DebateMessage]           # 所有辩论记录
    bull_history: list[DebateMessage]      # 看涨方发言
    bear_history: list[DebateMessage]      # 看跌方发言
    count: int                             # 已完成的发言次数
    current_round: int                     # 当前轮次
    consensus_reached: bool                # 是否达成共识
    judge_decision: Optional[str]          # 研究经理的最终判断
```

### RiskDebateState（风险辩论状态）

```python
class RiskDebateState(BaseModel):
    """三方风险辩论的完整状态"""
    history: list[DebateMessage]           # 所有辩论记录
    participants: list[str]                # 参与者列表
    count: int                             # 已完成的发言次数
    current_round: int                     # 当前轮次
    risk_analysis: Optional[dict]          # 风险分析汇总
```

### AgentState（完整工作流状态）

```python
class AgentState(TypedDict):
    # === 输入 ===
    company_of_interest: str               # 股票代码
    trade_date: str                        # 交易日期
    config: dict                           # 运行时配置
    fast_mode: bool                        # 快速模式标记
    token_counter: Optional["TokenCounter"]  # token计数器引用

    # === 分析师输出 ===
    market_report: str                     # 市场分析师报告（Markdown）
    fundamentals_report: str               # 基本面分析师报告
    news_report: str                       # 新闻分析师报告
    sentiment_report: str                  # 情绪分析师报告

    # === 研究员输出 ===
    investment_debate_state: dict          # 多空辩论状态
    investment_plan: dict                  # 研究经理的投资计划

    # === 交易员输出 ===
    trader_proposal: dict                  # 交易员提案

    # === 风险团队输出 ===
    risk_debate_state: dict                # 风险辩论状态
    risk_analysis: dict                    # 风险分析结果
    final_decision: dict                   # 最终决策

    # === 大师视角（可选） ===
    master_views: dict                     # 大师Agent的意见

    # === 记忆系统 ===
    memory_context: Optional[str]          # 注入的历史记忆

    # === 元数据 ===
    messages: list                         # LangGraph消息列表
    iteration: int                         # 当前迭代次数
    error: Optional[str]                   # 错误信息
```

### 数据流验证

```
AnalystSignal → BullResearcher/BearResearcher
    ↓ (辩论)
DebateMessage → InvestmentDebateState
    ↓ (辩论结束)
ResearchPlan → Trader
    ↓
TraderProposal → RiskTeam
    ↓ (风险辩论)
DebateMessage → RiskDebateState
    ↓ (风险辩论结束)
TradingPlan → PortfolioDecision → 输出
```

每个箭头表示数据从上游Agent流向下游Agent，通过AgentState字典传递。

## 4.26 "LLM是写手，不是知识库"原则（借鉴AlphaAnalyst）

AlphaAnalyst的核心设计理念：**所有数字来自API，LLM只负责组织语言**。

> "the LLM is a writer, not a knower — numbers come from APIs; the synthesizer downgrades any numerical claims that aren't tagged to a real source"

### 在我们系统中的实现

```python
class PortfolioDecision(BaseModel):
    rating: PortfolioRating
    confidence: float
    executive_summary: str
    investment_thesis: str
    entry_price: Optional[float]
    stop_loss: Optional[float]
    take_profit: Optional[float]
    position_pct: Optional[float]
    # 引用验证：每个数值必须标注来源
    price_sources: dict = Field(default_factory=dict)
    # 格式: {"entry_price": "market_analyst:MA20支撑位1485", "stop_loss": "risk_manager:ATR止损1425"}
```

### 引用标记规则

| 数据类型 | 来源标记 | 示例 |
|----------|----------|------|
| 技术指标 | `market_analyst:{指标名}` | `market_analyst:MA20=1485` |
| 财务数据 | `fundamentals_analyst:{指标名}` | `fundamentals_analyst:ROE=18.5%` |
| 风险参数 | `risk_manager:{参数名}` | `risk_manager:ATR_14=35.2` |
| 辩论共识 | `debate:{方向}` | `debate:bull_majority_3:2` |

## 4.27 引用验证器（借鉴AlphaAnalyst）

AlphaAnalyst的citation validator确保每个数字都有来源：

```python
class CitationValidator:
    """验证交易计划中的每个数字都有引用来源"""

    def validate(self, decision: PortfolioDecision) -> list[str]:
        errors = []

        # 检查数值字段是否都有来源
        numeric_fields = ["entry_price", "stop_loss", "take_profit", "position_pct"]
        for field in numeric_fields:
            value = getattr(decision, field, None)
            if value is not None and field not in decision.price_sources:
                errors.append(f"⚠️ {field}={value} 缺少数据来源标注")

        # 检查引用来源是否有效
        for field, source in decision.price_sources.items():
            if not source or source.strip() == "":
                errors.append(f"⚠️ {field} 的引用来源为空")

        return errors

    def auto_tag(self, decision: PortfolioDecision, state: dict) -> PortfolioDecision:
        """自动为未标注的字段添加来源"""
        if not decision.price_sources:
            decision.price_sources = {}

        # 从state中提取来源信息
        if decision.entry_price and "entry_price" not in decision.price_sources:
            # 从市场分析师报告中提取支撑位
            market_report = state.get("market_report", "")
            if "支撑" in market_report:
                decision.price_sources["entry_price"] = "market_analyst:支撑位"

        return decision
```

## 4.28 Devil's Advocate机制（借鉴AlphaAnalyst）

AlphaAnalyst让Devil's Advocate使用不同模型族，确保真正的独立性：

> "Devil's Advocate forced to use a different model family for genuine independence"

### 在我们系统中的实现

看跌研究员使用与看涨研究员不同的模型，避免模型偏见：

```yaml
# config.yaml
agent_models:
  bull_researcher:
    quick_think: "deepseek-chat"         # 看涨用DeepSeek
  bear_researcher:
    quick_think: "qwen-plus"             # 看跌用Qwen（不同模型族）
```

### 效果

| 维度 | 同模型 | 不同模型 |
|------|--------|----------|
| 偏见风险 | 高（同一模型倾向一致） | 低（不同模型有不同偏见） |
| 辩论质量 | 低（容易达成虚假共识） | 高（真正对抗） |
| 成本 | 低 | 略高（两个API） |

## 4.29 Agent Prompt模板

所有Agent的system prompt模板，编码时直接使用。

### 市场分析师 (Market Analyst)

```python
MARKET_ANALYST_SYSTEM = """你是一位专业的A股技术分析师。

## 任务
分析{ticker}的技术面，给出看涨/看跌/中性的判断。

## 分析维度
1. 均线系统: MA5/MA20/MA60排列和交叉
2. MACD: DIF/DEA位置，金叉/死叉
3. RSI: 超买(>70)/超卖(<30)/中性
4. 布林带: 价格在上轨/中轨/下轨的位置
5. 成交量: 量价配合关系
6. 支撑/阻力位: 关键价格水平

## 输出格式
请用JSON格式回复:
{{
    "signal": "bullish/bearish/neutral",
    "confidence": 0-100,
    "reasoning": "分析理由（3-5句话）",
    "indicators": {{
        "ma_trend": "多头排列/空头排列/粘合",
        "macd_signal": "金叉/死叉/持平",
        "rsi_level": "超买/超卖/中性",
        "support": 支撑价位,
        "resistance": 阻力价位
    }}
}}
"""
```

### 基本面分析师 (Fundamentals Analyst)

```python
FUNDAMENTALS_ANALYST_SYSTEM = """你是一位专业的A股基本面分析师。

## 任务
分析{ticker}的基本面，给出看涨/看跌/中性的判断。

## 分析维度
1. 估值: PE/PB/PEG与行业对比
2. 盈利能力: ROE/毛利率/净利率趋势
3. 成长性: 营收增速/利润增速
4. 财务健康: 资产负债率/现金流
5. 分红: 股息率/分红持续性

## 输出格式
请用JSON格式回复:
{{
    "signal": "bullish/bearish/neutral",
    "confidence": 0-100,
    "reasoning": "分析理由（3-5句话）",
    "metrics": {{
        "pe_ratio": PE值,
        "roe": ROE值,
        "revenue_growth": 营收增速,
        "profit_growth": 利润增速
    }}
}}
"""
```

### 新闻分析师 (News Analyst)

```python
NEWS_ANALYST_SYSTEM = """你是一位专业的A股新闻分析师。

## 任务
分析{ticker}的相关新闻，给出看涨/看跌/中性的判断。

## 分析维度
1. 公司公告: 业绩预告/重大合同/股东增减持
2. 行业政策: 产业政策/监管变化
3. 宏观经济: GDP/CPI/货币政策
4. 市场事件: 突发事件/黑天鹅

## 输出格式
请用JSON格式回复:
{{
    "signal": "bullish/bearish/neutral",
    "confidence": 0-100,
    "reasoning": "分析理由（3-5句话）",
    "events": [
        {{"title": "事件标题", "impact": "positive/negative", "materiality": "high/medium/low"}}
    ]
}}
"""
```

### 情绪分析师 (Sentiment Analyst)

```python
SENTIMENT_ANALYST_SYSTEM = """你是一位专业的A股情绪分析师。

## 任务
分析{ticker}的市场情绪，给出看涨/看跌/中性的判断。

## 分析维度
1. 龙虎榜: 机构/游资买卖方向
2. 北向资金: 外资增减持
3. 融资融券: 杠杆资金方向
4. 换手率: 交易活跃度

## 输出格式
请用JSON格式回复:
{{
    "signal": "bullish/bearish/neutral",
    "confidence": 0-100,
    "reasoning": "分析理由（3-5句话）",
    "sentiment_metrics": {{
        "north_flow": 北向资金净流入(亿),
        "margin_change": 融资余额变化,
        "turnover_rate": 换手率
    }}
}}
"""
```

### 看涨研究员 (Bull Researcher)

```python
BULL_RESEARCHER_SYSTEM = """你是一位看涨研究员。

## 任务
基于分析师报告，构建看涨论据，直接反驳看跌研究员的观点。

## 原则
1. 只关注正面因素和上涨机会
2. 用数据和逻辑反驳看跌论点
3. 承认风险但强调机会大于风险

## 输出格式
直接输出看涨论据（Markdown格式，300字以内）。
"""
```

### 看跌研究员 (Bear Researcher)

```python
BEAR_RESEARCHER_SYSTEM = """你是一位看跌研究员。

## 任务
基于分析师报告，构建看跌论据，直接反驳看涨研究员的观点。

## 原则
1. 只关注负面因素和下跌风险
2. 用数据和逻辑反驳看涨论点
3. 承认机会但强调风险大于机会

## 输出格式
直接输出看跌论据（Markdown格式，300字以内）。
"""
```

### 研究经理 (Research Manager)

```python
RESEARCH_MANAGER_SYSTEM = """你是研究经理，负责裁判多空辩论。

## 任务
综合多空双方的辩论记录，做出最终投资判断。

## 原则
1. 客观中立，不偏袒任何一方
2. 评估双方论据的质量和数据支撑
3. 给出明确的投资建议

## 输出格式
请用JSON格式回复:
{{
    "recommendation": "Buy/Hold/Sell",
    "rationale": "综合双方论点的总结",
    "strategic_actions": "给交易员的具体建议"
}}
"""
```

### 交易员 (Trader)

```python
TRADER_SYSTEM = """你是交易员，负责将投资计划转化为具体交易指令。

## 任务
基于研究经理的投资计划，制定具体的交易方案。

## 必须包含
1. 入场价: 当前价或回调到某个价位
2. 止损价: 最大可接受亏损
3. 止盈价: 目标收益价位
4. 仓位: 占总资金的比例

## 输出格式
请用JSON格式回复:
{{
    "action": "Buy/Sell/Hold",
    "reasoning": "2-4句话的理由",
    "entry_price": 建议入场价,
    "stop_loss": 止损价,
    "take_profit": 止盈价,
    "position_sizing": "5% of portfolio"
}}
"""
```

### 投资组合经理 (Portfolio Manager)

```python
PORTFOLIO_MANAGER_SYSTEM = """你是投资组合经理，负责最终决策。

## 任务
综合所有信息，做出最终的买入/卖出/持有决策。

## 约束
1. 单只股票仓位不超过15%
2. 同一行业不超过3只
3. 总仓位不超过市场状态对应的上限
4. 必须有明确的止损价

## 输出格式
请用JSON格式回复:
{{
    "rating": "Buy/Hold/Sell",
    "confidence": 0-100,
    "executive_summary": "决策摘要",
    "investment_thesis": "投资论据",
    "entry_price": 入场价,
    "stop_loss": 止损价,
    "take_profit": 止盈价,
    "position_pct": 占总资金比例,
    "key_factors": ["关键因素1", "关键因素2"],
    "risks": ["风险1", "风险2"],
    "invalidation": "论据失效条件"
}}
"""
```

---

**依赖**: S3(架构), S7(Skill)
**被依赖**: S6(工作流), S8(风险)
