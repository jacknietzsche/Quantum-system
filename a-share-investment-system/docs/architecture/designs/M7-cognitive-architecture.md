# Module 7: AI 认知架构 — 从打分器到持续学习的分析主体

**前置**: M1-M6（当前架构）  
**用途**: 重新定义 AI 在系统中的角色，使其从"顾问"变为"具备持续学习、概率思维和主动验证能力的分析主体"  
**状态**: Draft | **日期**: 2026-06-12  
**来源**: 架构评审 — 10 项核心改进建议

---

## 0. 核心问题

当前架构的根本缺陷：**把 AI 当成结论生成器，而不是认知架构。**

17 位大师并行评分 → AI 深度分析 → 多空辩论 → 评分+信号。这本质上是用大师名字做标签的因子评分，加上一层 LLM 润色。专业投资人不是这样工作的。

专业投资人的工作方式：
1. 构建世界观（宏观叙事）
2. 识别当前市场的主要矛盾
3. 测试特定假设
4. 分配概率
5. 在风险预算内下注

当前系统没有"世界观"演化，没有概率校准，没有假设检验闭环。单靠静态大师策略和尾盘 K 线数据，能击败的只有散户的情绪，击败不了市场效率。

---

## 1. 认知架构层：AI 必须具备连续、可演化的市场世界观

### 1.1 问题

当前系统每天"市场感知"输出牛/熊/震荡 + 风险等级。这是静态快照。专业投资人脑子里有一张不断更新的因果图。

### 1.2 设计：AI 持久状态与宏观叙事引擎

给 AI 一个**持久化状态对象**（State Object），跨交易日继承。

#### 状态结构

```python
class CognitiveState:
    """AI 认知状态 — 跨交易日持久化"""
    
    # 当前主导叙事
    current_narrative: Narrative
    
    # 叙事历史演化链
    narrative_history: list[Narrative]  # 最近 30 个交易日
    
    # 宏观环境状态
    macro_environment: MacroEnvironment
    
    # 策略权重（由叙事推导，非人工设置）
    strategy_weights: dict[str, float]
    
    # 风险预算
    risk_budget: RiskBudget
    
    # 假设跟踪
    active_hypotheses: list[Hypothesis]
    
    # 决策日志
    decision_log: list[DecisionRecord]


class Narrative:
    """市场叙事"""
    
    id: str
    title: str  # 如"政策底与市场底的博弈"
    description: str  # 叙事的完整描述
    confidence: float  # 0-1，置信度
    key_indicators: list[str]  # 验证此叙事的关键指标
    indicator_values: dict[str, float]  # 这些指标的当前值
    birth_date: str  # 叙事形成日期
    last_validated: str  # 最近一次验证日期
    parent_narrative: str | None  # 前一个叙事（演化链）
    death_reason: str | None  # 叙事消亡原因


class MacroEnvironment:
    """宏观环境状态"""
    
    # 利率环境
    shibor_1m: float  # 1 个月 Shibor
    bond_10y: float  # 10 年期国债收益率
    credit_spread: float  # 信用利差
    
    # 流动性
   社融增速: float  # 社会融资规模增速
    m2增速: float  # M2 增速
    
    # 资金流
    northbound_cumulative: float  # 北向资金累计流向
    margin_balance: float  # 融资余额
    margin_buy_ratio: float  # 融资买入占成交额比
    
    # 汇率与外部
    usdcny: float  # 美元/人民币
    vix: float  # 波动率指数（用恒生波幅替代）
    
    # 大宗商品
    copper: float  # 铜价
    crude: float  # 原油
    
    # 市场结构
    breadth: float  # 市场宽度（涨跌比）
    turnover_rate: float  # 全市场换手率
    limit_up_count: int  # 涨停家数
    limit_down_count: int  # 跌停家数
```

#### 每日更新流程

```
收盘数据到达
  ↓
LLM 读取当日数据 + 当前叙事 + 宏观环境
  ↓
判断：当前数据是否支持当前叙事？
  ├── 支持 → 更新叙事置信度，记录验证结果
  └── 不支持 → 触发"叙事危机"分析
        ↓
      生成新叙事候选
        ↓
      对比历史类似叙事的后续表现
        ↓
      选择最佳新叙事，记录演化链
        ↓
      基于新叙事重新推导策略权重
```

#### 叙事驱动的策略权重

不是人工设置"价值60%、成长25%"，而是 AI 基于叙事推导：

