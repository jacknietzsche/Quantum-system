# AShare-X：A股超级智能投研系统 — 项目蓝图

> 日期: 2026-05-08 | 基于对12个兄弟项目的深度分析 | 渐进重构方案

---

## 一、背景与定位

### 1.1 当前项目基线

a-share-investment-system 已具备7层超级工作流、18个Skill适配器、44个Agent、三层风险审计、Web UI/API等成熟基础设施。

### 1.2 核心问题

大部分Skill适配器的 `_fallback_execute` 仅生成LLM prompts或使用硬编码逻辑，未真正执行源项目的智能体代码。系统是"外壳"而非"引擎"。

### 1.3 定位

**渐进重构**：保留基础设施层（DataBus/ModelHub/ConfigMgr/Scheduler/Web UI），重构领域服务层和编排引擎层。

### 1.4 核心优先级

1. **决策质量优先**：多空辩论+5维市场感知+向量记忆+量化子分析先行
2. **自动化进化优先**：自动因子挖掘+策略YAML化+参数鲁棒性检验
3. **实盘执行优先**：订单管理+成本感知+T+1约束+风控熔断

### 1.5 运行模式

- **半自动模式**：系统生成订单→Web UI展示→用户确认/修改后执行
- **全自动模拟盘**：系统自动分析→自动下单→模拟执行→T+5复盘→自我学习

---

## 二、整体架构（4层）

```
┌──────────────────────────────────────────────────────────────────┐
│                        UI/API 层 (保留)                           │
│  Web仪表盘 / 邮件报告 / 飞书企微 / REST API                       │
├──────────────────────────────────────────────────────────────────┤
│                    编排引擎层 (LangGraph, 重构)                    │
│  SuperWorkflow(12节点) / SingleStockWorkflow(9节点) /             │
│  BacktestLoop(7节点, 新增)                                       │
├──────────────────────────────────────────────────────────────────┤
│                    领域服务层 (核心重构区, 7个独立模块)             │
│  ┌──────────────┬──────────────┬──────────────┬──────────────┐  │
│  │ DebateEngine │ FactorFarm   │ TradeExecutor│ MemoryBank   │  │
│  │ (新增)       │ (新增)       │ (新增)       │ (新增)       │  │
│  ├──────────────┼──────────────┼──────────────┼──────────────┤  │
│  │ MarketPerc   │ RiskEngine   │ PortfolioOpt │              │  │
│  │ (增强)       │ (增强)       │ (增强)       │              │  │
│  └──────────────┴──────────────┴──────────────┴──────────────┘  │
│  统一接口: ServiceResult = {status, data, errors, metrics}       │
├──────────────────────────────────────────────────────────────────┤
│                    基础设施层 (保留)                              │
│  DataBus / ModelHub / SkillRegistry / ConfigMgr / Scheduler      │
└──────────────────────────────────────────────────────────────────┘
```

**设计原则**：
- 领域服务层是唯一重构区，每个服务独立 `.py` 文件
- 编排层通过依赖注入调用领域服务，不直接依赖具体实现
- 基础设施层不动

---

## 三、领域服务层 — 模块设计

### 3.1 DebateEngine（多空辩论引擎）[新增]

**来源**：TradingAgents-AShare + TradingAgents-CN

**架构**：
```
DebateEngine
├── ClaimManager          # 声明生命周期(open→addressed→resolved/unresolved)
├── BullResearcher        # 多头研究员(BM25Memory查历史做多经验)
├── BearResearcher        # 空头研究员(BM25Memory查历史做空经验)
├── ResearchManager       # 研究经理(时间框架加权裁决)
└── RiskDebateTrio        # 风控三方辩论→RiskManager.verdict(pass/revise/reject)
```

**接口**：
```python
def run_debate(stock_code, analyst_reports, market_context, max_rounds=2) -> DebateResult
# Returns: verdict, confidence, target_price, invalidation_condition, claim_history, risk_verdict
```

**防同质化设计**（解决"相同事实不同措辞"风险）：
- **信息源差异化隔离**：
  - 多头记忆库：仅索引公司基本面改善案例（ROE提升/毛利率扩张/现金流好转/管理层增持）+ 分析师上调评级事件
  - 空头记忆库：仅索引技术性反转失败案例（金叉后下跌/突破后回落/放量后缩量）+ 财务恶化和减持事件
  - 两库严格物理隔离（独立BM25索引文件），禁止交叉检索
