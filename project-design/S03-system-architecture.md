# S3 — 系统总体架构

## 3.1 架构概览

```
┌─────────────────────────────────────────────────────────────────┐
│                    表现层 (Presentation)                         │
│  React/Vite + Tailwind CSS + ReactFlow + Recharts + SSE         │
├─────────────────────────────────────────────────────────────────┤
│                    API网关 (Gateway)                             │
│  FastAPI + SSE流式响应 + REST API + 静态文件服务                  │
├─────────────────────────────────────────────────────────────────┤
│                    编排层 (Orchestration)                        │
│  LangGraph StateGraph + 条件路由 + 并行调度 + 检查点恢复        │
├─────────────────────────────────────────────────────────────────┤
│                    Agent层 (Agents)                              │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐            │
│  │ 分析师团队    │ │ 研究员团队    │ │ 风险管理团队  │            │
│  │ (4 Agents)   │ │ (3 Agents)   │ │ (4 Agents)   │            │
│  └──────────────┘ └──────────────┘ └──────────────┘            │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐            │
│  │ 交易员       │ │ 组合经理      │ │ 大师视角层    │            │
│  │ (1 Agent)    │ │ (1 Agent)    │ │ (可选, 7人)   │            │
│  └──────────────┘ └──────────────┘ └──────────────┘            │
├─────────────────────────────────────────────────────────────────┤
│                    Skill层 (Skills)                              │
│  投资哲学技能库 + A股特化技能 + 技术分析技能                     │
├─────────────────────────────────────────────────────────────────┤
│                    工具层 (Tools)                                 │
│  数据获取工具 + 技术指标计算 + 财务分析 + 新闻搜索 + 模拟交易    │
├─────────────────────────────────────────────────────────────────┤
│                    数据层 (Data)                                  │
│  SQLite(主存储) + 文件系统(报告/记忆) — 无外部数据库依赖        │
├─────────────────────────────────────────────────────────────────┤
│                    基础设施 (Infrastructure)                     │
│  Python 3.10+ / FastAPI / LangGraph / 纯本地运行               │
└─────────────────────────────────────────────────────────────────┘
```

## 3.2 技术栈选择理由

| 组件 | 选择 | 为什么不用其他 |
|------|------|----------------|
| 数据库 | SQLite | 不需要Redis/MongoDB，SQLite够用且零配置 |
| 缓存 | 内存字典+SQLite | 不需要外部缓存服务 |
| 工作流 | LangGraph | 状态机模式最适合多Agent协作，条件分支天然支持 |
| LLM | DeepSeek API | V4-Flash($0.14/1M)+V4-Pro($1.74+/1M)，低成本非免费。详见 S11.4 成本估算 |
| 前端 | React+Vite+Tailwind+ReactFlow | 现代前端标准，ReactFlow用于Agent可视化 |
| 后端 | FastAPI | 异步框架，SSE支持好，与LangGraph集成 |
| 桌面 | Electron | 桌面应用壳（与前端同栈 Node.js，自带 Chromium 渲染一致性最佳；VS Code/Discord 同栈） |
| ORM | SQLAlchemy 2.0 | Python标准ORM，SQLite支持最好 |

## 3.3 目录结构