| 叙事类型 | 自动推导的权重 |
|----------|----------------|
| "存量博弈，偏防御" | Graham +40%, Taleb +30%, Wood -50% |
| "政策底确认，价值重估" | Buffett +30%, Graham +20%, Lynch -20% |
| "AI 泡沫末端，杀估值" | Wood -60%, Burry +40%, Graham +30% |
| "流动性宽松，成长反弹" | Lynch +40%, Wood +30%, Graham -30% |

---

## 2. AI 分析深度重构：从多空辩论到反事实推理与情景规划

### 2.1 问题

当前 AI 深度分析是：看涨论点 vs 看跌论点 + AI 裁决。太浅，等于让 LLM 左右互搏然后选一边，极易产生幻觉或被最近的文本段落带偏。

### 2.2 设计：反事实推理引擎

对每只候选股，AI 必须回答三个反事实问题：

#### 反事实问题模板

```
问题 1（证伪预警）：
"如果我对这只股票最看好的核心逻辑（例如：新产品放量）在未来两个季度被证伪，
那最早会出现在哪个先行指标上？我现在能看到这个指标的什么预警吗？"

问题 2（条件要求）：
"如果我判断这只股票会涨 30%，市场需要发生哪些现在并没有 price-in 的事情？"

问题 3（失败归因）：
"如果这只股票下跌 20%，最可能的原因是什么？
这种原因是否与当前我的宏观叙事矛盾？"
```

#### 输出结构

```python
class CounterfactualAnalysis:
    """反事实分析结果"""
    
    stock_code: str
    
    # 问题 1：证伪预警
    core_logic: str  # 最核心的看涨逻辑
    leading_indicator: str  # 最早能验证的先行指标
    current_warning: str  # 该指标当前的预警信号
    falsification_timeline: str  # 预计证伪时间窗口
    
    # 问题 2：条件要求
    required_events: list[str]  # 需要发生但尚未发生的事件
    market_pricing_gap: str  # 市场当前定价与目标的差距
    
    # 问题 3：失败归因
    failure_scenario: str  # 最可能的失败原因
    narrative_conflict: bool  # 是否与当前宏观叙事矛盾
    max_drawdown_estimate: float  # 估计最大回撤
    
    # 预警清单
    warning_checklist: list[WarningItem]  # 可监测的预警指标
```

#### 预警清单关联到跟踪面板

```
贵州茅台 (600519)
├── 核心逻辑：批价稳中有升，直营占比提升
├── 证伪预警：
│   ├── 指标：批发价周度变化
│   ├── 当前值：2650 元/瓶（持平）
│   └── 预警阈值：连续 2 周下跌 >2%
├── 条件要求：
│   ├── 需要：Q2 直营收入占比 >35%
│   └── 当前：Q1 为 32%（接近但未达标）
└── 失败场景：
    ├── 原因：宏观消费降级超预期
    └── 与叙事矛盾：是（当前叙事是"消费复苏"）
```

### 2.3 设计：概率化输出

抛弃 strong_buy / buy / hold 这类模糊类别。要求 AI 输出：

```python
class ProbabilisticRecommendation:
    """概率化推荐"""
    
    stock_code: str
    
    # 概率估计
    excess_return_probability: float  # 未来 20 个交易日超越基准的概率
    expected_excess_return: float  # 预期超额收益（%）
    expected_drawdown: float  # 预期最大回撤（%）
    asymmetry_ratio: float  # 不对称比 = 预期上涨 / 预期下跌
    
    # 校准度
    calibration_score: float  # 基于类似情景的历史胜率
    similar_cases_count: int  # 类似案例数量
    similar_cases_avg_return: float  # 类似案例平均收益
    
    # 概率分布（可选）
    return_distribution: dict  # {percentile: return} 分位数分布
    
    # 置信度
    confidence: float  # AI 对自身判断的置信度
    confidence_reasoning: str  # 为什么这个置信度
```

#### 概率校准机制

要求系统自动完成，不是让 AI 猜：

```
对于每只候选股：
1. 提取过去 5 年中具有类似特征的时段：
   - 类似技术形态（K 线模式、均线位置）
   - 类似基本面特征（PE/PB/ROE 分位数）
   - 类似宏观背景（利率环境、市场状态）
2. 计算这些类似时段后续 5/10/20 日的收益分布
3. AI 仅解释这个分布，不猜测概率
```

---

## 3. AI 自我进化闭环：实盘/模拟反馈与大师策略动态权重

### 3.1 问题

Agent 健康度只展示 7 天/30 天准确率，大师策略是静态的。完全浪费了 AI 的学习潜力。

### 3.2 设计：决策-结果反馈数据库