- **强制性负面挖掘**：空头研究员必须输出至少1条基于历史下跌案例中失败信号的声明（标注 `source:bear_memory`），否则该轮辩论无效需重试
- **声明来源标注**：每条声明携带 `evidence_source` 字段（`bull_fundamental` / `bear_technical` / `analyst_report` / `market_data`），ResearchManager裁决时对同源声明降权（同源声明的共识权重×0.7）
- **分歧度门控**：辩论结束后计算声明来源重合率。若多头和空头的 `evidence_source` 重合>50%，判定为"低信息增量辩论"，裁决置信度自动降一档

**其他设计**：
- BM25本地记忆（jieba分词），零外部依赖
- 每轮目标递进：建声明→攻弱点→判时机→查失效
- 声明用HTML注释中的JSON块追踪，机器可解析
- 默认2轮（4次交锋），可配置

### 3.2 FactorFarm（因子工厂）[新增]

**来源**：RD-Agent + QuantLLM

**架构**：
```
FactorFarm
├── HypothesisGenerator   # 假说生成(基于历史因子库+数据源+市场特征)
├── FactorCoder           # 代码生成(LLM→沙箱验证→CoSTEER知识库)
├── FactorEvaluator       # 多阶段评估(执行→格式→IC/ICIR→去重)
├── FactorLibrary         # SQLite存储(IC/ICIR/创建时间/状态)
└── BanditAllocator       # Thompson采样分配"挖新因子"vs"优化组合"
```

**接口**：
```python
def mine_factors(stock_pool, forward_period=5, max_new=3) -> MineResult
def evaluate_factor(factor_name) -> FactorReport
def get_top_factors(n=20, min_ic=0.03) -> List[Factor]
def build_factor_score(stock_code) -> float
```

**关键设计**：
- 因子挖掘作为后台定时任务（非实时）
- 初始因子库：QuantLLM 28个 + 业界经典10个
- 代码沙箱使用 `exec()` + 超时，不依赖Docker
- 去重IC阈值：因子间0.95，模板间0.99

### 3.3 TradeExecutor（交易执行器）[新增]

**来源**：a-share-skill + QuantLLM

**架构**：
```
TradeExecutor
├── OrderGenerator        # 信号→订单(成本过滤+T+1检查+涨跌停限制)
├── SimulatedExecution    # 模拟执行(滑点模型+佣金+部分成交)
├── PositionTracker       # 仓位追踪(多账户+净值计算+每日快照)
└── KillSwitch            # 熔断(日亏>5%停开仓/周亏>10%降仓/月亏>15%清仓)
```

**接口**：
```python
def generate_orders(signals, mode="paper") -> List[Order]
def execute_paper(orders, date) -> ExecutionReport
def get_positions() -> List[Position]
def check_kill_switch() -> KillSwitchStatus
```

**关键设计**：
- 成本参数可配置（佣金万2.5/印花税千1/滑点bps）
- 复用现有 Order/Trade/DailyNAV 数据模型
- 半自动：订单→UI确认；全自动：订单→模拟执行→复盘

### 3.4 MemoryBank（记忆银行）[新增]

**来源**：TradingAgents-CN + TradingAgents-AShare

**架构**：
```
MemoryBank
├── SituationEncoder      # 场景编码(市场向量+个股特征向量→固定维度)
├── BM25Retriever         # 第一阶段关键词检索(jieba+停用词→候选top-100)
├── VectorRetriever       # 第二阶段向量检索(ChromaDB可选升级)
├── LessonExtractor       # 经验提取(成功条件/失败信号/胜率统计)
└── PromptInjector        # 历史经验注入Agent系统提示
```

**接口**：
```python
def store(situation, decision, outcome) -> str  # memory_id
def retrieve(current_situation, top_k=5) -> List[Memory]
def get_lessons(stock_code, decision_type="all") -> List[Lesson]
def inject_into_prompt(base_prompt, current_situation) -> str
```

**关键设计**：
- 第一阶段BM25（零成本），第二阶段ChromaDB可选
- 存储触发：T+5日决策结果确认后
- 过期策略：>1年降权；市场环境剧变时降权
- 多头/空头/风控各自独立记忆空间

### 3.5 MarketPerception（5维市场感知）[增强]

**来源**：QuantLLM + TradingAgents-AShare