```
ashare-x/
├── main.py                          # CLI入口
├── server.py                        # FastAPI服务器入口
├── launch.py                        # 一键启动脚本
├── pyproject.toml                   # 项目配置
│
├── core/                            # 核心框架
│   ├── agent_base.py                # Agent基类
│   ├── state.py                     # 全局状态定义 (TypedDict)
│   ├── config.py                    # 配置管理（config.yaml）
│   └── llm_factory.py              # LLM工厂（多提供商API）
│
├── agents/                          # Agent定义（含执行逻辑）
│   ├── analysts/                    # 分析师团队
│   │   ├── market_analyst.py        # 市场分析师（技术面）
│   │   ├── fundamentals_analyst.py  # 基本面分析师
│   │   ├── news_analyst.py          # 新闻分析师
│   │   └── sentiment_analyst.py     # 情绪分析师
│   ├── researchers/                 # 研究员团队
│   │   ├── bull_researcher.py       # 看涨研究员
│   │   ├── bear_researcher.py       # 看跌研究员
│   │   └── research_manager.py      # 研究经理（裁判）
│   ├── risk_mgmt/                   # 风险管理团队
│   │   ├── aggressive_analyst.py    # 激进分析师
│   │   ├── conservative_analyst.py  # 保守分析师
│   │   ├── neutral_analyst.py       # 中性分析师
│   │   └── portfolio_manager.py     # 投资组合经理（最终决策）
│   ├── trader/
│   │   └── trader.py                # 交易员
│   └── masters/                     # 大师视角层（可选）
│       ├── buffett.py
│       ├── munger.py
│       ├── lynch.py
│       ├── fisher.py
│       ├── burry.py
│       ├── druckenmiller.py
│       └── wood.py
│
├── graph/                           # LangGraph编排（仅编排，不含Agent执行逻辑）
│   ├── trading_graph.py             # 主工作流定义（节点注册+边连接）
│   └── conditional_logic.py         # 条件路由（辩论轮次/终止判断）
│
├── tools/                           # Agent可用工具
│   ├── stock_data.py                # 股票数据获取
│   ├── technical_indicators.py      # 技术指标计算
│   ├── fundamentals.py              # 基本面数据
│   ├── news_search.py               # 新闻搜索
│   ├── social_sentiment.py          # 社交情绪
│   ├── paper_trading.py             # 模拟交易
│   └── web_search.py                # 网络搜索
│
├── providers/                       # 数据提供商（从现有系统迁移）
│   ├── sources/                     # 数据源适配器（11个）
│   │   ├── tencent.py               # 腾讯行情（主）
│   │   ├── sina.py                  # 新浪行情（备）
│   │   ├── sina_financial.py        # 新浪财务报表
│   │   ├── eastmoney.py             # 东方财富（备）
│   │   ├── akshare_src.py           # AKShare（综合）
│   │   ├── baostock_src.py          # BaoStock（历史K线+回测）
│   │   ├── yfinance_src.py          # yfinance（美股/港股参考+备用）
│   │   ├── lhb.py                   # 龙虎榜
│   │   ├── hot_rank.py              # 热门股票
│   │   ├── board_rank.py            # 板块排行
│   │   └── zt_pool.py              # 涨停池
│   ├── base.py                      # 提供商基类（断路器+重试+连接池）
│   ├── data_bus.py                  # DatabaseBackedDataBus
│   ├── data_quality.py              # 数据质量检查
│   └── market_data.py               # 数据总线入口
│
├── skills/                          # Skill系统
│   ├── skill_engine.py              # Skill引擎
│   ├── registry.py                  # Skill注册表
│   ├── buffett/SKILL.md + references/
│   ├── munger/SKILL.md + references/
│   ├── taleb/SKILL.md + references/
│   ├── a-share-trading/SKILL.md + references/
│   └── china-stock-research/SKILL.md + references/
│
├── memory/                          # 记忆系统
│   ├── decision_log.py              # 决策日志
│   ├── reflection.py                # 反思引擎
│   └── long_term.py                 # 长期记忆
│
├── services/                        # 业务服务
│   ├── screening.py                 # 选股服务
│   ├── portfolio.py                 # 组合管理
│   ├── risk_engine.py               # 风险引擎
│   ├── trading_plan.py              # 交易计划生成
│   ├── market_perception.py         # 市场感知
│   ├── backtest.py                  # 回测引擎（仅因子回测）
│   └── report.py                    # 报告生成
│
├── api/routes/                      # FastAPI路由
├── frontend/                        # React前端
│   ├── src/                         # React源码
│   ├── dist/                        # 构建输出
│   └── package.json
├── electron/                        # Electron桌面壳
│   ├── main.ts                      # 主进程入口
│   ├── preload.ts                   # 预加载脚本（contextBridge）
│   └── electron-builder.yml         # 打包配置
├── tests/                           # 测试
├── strategies/                      # YAML策略定义
├── config/config.yaml               # 主配置
├── runtime/                         # 运行时数据（SQLite数据库+检查点）
├── reports/                         # 生成的报告
└── logs/                            # 日志
```

## 3.4 数据流

```
用户请求
  │
  ▼
API网关 (FastAPI)
  │
  ▼
编排层 (LangGraph StateGraph)
  │
  ├──→ Agent层 ──→ 工具层 ──→ 数据层
  │     │              │           │
  │     │              │     ┌─────┴─────┐
  │     │              │     │ SQLite缓存 │
  │     │              │     │  ↓ (miss)  │
  │     │              │     │ 在线API    │
  │     │              │     └───────────┘
  │     │              │
  │     └── Skill层 (注入prompt)
  │
  ├──→ 输出 (结构化交易计划)
  │     │
  │     ├──→ SSE实时推送 → 前端
  │     ├──→ decision_log → SQLite
  │     ├──→ 文件存储 → reports/
  │     └──→ 反思引擎 → memory/
```

