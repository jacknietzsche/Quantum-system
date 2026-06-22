# A股智能投资系统 — 架构蓝图 v6.0

> **设计哲学**: 插件化一切, 声明式配置, 数据本地优先, 模块化分析流水线  
> **借鉴来源**: TradingAgents-AShare (DataCollector/ProviderRegistry/SSE), ai-hedge-fund (ANALYST_CONFIG/call_llm/Pydantic), QuantLLM (YAML+validate), ChinaStock (模块化编排), daily_stock_analysis (多源数据层)  
> **最后更新**: 2026-05-08

---

## 一、核心架构: 6层 + 插件体系

```
┌──────────────────────────────────────────────────────────────────┐
│  api/                    接口层 (FastAPI)                        │
│  routes/ (12 files)     参数解析, 调用service, 返回JSON          │
│  deps.py                 依赖注入                                 │
│  依赖: services                                                  │
├──────────────────────────────────────────────────────────────────┤
│  services/               业务层                                   │
│  market.py               市场数据 (SQLite优先+日频)               │
│  watchlist.py            自选股 CRUD                              │
│  portfolio.py            持仓+交易                                │
│  workflow.py             工作流编排                               │
│  risk.py                 风控审计                                 │
│  data_mgmt.py            数据管理                                 │
│  analysis/               分析引擎 (新增)                           │
│    orchestrator.py       编排器 — 协调agents+skills并行执行        │
│    agents/               分析代理 (借鉴ai-hedge-fund)              │
│      base.py             IAnalysisAgent ABC                       │
│      registry.py         AgentRegistry — 声明式注册                │
│      technical.py        技术分析 (rule-based, 无LLM)             │
│      fundamental.py      基本面 (rule-based)                      │
│      sentiment.py        情绪分析                                  │
│      value.py            价值投资 (LLM)                            │
│      risk_agent.py       风险评估 (LLM)                            │
│    skills/               分析技能 (借鉴ChinaStock)                 │
│      base.py             IAnalysisSkill ABC                       │
│      registry.py         SkillRegistry                            │
│      buffett.py, munger.py, taleb.py...                           │
│  依赖: providers                                                  │
├──────────────────────────────────────────────────────────────────┤
│  providers/              数据层 (插件化, 6源)                      │
│  registry.py             ProviderRegistry — 优先级降级调度          │
│  base.py                 IDataProvider ABC + call_with_timeout    │
│  eastmoney.py            P1 东方财富 (HTTP, 最快, 热门+指数)       │
│  tencent.py              P2 腾讯财经 (HTTP, 指数+K线)             │
│  sina.py                 P3 新浪财经 (HTTP, 全市场+指数)          │
│  akshare.py              P4 AKShare (Python库, 全量但慢)         │
│  baostock.py             P5 BaoStock (Python库, K线专用)         │
│  tickflow.py             P6 TickFlow (REST API, K线+基本面)      │
│  database.py, cache.py, llm.py, email.py                         │
│  依赖: shared                                                     │
├──────────────────────────────────────────────────────────────────┤
│  shared/                 横切共享层 (零业务依赖)                    │
│  config.py               统一配置 (YAML+验证, 借鉴QuantLLM)        │
│  models.py               11张ORM表 (含MarketSnapshot)             │
│  dto.py                  8个frozen dataclass                      │
│  exceptions.py           12个异常类                               │
├──────────────────────────────────────────────────────────────────┤
│  config/                 配置文件                                  │
│  config.yaml             所有参数 (唯一真相源)                     │
│  .env                    密钥                                     │
└──────────────────────────────────────────────────────────────────┘
```

## 二、插件体系: 三大注册中心

### 2.1 ProviderRegistry (数据源, 6个)

借鉴 **TradingAgents-AShare** 的 `DataProviderRegistry`:

```python
class ProviderRegistry:
    def __init__(self):
        self._providers: list[IDataProvider] = []

    def register(self, p: IDataProvider):
        self._providers.append(p)
        self._providers.sort(key=lambda x: x.priority)

    def execute(self, method: str, *args):
        """按优先级依次尝试, 首个成功即返回 (源名, 数据)"""
        for p in self._providers:
            if not p.is_available(): continue
            fn = getattr(p, method, None)
            if fn is None: continue
            result = IDataProvider.call_with_timeout(lambda: fn(*args), p.timeout)
            if result is not None:
                return (p.name, result)
        return (None, None)
```

**扩展方式**: 新增数据源只需实现 `IDataProvider` → 注册到Registry。自动参与所有降级链。

### 2.2 AgentRegistry (分析代理)

借鉴 **ai-hedge-fund** 的 `ANALYST_CONFIG`:

```python
class AgentRegistry:
    def __init__(self):
        self._agents: dict[str, IAnalysisAgent] = {}

    def register(self, agent: IAnalysisAgent):
        self._agents[agent.name] = agent

    def get(self, name: str) -> IAnalysisAgent | None: ...
    def list_all(self) -> list[dict]: ...
    def execute(self, names: list[str], context: dict) -> dict[str, AnalysisResult]: ...
```

**扩展方式**: 写一个函数 `def my_agent(state, agent_id) -> dict` → 注册到AgentRegistry。前端自动显示可选。

### 2.3 SkillRegistry (分析技能)

```python
class SkillRegistry:
    def __init__(self):
        self._skills: dict[str, IAnalysisSkill] = {}

    def register(self, skill: IAnalysisSkill): ...
    def execute(self, name: str, context: dict) -> AnalysisResult: ...
```

## 三、数据流: SQLite优先 + 6源降级