```python
class DecisionRecord:
    """决策记录 — 每笔 AI 建议"""
    
    id: str
    date: str  # 建议日期
    stock_code: str
    action: str  # buy / sell / hold
    
    # 决策上下文
    macro_state: MacroEnvironment  # 当时的宏观状态
    narrative: Narrative  # 当时的叙事
    stock_features: dict  # 该股当时的特征
    master_scores: dict  # 各大师评分
    ai_probability: ProbabilisticRecommendation  # AI 给出的概率
    
    # 结果验证（5/10/20 个交易日后自动填写）
    result_5d: TradeResult | None
    result_10d: TradeResult | None
    result_20d: TradeResult | None


class TradeResult:
    """交易结果"""
    
    return_pct: float  # 实际收益率
    excess_return: float  # 超额收益（vs 沪深 300）
    max_drawdown: float  # 期间最大回撤
    triggered_stop_loss: bool  # 是否触发止损
    peak_return: float  # 最高收益（最大盈利回吐）
```

### 3.3 设计：元 AI（Meta-Agent）

每周分析决策日志，识别系统性失败模式：

```python
class MetaAgent:
    """元 AI — 分析决策日志，调整策略权重"""
    
    def weekly_review(self, decision_log: list[DecisionRecord]) -> MetaAnalysis:
        """每周复盘"""
        
        # 1. 识别失败模式
        failures = self._identify_failure_patterns(decision_log)
        # 例："当防御性叙事叠加高波动环境时，Graham 策略推荐的股票实际超额为负"
        
        # 2. 分析原因
        for failure in failures:
            root_cause = self._analyze_root_cause(failure)
            # 例："因为此时这类股票往往是被错杀的周期股而非真正的防御标的"
        
        # 3. 生成调整建议
        adjustments = self._generate_adjustments(failures)
        # 例：下次类似情景下 Graham 权重 -30%，Taleb 权重 +20%
        
        # 4. 生成临时规则
        new_rules = self._generate_temporary_rules(failures)
        # 例：当波动率 >30% 且叙事为防御性时，排除周期股
        
        return MetaAnalysis(
            failures=failures,
            adjustments=adjustments,
            new_rules=new_rules,
        )
```

### 3.4 设计：动态大师调度

废除固定的 17 位大师并行评分，改为动态智能调度：

```
当前宏观叙事: "政策底确认，价值重估"
当前波动率: 中等 (20-30%)
  ↓
Meta-Agent 决策：
  激活大师: Buffett, Graham, Lynch（3 位）
  原因: 价值重估叙事下，这 3 位的大师框架最相关
  权重: Buffett 40%, Graham 35%, Lynch 25%
  ↓
要求这 3 位大师给出基于当前环境的专门论述
而不是套用其通用语录
```

#### 临时复合策略生成

AI 可以创建临时复合策略：

```
当前市场类似于 2016 年供给侧改革启动期的"价值重估+高波动"
  ↓
生成临时混合评分函数：
  - Graham 的安全边际（权重 40%）：筛选低估值标的
  - Livermore 的突破确认（权重 30%）：确认趋势启动
  - Taleb 的反脆弱（权重 30%）：排除尾部风险高的标的
  ↓
这个临时策略会被记录，事后由 Meta-Agent 验证其有效性
```

---

## 4. 主动信息猎取与另类数据处理

### 4.1 问题

数据源仅限于量价和基础财务。专业投资人会主动收集情报。

### 4.2 设计：AI 驱动的主动信息检索

```python
class InformationHunter:
    """AI 驱动的信息猎手"""
    
    def generate_queries(
        self, 
        candidates: list[str], 
        holdings: list[str],
        narrative: Narrative,
    ) -> list[SearchQuery]:
        """AI 生成每日信息查询问题"""
        
        queries = []
        
        for stock in candidates + holdings:
            # AI 基于叙事和该股特征，生成具体问题
            query = self.llm.generate(
                f"当前市场叙事: {narrative.title}\n"
                f"股票: {stock}\n"
                f"请生成 3-5 个具体的信息查询问题，用于验证或证伪当前的投资逻辑。"
            )
            queries.extend(query)
        
        return queries
    
    def search_and_summarize(self, queries: list[SearchQuery]) -> list[InfoDigest]:
        """搜索并摘要"""
        
        results = []
        for q in queries:
            # 搜索新闻 API
            raw = self.news_api.search(q.text)
            
            # AI 摘要
            summary = self.llm.summarize(raw, q.context)
            
            results.append(InfoDigest(
                query=q,
                source=q.news_api,
                summary=summary,
                freshness=self._calc_freshness(raw),
                relevance_score=self._calc_relevance(summary, q),
            ))
        
        return results
```