## 3.5 容错策略

Agent层采用"降级继续"模式，任何单点失败不阻断整个流程：

| 失败场景 | 降级策略 | 影响 |
|----------|----------|------|
| 分析师调用超时 | 该维度标记"数据不可用"，继续后续Agent | 缺失一个分析维度 |
| 研究员辩论失败 | 跳过辩论，直接用分析师报告综合判断 | 缺少多空对抗 |
| 风险团队失败 | 使用保守默认值（"Hold"，风险等级"HIGH"） | 偏保守 |
| 投资组合经理失败 | 使用交易员提案作为最终决策 | 缺少组合层面考量 |
| 大师视角失败 | 跳过大师层，不影响主流程 | 缺少额外视角 |
| LLM API完全不可用 | 返回"系统暂时不可用，请稍后重试" | 完全中断 |

每个Agent自带超时和重试（见S4.9），数据层自带断路器和故障转移（见S5）。

## 3.6 Token预算管理

DeepSeek免费额度：`deepseek-chat` 500万token/天，`deepseek-reasoner` 另有独立额度。系统需要预算控制防止超额：

```yaml
# config.yaml
token_budget:
  # 每个Agent的单次调用上限
  analyst_per_call: 2000           # 每个分析师最多2000 token
  debate_round: 3000               # 每轮辩论3000 token
  risk_debate_round: 2000          # 每轮风险辩论2000 token
  master_view: 1500                # 每个大师视角1500 token
  research_manager: 2500           # 研究经理
  trader: 1500                     # 交易员
  portfolio_manager: 3000          # 投资组合经理

  # 每日总预算（安全线，留20%余量）
  daily_total: 400000              # 40万token/天（免费额度的80%）

  # 单只股票分析预算上限
  per_stock: 25000                 # 2.5万token/只
```

**超预算处理**: 当日累计token使用达到 `daily_total` 的90%时，后续分析降级为"快速模式"——跳过辩论和大师层，仅执行分析师+交易员+投资组合经理。

> 注意：以上数字为初始估算值，需根据实际运行调整。

## 3.7 安全设计

| 风险 | 措施 |
|------|------|
| API密钥泄露 | .env文件gitignore，不硬编码到代码 |
| LLM调用超限 | Token预算控制（见3.6） |
| 数据源滥用 | 断路器+频率限制（见S5） |
| 用户输入注入 | Agent prompt模板化，不直接拼接用户输入 |
| 本地文件安全 | SQLite数据库和配置文件仅本机可访问 |

## 3.8 部署方案

**推荐**: 本地直接运行（无Docker依赖）

```bash
# 一键启动（构建前端+启动后端+打开浏览器）
python launch.py

# 仅启动API
python main.py serve

# 全市场扫描
python main.py screen

# 单股深度分析
python main.py analyze 600519

# 每日分析（市场感知+选股+交易计划）
python main.py daily

# Electron桌面应用
cd electron && npm run electron:dev    # 开发模式
cd electron && npm run electron:build  # 打包发布（electron-builder）
```

## 3.9 配置管理

配置加载顺序（优先级从高到低）：
1. 环境变量（`DEEPSEEK_API_KEY` 等）
2. `config/.env`（本地密钥，gitignore）
3. `config/config.yaml`（主配置）
4. 代码中的默认值

关键配置项：
- `llm`: LLM提供商和模型选择
- `token_budget`: token预算控制
- `debate`: 辩论轮次配置
- `data_providers`: 数据源优先级

## 3.10 监控与日志

| 监控项 | 实现方式 | 存储位置 |
|--------|----------|----------|
| Agent执行状态 | 进度事件(SSE) | 内存 |
| LLM调用日志 | 结构化日志 | logs/llm.log |
| Token使用量 | 内存计数器 | 日终写入SQLite |
| 数据源健康 | 断路器状态 | 内存 |
| 决策记录 | decision_log表 | SQLite |
| 错误日志 | Python logging | logs/error.log |

## 3.11 测试策略