```
请求 → Service
       → SELECT market_snapshot WHERE trade_date = 最新有效日期
       → 命中 → 返回 (≤50ms)
       → 未命中 → SELECT ORDER BY trade_date DESC LIMIT 1
       → 命中 → 返回昨日数据 + 后台刷新
       → 未命中 → ProviderRegistry.execute("get_indices")
                    → EastMoney(P1,0.2s) → 成功 ✅
                    → 写入market_snapshot → 返回
```

**日频规则**: 17:00前用昨日, 17:00后用今日

## 四、分析流水线 (新增)

借鉴 **TradingAgents-AShare** 的并行分析师 + **ai-hedge-fund** 的声明式信号:

```
用户请求分析 → Orchestrator
             → [并行] TechnicalAgent (rule-based) → signal
             → [并行] FundamentalAgent (rule-based) → signal
             → [并行] SentimentAgent (data-driven) → signal
             → [并行] ValueAgent (LLM) → signal
             → [并行] RiskAgent (LLM) → signal
             → 聚合器: compute_allowed_actions (确定性)
             → PortfolioManager (LLM) → 最终决策 → 报告
```

**Agent统一签名** (借鉴ai-hedge-fund):
```python
def agent(state: AnalysisState, agent_id: str = "default") -> dict:
    # 1. 获取数据 (从DataCollector)
    # 2. 计算指标 (纯Python)
    # 3. 调用LLM (可选)
    # 4. 返回 {"messages": [...], "data": state["data"]}
    return {"messages": [msg], "data": state["data"]}
```

**每个Agent输出统一Pydantic信号**:
```python
class AgentSignal(BaseModel):
    signal: Literal["bullish", "bearish", "neutral"]
    confidence: int = Field(ge=0, le=100)
    reasoning: str
```

## 五、配置系统 (借鉴QuantLLM)

`config/config.yaml`:
```yaml
providers:
  priority:
    eastmoney: 1
    tencent: 2
    sina: 3
    akshare: 4
    baostock: 5
    tickflow: 6
  timeout: 8

data:
  daily_cutoff_hour: 17
  ttl:
    indices: 300
    hot_stocks: 600
    kline: 86400

llm:
  model_roles:
    primary: "siliconflow:deepseek-ai/DeepSeek-R1"
    secondary: "chatanywhere:gpt-4o"
  retry:
    max_attempts: 3
    default_factory: true

agents:
  enabled: [technical, fundamental, sentiment, value, risk]
  parallel: true
  debate:
    max_rounds: 2
```

`shared/config.py`:
```python
class Config:
    def _validate(self):
        """启动时验证所有配置值合法性"""
        for section in ["providers", "data", "llm", "agents"]:
            assert section in self._data, f"Missing: {section}"
        # 验证数值范围...
```

## 六、项目文件结构

```
a-share-investment-system/
├── config/
│   ├── config.yaml              # 所有参数
│   └── .env                     # 密钥
├── shared/                      # 横切共享 (4 files)
│   ├── config.py, models.py, dto.py, exceptions.py
├── providers/                   # 数据插件 (11 files)
│   ├── base.py, registry.py
│   ├── eastmoney.py, tencent.py, sina.py
│   ├── akshare.py, baostock.py, tickflow.py
│   ├── database.py, cache.py, llm.py, email.py
├── services/                    # 业务 (6 + analysis/)
│   ├── market.py, watchlist.py, portfolio.py
│   ├── workflow.py, risk.py, data_mgmt.py
│   └── analysis/
│       ├── orchestrator.py
│       ├── agents/ (base.py, registry.py, technical.py, fundamental.py, sentiment.py, value.py, risk_agent.py)
│       └── skills/ (base.py, registry.py, buffett.py, munger.py, taleb.py)
├── api/                         # 接口 (12 routes)
│   ├── app.py, deps.py
│   └── routes/ (dashboard, watchlist, hot_stocks, portfolio, workflow, risk, reports, email, config, skills, dataman, system)
├── static/                      # 前端 (不变)
├── templates/                   # 模板 (不变)
├── start.bat
└── pyproject.toml
```

**总计: ~45个Python文件, 每个 ≤150行**

## 七、扩展方式

**添加新数据源**:
1. 创建 `providers/new_source.py` → 继承 `IDataProvider`
2. 实现 `is_available()` + 覆写需要的方法
3. 在 `registry.py` 注册: `registry.register(NewSource())`
4. 自动参与降级链, 无需改其他代码

**添加新分析Agent**:
1. 创建 `services/analysis/agents/new_agent.py`
2. 实现 `def new_agent(state, agent_id) -> dict`
3. 在 `registry.py` 注册, 配置显示名/描述
4. 前端自动显示为可选

**添加新分析Skill**:
1. 创建 `services/analysis/skills/new_skill.py`
2. 继承 `IAnalysisSkill`
3. 注册到 `SkillRegistry`
4. 可被Agent或工作流调用

## 八、验证标准

- [ ] `python api/app.py` 启动成功, 所有路由注册
- [ ] 6个数据源全部可单独检测可用性
- [ ] ProviderRegistry降级链正确: tencent → sina → eastmoney → akshare → baostock → tickflow
- [ ] 市场数据即时加载 (≤50ms from SQLite)
- [ ] 热门股票100只实时数据 (EastMoney)
- [ ] 市场广度~5000只全市场 (EastMoney分页并行)
- [ ] 3个Registry均可动态注册/查询
- [ ] Agent并行执行正确 (所有agents同时启动)
- [ ] 所有API端点返回200