**5维度评分**：
| 维度 | 指标 | 范围 |
|------|------|------|
| D1 趋势位置 | 价格vs MA120偏离 | -2 ~ +2 |
| D2 趋势方向 | MA120斜率(20日) | -2 ~ +2 |
| D3 量能确认 | 20日均量vs 60日均量 | -1 ~ +1 |
| D4 波动率 | 近期波动vs长期波动 | -1 ~ +1 |
| D5 价格动量 | 60日收益率 | -1 ~ +1 |

**环境分类**：
- 总分≥+2 → BULL（目标仓位95%, 最大10只, 选股阈值buy+strong_buy）
- 总分≤-2 → BEAR（目标仓位30%, 最大3只, 仅strong_buy+防御型）
- 中间 → NEUTRAL（目标仓位50%, 最大5只）
- 特殊：PANIC（跌停>50+总分<-3）/ OVERHEAT（涨停>80+北向流出）/ LIQUIDITY_CRISIS

**接口**：
```python
def perceive(market_data) -> MarketRegime
def get_position_limits() -> PositionLimits
def is_trading_day(date=None) -> bool
```

### 3.6 RiskEngine（风控引擎）[增强]

**来源**：ai-hedge-fund RiskManager + Taleb-skill

**三层风控增强**：
- 第一层（市场）：保留恐慌指数 + 新增市场周期定位 + 尾部事件检测
- 第二层（个股）：保留ST检查 + 新增黑天鹅脆弱性/流动性风险/反身性风险
- 第三层（组合）：波动率调整限额(vol<15%→25%, >50%→5%) + 相关性矩阵乘数(≥0.8→×0.70) + 集中度风险 + 压力测试

**接口**：
```python
def full_audit(portfolio, market_regime, candidate_orders=None) -> RiskReport
# Returns: pass, market_risk, stock_risks, portfolio_risk, kill_switch, position_limits
```

### 3.7 PortfolioOptimizer（组合优化器）[增强]

**来源**：ai-hedge-fund PortfolioManager + QuantLLM

**核心增强**：
- ConstraintPrecomputer：确定性约束预计算（现金/持仓/涨跌停/T+1/单股上限/行业上限）
- SignalAggregator：多源信号融合+LLM最终决策(仅在有>1种选择时调用)
- 预填充优化：只有1种允许操作→跳过LLM
- RebalanceEngine：成本感知再平衡+杠铃结构维护

**接口**：
```python
def optimize(current_positions, signals, risk_report, cash) -> OptimizationResult
# Returns: target_weights, orders, skipped, rebalance_plan, barbell_status
```

### 3.8 YAML策略系统 — DSL边界与安全约束

**DSL复杂度控制**：
YAML策略定义限制为以下**白名单字段**，禁止任意代码执行：

```yaml
# 合法字段白名单（超出此范围的字段在加载时被忽略并告警）
name: str              # 策略名称（必填）
description: str        # 策略描述
market_regimes: [...]   # 适用环境: [bull, neutral, bear, panic]
required_indicators:    # 依赖指标（必须来自指标注册表）
  - name: ma5
    params: {window: 5}
scoring:                # 评分规则（仅支持四则运算+比较）
  - name: golden_cross
    formula: "ma5 > ma20"          # 白名单表达式语法
    weight: 30
filters:                # 过滤条件（仅支持比较运算符）
  - condition: "turnover_rate > 0.5"
entry_threshold: 65     # 最低入场分
stop_loss_pct: -5.0     # 止损百分比
take_profit_pct: 15.0   # 止盈百分比
max_hold_days: 20       # 最大持仓天数
```

**表达式安全沙箱**：
- `formula` 和 `condition` 字段使用受限语法解析器，**禁止**：函数调用、属性访问、导入语句、列表推导
- 合法操作符白名单：`+`, `-`, `*`, `/`, `>`, `<`, `>=`, `<=`, `==`, `!=`, `and`, `or`, `not`
- 合法操作数白名单：指标名（来自 `required_indicators`）+ 数值字面量
- 解析失败→拒绝加载该策略 + 写入告警日志

**前视偏差自动审计**（每个YAML策略加载时强制执行）：
1. **shift检查**：`formula` 中如果使用了 `shift(-N)` 或 `.shift()` 负偏移 → 拒绝加载
2. **rolling检查**：`formula` 中如果 `rolling().mean()` 使用了 `center=True` → 告警
3. **全样本标准化检查**：`formula` 中如果出现 `zscore` / `standardize` 且未指定 `expanding` 窗口 → 告警
4. **信号对齐检查**：`entry_threshold` 触发日期 vs 实际可交易日期（T+1）→ 不一致则拒绝
5. **偷价检查**：`formula` 中使用了当日 `close` 价格且策略声称"开盘买入" → 拒绝