| 测试类型 | 范围 | 工具 |
|----------|------|------|
| 单元测试 | 工具函数、数据解析 | pytest |
| 集成测试 | Agent工作流 | pytest + mock LLM |
| 因子回测 | 量化因子有效性 | backtest.py（仅因子，不回测LLM决策） |
| 纸上交易 | 每日生成交易计划，30天后统计胜率 | 系统自动记录 |
| 手动验证 | 交易计划质量 | 人工抽检 |

### 回测与未来信息泄露防范

**核心问题**: LLM的训练数据包含未来信息，导致回测结果不可信。

| 信息泄露类型 | 例子 | 防范措施 |
|-------------|------|----------|
| 训练数据泄露 | LLM训练数据包含回测期间的财报 | 无法避免，只能标注"仅供参考" |
| 数据源泄露 | API返回了回测日期之后的新闻 | 只用回测日期之前的数据 |
| 指标泄露 | 技术指标用了未来收盘价 | 严格时间对齐，只用历史数据 |

**正确的验证路径**:
1. **因子回测**（高可信度）：只回测量化因子（PE/ROE/动量），不经过LLM
2. **纸上交易**（中可信度）：每天运行系统记录交易计划，30/60/90天后统计
3. **滚动分析**（中可信度）：每天重新分析，验证LLM是否能选出更好的标的

> 注意：LLM决策的回测结果只能作为参考，不能作为策略有效性的证明。

## 3.12 完整配置Schema

配置文件 `config/config.yaml` 的完整结构（合并S03/S04/S07/S11中的分散配置项）：

