# AShare-X 实现计划

> **目标**: 从设计文档到可运行代码的完整实现路径
> **原则**: 底层优先，逐层构建，每层独立可测

---

## 0. 定位声明（先读这一节）

> **⚠️ 本计划是「全新重写」，不是对现有代码的改造。**

- 本计划描述的是一个**理想化的全新项目** `ashare-x/`，与仓库内现有的 `a-share-investment-system/`（已含 `server.py` / `super_workflow.py` 2355 行 / `skills.py` / `services/` / `electron/` 等）**并存**，不修改、不依赖现有代码。
- 现有代码库**不作为本计划的前置条件**：不从中 import、不引用其模块、不共享 `data/` 或 `config/`。两者是独立的两套实现，本计划产出的是第二条技术路线。
- 选择重写而非演进的依据：现有代码（尤其 `super_workflow.py` 2355 行单文件、根级 `skills.py` 与 `services/skill_engine.py` 职责重叠）已积累足够结构性债务，演进式修改的成本与风险高于按 S01-S15 设计文档从零实现。
- **复用边界**：本计划**仅复用**以下「非代码资产」——`project-design/` 设计文档、`experiments/` 实验数据与结论（含 exp14 真实定价）、`quant-agents/` 的 SKILL.md 知识源。**不复用任何 .py 文件**。
- 现有 `a-share-investment-system/` 的去留在本计划交付、并经端到端验证后另行决定（见 §七「迁移与退役说明」）。

---

## 0.1 预算与成本口径（RMB 结算）

> exp14 已推翻旧的「单股 17,500 token / 400k token 预算」假设（实测完整模式 **63,600 token/股**）。本计划统一改用 **RMB 月成本**作为预算口径，token 计数仅作中间量。