**策略版本与回滚**：
- 每个策略YAML头部携带 `version` 和 `updated_at` 字段
- 策略变更后必须重新通过回测验证（BacktestLoop自动触发）
- 回测指标退化>10% → 自动回滚到上一版本

---

## 四、编排引擎层 — 三个工作流

### 4.1 SuperWorkflow（日频全市场，12节点）

```
fetch_global_data → skill_analysis_parallel → multi_perspective_analysis(★)
→ debate_committee(★) → fincept_master_verify → risk_control_audit(增强)
→ portfolio_management(增强) → multi_model_vote → generate_orders(★)
→ generate_recommendations → [execute_paper(★)] → generate_report → END
                                                              ↓
                                                     MemoryBank.store()(后台)
```

★=新增/大幅增强节点

### 4.2 SingleStockWorkflow（单股深度分析，9节点）

```
fetch_stock_data → skill_deep_analysis → factor_scoring
→ multi_perspective_signal → debate_single_stock → risk_check
→ generate_orders → generate_report → [execute_paper] → END
```

### 4.3 BacktestLoop（回测+因子验证，7节点）[新增]

```
set_date_range → factor_hypothesis_gen → [循环] factor_code_generate
→ factor_evaluate → factor_backtest → summarize_round → factor_report → END
```

BanditAllocator在每个循环中Thompson采样决定"挖新因子"vs"优化组合"。

### 4.4 双模式运行

```
Scheduler(15:30触发) → SuperWorkflow
                        ├── 半自动: 订单→Web UI→人工确认
                        └── 全自动: 订单→模拟执行→DailyNAV→T+5复盘→MemoryBank
```

---

## 五、数据流

```
[AkShare/Baostock] → DataBus → MarketRegime + SkillOutputs + FactorScores
                                    ↓
                              MemoryBank.retrieve() → 历史经验注入
                                    ↓
                              19大师纯Py子分析 → LLM信号
                                    ↓
                              DebateEngine.run() → 裁决+声明
                                    ↓
                              RiskEngine.full_audit() → RiskReport
                                    ↓
                              PortfolioOptimizer.optimize() → 订单
                                    ↓
                         ┌────────┴────────┐
                   半自动模式          全自动模拟盘
                   Web UI展示          TradeExecutor.execute()
                                      DailyNAV → MemoryBank.store()
```

---

## 六、文件变更清单

### 新增文件
| 文件 | 模块 | 来源 |
|------|------|------|
| `services/base.py` | ServiceResult + BaseService | — |
| `services/protocols.py` | 7个服务接口协议 | — |
| `services/market_perception.py` | MarketPerception | QuantLLM |
| `services/debate_engine.py` | DebateEngine | TradingAgents-AShare |
| `services/factor_farm.py` | FactorFarm | RD-Agent |
| `services/trade_executor.py` | TradeExecutor | a-share-skill |
| `services/memory_bank.py` | MemoryBank | TradingAgents-CN |
| `services/risk_engine.py` | RiskEngine | ai-hedge-fund |
| `services/portfolio_optimizer.py` | PortfolioOptimizer | ai-hedge-fund |
| `services/backtest_loop.py` | BacktestLoop | RD-Agent |
| `services/quant_analyzers.py` | 19大师纯Py子分析 | ai-hedge-fund |
| `services/strategy_loader.py` | YAML策略加载器 | daily_stock_analysis |
| `strategies/` | YAML策略定义目录 | daily_stock_analysis |

### 增强文件
| 文件 | 改动 |
|------|------|
| `super_workflow.py` | 依赖注入框架 + 3个新节点 + 4个增强节点 |
| `workflow.py` | 注入领域服务 |
| `skills.py` | 移除内置分析逻辑，保留适配器 |
| `scheduler.py` | 新增T+5复盘任务 |

### 可废弃文件
| 文件 | 替代者 |
|------|--------|
| `optimizations.py` | 拆分入各新服务 |
| `decision_review.py` | MemoryBank |
| `multi_model_voter.py` | PortfolioOptimizer.SignalAggregator |

---

## 七、实施路线图