```yaml
# config/config.yaml — 完整配置

# === LLM配置 ===
llm:
  quick_think:                          # 日常分析模型
    provider: "deepseek"
    model: "deepseek-chat"
    api_key: $DEEPSEEK_API_KEY          # 从.env加载
    temperature: 0.7
    max_tokens: 4000
    timeout: 60.0
  deep_think:                           # 深度推理模型
    provider: "deepseek"
    model: "deepseek-reasoner"
    api_key: $DEEPSEEK_API_KEY
    temperature: 0.7
    max_tokens: 8000
    timeout: 120.0
  # 备选配置
  # quick_think:
  #   provider: "dashscope"
  #   model: "qwen-turbo"
  #   api_key: $DASHSCOPE_API_KEY

# === Token预算 ===
token_budget:
  daily_total: 400000                   # 每日总预算（40万）
  per_stock: 25000                      # 单股分析上限（2.5万）
  fast_mode_threshold: 0.9              # 快速模式触发阈值（90%）
  analyst_per_call: 2000                # 每个分析师单次上限
  debate_round: 3000                    # 每轮辩论上限
  risk_debate_round: 2000               # 每轮风险辩论上限
  master_view: 1500                     # 每个大师视角上限
  research_manager: 2500                # 研究经理上限
  trader: 1500                          # 交易员上限
  portfolio_manager: 3000               # 投资组合经理上限

# === 辩论配置 ===
debate:
  investment:
    max_rounds: 2                       # 多空辩论最大轮次
    min_rounds: 1
    termination: "consensus_or_max"     # 终止条件
  risk:
    max_rounds: 2                       # 风险辩论最大轮次
    min_rounds: 1
    participants: ["aggressive", "conservative", "neutral"]

# === Agent配置 ===
agent:
  retry:
    max_attempts: 2                     # 最多重试次数
    base_delay: 2.0                     # 基础延迟（秒）
    backoff_multiplier: 2.0             # 指数退避倍数
    max_delay: 30.0                     # 最大延迟（秒）
  timeout:
    analyst: 60                         # 分析师超时（秒）
    researcher: 120                     # 研究员超时（辩论多轮）
    trader: 45                          # 交易员超时
    risk_analyst: 60                    # 风险分析师超时
    portfolio_manager: 90               # 组合经理超时
    workflow_total: 600                 # 全局超时（10分钟）

# === 数据源配置 ===
data_providers:
  priority:                             # 优先级（数字越小越优先）
    - tencent                           # 1: 主数据源
    - sina                              # 2: 备用
    - eastmoney                         # 3: 备用
    - akshare                           # 4: 综合数据
    - baostock                          # 5: 回测数据
  circuit_breaker:
    failure_threshold: 3                # 连续失败次数触发熔断
    cooldown_seconds: 300               # 熔断冷却时间（5分钟）
    half_open_max_calls: 1              # 半开状态最大请求数
  retry:
    max_retries: 2                      # 数据获取最大重试
    base_delay: 1.5                     # 基础退避延迟
    backoff_multiplier: 2.0
  rate_limit:
    max_concurrent: 5                   # 最大并发API请求
    zombie_timeout: 120                 # 僵尸线程回收时间（秒）

# === Skill配置 ===
skills:
  enabled:
    - buffett                           # 巴菲特价值投资框架
    - munger                            # 芒格多元思维模型
    - taleb                             # 塔勒布反脆弱框架
    - a-share-trading                   # A股特化规则
    - china-stock-research              # A股全栈研究
  auto_load: true                       # 自动发现并加载

# === 功能开关 ===
features:
  enable_masters: false                 # 启用大师视角层（可选）
  enable_memory: true                   # 启用记忆系统
  enable_paper_trading: true            # 启用模拟交易
  enable_reflection: true               # 启用反思引擎

# === 服务器配置 ===
server:
  host: "127.0.0.1"
  port: 8765                            # 默认端口（搜索8765-8775空闲端口）
  frontend_dir: "frontend/dist"         # 前端构建输出目录
  cors_origins: ["http://localhost:5173"]  # 开发模式CORS

# === 日志配置 ===
logging:
  level: "INFO"                         # DEBUG/INFO/WARNING/ERROR
  format: "json"                        # json/text
  dir: "logs"                           # 日志目录
  llm_log: "logs/llm.log"              # LLM调用日志
  agent_log: "logs/agent.log"           # Agent执行日志
  error_log: "logs/error.log"           # 错误日志
  max_file_size_mb: 50                  # 单文件最大50MB
  backup_count: 5                       # 保留5个备份

# === 数据库配置 ===
database:
  path: "runtime/investment.db"         # SQLite数据库路径
  checkpoint_dir: "runtime/checkpoints" # LangGraph检查点目录
  reports_dir: "reports"                # 报告输出目录

# === 选股配置 ===
screening:
  max_results: 20                       # 最大返回数量
  min_score: 60.0                       # 最低综合评分
  exclude_st: true                      # 排除ST
  exclude_new_days: 60                  # 排除次新（上市<60天）
  min_turnover: 5000000                 # 最低日成交额（元）

# === 风控配置 ===
risk:
  market_state_caps:                    # 市场状态→仓位上限
    PANIC: 0.10
    BEAR: 0.30
    NEUTRAL: 0.60
    BULL: 0.80
    OVERHEAT: 0.50
  max_single_position: 0.15             # 单只最大仓位（15%）
  max_industry_exposure: 0.30           # 单行业最大暴露（30%）
  paper_trading:
    initial_capital: 1000000            # 初始资金（100万）
    commission_rate: 0.00025            # 佣金费率（万2.5）
    stamp_tax_rate: 0.001               # 印花税（千1，仅卖出）
    transfer_fee_rate: 0.00001          # 过户费（十万分之一）
```

### 配置加载优先级

1. 环境变量（`DEEPSEEK_API_KEY` 等）
2. `config/.env`（本地密钥，gitignore）
3. `config/config.yaml`（主配置）
4. 代码中的默认值

## 3.13 部署与环境

### Python依赖清单

```toml
# pyproject.toml 核心依赖
[project]
name = "ashare-x"
version = "0.1.0"
requires-python = ">=3.10"

dependencies = [
    # 后端框架
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.34.0",
    "httpx>=0.28.0",                    # HTTP客户端

    # LLM
    "langchain-core>=0.3.0",
    "langchain-openai>=0.3.0",          # OpenAI兼容API（DeepSeek/Qwen）
    "langgraph>=0.3.0",                 # 工作流引擎

    # 数据层
    "sqlalchemy>=2.0.0",
    "aiosqlite>=0.20.0",               # 异步SQLite
    "pydantic>=2.10.0",                 # 数据模型

    # 数据源
    "akshare>=1.15.0",                  # A股综合数据
    "baostock>=0.8.8",                  # 历史K线（日频+）
    "yfinance>=0.2.40",                 # 美股/港股/全球市场（日频+）
    "pandas>=2.2.0",                    # 数据处理
    "stockstats>=0.6.0",                # 技术指标计算

    # 工具
    "pyyaml>=6.0",                      # 配置文件
    "python-dotenv>=1.0.0",             # .env加载
    "sse-starlette>=2.0.0",             # SSE支持
]
```

