# AShare-X 实际架构（个人使用版）

> **注意**: 本文档描述当前代码的实际状态。目标架构参见 `docs/architecture/designs/M1-M6`。

**版本**: 1.0 | **状态**: Current | **日期**: 2026-06-12

---

## 系统定位

个人 A 股投资分析工具，每天收盘后跑一次，输出交易建议。不做实时交易，不做多用户，不做国际化。

---

## 实际目录结构

```
a-share-investment-system/
├── services/                 # 核心业务逻辑（51 个模块）
│   ├── screening/            # 选股 Pipeline（4 阶段，18 个文件）
│   │   ├── pipeline.py       # 统一选股编排
│   │   ├── stages/           # Stage 1-4 实现
│   │   ├── ai_orchestrator.py # AI 评分调整
│   │   ├── ai_agents.py      # AI Agent 分析
│   │   └── ...
│   ├── agents/               # AI 分析 Agent（3 个）
│   │   ├── stock_agent.py    # 个股分析 Agent
│   │   ├── portfolio_agent.py # 组合分析 Agent
│   │   └── decision_agent.py # 交易计划生成 Agent
│   ├── risk_engine.py        # 风控引擎（VaR + 预警）
│   ├── master_agents.py      # 17 位大师分析器
│   ├── trading_orchestrator.py # TradingStrategyOrchestrator
│   ├── trading_plan.py       # 交易计划生成器
│   ├── portfolio_optimizer.py # 组合优化器
│   ├── factor_farm.py        # 因子工厂
│   ├── hard_filter.py        # 硬过滤器
│   ├── market_perception.py  # 市场感知
│   ├── debate_engine.py      # 辩论引擎
│   └── ...                   # 其他 38 个模块
├── workflows/nodes/          # 工作流节点（14 个，非 LangGraph）
│   ├── node_data_collector.py
│   ├── node_generate_recommendations.py
│   ├── node_portfolio_management.py
│   ├── node_risk_control_audit.py
│   └── ...
├── skills/                   # 17 个投资技能（Prompt Skill）
│   ├── turtle-trading-rules/
│   ├── livermore-trading-methods/
│   ├── candlestick-patterns/
│   └── ...
├── agents_v2/                # 旧版 Agent 系统（未完全迁移）
├── api/routes/               # 22 个 API 路由
├── providers/                # 13 个数据源适配器
├── frontend/src/views/       # 15 个前端页面
├── shared/                   # 配置、模型、日志
├── llm_clients/              # LLM 客户端抽象层
└── config/                   # config.yaml + .env
```

---

## 核心工作流

### 每日分析流程

```bash
python main.py daily
```

执行顺序：
1. K 线数据刷新
2. 市场感知（判断牛熊市）
3. 全市场选股（4 阶段漏斗）
4. AI 深度分析（StockAgent → PortfolioAgent → DecisionAgent）
5. 交易计划生成
6. 保存报告到 `reports/daily_YYYYMMDD.json`

### 选股 Pipeline（4 阶段）

| 阶段 | 功能 | 实现文件 |
|------|------|----------|
| Stage 0 | 全市场加载（5000+ 只） | `screening/pipeline.py` |
| Stage 1 | 硬过滤（成交额/ST/上市天数） | `screening/stages/stage1.py` |
| Stage 2 | 大师评分（17 位并行） | `screening/stages/stage2.py` |
| Stage 3 | AI 深度分析 | `screening/stages/stage3.py` |
| Stage 4 | Agent 工作流 | `screening/stages/stage4.py` |

### 支持的选股风格

- 价值（value）
- 成长（growth）
- 动量（momentum）
- 涨停（limit_up）
- 混合（hybrid）

---

## Agent 架构（实际 3 Agent）

| Agent | 职责 | 实现文件 |
|-------|------|----------|
| **StockAgent** | 个股深度分析，调用大师分析器 + Skill | `services/agents/stock_agent.py` |
| **PortfolioAgent** | 组合风险分析，仓位分配 | `services/agents/portfolio_agent.py` |
| **DecisionAgent** | 最终交易计划生成 | `services/agents/decision_agent.py` |

**注意**: 设计文档描述的 5 Agent 架构（Master + Market + Analyst + Portfolio + Reflection）是目标架构，未实现。

---

## 数据源状态

