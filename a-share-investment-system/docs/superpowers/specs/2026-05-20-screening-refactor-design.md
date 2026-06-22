# 选股模块重构设计 — AI 驱动的深度分析 + 交易计划生成

## 1. 背景与现状

### 当前架构

```
StockScreener (4 级流水线)
├─ Stage 0: 加载全市场股票池
├─ Stage 1: Hard Filter (风格专属条件)
├─ Stage 2: Stage3 大师量化评分 (MasterAgentRegistry, 17 个纯 Python 分析器)
└─ Stage 3: Stage4 Agent 工作流 (AgentWorkflowService, 简单的 HTTPX LLM + 规则)

问题：
1. Stage3 和 Stage4 彼此独立 — 大师输出只有分数，LLM 看不到推理细节
2. 大师调用硬编码 (每种 style 固定几个大师)
3. SkillEngine 的知识被被动注入为"参考"，而非主动调用
4. 最终输出是个股推荐列表，不是完整的交易计划
5. 没有考虑持仓上下文
```

### 参考项目 (quant-agents/TradingAgents-CN)

- LangGraph StateGraph 编排 14 个 Agent 节点
- Skill 作为**行为指令**注入 LLM 系统提示，而非参考知识
- 看涨/看跌辩论 → 研究经理 → 交易员 → 风险辩论 → 风险经理
- PortfolioAgent 在个股分析后进行组合级分析
- 最终输出为结构化交易决策

## 2. 整体架构

```
全市场 5000+ 只
        │
        ▼ 用户定义的量化初筛 (HardFilter)
        ├─ 短期策略: 成交额>1亿, 5日涨幅>5%, 量比>1.5, 均线多头...
        ├─ 中期策略: 净利润增长>50%, 市值50-500亿, 年线上方...
        ├─ 长期策略: 连续3年ROE>15%, 现金流/净利润>1, 分红>20%...
        └─ 负面排除: 非ST, 上市>250天, 审计无保留...
        │
        ▼ 20-30 只候选股
        │
        ▼ TradingStrategyOrchestrator (AI 深度分析层)
        ├─ 阶段 1: StockAgent (每只候选股)
        │   ├─ Tool: master_analyze (自主选择大师)
        │   └─ Tool: skill_knowledge (按需注入技能)
        ├─ 阶段 2: PortfolioAgent (组合级分析)
        │   ├─ 读取全部个股分析意见 + 当前持仓
        │   └─ 仓位分配 / 行业集中度 / 相关性
        └─ 阶段 3: DecisionAgent (生成最终交易计划)
            ├─ 融合: 个股分析 + 组合评估 + 持仓
            └─ 输出: 完整交易计划
        │
        ▼
        └─ 交易计划 → 保存到 AnalysisTask + SSE 推送
```

## 3. 组件详细设计

### 3.1 HardFilter — 量化初筛

**三个策略模板**（来自用户定义的量化标准）：

**短期 (1d-4w):** `成交额>1亿, 收盘价>20日均线, 20日均线>60日均线, 5日涨幅>5%, 成交量/昨日成交量>1.5, 主力净流入>1000万, 非ST`

**中期 (1-12m):** `预告净利润同比增长率>50%, 净利润现金含量>80%, 市盈率<行业均值, 总市值50-500亿, 60日涨幅>20%, 股价>年线, 非ST`

**长期 (1y+):** `连续3年ROE>15%, 连续3年经营性现金流/净利润>1, 连续5年股利支付率>20%, 市盈率近5年分位<30%, 资产负债率<60%, 非ST`

**通用负面排除:** `非ST/*ST, 上市天数>250, 审计标准无保留意见, 诉讼仲裁/净资产<10%`

所有阈值从 `config/config.yaml` 读取，支持动态调整。

### 3.2 TradingStrategyOrchestrator — 编排器