**定价依据**（exp14 实测，[官方 Pricing](https://api-docs.deepseek.com/quick_start/pricing)，2026-06；汇率取 $1 ≈ ¥7.2）：

| 模型 | input ¥/1M token | output ¥/1M token | cached_input ¥/1M token |
|------|-----------------:|------------------:|------------------------:|
| V4-Flash | ¥1.01 | ¥2.02 | ¥0.10 |
| V4-Pro | ¥12.53 | ¥25.06 | ¥1.25 |

**单股完整流程 token**（exp14，input 52,200 + output 11,400 = **63,600**）；**快速模式约 22,000**（跳过大师视角、辩论压缩为 1 轮、部分 Agent 合并）。

**月成本基线**（决定 fast_mode 触发与告警）：

| 场景 | 月成本(无缓存) | 月成本(60%缓存) |
|------|-------------:|--------------:|
| 10只/天 完整模式 | **¥74** | **¥46** |
| 25只/天 完整模式 | ¥185 | ¥115 |
| 50只/天 快速模式 | ¥190 | ¥118 |

**预算策略**：
- 默认月预算上限 **¥100/月**（个人日常，约 10-15 只/天 完整模式）。
- 用量达 **80% 月预算（¥80）** → 告警；达 **100%** → 自动降级为快速模式；达 **120%** → 暂停非紧急分析任务。
- TokenCounter 必须区分 `input / output / cached_input` 三类，按上表分别计价累计，不得用 `total_tokens` 线性外推（exp14 暴露的关键认知：input:output ≈ 4.6:1，缓存只省 input）。
- 真实 token 计数以 DeepSeek API 返回的 `usage` 字段为准（估算器误差 ±15-37%，见 exp14.4）。

---

## 一、项目目录结构

```
ashare-x/
├── pyproject.toml                   # 项目配置
├── .env.example                     # 环境变量模板
├── .gitignore
│
├── main.py                          # CLI入口
├── server.py                        # FastAPI服务器
├── launch.py                        # 一键启动
│
├── core/                            # 第1层: 核心框架
│   ├── __init__.py
│   ├── config.py                    # 配置管理（加载+热更新+环境变量覆盖）
│   ├── state.py                     # AgentState TypedDict定义
│   ├── llm_client.py                # LLM客户端（Provider工厂+重试+Token计数）
│   ├── exceptions.py                # 异常分层（AgentError/LLMError/ToolError）
│   └── i18n.py                      # 国际化（错误消息/日志语言）
│
├── providers/                       # 第2层: 数据提供商
│   ├── __init__.py
│   ├── base.py                      # SourceAdapter基类（断路器+重试+连接池）
│   ├── data_bus.py                  # DatabaseFirstDataBus（数据库优先）
│   ├── normalizer.py                # StockCodeNormalizer（代码标准化）
│   ├── health.py                    # DataProviderHealth（健康检查）
│   └── sources/                     # 数据源适配器
│       ├── __init__.py
│       ├── tencent.py               # 腾讯行情
│       ├── sina.py                  # 新浪行情
│       ├── akshare_src.py           # AKShare
│       ├── baostock_src.py          # BaoStock
│       ├── yfinance_src.py          # yfinance
│       └── eastmoney.py             # 东方财富
│
├── db/                              # 第3层: 数据库
│   ├── __init__.py
│   ├── engine.py                    # SQLAlchemy引擎（线程安全）
│   ├── models.py                    # ORM模型定义
│   ├── migrations.py                # 迁移管理（版本追踪+幂等迁移）
│   └── migrations/                  # 迁移脚本
│       ├── v001_create_kline.sql
│       ├── v002_create_stock_info.sql
│       ├── v003_create_reports.sql
│       └── v004_create_decisions.sql
│
├── tools/                           # 第4层: Agent工具
│   ├── __init__.py
│   ├── stock_data.py                # 股票数据获取工具
│   ├── technical_indicators.py      # 技术指标计算
│   ├── fundamentals.py              # 基本面数据
│   ├── news_search.py               # 新闻搜索
│   ├── social_sentiment.py          # 社交情绪
│   ├── paper_trading.py             # 模拟交易
│   └── market_state.py              # 市场状态检测
│
├── agents/                          # 第5层: Agent定义
│   ├── __init__.py
│   ├── base.py                      # Agent工厂基类
│   ├── analysts/                    # 分析师团队
│   │   ├── __init__.py
│   │   ├── market_analyst.py        # 市场分析师
│   │   ├── fundamentals_analyst.py  # 基本面分析师
│   │   ├── news_analyst.py          # 新闻分析师
│   │   └── sentiment_analyst.py     # 情绪分析师
│   ├── researchers/                 # 研究员团队
│   │   ├── __init__.py
│   │   ├── bull_researcher.py       # 看涨研究员
│   │   ├── bear_researcher.py       # 看跌研究员
│   │   └── research_manager.py      # 研究经理
│   ├── risk_mgmt/                   # 风险管理团队
│   │   ├── __init__.py
│   │   ├── aggressive_analyst.py    # 激进分析师
│   │   ├── conservative_analyst.py  # 保守分析师
│   │   ├── neutral_analyst.py       # 中性分析师
│   │   └── portfolio_manager.py     # 投资组合经理
│   ├── trader/
│   │   ├── __init__.py
│   │   └── trader.py                # 交易员
│   └── masters/                     # 大师视角层
│       ├── __init__.py
│       ├── selector.py              # 大师选择算法
│       ├── buffett.py
│       ├── munger.py
│       └── ...（其他大师）
│
├── graph/                           # 第6层: 工作流编排
│   ├── __init__.py
│   ├── trading_graph.py             # 主工作流定义
│   ├── conditional_logic.py         # 条件路由（辩论终止）
│   └── propagation.py               # 状态传播
│
├── skills/                          # 第7层: Skill系统
│   ├── __init__.py
│   ├── engine.py                    # SkillEngine（发现+加载+注入）
│   ├── buffett/SKILL.md
│   ├── munger/SKILL.md
│   ├── taleb/SKILL.md
│   ├── a-share-trading/SKILL.md
│   └── china-stock-research/SKILL.md
│
├── memory/                          # 第8层: 记忆系统
│   ├── __init__.py
│   ├── decision_log.py              # 决策日志
│   ├── reflection.py                # 反思引擎
│   └── injection.py                 # 记忆注入
│
├── services/                        # 第9层: 业务服务
│   ├── __init__.py
│   ├── screening.py                 # 选股服务（评分+排名）
│   ├── portfolio.py                 # 组合管理（仓位优化）
│   ├── risk_engine.py               # 风险引擎（三层风险）
│   ├── trading_plan.py              # 交易计划生成
│   ├── market_perception.py         # 市场感知
│   ├── backtest.py                  # 回测引擎
│   ├── report.py                    # 报告生成
│   └── updater.py                   # 定时数据更新
│
├── api/                             # 第10层: API路由
│   ├── __init__.py
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── analysis.py              # 分析相关路由
│   │   ├── portfolio.py             # 持仓路由
│   │   ├── screening.py             # 选股路由
│   │   ├── reports.py               # 报告路由
│   │   ├── settings.py              # 设置路由
│   │   └── stream.py                # SSE事件流
│   └── sse_manager.py               # SSE连接管理
│
├── frontend/                        # 第11层: React前端（Electron 桌面壳）
│   ├── package.json
│   ├── vite.config.ts
│   ├── src/
│   │   ├── App.tsx
│   │   ├── main.tsx
│   │   ├── stores/                  # Zustand状态管理
│   │   ├── components/              # 组件
│   │   ├── pages/                   # 页面
│   │   └── hooks/                   # 自定义Hook
│   └── electron/                    # Electron 桌面壳（与现有项目技术栈一致：React/Vite/Tailwind）
│       ├── package.json
│       ├── main.ts                  # Electron 主进程
│       ├── preload.ts               # 预加载脚本（contextBridge）
│       └── electron-builder.yml     # 打包配置
│
├── config/
│   ├── config.yaml                  # 主配置
│   └── .env                         # 本地密钥（gitignore）
│
├── runtime/                         # 运行时数据
│   ├── investment.db                # SQLite数据库
│   ├── checkpoints/                 # LangGraph检查点
│   └── logs/                        # 日志文件
│
├── reports/                         # 生成的报告
│
├── tests/                           # 测试
│   ├── unit/
│   ├── integration/
│   └── backtest/
│
└── experiments/                     # 实验代码（已完成）
    └── ...
```

---

## 二、实现顺序（按依赖关系）

### Phase 1: 基础设施（第1-3层）

| 顺序 | 文件 | 依赖 | 预估行数 | 说明 |
|------|------|------|----------|------|
| 1.1 | `core/config.py` | 无 | ~100 | 配置加载+热更新+环境变量覆盖 |
| 1.2 | `core/exceptions.py` | 无 | ~50 | 异常分层 |
| 1.3 | `core/i18n.py` | 无 | ~60 | 国际化消息 |
| 1.4 | `core/state.py` | 无 | ~80 | AgentState TypedDict |
| 1.5 | `db/engine.py` | config | ~60 | SQLAlchemy引擎 |
| 1.6 | `db/models.py` | engine | ~200 | ORM模型 |
| 1.7 | `db/migrations.py` | engine | ~80 | 迁移管理 |
| 1.8 | `providers/base.py` | config | ~150 | 断路器+重试+连接池 |
| 1.9 | `providers/normalizer.py` | 无 | ~60 | 股票代码标准化 |
| 1.10 | `providers/health.py` | base | ~50 | 健康检查 |
| 1.11 | `providers/sources/*.py` | base | ~500 | 6个数据源适配器 |
| 1.12 | `providers/data_bus.py` | models,base | ~200 | 数据库优先数据总线 |

**Phase 1 总计**: ~1,490行，可独立测试

### Phase 2: Agent工具（第4层）

| 顺序 | 文件 | 依赖 | 预估行数 | 说明 |
|------|------|------|----------|------|
| 2.1 | `tools/stock_data.py` | data_bus | ~80 | 股票数据获取 |
| 2.2 | `tools/technical_indicators.py` | 无 | ~100 | MA/MACD/RSI/Bollinger |
| 2.3 | `tools/fundamentals.py` | data_bus | ~60 | 基本面数据 |
| 2.4 | `tools/news_search.py` | data_bus | ~50 | 新闻搜索 |
| 2.5 | `tools/social_sentiment.py` | data_bus | ~50 | 情绪数据 |
| 2.6 | `tools/market_state.py` | data_bus | ~80 | 市场状态检测 |
| 2.7 | `tools/paper_trading.py` | models | ~120 | 模拟交易 |

**Phase 2 总计**: ~540行，可独立测试

### Phase 3: LLM + Agent（第5层）

| 顺序 | 文件 | 依赖 | 预估行数 | 说明 |
|------|------|------|----------|------|
| 3.1 | `core/llm_client.py` | config | ~250 | LLM客户端+重试+Token计数 |
| 3.2 | `agents/base.py` | llm_client | ~80 | Agent工厂基类 |
| 3.3 | `agents/analysts/*.py` | base,tools | ~400 | 4个分析师 |
| 3.4 | `agents/researchers/*.py` | base | ~200 | 2个研究员+研究经理 |
| 3.5 | `agents/risk_mgmt/*.py` | base | ~250 | 3个风险分析师+组合经理 |
| 3.6 | `agents/trader/trader.py` | base | ~80 | 交易员 |
| 3.7 | `agents/masters/selector.py` | 无 | ~60 | 大师选择算法 |
| 3.8 | `agents/masters/*.py` | base | ~200 | 7个大师Agent |

**Phase 3 总计**: ~1,520行，可独立测试

### Phase 4: 工作流 + Skill + 记忆（第6-8层）

| 顺序 | 文件 | 依赖 | 预估行数 | 说明 |
|------|------|------|----------|------|
| 4.1 | `graph/conditional_logic.py` | 无 | ~60 | 辩论终止判断 |
| 4.2 | `graph/propagation.py` | 无 | ~40 | 状态传播 |
| 4.3 | `graph/trading_graph.py` | agents | ~200 | 主工作流 |
| 4.4 | `skills/engine.py` | 无 | ~100 | Skill引擎 |
| 4.5 | `skills/*/SKILL.md` | 无 | ~200 | 5个Skill定义 |
| 4.6 | `memory/decision_log.py` | models | ~80 | 决策日志 |
| 4.7 | `memory/reflection.py` | llm_client | ~60 | 反思引擎 |
| 4.8 | `memory/injection.py` | decision_log | ~40 | 记忆注入 |

**Phase 4 总计**: ~780行，可独立测试

### Phase 5: 业务服务（第9层）

| 顺序 | 文件 | 依赖 | 预估行数 | 说明 |
|------|------|------|----------|------|
| 5.1 | `services/screening.py` | tools,data_bus | ~150 | 选股评分 |
| 5.2 | `services/portfolio.py` | models | ~120 | 组合优化 |
| 5.3 | `services/risk_engine.py` | tools | ~100 | 风险引擎 |
| 5.4 | `services/trading_plan.py` | agents | ~80 | 交易计划 |
| 5.5 | `services/market_perception.py` | tools | ~60 | 市场感知 |
| 5.6 | `services/backtest.py` | models | ~150 | 回测引擎 |
| 5.7 | `services/report.py` | models | ~80 | 报告生成 |
| 5.8 | `services/updater.py` | data_bus | ~100 | 定时更新 |

**Phase 5 总计**: ~740行，可独立测试

### Phase 6: API + 前端（第10-11层）

| 顺序 | 文件 | 依赖 | 预估行数 | 说明 |
|------|------|------|----------|------|
| 6.1 | `api/sse_manager.py` | 无 | ~100 | SSE连接管理 |
| 6.2 | `api/routes/*.py` | services | ~300 | 6个路由模块 |
| 6.3 | `server.py` | api | ~80 | FastAPI入口 |
| 6.4 | `main.py` | server | ~60 | CLI入口 |
| 6.5 | `launch.py` | 无 | ~50 | 启动脚本 |
| 6.6 | `frontend/` | — | ~2000 | React前端（Phase 2） |

**Phase 6 总计**: ~2,590行

---

## 三、总代码量预估

| 层级 | 生产代码 | 测试代码 | 文件数 |
|------|----------|----------|--------|
| Phase 1: 基础设施 | ~1,490 | ~900 | 12 |
| Phase 2: Agent工具 | ~540 | ~400 | 7 |
| Phase 3: LLM + Agent | ~2,400 | ~1,500 | 8 |
| Phase 4: 工作流+Skill+记忆 | ~1,100 | ~600 | 8 |
| Phase 5: 业务服务 | ~1,000 | ~600 | 8 |
| Phase 6: API+前端 | ~2,590 | ~300 | 10+ |
| **总计** | **~9,120** | **~4,300** | **53+** |

> **修订说明**：
> - Phase 3 由 ~1,520 上调到 ~2,400：12 个 Agent（每个含 prompt + schema + 解析 fallback），参考现有 `super_workflow.py` 单文件 2,355 行的真实复杂度，原预估偏乐观。
> - 新增「测试代码」列。pyproject 要求覆盖率 ≥50%，测试代码经验值 ≈ 生产代码的 0.4-0.6×。
> - Phase 6 前端测试只计关键 hook/store 单测，E2E 另算（不计入）。

---

## 四、每个Phase的验证方式

> **前提**：每个 Phase 的测试文件**作为该 Phase 的交付物一并实现**，不得留到最后补（否则验证命令无法执行）。下表的命令在对应 Phase 完成时即可运行。

| Phase | 验证方式 | 验证命令 |
|-------|----------|----------|
| Phase 1 | 单元测试 | `pytest tests/unit/test_config.py tests/unit/test_exceptions.py tests/unit/test_db.py tests/unit/test_providers.py -v` |
| Phase 2 | 单元测试 | `pytest tests/unit/test_tools.py tests/unit/test_indicators.py -v` |
| Phase 3 | 集成测试（mock LLM） | `pytest tests/integration/test_agents.py tests/unit/test_llm_budget.py -v` |
| Phase 4 | 集成测试 | `pytest tests/integration/test_workflow.py tests/integration/test_skill_engine.py -v` |
| Phase 5 | 集成测试 | `pytest tests/integration/test_services.py -v` |
| Phase 6 | 端到端测试 | `python main.py analyze 600519`（需真实 DEEPSEEK_API_KEY，会产生约 ¥0.5 成本） |

> **新增 `tests/unit/test_llm_budget.py`**：验证 `BudgetState` 的 RMB 计价与 `policy()` 三级降级（warn/fast_mode/halt），用 exp14 的单股 63,600 token 数据构造 fixture，断言 10 只/天 ≈ ¥74/月。这是 exp14 结论在代码层的回归测试。

---

## 五、关键文件详细设计

### 5.1 core/config.py

```python
"""配置管理：加载+热更新+环境变量覆盖"""
import os
import yaml
from pathlib import Path

class Config:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self.config_path = Path("config/config.yaml")
        self.last_mtime = 0
        self.data = {}
        self.load()

    def load(self):
        if self.config_path.exists():
            with open(self.config_path) as f:
                self.data = yaml.safe_load(f) or {}
            self.last_mtime = self.config_path.stat().st_mtime
        self._apply_env_overrides()

    def get(self, key: str, default=None):
        # 检查热更新
        if self.config_path.exists():
            mtime = self.config_path.stat().st_mtime
            if mtime > self.last_mtime:
                self.load()
        # 嵌套key
        keys = key.split(".")
        value = self.data
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                return default
        return value if value is not None else default

    def _apply_env_overrides(self):
        ENV_MAP = {
            "ASHARE_X_LLM_PROVIDER": "llm.quick_think.provider",
            "ASHARE_X_DEEPSEEK_API_KEY": "llm.deepseek.api_key",
            "ASHARE_X_MONTHLY_BUDGET_RMB": "llm.monthly_budget_rmb",
            # ... 更多映射
        }
        for env_key, config_key in ENV_MAP.items():
            env_val = os.environ.get(env_key)
            if env_val:
                self._set_nested(config_key, env_val)

    def _set_nested(self, key: str, value):
        keys = key.split(".")
        d = self.data
        for k in keys[:-1]:
            d = d.setdefault(k, {})
        d[keys[-1]] = value
```

### 5.2 core/llm_client.py

```python
"""LLM客户端：Provider工厂+重试+RMB成本计量（基于 exp14 实测定价）"""
import time
from dataclasses import dataclass, field
from openai import OpenAI
from .config import Config
from .exceptions import LLMError, TimeoutError, RateLimitError

# 2026-06 V4 定价，单位: RMB / 1M token（汇率 $1 ≈ ¥7.2，来源 exp14）
# 字段区分 input / output / cached_input，不能用单一 total 线性外推
PRICING_RMB = {
    "deepseek-v4-flash": {"input": 1.01,  "output": 2.02,  "cached_input": 0.10},
    "deepseek-v4-pro":   {"input": 12.53, "output": 25.06, "cached_input": 1.25},
}


@dataclass
class UsageRecord:
    """单次调用的真实 usage（来自 API 返回，不用估算器）"""
    model: str
    prompt_tokens: int          # 含 cached 与 fresh，需配合 cached_prompt_tokens 拆分
    cached_prompt_tokens: int   # DeepSeek 在 usage 中返回缓存命中量
    completion_tokens: int

    @property
    def fresh_input(self) -> int:
        return self.prompt_tokens - self.cached_prompt_tokens


@dataclass
class BudgetState:
    """月预算状态（RMB 结算）。token 仅作中间量，决策口径是 ¥。"""
    monthly_budget_rmb: float = 100.0   # 默认 ¥100/月
    month_used_rmb: float = 0.0
    # 三类 token 累计，用于成本归因与 debug
    input_tokens: int = 0
    output_tokens: int = 0
    cached_input_tokens: int = 0
    per_agent: dict = field(default_factory=dict)   # agent_name -> {"rmb":..., "calls":...}

    def cost_of(self, u: UsageRecord) -> float:
        p = PRICING_RMB[u.model]
        return (
            u.cached_prompt_tokens * p["cached_input"]
            + u.fresh_input * p["input"]
            + u.completion_tokens * p["output"]
        ) / 1_000_000

    def record(self, agent: str, u: UsageRecord):
        cny = self.cost_of(u)
        self.month_used_rmb += cny
        self.input_tokens += u.fresh_input
        self.output_tokens += u.completion_tokens
        self.cached_input_tokens += u.cached_prompt_tokens
        slot = self.per_agent.setdefault(agent, {"rmb": 0.0, "calls": 0})
        slot["rmb"] += cny
        slot["calls"] += 1

    def usage_ratio(self) -> float:
        return self.month_used_rmb / self.monthly_budget_rmb

    def policy(self) -> str:
        """返回当前应执行的策略：normal / fast_mode / halt"""
        r = self.usage_ratio()
        if r >= 1.2:
            return "halt"          # 暂停非紧急分析
        if r >= 1.0:
            return "fast_mode"     # 强制降级快速模式（辩论压缩为1轮、跳过大师层）
        if r >= 0.8:
            return "warn"          # 告警但仍走完整模式
        return "normal"


class LLMClient:
    def __init__(self, config: Config):
        self.config = config
        self.budget = BudgetState(
            monthly_budget_rmb=config.get("llm.monthly_budget_rmb", 100.0)
        )
        self._clients = {}

    def _get_client(self, provider: str = "deepseek") -> OpenAI:
        if provider not in self._clients:
            api_key = self.config.get(f"llm.{provider}.api_key")
            base_url = self.config.get(f"llm.{provider}.base_url")
            self._clients[provider] = OpenAI(api_key=api_key, base_url=base_url)
        return self._clients[provider]

    def complete(self, messages, model_tier="quick", agent_name="unknown", **kwargs):
        provider = self.config.get(f"llm.{model_tier}.provider", "deepseek")
        model = self.config.get(f"llm.{model_tier}.model", "deepseek-chat")
        client = self._get_client(provider)

        for attempt in range(3):
            try:
                start = time.time()
                response = client.chat.completions.create(
                    model=model, messages=messages, **kwargs
                )
                latency = (time.time() - start) * 1000
                # ⚠️ 必须用 API 返回的 usage，而非估算器（exp14.4: 估算误差 37%）
                usage = response.usage
                rec = UsageRecord(
                    model=model,
                    prompt_tokens=usage.prompt_tokens,
                    cached_prompt_tokens=getattr(usage, "prompt_cache_hit_tokens", 0),
                    completion_tokens=usage.completion_tokens,
                )
                self.budget.record(agent_name, rec)
                return {
                    "content": response.choices[0].message.content,
                    "usage": rec,
                    "cost_rmb": self.budget.cost_of(rec),
                    "latency_ms": latency,
                    "model": model,
                }
            except Exception as e:
                if attempt < 2:
                    time.sleep(2 ** attempt)
                else:
                    raise
```

> **设计要点（来自 exp14）**：
> 1. 预算口径是 **RMB 月成本**，不是 token 数。fast_mode 由 `usage_ratio() >= 1.0`（月预算 100%）触发，而非旧的「400k token × 90%」——旧阈值在 63,600/股 的真实消耗下约 6 股就触发，毫无意义。
> 2. `UsageRecord` 区分 `cached / fresh input / output`，对应三档定价，禁止用 `total_tokens` 线性外推（input:output ≈ 4.6:1，缓存只省 input）。
> 3. token 计数**只用 API 返回值**，估算器仅用于规划/展示（误差 37%，见 exp14.4）。
> 4. `policy()` 三级降级（warn → fast_mode → halt），可在工作流编排层读取以决定是否压缩辩论轮次。

### 5.3 providers/base.py

```python
"""数据源适配器基类：断路器+重试+连接池"""
import time
import httpx
from enum import Enum

class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

class CircuitBreaker:
    def __init__(self, failure_threshold=3, cooldown=300):
        self.failure_threshold = failure_threshold
        self.cooldown = cooldown
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time = 0

    def can_execute(self) -> bool:
        if self.state == CircuitState.CLOSED:
            return True
        if self.state == CircuitState.OPEN:
            if time.time() - self.last_failure_time >= self.cooldown:
                self.state = CircuitState.HALF_OPEN
                return True
            return False
        return True  # HALF_OPEN

    def record_success(self):
        self.failure_count = 0
        self.state = CircuitState.CLOSED

    def record_failure(self):
        self.failure_count += 1
        self.last_failure_time = time.time()
        if self.failure_count >= self.failure_threshold:
            self.state = CircuitState.OPEN

class SourceAdapter:
    def __init__(self, name: str, priority: int = 99):
        self.name = name
        self.priority = priority
        self.breaker = CircuitBreaker()
        self.client = httpx.Client(timeout=10, pool_connections=20)

    def fetch_kline(self, code: str, days: int = 365):
        if not self.breaker.can_execute():
            raise ConnectionError(f"{self.name} 熔断中")
        try:
            result = self._do_fetch_kline(code, days)
            self.breaker.record_success()
            return result
        except Exception as e:
            self.breaker.record_failure()
            raise
```

---

## 六、开始实现的第一步

**立即可以做的**（这些文件相互独立，可并行实现，且不需要外部 API 调用）：

1. 创建 `ashare-x/` 项目目录结构 + `pyproject.toml` + `.env.example` + `.gitignore`
2. 实现 `core/config.py`（含 `llm.monthly_budget_rmb` 默认 ¥100）
3. 实现 `core/exceptions.py`
4. 实现 `core/state.py`（AgentState TypedDict）
5. 实现 `db/engine.py` + `db/models.py` + `db/migrations.py`
6. **同步**：为上述每个文件写 `tests/unit/test_*.py`（不得延后，见 §四前提）

> 配套的 RMB 预算表（§0.1）与 exp14 实测数据已就绪，`test_llm_budget.py` 可在 Phase 3 与 `llm_client.py` 同步落地。

---

## 七、风险与未知

| # | 风险/未知 | 影响 | 应对 |
|---|----------|------|------|
| R1 | **exp14 定价时效**：V4 定价/分层可能在实现期内变动 | 预算阈值失准 | `PRICING_RMB` 抽成可配置项（config.yaml），定期对齐官方页面；加版本号与更新日期字段 |
| R2 | **token 计数误差 37%**（exp14.4，tiktoken vs DeepSeek tokenizer） | 规划期成本预估偏差 | 生产路径**只用 API 返回的 usage**，估算器仅用于规划展示；预算阈值留 20% 缓冲（halt 在 120%） |
| R3 | **`super_workflow.py` 真实复杂度**（2355 行）提示 Phase 3/4 可能进一步超估 | 工期风险 | Phase 3 行数已上调到 2400；若实施中发现 Agent prompt/schema 复杂度超预期，及时回写本计划 |
| R4 | **月预算在「全市场扫描」场景下不够用**（50 只/天 快速模式 ≈ ¥118/月） | 用户超预算 | 默认 ¥100/月 仅适用日常；扫描类任务单独走「快速模式 + 任务级预算授权」，不占用日常月额度 |
| R5 | **与现有 `a-share-investment-system/` 的数据隔离** | 两套 DB 各自维护，数据冗余 | 明确不共享 `data/`（见 §0）；本计划用独立 `runtime/` 目录。短期可接受，长期见 §八 |
| R6 | **辩论机制是成本大头**（exp14：占 token 60%） | 预算紧张时被迫降质 | `budget.policy()` 触发 fast_mode 时自动把辩论从 2 轮压到 1 轮（S06 可配置），作为成本-质量旋钮 |
| R7 | **缓存命中率不可控**（exp14：50% 命中实际只省 31.6%） | 降本效果不及预期 | 不把缓存当作硬依赖；预算按「无缓存」上界设，缓存收益作为下行惊喜 |
| R8 | **Tauri 已从计划中移除**，但 S10/S11 设计文档若仍提 Tauri 需同步修正 | 文档不一致 | 本计划已对齐 Electron；需检查 `project-design/S10-frontend.md` 是否提 Tauri，若有则一并订正（属设计文档维护，不在本计划交付内） |

---

## 八、迁移与退役说明（现有代码的处置）

> 本计划是重写，交付前**不动现有 `a-share-investment-system/`**。以下是在本计划验证通过后的后续处置预案，**不属于本计划的执行内容**。

1. **验证门槛**：`ashare-x/` 通过 §四 Phase 6 端到端测试（`main.py analyze 600519` 产出完整报告 + 决策），且 `test_llm_budget.py` 断言月成本曲线与 exp14 一致。
2. **数据迁移**：若决定退役旧项目，将其 `data/*.db` 中的 K 线、财报数据通过一次性脚本导入 `ashare-x/runtime/`（schema 不同需映射），决策/报告历史不迁移（语义已变）。
3. **知识复用**：`quant-agents/` 的 SKILL.md 在本计划 §4.5 已直接复用，不涉及迁移。
4. **退役判定**：新旧两套并行运行 2-4 周，对比同股票同日分析结果的一致性与成本，确认新版不劣于旧版后归档旧项目（保留只读）。
5. **不做的事**：本计划不提供「从旧代码增量迁移到新结构」的脚本——重写的意义就在于摆脱旧结构，增量迁移会带入结构性债务。

---

**是否现在开始 Phase 1？**