### 环境变量清单

```bash
# config/.env 模板
DEEPSEEK_API_KEY=sk-xxx                # DeepSeek API密钥（必填）
DASHSCOPE_API_KEY=sk-xxx               # 阿里云DashScope（备选）
ZHIPU_API_KEY=xxx                      # 智谱AI（备选）
API_KEY=                               # 本地API访问密钥（可选）
```

### 首次运行初始化

```bash
# 1. 克隆项目
git clone <repo-url> ashare-x
cd ashare-x

# 2. 创建虚拟环境
python -m venv .venv
.venv\Scripts\activate                  # Windows
# source .venv/bin/activate            # Linux/Mac

# 3. 安装依赖
pip install -e .

# 4. 配置环境变量
cp config/.env.example config/.env
# 编辑config/.env，填入DEEPSEEK_API_KEY

# 5. 构建前端
cd frontend
npm install
npm run build
cd ..

# 6. 启动
python launch.py                       # 一键启动（构建+后端+浏览器）
# 或
python main.py serve                   # 仅启动API
python main.py analyze 600519          # 单股分析
python main.py daily                   # 每日分析
python main.py screen                  # 全市场扫描
```

### 前端构建

```bash
cd frontend
npm install                            # 安装依赖
npm run dev                            # 开发模式（热重载，端口5173）
npm run build                          # 生产构建（输出到dist/）
npm run lint                           # 代码检查
npm run typecheck                      # 类型检查
```

## 3.14 日志与可观测性

### 结构化日志格式

```python
# JSON Lines格式，每条日志一行JSON
{
    "timestamp": "2026-06-13T10:30:15.123Z",
    "level": "INFO",
    "module": "agent.market_analyst",
    "event": "llm_call",
    "ticker": "600519",
    "agent": "market_analyst",
    "model": "deepseek-chat",
    "prompt_tokens": 1200,
    "completion_tokens": 800,
    "total_tokens": 2000,
    "latency_ms": 3500,
    "cost": 0.0,
    "status": "success"
}
```

### 日志类别

| 日志文件 | 内容 | 格式 |
|----------|------|------|
| `logs/llm.log` | 每次LLM调用的详细记录 | JSON Lines |
| `logs/agent.log` | Agent执行状态变更 | JSON Lines |
| `logs/error.log` | 错误和异常 | JSON Lines |
| `logs/access.log` | HTTP请求日志 | Combined |

### LLM调用追踪

```python
class LLMCallTracker:
    """每次LLM调用自动记录"""

    def __init__(self, log_file: str = "logs/llm.log"):
        self.logger = logging.getLogger("llm")
        handler = RotatingFileHandler(log_file, maxBytes=50*1024*1024, backupCount=5)
        handler.setFormatter(JsonFormatter())
        self.logger.addHandler(handler)

    def log_call(self, agent: str, model: str, usage: TokenUsage, latency_ms: float, status: str):
        self.logger.info({
            "event": "llm_call",
            "agent": agent,
            "model": model,
            "prompt_tokens": usage.prompt_tokens,
            "completion_tokens": usage.completion_tokens,
            "total_tokens": usage.total_tokens,
            "latency_ms": latency_ms,
            "status": status,
        })
```

### Agent执行追踪

```python
class AgentTracker:
    """Agent节点执行追踪"""

    def log_start(self, agent: str, ticker: str):
        """记录Agent开始执行"""
        ...

    def log_complete(self, agent: str, ticker: str, duration_ms: float, token_usage: int):
        """记录Agent执行完成"""
        ...

    def log_error(self, agent: str, ticker: str, error: str):
        """记录Agent执行错误"""
        ...
```

### 前端实时指标

通过SSE推送的系统指标：

```python
class SystemMetrics:
    """系统运行指标"""

    def get_metrics(self) -> dict:
        return {
            "token_used_today": self.counter.daily_used,
            "token_budget_remaining": self.counter.remaining(),
            "token_utilization_pct": self.counter.daily_used / self.counter.daily_budget * 100,
            "active_jobs": self.job_manager.active_count(),
            "data_source_health": self.data_bus.get_health(),  # 各数据源断路器状态
            "llm_avg_latency_ms": self.tracker.avg_latency(),
            "error_rate_24h": self.tracker.error_rate(hours=24),
        }
```