```python
class TradingStrategyOrchestrator:
    """AI 驱动的深度分析编排器"""

    def __init__(self, style: str, portfolio_holdings: dict = None):
        self.style = style
        self.portfolio_holdings = portfolio_holdings or {}
        self.llm = self._init_llm()

    async def run(self, candidates: list[dict]) -> TradingPlan:
        """
        编排流程:
        1. 并行运行 StockAgent 分析每只候选股
        2. 运行 PortfolioAgent 分析组合
        3. 运行 DecisionAgent 生成最终交易计划
        """
        # 阶段1: 并行个股分析
        stock_opinions = await self._parallel_analyze(candidates)

        # 阶段2: 组合级分析
        portfolio_assessment = await self._portfolio_analyze(stock_opinions)

        # 阶段3: 最终交易计划
        trading_plan = await self._decide(stock_opinions, portfolio_assessment)

        return trading_plan
```

### 3.3 StockAgent — AI 个股分析师

这是核心的"AI 直接调用 master agent 和 skill"的组件。

**Tool 定义:**

| Tool 名 | 函数 | 用途 |
|---------|------|------|
| `get_master_list` | 返回所有大师的名称+风格描述 | Agent 了解可用的大师资源 |
| `master_analyze` | 调用指定大师分析器 | 获取量化评分+推理 |
| `skill_knowledge` | 注入指定技能知识 | 获取分析框架/方法论 |
| `get_stock_data` | 获取实时行情+基本面 | 补充分析数据 |

**Agent 推理流程 (示例):**

```
输入: {"code": "000xxx", "price": 12.5, "turnover_rate": 15, ...}

Step 1: 调用 get_master_list()
        → 看到可用的 17 位大师及其风格描述

Step 2: 判断"换手率15%, 涨幅8%, 短期资金驱动型股票"
        → 调用 master_analyze("000xxx", ["limit_up_master", "turtle_master"])
        → 返回:
           limit_up_master: {score: 78, signal: "买入", reasoning: "..."}
           turtle_master:   {score: 72, signal: "买入", reasoning: "..."}

Step 3: "大师评分不错，但需要评估风险"
        → 调用 master_analyze("000xxx", ["risk_sentinel"])
        → 返回: {score: 65, signal: "中性", details: {"risk_score": 35}}

Step 4: "换手率偏高有风险，需要塔勒布的反脆弱框架"
        → 调用 skill_knowledge("taleb-perspective", "000xxx")
        → 返回塔勒布的风险评估方法论文本

Step 5: 综合所有信息，输出结构化分析意见:
        {
          "stock_code": "000xxx",
          "overall_score": 74,
          "signal": "买入",
          "masters_used": ["limit_up_master(78)", "turtle_master(72)", "risk_sentinel(65)"],
          "skills_injected": ["taleb-perspective"],
          "entry": {"price_range": "12.0-12.8", "timing": "放量突破确认"},
          "stop_loss": "11.5 (-8%)",
          "take_profit": "15.0 (+20%)",
          "position_size": "轻仓(10%)",
          "reasoning": "..."
        }
```

**取消硬编码的关键：** Agent 通过 `get_master_list()` 工具在运行时动态了解可用大师，不再需要 `stage3_master_agents` 配置。

**Skill 如何被调用（具体机制）：**

借鉴 quant-agents 的 `SkillAgent` 模式，但简化：

```python
# 将 SkillEngine 包装为 LLM Tool
skill_tool = Tool(
    name="skill_knowledge",
    description="获取指定投资技能的分析框架。可用技能: buffett(巴菲特价值投资), munger-perspective(芒格思维), taleb-perspective(塔勒布反脆弱), financial-health(财务健康), industry-competition-moat(行业竞争护城河), risk-warning-catalysts(风险预警), valuation-investment-strategy(估值策略)...",
    parameters={
        "skill_name": {"type": "string", "description": "技能名称"},
        "context": {"type": "string", "description": "上下文(股票代码或分析焦点)"},
    },
    func=lambda skill_name, context: skill_engine.inject_knowledge(skill_name, context)
)
```

Agent 在分析过程中按需调用，每次调用返回格式化的知识文本供 Agent 推理。

### 3.4 PortfolioAgent — 组合分析师

参考 quant-agents 的 `PortfolioAgent`，在全部个股分析完成后运行。

**输入:** 所有候选股的 StockAgent 分析意见 + 当前持仓

**职责:**
1. 分析行业集中度 (单行业 > 40% 预警)
2. 检查个股相关性 (同向高相关提示)
3. 建议仓位权重分配
4. 结合持仓做增减判断
5. 输出组合风险评估