#### 信息源

| 源 | 用途 | 优先级 |
|----|------|--------|
| 财新/华尔街见闻 | 宏观政策、行业动态 | P0 |
| 金十数据 | 实时快讯 | P0 |
| 互动易/e互动 | 公司问答、董秘回复 | P1 |
| 研报摘要 | 券商观点 | P1 |
| 社交媒体情绪 | 散户情绪 | P2 |

### 4.3 设计：资金流和微观结构信号

```python
class MicrostructureSignals:
    """微观结构信号"""
    
    # 大单/小单资金流
    big_order_net: float  # 大单净流入
    small_order_net: float  # 小单净流入
    order_divergence: float  # 大小单分歧度
    
    # 融资融券
    margin_balance_change: float  # 融资余额变化
    short_balance_change: float  # 融券余额变化
    margin_buy_ratio: float  # 融资买入占成交额比
    
    # 北向资金
    northbound_net: float  # 北向净流入
    northbound_cumulative_5d: float  # 5 日累计
    
    # AI 解释
    ai_interpretation: str  # AI 对这些信号的解释
    # 例："股价滞涨但融资买入激增，为看跌背离信号"
```

---

## 5. AI 作为执行教练和风控的动态协商者

### 5.1 问题

风控是硬规则：单股亏损 >8% 建议止损。这是上世纪 90 年代的散户工具水平。

### 5.2 设计：头寸规模与风险预算的动态 AI 协商

```python
class DynamicPositionSizing:
    """动态仓位计算"""
    
    def calculate(
        self,
        stock: str,
        narrative: Narrative,
        portfolio: Portfolio,
        volatility: float,
        liquidity: float,
    ) -> PositionRecommendation:
        """AI 动态计算仓位"""
        
        # 1. Kelly 公式基础仓位
        kelly_base = self._kelly_formula(
            win_prob=stock.excess_return_probability,
            win_size=stock.expected_excess_return,
            lose_size=stock.expected_drawdown,
        )
        
        # 2. 叙事置信度调整
        narrative_adj = self._narrative_adjustment(
            kelly_base, narrative.confidence
        )
        
        # 3. 组合集中度调整
        concentration_adj = self._concentration_adjustment(
            narrative_adj, portfolio
        )
        
        # 4. 流动性冲击成本调整
        liquidity_adj = self._liquidity_adjustment(
            concentration_adj, liquidity
        )
        
        # 5. 输出最终仓位
        final_position = liquidity_adj
        
        return PositionRecommendation(
            kelly_suggested=kelly_base,
            narrative_adjusted=narrative_adj,
            concentration_adjusted=concentration_adj,
            liquidity_adjusted=liquidity_adj,
            final_position=final_position,
            reasoning=self._explain_adjustments(
                kelly_base, narrative_adj, 
                concentration_adj, liquidity_adj
            ),
        )
```

### 5.3 设计：动态止损

止损不应是死的 -8%。AI 需要根据该股历史波动率结构和近期关键技术位，动态设定：

```python
class DynamicStopLoss:
    """动态止损"""
    
    def calculate(
        self,
        stock: str,
        entry_price: float,
        current_price: float,
        volatility: float,
        key_levels: list[float],  # 关键技术位
        initial_logic: str,  # 最初推荐逻辑
    ) -> StopLossRecommendation:
        
        # 技术止损：基于波动率和关键位
        technical_stop = self._technical_stop_loss(
            current_price, volatility, key_levels
        )
        
        # 逻辑止损：基于推荐逻辑的失效条件
        logic_stop = self._logic_stop_loss(
            initial_logic, stock
        )
        
        # 选择更紧的止损
        final_stop = max(technical_stop, logic_stop)
        
        return StopLossRecommendation(
            technical_stop=technical_stop,
            logic_stop=logic_stop,
            final_stop=final_stop,
            stop_type="technical" if technical_stop > logic_stop else "logic",
            reasoning=self._explain_stop_choice(
                technical_stop, logic_stop, final_stop
            ),
        )
```

### 5.4 设计：情景压力测试

每日针对持仓，AI 运行至少三种情景：