## 3.15 环境变量覆盖机制（借鉴TradingAgents v0.2.5）

TradingAgents通过`TRADINGAGENTS_*`环境变量覆盖config，我们采用同样的模式：

```python
# 单一配置源：环境变量 → config.yaml → 代码默认值
_ENV_OVERRIDES = {
    "ASHARE_X_LLM_PROVIDER":           "llm.quick_think.provider",
    "ASHARE_X_DEEP_THINK_MODEL":       "llm.deep_think.model",
    "ASHARE_X_QUICK_THINK_MODEL":      "llm.quick_think.model",
    "ASHARE_X_DAILY_TOKEN_BUDGET":     "token_budget.daily_total",
    "ASHARE_X_MAX_DEBATE_ROUNDS":      "debate.investment.max_rounds",
    "ASHARE_X_MAX_RISK_ROUNDS":        "debate.risk.max_rounds",
    "ASHARE_X_CHECKPOINT_ENABLED":     "features.checkpoint_enabled",
    "ASHARE_X_OUTPUT_LANGUAGE":        "features.output_language",
    "ASHARE_X_TEMPERATURE":            "llm.quick_think.temperature",
}
```

### 加载优先级

```
1. 环境变量 (ASHARE_X_*)
2. config/.env (本地密钥)
3. config/config.yaml (主配置)
4. 代码中的默认值
```

### 实现

```python
import os
import yaml
from typing import Any

def load_config(config_path: str = "config/config.yaml") -> dict:
    """加载配置，支持环境变量覆盖"""
    # 1. 加载config.yaml
    with open(config_path) as f:
        config = yaml.safe_load(f)

    # 2. 应用环境变量覆盖
    for env_var, config_key in _ENV_OVERRIDES.items():
        raw = os.environ.get(env_var)
        if raw is None or raw == "":
            continue
        # 按config_key路径设置值
        _set_nested(config, config_key, _coerce(raw, _get_nested(config, config_key)))

    return config

def _set_nested(d: dict, key: str, value: Any):
    """设置嵌套字典值，如 'llm.quick_think.provider'"""
    keys = key.split(".")
    for k in keys[:-1]:
        d = d.setdefault(k, {})
    d[keys[-1]] = value

def _get_nested(d: dict, key: str, default=None):
    """获取嵌套字典值"""
    keys = key.split(".")
    for k in keys:
        if isinstance(d, dict):
            d = d.get(k, default)
        else:
            return default
    return d

def _coerce(value: str, reference):
    """将环境变量字符串转换为目标类型"""
    if isinstance(reference, bool):
        return value.strip().lower() in ("true", "1", "yes", "on")
    if isinstance(reference, int) and not isinstance(reference, bool):
        return int(value)
    if isinstance(reference, float):
        return float(value)
    return value
```

## 3.16 CLI工具（借鉴TradingAgents + AI Hedge Fund）

使用typer构建CLI，rich格式化终端输出：

```python
# cli/main.py
import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

app = typer.Typer(name="ashare-x", help="AShare-X AI投研系统")
console = Console()

@app.command()
def analyze(
    ticker: str = typer.Argument(help="股票代码，如 600519"),
    fast: bool = typer.Option(False, "--fast", "-f", help="快速模式"),
    masters: bool = typer.Option(False, "--masters", "-m", help="启用大师视角"),
):
    """单股深度分析"""
    with Progress(SpinnerColumn(), TextColumn("{task.description}")) as progress:
        task = progress.add_task(f"分析 {ticker} ...", total=None)
        result = run_analysis(ticker, fast_mode=fast, enable_masters=masters)
        progress.update(task, description=f"✅ {ticker} 分析完成")

    # Rich格式化输出
    print_trading_plan(result)

@app.command()
def daily(
    count: int = typer.Option(10, "--count", "-n", help="分析股票数量"),
    fast: bool = typer.Option(False, "--fast", "-f", help="快速模式"),
):
    """每日分析（市场感知+选股+交易计划）"""
    ...

@app.command()
def screen(
    style: str = typer.Option("value", "--style", "-s", help="选股风格(value/growth/momentum)"),
    top: int = typer.Option(20, "--top", "-n", help="返回数量"),
):
    """全市场扫描选股"""
    ...

@app.command()
def serve(
    port: int = typer.Option(8765, "--port", "-p", help="API端口"),
    host: str = typer.Option("127.0.0.1", "--host", help="监听地址"),
):
    """启动Web服务器"""
    ...

def print_trading_plan(result):
    """Rich格式化输出交易计划"""
    # 决策标签
    action_colors = {"Buy": "red", "Sell": "green", "Hold": "blue"}
    color = action_colors.get(result.trading_plan.action, "white")

    # 交易计划面板
    table = Table(show_header=True, header_style="bold")
    table.add_column("字段", style="dim")
    table.add_column("值")
    table.add_row("股票", f"{result.ticker} {result.stock_name}")
    table.add_row("决策", f"[{color}]{result.trading_plan.action}[/{color}]")
    table.add_row("置信度", f"{result.trading_plan.confidence:.0f}%")
    table.add_row("入场价", f"¥{result.trading_plan.entry_price:.2f}")
    table.add_row("止损价", f"¥{result.trading_plan.stop_loss:.2f}")
    table.add_row("止盈价", f"¥{result.trading_plan.take_profit:.2f}")
    table.add_row("仓位", f"{result.trading_plan.position_pct:.1f}%")

    console.print(Panel(table, title="交易计划", border_style=color))
```