```python
输出示例:
{
  "portfolio_risk_score": 6,       # 1-10
  "sector_exposure": {"消费": 35%, "科技": 25%, ...},
  "position_plan": [
    {"code": "000xxx", "weight": 0.15, "action": "新开仓"},
    {"code": "600519", "weight": 0.20, "action": "持有不变"},
    {"code": "300xxx", "weight": 0.10, "action": "加仓至0.15"},
  ],
  "warnings": ["科技板块集中度偏高"]
}
```

### 3.5 DecisionAgent — 最终决策者

生成完整的**交易计划**（灵感来自 quant-agents 的 RiskManager + Trader）。

**输入:** 个股分析意见 + 组合评估 + 持仓

**输出 (TradingPlan):**

```json
{
  "market_assessment": {
    "regime": "震荡偏多",
    "risk_level": "中等",
    "max_total_position": 0.7
  },

  "portfolio_context": {
    "cash_ratio": 0.35,
    "current_positions": [
      {"code": "600519", "name": "贵州茅台", "qty": 100, "cost": 1800,
       "pnl_pct": 5.2, "suggested_action": "持有不变",
       "reasoning": "大师评分78分，持仓盈利5%，建议继续持有"}
    ]
  },

  "execution_plan": {
    "immediate": {
      "summary": "首批建仓2只，减仓1只",
      "orders": [
        {"code": "000xxx", "action": "买入", "qty": 5000,
         "limit_price": "≤12.80", "time": "开盘后30min",
         "weight": "15%", "confidence": "高",
         "stop_loss": "11.50", "take_profit": "15.00",
         "reasoning": "涨停大师78分+海龟72分，换手率放量突破..."}
      ]
    },
    "conditional": [
      {"condition": "000xxx 3日内涨幅>5%", "action": "加仓2000股", "timing": "D+3"},
      {"condition": "大盘单日跌>2%", "action": "暂停所有买入"}
    ],
    "monitoring": {
      "key_signals": ["北向资金", "成交额变化"],
      "review_frequency": "每日收盘后"
    }
  },

  "risk_management": {
    "circuit_breaker": "单股亏损>8%强制止损",
    "portfolio_stop": "总回撤>5%减仓至50%",
    "key_risks": ["某某行业政策风险", "某某股质押比例偏高"]
  }
}
```

## 4. 与现有系统的关系

### 保留的现有代码

| 组件 | 保留/改造 | 说明 |
|------|-----------|------|
| `StockScreener` | 改造 | 保留 run() 入口，替换 Stage3+Stage4 为 Orchestrator |
| `MasterAgentRegistry` | 保留 | 17 位大师分析器不变，包装为 Tool |
| `SkillEngine` | 保留 | 继续从 SKILL.md 发现知识，包装为 Tool |
| `skills.py` | 保留 | SkillRegistry 保留 |
| `analysis_task` 模型 | 保留 | 扩展以存储交易计划 |
| `/api/screening` | 改造 | 接入新的 Orchestrator |

### 新建文件

| 文件 | 用途 |
|------|------|
| `services/trading_orchestrator.py` | TradingStrategyOrchestrator 编排器 |
| `services/agents/stock_agent.py` | StockAgent (个股分析 Agent) |
| `services/agents/portfolio_agent.py` | PortfolioAgent (组合分析 Agent) |
| `services/agents/decision_agent.py` | DecisionAgent (交易计划生成) |
| `services/agents/base_agent.py` | 工具注册基类 |
| `services/trading_plan.py` | TradingPlan 数据模型 |
| `services/hard_filter.py` | 用户定义的量化初筛（替代现有 _hard_filter_xx） |

### 改造文件

| 文件 | 改造内容 |
|------|----------|
| `services/stock_screener.py` | 替换 Stage3/Stage4 为 TradingStrategyOrchestrator 调用 |
| `api/routes/screening.py` | 调整 SSE 进度事件，适配新输出 |
| `config/config.yaml` | 新增三层初筛阈值配置 |

### 可删除/废弃的代码

| 文件/函数 | 原因 |
|-----------|------|
| `services/agent_workflow.py` | 被 TradingStrategyOrchestrator 替代 |
| `StockScreener._stage3_deep_analyze()` | 被 AI 分析替代 |
| `StockScreener._run_stage4_agent_workflow()` | 被替代 |
| `StockScreener._stage3_enhanced_*()` | 硬编码大师组合，被取消 |