| 数据源 | 状态 | 延迟 | 备注 |
|--------|------|------|------|
| 腾讯 | ✅ 稳定 | 0.2s | 主力源 |
| 东方财富 | ✅ 稳定 | 0.5s | 备用源 |
| 新浪 | ✅ 稳定 | 0.2s | 备用源 |
| Baostock | ✅ 稳定 | 0.5s | 备用源 |
| AKShare | ⚠️ 慢 | ~10s | 仅备用 |
| TickFlow | ❌ 需代理 | - | 不启用 |
| Tushare | ⚠️ 不稳定 | - | 仅备用 |

---

## API 端点（实际 22 个）

| 路由文件 | 端点数 | 功能 |
|----------|--------|------|
| `screening.py` | 5 | 选股 + 交易计划 |
| `portfolio.py` | 4 | 持仓管理 |
| `risk.py` | 5 | 风控预警 |
| `market.py` | 2 | 市场状态 |
| `analysis.py` | 2 | 个股分析 |
| `reports.py` | 2 | 报告管理 |
| `system.py` | 1 | 系统状态 |
| 其他 | 1 | 健康检查 |

**注意**: 设计文档描述的 12 端点是目标架构，实际有 22 个。

---

## 前端页面（实际 15 个）

| 页面 | 功能 | 状态 |
|------|------|------|
| Dashboard | 市场概览 + AI 认知简报 | ✅ 已实现 |
| Screening | 选股 + 交易计划生成 | ✅ 已实现 |
| Portfolio | 持仓管理 | ✅ 已实现 |
| Analysis | 个股分析 | ✅ 已实现 |
| Reports | 报告管理 | ✅ 已实现 |
| Settings | 邮箱配置 | ✅ 已实现 |
| AIMemory | AI 复盘 | ⚠️ 部分实现 |
| Database | 数据库管理 | ✅ 已实现 |
| DecisionCenter | 决策中心 | ✅ 已实现 |
| Favorites | 自选股 | ✅ 已实现 |
| Logs | 日志查看 | ✅ 已实现 |
| Tasks | 任务管理 | ✅ 已实现 |
| TrackingBoard | 跟踪面板 | ✅ 已实现 |
| Workflow | 工作流 | ✅ 已实现 |
| About | 关于页面 | ✅ 已实现 |

---

## 与设计文档的差异

| 设计文档 | 实际状态 | 差异说明 |
|----------|----------|----------|
| M1 基础设施 | 部分实现 | config.py 已实现，models_v2 未实现 |
| M2 Skill 系统 | 未实现 | 无 SkillExecutor，量化逻辑在 services/screening/ |
| M3 Agent 架构 | 部分实现 | 3 Agent 已实现，不是 5 Agent |
| M3.5 State + Interrupt | 未实现 | 无 LangGraph interrupt 机制 |
| M4 LangGraph 图 | 未实现 | 用的是 workflows/nodes/ 的简单编排 |
| M5 API 设计 | 部分实现 | 22 端点 vs 文档 12 端点 |
| M6 前端 | 基本实现 | 15 页面已实现 |
| **M7 认知架构** | **未实现** | **未来方向：叙事引擎、反事实推理、概率化输出、元 AI** |

---

## 未来演进方向（M7 认知架构）

当前系统是"多因子打分器 + LLM 润色"。要逼近专业投资人的判断力，需要在以下 5 个层面重构 AI 的角色：

| 层面 | 当前状态 | 目标状态 |
|------|----------|----------|
| 市场世界观 | 静态快照（牛/熊/震荡） | 持久化叙事 + 跨日演化 |
| 分析深度 | 多空辩论 | 反事实推理 + 概率化输出 |
| 自我进化 | 无反馈闭环 | 决策-结果数据库 + 元 AI |
| 信息获取 | 被动拉取量价数据 | 主动检索新闻 + 另类数据 |
| 风控 | 硬规则（-8% 止损） | 动态 AI 协商 + 情景压力测试 |

详见 `docs/architecture/designs/M7-cognitive-architecture.md`。

---

## 不实现的部分

以下功能在设计文档中描述但**不在个人使用范围内**：

- [ ] LangGraph Agent 编排（保持现有 workflows/nodes/）
- [ ] Master-Specialist 5 Agent 架构（保持现有 3 Agent）
- [ ] Skill 执行引擎（保持现有 services/screening/）
- [ ] 多用户支持
- [ ] 国际化
- [ ] 移动端适配
- [ ] 实盘交易对接

---

**文档日期**: 2026-06-12
**维护者**: 个人使用