### CLI命令清单

| 命令 | 用途 | 示例 |
|------|------|------|
| `ashare-x analyze <ticker>` | 单股深度分析 | `ashare-x analyze 600519` |
| `ashare-x daily` | 每日分析 | `ashare-x daily -n 10` |
| `ashare-x screen` | 全市场选股 | `ashare-x screen -s value -n 20` |
| `ashare-x serve` | 启动Web服务器 | `ashare-x serve -p 8765` |
| `ashare-x health` | 健康检查 | `ashare-x health` |

## 3.17 输出语言配置（借鉴TradingAgents）

TradingAgents将Agent辩论保持在英文（推理质量更好），输出翻译为目标语言：

```yaml
# config.yaml
features:
  output_language: "zh"                 # 输出语言（zh/en）
  debate_language: "en"                 # 辩论语言（英文推理质量更好）
  error_language: "zh"                 # 错误消息语言
  log_language: "en"                   # 日志语言（英文便于分析）
```

### 实现策略

```python
def build_agent_prompt(agent_name: str, state: dict, config: dict) -> str:
    debate_lang = config.get("features", {}).get("debate_language", "en")
    output_lang = config.get("features", {}).get("output_language", "zh")

    # 辩论Agent用英文prompt（提升推理质量）
    if agent_name in ("bull_researcher", "bear_researcher",
                       "aggressive_analyst", "conservative_analyst", "neutral_analyst"):
        system_msg = f"You are a {agent_name}. Respond in {debate_lang}."
    else:
        # 输出Agent用目标语言
        system_msg = f"你是一个{agent_name}。请用{output_lang}回复。"

    return system_msg
```

## 3.18 配置热更新机制

修改config.yaml后无需重启，系统自动检测并重新加载：

```python
class ConfigHotReload:
    """配置热更新"""

    def __init__(self, config_path: str):
        self.config_path = Path(config_path)
        self.last_mtime = 0
        self.config = self._load()

    def _load(self) -> dict:
        if self.config_path.exists():
            with open(self.config_path) as f:
                config = yaml.safe_load(f)
            self.last_mtime = self.config_path.stat().st_mtime
            return config or {}
        return {}

    def get(self, key: str, default=None):
        """获取配置值（自动检测变更）"""
        if self.config_path.exists():
            current_mtime = self.config_path.stat().st_mtime
            if current_mtime > self.last_mtime:
                self.config = self._load()

        keys = key.split(".")
        value = self.config
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                return default
        return value if value is not None else default
```

### 支持热更新的配置项

| 配置项 | 热更新 | 说明 |
|--------|--------|------|
| llm.* | ✅ | 下次调用生效 |
| token_budget.* | ✅ | 立即生效 |
| debate.* | ✅ | 下次分析生效 |
| features.* | ✅ | 立即生效 |
| agent.retry.* | ✅ | 下次重试生效 |
| agent.timeout.* | ✅ | 下次调用生效 |
| server.* | ❌ | 需要重启 |
| database.* | ❌ | 需要重启 |

---

**依赖**: S1(问题), S2(理念)
**被依赖**: S4(Agent), S5(数据), S6(工作流), S10(前端), S11(技术栈)