## 5. API 变化

### `/api/screening/run/stream` SSE 事件调整

```
当前: 阶段0 → Hard Filter → Stage3 → Stage4 → 完成
新:   阶段0 → Hard Filter → StockAgent(并行) → PortfolioAgent → DecisionAgent → 完成

进度百分比:
  0%  : 开始
  5%  : 全市场加载完成
  15% : Hard Filter 完成 (N只候选)
  35% : StockAgent 分析完成 (每个完成的个股发送事件)
  60% : PortfolioAgent 完成
  80% : DecisionAgent 完成
  100%: 交易计划保存完成
```

### 新增端点

| 端点 | 方法 | 用途 |
|------|------|------|
| `/api/screening/plan` | GET | 获取最新交易计划 |
| `/api/screening/plan/{run_id}` | GET | 获取指定 run 的交易计划 |

## 6. 数据流

```
Request (GET /api/screening/run/stream?style=momentum)
  │
  ▼
StockScreener.run()
  ├─ _load_universe()           → 5000+ stocks
  ├─ HardFilter.apply(style)    → 20-30 stocks (使用用户定义的量化条件)
  │
  ▼
TradingStrategyOrchestrator.run(candidates, portfolio)
  ├─ StockAgent.analyze()  × N  (并行)
  │   ├─ master_analyze()   → MasterAgentRegistry
  │   ├─ skill_knowledge()  → SkillEngine
  │   └─ → StockOpinion[]
  ├─ PortfolioAgent.analyze(opinions, portfolio)
  │   └─ → PortfolioAssessment
  └─ DecisionAgent.decide(opinions, assessment, portfolio)
      └─ → TradingPlan
  │
  ▼
SSE 推送到前端 + 保存到 AnalysisTask 表
```

## 7. Edge Cases 与降级策略

| 场景 | 处理 |
|------|------|
| LLM API 不可用 | 降级到纯 MasterAgent 评分 + 规则化交易计划 |
| 候选股 < 3 只 | 直接使用规则生成简单计划，跳过 AI 分析 |
| 大师分析器数据不足 | 该大师返回 `data_quality: insufficient`，Agent 忽略该评分 |
| 持仓为空 | PortfolioAgent 跳过持有分析 |
| SSE 连接中断 | 后台继续执行，结果可通过 `/api/screening/plan` 查询 |
| 并行分析 token 限流 | 使用信号量控制并发数 (默认 3) |

## 8. 配置项 (config.yaml)

```yaml
screening:
  styles:
    short_term:
      hard_filter:
        min_amount: 100000000          # 成交额 >1亿
        min_turnover_rate: 1.5         # 量比 >1.5
        min_change_5d: 5               # 5日涨幅 >5%
        require_uptrend: true          # 均线多头排列
        min_net_inflow: 10000000       # 主力净流入 >1000万
        ...
    mid_term:
      ...
    long_term:
      ...
  deep_analysis:
    enabled: true
    model: "siliconflow:deepseek-ai/DeepSeek-R1"
    parallel_limit: 3                  # 并行分析数
    skill_candidates:                  # Agent 可选的技能列表
      - buffett
      - munger-perspective
      - taleb-perspective
      - financial-health
      - industry-competition-moat
      - risk-warning-catalysts
      - valuation-investment-strategy
```

## 9. 与 quant-agents 的关键设计区别

| 维度 | quant-agents | 本方案 |
|------|-------------|--------|
| 工作流框架 | LangGraph StateGraph | 轻量编排器 (asyncio + Tool) |
| 依赖 | langchain, chromadb, 大量包 | 最低依赖，复用现有 httpx |
| 分析师数量 | 4 个分析师各一个大模型调用 | 1 个 Agent 但调用多次 Tool |
| 辩论模式 | 看涨/看跌交替辩论 + 风险辩论 | 不需要 (A股短线不适用多轮辩论) |
| 记忆系统 | ChromaDB 向量记忆 | 简化 (session 级缓存) |
| 组合分析 | 通过 PortfolioAgent | 相同模式 |
| 最终输出 | 单个交易决策 | 完整交易计划 (含分批执行) |