```python
class StressTest:
    """情景压力测试"""
    
    def run_daily(self, portfolio: Portfolio) -> StressTestResult:
        """每日压力测试"""
        
        scenarios = [
            # 场景 1：流动性危机（如 2015 年 7 月）
            self._liquidity_crisis(portfolio),
            
            # 场景 2：风格极致反转
            self._style_reversal(portfolio),
            
            # 场景 3：黑天鹅（重仓股被立案调查）
            self._black_swan(portfolio),
        ]
        
        return StressTestResult(
            scenarios=scenarios,
            max_loss=max(s.expected_loss for s in scenarios),
            survival_probability=self._calc_survival(scenarios),
            action_plans=[s.action_plan for s in scenarios],
        )
    
    def _liquidity_crisis(self, portfolio: Portfolio) -> Scenario:
        """流动性危机场景"""
        # 模拟 2015 年 7 月的市场环境
        # 计算组合回撤
        # 识别哪些股票会跌停卖不出
        ...
    
    def _style_reversal(self, portfolio: Portfolio) -> Scenario:
        """风格极致反转场景"""
        # 假设最集中的因子突然失效
        # 计算最大损失路径
        ...
    
    def _black_swan(self, portfolio: Portfolio) -> Scenario:
        """黑天鹅场景"""
        # 假设重仓股被立案调查，一天跌 20%
        # 计算组合能否活下来
        ...
```

#### Dashboard 展示

```
┌─ 压力测试 ──────────────────────────────────────┐
│                                                  │
│  场景 1: 流动性危机 (2015.7 情景)                │
│  预计回撤: -12.3%    可能跌停: 3 只              │
│  应对方案: 提前减仓高 Beta 股，保留现金缓冲      │
│                                                  │
│  场景 2: 风格反转 (成长→价值)                    │
│  预计回撤: -8.7%     受影响: 5 只成长股          │
│  应对方案: 增加价值因子暴露，降低成长集中度      │
│                                                  │
│  场景 3: 黑天鹅 (重仓股被调查)                   │
│  预计回撤: -6.2%     单股最大损失: -20%          │
│  应对方案: 单股仓位已控制在 15% 以内，可承受      │
│                                                  │
│  组合生存概率: 98.5%    建议: 维持当前仓位        │
└──────────────────────────────────────────────────┘
```

---

## 6. 实施优先级

| 优先级 | 模块 | 依赖 | 工时估计 |
|--------|------|------|----------|
| **P0** | 反事实推理引擎 | 无 | 3-5 天 |
| **P0** | 概率化输出 | 回测数据库 | 5-7 天 |
| **P0** | 决策-结果反馈数据库 | 无 | 2-3 天 |
| **P1** | 元 AI（Meta-Agent） | 反馈数据库 | 5-7 天 |
| **P1** | 叙事引擎 | 宏观数据源 | 7-10 天 |
| **P1** | 动态大师调度 | 叙事引擎 + 元 AI | 3-5 天 |
| **P2** | 主动信息检索 | 新闻 API | 3-5 天 |
| **P2** | 微观结构信号 | Level-2 数据 | 5-7 天 |
| **P2** | 动态仓位计算 | 反事实推理 | 3-5 天 |
| **P2** | 情景压力测试 | 组合数据 | 3-5 天 |

**关键路径**：P0 模块必须先做，P1 依赖 P0，P2 依赖 P1。

---

## 7. 风险警告

1. **AI 幻觉风险**：所有概率估计和反事实推理都可能被 LLM 幻觉污染。必须有严格的验证框架。
2. **数据有效性风险**：宏观因子和资金流数据在 A 股中的有效性需实盘检验，不可默认有效。
3. **过拟合风险**：元 AI 调整策略权重时，可能过拟合历史数据。需要交叉验证。
4. **回测先行**：所有新增信号必须先在回测沙盒中验证，再引入 AI 做解释和动态调整。否则只是增加噪声维度，降低信噪比。

---

## 8. 与当前架构的关系

| 当前架构 | 新架构 | 变化 |
|----------|--------|------|
| 静态市场感知 | 叙事引擎 | 从快照变为演化 |
| 17 位大师并行 | 动态大师调度 | 从全量变为选择性激活 |
| 多空辩论 | 反事实推理 | 从左右互搏变为证伪检验 |
| 标签推荐 | 概率化输出 | 从模糊类别变为概率分布 |
| 硬止损规则 | 动态止损 | 从固定阈值变为 AI 协商 |
| 无反馈闭环 | 决策-结果数据库 + 元 AI | 新增自我进化能力 |
| 被动数据拉取 | 主动信息检索 | 从被动变为主动猎取 |

---

**上一节**: [M6 前端架构](M6-frontend-architecture.md)  
**文档索引**: [README](../README.md)