### 阶段0：基础设施准备（1-2天）
- 定义ServiceResult/BaseService/接口协议
- 搭建strategies/和memory/目录
- 在super_workflow.py中注入依赖框架（不改行为）

### 阶段1：决策质量（1-2周）
- MarketPerception + MemoryBank + DebateEngine + 量化子分析
- 目标：LLM调用量减少30%+，辩论流程完整可运行

### 阶段2：自动化进化（2-3周）
- FactorFarm + YAML策略系统 + BacktestLoop
- 目标：成功生成1个新因子，回测循环完整运行

### 阶段3：实盘执行（2-3周）
- TradeExecutor + RiskEngine增强 + PortfolioOptimizer增强
- 目标：双模式运行，模拟执行+复盘学习闭环

### 阶段4：清理收尾（1周）
- 移除废弃代码 + 更新文档 + 集成测试

**总工期**：约7周

---

## 八、风险与缓解

| 风险 | 概率 | 缓解措施 |
|------|------|---------|
| 辩论同质化（多头空头用相同记忆源） | 高 | 信息源差异化隔离 + 强制性负面挖掘 + 来源重合度门控 |
| YAML策略引入前视偏差/偷价 | 中 | 白名单表达式语法 + 5项自动审计 + 版本回滚机制 |
| LLM生成因子代码安全漏洞 | 中 | exec沙箱+超时+白名单模块 |
| 辩论增加延迟过长 | 中 | 默认2轮+低信息增量自动终止+超时降级为投票 |
| BM25中文分词精度不足 | 低 | jieba+金融词典；可升级ChromaDB |
| 模拟执行与实际成交偏差 | 中 | 滑点模型+冲击成本估算 |
| 新增文件与现有模块冲突 | 低 | 接口协议隔离；渐进替换 |
| A股长期熊市中Sharpe目标偏乐观 | 中 | 分环境设定目标；熊市目标为跑赢基准而非绝对收益 |

---

## 九、成功标准（含统计显著性要求）

### 9.1 决策质量

| 指标 | 目标值 | 统计约束 | 测量方法 |
|------|--------|---------|---------|
| 辩论裁决方向正确率 | >60% (基线~50%) | 最小样本N≥100次裁决；二项检验p<0.05 vs 随机(50%)；报告95% Wilson置信区间 | 裁决后T+5/T+20日实际涨跌方向对比 |
| 裁决置信度校准 | 置信度与正确率Pearson r>0.5 | N≥100 | 按置信度分桶(0.5-0.6/0.6-0.7/0.7-0.8/0.8+)统计每桶正确率 |
| 低信息增量辩论触发率 | <30% | — | evidence_source重合>50%的辩论占比 |

### 9.2 因子挖掘

| 指标 | 目标值 | 统计约束 | 测量方法 |
|------|--------|---------|---------|
| 新因子IC均值 | >0.03 | IC t检验p<0.05（H0: IC=0）；N≥60个交易日 | 日度IC序列的t统计量 |
| 新因子ICIR | >0.3 | — | IC均值/IC标准差 |
| 因子库冗余率 | <20% | — | 两两IC>0.8的因子对占比 |

### 9.3 模拟盘表现（分市场环境）

| 环境 | Sharpe目标 | 最大回撤上限 | 年化收益目标 | 统计约束 |
|------|-----------|-------------|-------------|---------|
| 牛市（CSI300>MA120且斜率向上） | >0.5 | <20% | >CSI300基准 | 滚动12个月计算，避免单段拟合 |
| 震荡市（中性） | >0.2 | <20% | >0%（正收益） | 同上 |
| 熊市（CSI300<MA120且斜率向下） | >-0.3 | <30% | 跑赢CSI300≥5% | 熊市中Sharpe可为负但需跑赢基准 |

**通用统计要求**：
- 回测/模拟盘观测期≥3年（覆盖至少1个完整牛熊周期）
- 报告滚动1年/2年/3年Sharpe，不报告单期点估计
- 使用Deflated Sharpe Ratio检验（控制多重试验偏差，阈值>0.05才接受）
- 最大回撤报告日期区间以便审计（"2024-02至2024-09: -18.3%"）

### 9.4 系统稳定性

| 指标 | 目标值 |
|------|--------|
| 日频运行成功率 | 100次运行无未处理异常 |
| 领域服务健康检查通过率 | >99% |
| 降级触发率（超时回退默认值） | <5% |
| LLM调用超时率 | <3% |
