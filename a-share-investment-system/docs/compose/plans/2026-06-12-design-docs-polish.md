# Design Documents Polish Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use compose:subagent (recommended) or compose:execute to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Update design documents to reflect actual codebase state for personal use, without modifying any code.

**Architecture:** Create new documents for actual architecture and personal use guide, update existing docs to mark implementation status, add "target architecture" labels to aspirational docs.

**Tech Stack:** Markdown documentation only

---

## File Structure

| Action | File | Purpose |
|--------|------|---------|
| Create | `docs/ACTUAL_ARCHITECTURE.md` | Current actual architecture (vs target architecture in M1-M6) |
| Create | `docs/PERSONAL_USE_GUIDE.md` | Operation manual for daily use |
| Modify | `docs/architecture/09-roadmap.md` | Mark completed/pending/skip tasks |
| Modify | `docs/architecture/optimizations/P0-P1-factor-and-selection-optimizations.md` | Mark implementation status |
| Modify | `docs/architecture/designs/M1-infrastructure-and-config.md` | Add "TARGET ARCHITECTURE" label |
| Modify | `docs/architecture/designs/M2-skill-system.md` | Add "TARGET ARCHITECTURE" label |
| Modify | `docs/architecture/designs/M3-agent-architecture.md` | Add "TARGET ARCHITECTURE" label |
| Modify | `docs/architecture/designs/M3.5-agent-runtime-state.md` | Add "TARGET ARCHITECTURE" label |
| Modify | `docs/architecture/designs/M3.5-interrupt-mechanism.md` | Add "TARGET ARCHITECTURE" label |
| Modify | `docs/architecture/designs/M4-langgraph-graph.md` | Add "TARGET ARCHITECTURE" label |
| Modify | `docs/architecture/designs/M5-api-design.md` | Add "TARGET ARCHITECTURE" label |
| Modify | `docs/architecture/designs/M6-frontend-architecture.md` | Add "TARGET ARCHITECTURE" label |
| Modify | `docs/superpowers/specs/01-overview.md` | Mark implementation status |
| Modify | `docs/superpowers/specs/02-api-contracts.md` | Mark as outdated |
| Modify | `docs/superpowers/specs/03-screening-narrative.md` | Mark as implemented |
| Modify | `docs/superpowers/specs/04-dashboard-ai-zone.md` | Mark as implemented |
| Modify | `docs/superpowers/specs/05-memory-page.md` | Mark as unimplemented |

---

## Task 1: Create ACTUAL_ARCHITECTURE.md

**Covers:** Current system state documentation

**Files:**
- Create: `docs/ACTUAL_ARCHITECTURE.md`

- [ ] **Step 1: Create the actual architecture document**

```markdown
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
```

- [ ] **Step 2: Verify file created**

Run: `ls docs/ACTUAL_ARCHITECTURE.md`
Expected: File exists

---

## Task 2: Create PERSONAL_USE_GUIDE.md

**Covers:** Daily operation manual

**Files:**
- Create: `docs/PERSONAL_USE_GUIDE.md`

- [ ] **Step 1: Create the personal use guide**

```markdown
# 个人使用指南

> 本文档是面向自己的操作手册，不是对外发布的用户文档。

**最后更新**: 2026-06-12

---

## 每日操作流程

### 收盘后运行（推荐 17:00 后）

```bash
python main.py daily
```

执行时间：约 60-90 秒

输出：
- 终端：实时进度 + 最终报告摘要
- 文件：`reports/daily_YYYYMMDD.json`

### 查看报告

**方式 1: 前端界面**
```bash
python launch.py
# 打开 http://localhost:8765
# 进入 Screening 页面 → Generate Plan
```

**方式 2: CLI**
```bash
python main.py analyze 600519  # 单股分析
```

**方式 3: 直接查看 JSON**
```bash
# reports/daily_20260612.json
```

### 每日检查清单

- [ ] 运行 `python main.py daily`
- [ ] 检查报告中的推荐股票
- [ ] 对比大盘涨跌
- [ ] 如有持仓，检查止损/止盈信号

---

## 选股流程详解

### Stage 1: 硬过滤

条件（可配置）：
- 成交额 > 5000 万
- 非 ST/*ST
- 上市天数 > 250
- PE > 0 且 PE < 200

输出：约 200-500 只候选股

### Stage 2: 大师评分

17 位大师并行评分：
- Buffett（价值投资）
- Graham（安全边际）
- Lynch（成长投资）
- Taleb（反脆弱）
- Livermore（趋势交易）
- ...

输出：每只股票的综合评分

### Stage 3: AI 深度分析

StockAgent 分析：
- 调用大师分析器
- 注入投资技能知识
- 输出：评分 + 信号 + 理由

### Stage 4: 交易计划

PortfolioAgent + DecisionAgent：
- 仓位分配
- 止损/止盈设置
- 条件触发单

输出：完整交易计划

---

## 风控规则

### 仓位限制

| 波动率 | 单股最大仓位 |
|--------|--------------|
| < 15% | 25% |
| 15-30% | 15% |
| 30-50% | 10% |
| > 50% | 5% |

### 止损规则

- 单股止损：-8%
- 组合止损：总回撤 > 5% 减仓至 50%

### 集中度限制

- 单行业 < 40%
- 单股 < 25%

---

## 数据源优先级

1. **腾讯**（0.2s，最稳定）— 主力源
2. **东方财富**（0.5s）— 备用源
3. **新浪**（0.2s）— 备用源
4. **Baostock**（0.5s）— 备用源
5. **AKShare**（10s）— 仅当以上都失败时

### 数据源健康检查

```bash
python -c "from providers.market_data import MarketDataProvider; print(MarketDataProvider().health_check())"
```

---

## 已知问题

### 测试问题

```
tests/test_integration_phase2.py → cannot import 'BUILTIN_FACTORS'
tests/unit/test_workflow_nodes.py → cannot import 'Column'
```

**影响**: 不影响运行，仅影响测试收集
**修复**: 需更新 import 语句

### 数据源问题

- TickFlow 需要代理，不启用
- AKShare 响应慢（~10s），仅备用
- 部分数据源时好时坏

### 架构问题

- 设计文档描述的 LangGraph 架构未实现
- 实际用的是 workflows/nodes/ 的简单编排
- 3 Agent vs 文档描述的 5 Agent

---

## 配置文件

### config.yaml

位置: `config/config.yaml`

关键配置：
```yaml
llm:
  provider: deepseek
  model: deepseek-chat

screening:
  styles:
    value: { ... }
    momentum: { ... }

data:
  primary_sources: [tencent, eastmoney]
```

### .env

位置: `config/.env`

必需配置：
```
DEEPSEEK_API_KEY=your_key
SILICONFLOW_API_KEY=your_key
QQ_EMAIL=your@qq.com
QQ_SMTP_PASSWORD=your_password
```

---

## 常用命令

```bash
# 每日分析
python main.py daily

# 单股分析
python main.py analyze 600519

# 全市场选股
python main.py screen

# 启动前端
python launch.py

# 开发模式
python launch.py --dev

# 运行测试
pytest tests/ -m "not slow"

# 代码检查
ruff check .
ruff format --check .
```

---

## 参考资源

### 设计文档

- `docs/ACTUAL_ARCHITECTURE.md` — 当前实际架构
- `docs/architecture/README.md` — 目标架构索引
- `OPTIMIZATION_PLAN.md` — 优化计划

### 代码入口

- `main.py` — CLI 入口
- `server.py` — API 服务器
- `launch.py` — 启动脚本
- `services/screening/pipeline.py` — 选股核心
- `services/trading_orchestrator.py` — AI 分析编排

---

**维护者**: 个人使用
**更新频率**: 遇到问题时更新
```

- [ ] **Step 2: Verify file created**

Run: `ls docs/PERSONAL_USE_GUIDE.md`
Expected: File exists

---

## Task 3: Update 09-roadmap.md

**Covers:** Mark completed/pending/skip tasks

**Files:**
- Modify: `docs/architecture/09-roadmap.md`

- [ ] **Step 1: Replace content with updated roadmap**

```markdown
# 9. 开发路线图与任务拆分

> **注意**: 本文档已更新为实际状态。原始 5 Phase 计划大部分已跳过或部分完成。

**最后更新**: 2026-06-12

---

## 已完成

| 任务 | 状态 | 说明 |
|------|------|------|
| 数据源适配 | ✅ 完成 | 5 个稳定源（腾讯/东方财富/新浪/Baostock/AKShare） |
| 选股 Pipeline | ✅ 完成 | 4 阶段漏斗（hard_filter → master_analyze → deep_analyze → agent_workflow） |
| 17 位大师分析器 | ✅ 完成 | services/master_agents.py |
| AI 深度分析 | ✅ 完成 | 3 Agent（StockAgent/PortfolioAgent/DecisionAgent） |
| 风控引擎 | ✅ 完成 | VaR + 预警 + 集中度检查 |
| 交易计划生成 | ✅ 完成 | services/trading_plan.py |
| 前端 15 个页面 | ✅ 完成 | Dashboard/Screening/Portfolio/Analysis/Reports 等 |
| 22 个 API 端点 | ✅ 完成 | api/routes/ 下 22 个路由文件 |
| 17 个投资技能 | ✅ 完成 | skills/ 目录下 Prompt Skill |

---

## 待完善

| 任务 | 优先级 | 说明 |
|------|--------|------|
| 修复测试 import 错误 | P0 | 2 个测试文件 import 断裂 |
| 数据源 fallback 加固 | P1 | 主源超时自动切换备用源 |
| 风控引擎端到端验证 | P1 | 构造测试组合验证 VaR 计算 |
| 回测闭环验证 | P2 | 用历史数据验证选股有效性 |
| 数据缓存优化 | P2 | 同一天数据拉一次后缓存 |

---

## 不做（个人使用不需要）

| 任务 | 原因 |
|------|------|
| LangGraph Agent 编排 | 现有 workflows/nodes/ 够用 |
| Master-Specialist 5 Agent | 现有 3 Agent 够用 |
| Skill 执行引擎 | 现有 services/screening/ 够用 |
| models_v2 新表 | 现有 models.py 够用 |
| 多用户支持 | 个人使用 |
| 国际化 | 个人使用 |
| 移动端适配 | 个人使用 |
| 实盘交易对接 | 先把分析做准 |
| Electron 桌面版 | Web 版够用 |

---

## 原始 Phase 计划（仅供参考）

> 以下原始计划大部分已跳过，保留供参考。

### Phase 1: 基础框架（已跳过）

| 任务 | 状态 | 说明 |
|------|------|------|
| T1.1 搭建重构项目骨架 | ⏭️ 跳过 | 实际没做 backend/shared/ 重构 |
| T1.2 迁移数据源适配层 | ✅ 完成 | providers/ 利旧 |
| T1.3 精简 ORM 模型 | ⏭️ 跳过 | 保持现有 models.py |
| T1.4 Skill 执行引擎 | ⏭️ 跳过 | 无 SkillExecutor |
| T1.5 Skill 注册中心 | ⏭️ 跳过 | 无 SkillRegistry |

### Phase 2: 核心 Skill（部分完成）

| 任务 | 状态 | 说明 |
|------|------|------|
| T2.1 Data Skills | ✅ 完成 | providers/ 直接复用 |
| T2.2 P0-1 因子标准化 | ⏭️ 跳过 | 个人使用不需要 |
| T2.3 P0-2 因子定义标准化 | ⚠️ 部分 | factor_farm.py 有基础实现 |
| T2.4 P0-3 流动性过滤 | ✅ 完成 | hard_filter.py 已实现 |
| T2.5 P1-4 ICIR 加权 | ⏭️ 跳过 | 个人使用等权足够 |
| T2.6 P1-5 分风格推荐 | ✅ 完成 | 4 种风格已支持 |
| T2.7 Report Skills | ✅ 完成 | 报告生成已实现 |
| T2.8 Communication Skills | ✅ 完成 | 邮件发送已实现 |
| T2.9 Memory Skills | ⏭️ 跳过 | 无独立 Memory Skill |

### Phase 3: Agent 与工作流（部分完成）

| 任务 | 状态 | 说明 |
|------|------|------|
| T3.1 Master Agent | ⏭️ 跳过 | 无 Master Agent |
| T3.2 Market Agent | ⚠️ 部分 | market_perception.py 实现 |
| T3.3 Analyst Agent | ✅ 完成 | StockAgent 实现 |
| T3.4 Portfolio Agent | ✅ 完成 | PortfolioAgent 实现 |
| T3.5 Reflection Agent | ⏭️ 跳过 | 无 Reflection Agent |
| T3.6 Daily Workflow | ⚠️ 部分 | workflows/nodes/ 实现 |
| T3.7 Stock Deep Dive | ✅ 完成 | StockAgent 实现 |
| T3.8 Report+Email | ✅ 完成 | 报告+邮件已实现 |

### Phase 4: API + 前端（基本完成）

| 任务 | 状态 | 说明 |
|------|------|------|
| T4.1 FastAPI 路由 | ✅ 完成 | 22 个端点 |
| T4.2 SSE 流式推送 | ✅ 完成 | SSE 已实现 |
| T4.3 Vue 3 项目初始化 | ✅ 完成 | 前端已搭建 |
| T4.4 Chat 面板 | ✅ 完成 | 对话 UI 已实现 |
| T4.5 Dashboard 页面 | ✅ 完成 | Dashboard 已实现 |
| T4.6 Report 页面 | ✅ 完成 | 报告页面已实现 |
| T4.7 K 线图组件 | ✅ 完成 | ECharts 已集成 |
| T4.8 选股漏斗可视化 | ✅ 完成 | Screening 页面已实现 |
| T4.9 Portfolio 页面 | ✅ 完成 | 持仓页面已实现 |
| T4.10 Settings 页面 | ✅ 完成 | 设置页面已实现 |

### Phase 5: 测试与发布（未完成）

| 任务 | 状态 | 说明 |
|------|------|------|
| T5.1 单元测试 | ⚠️ 部分 | 1193 个测试，2 个文件有 import 错误 |
| T5.2 集成测试 | ⏭️ 跳过 | 未实现 |
| T5.3 前端冒烟测试 | ⏭️ 跳过 | 未实现 |
| T5.4 文档编写 | ⚠️ 部分 | 部分文档已写 |
| T5.5 快速回放验证 | ⏭️ 跳过 | 未实现 |
| T5.6 MVP 发布 | ⚠️ 部分 | 可运行但不完善 |

---

## 统计

| 类别 | 数量 |
|------|------|
| 已完成 | 15 |
| 部分完成 | 7 |
| 跳过 | 13 |
| 待完善 | 5 |

---

**返回**: [README.md](README.md)
```

- [ ] **Step 2: Verify file modified**

Run: `head -20 docs/architecture/09-roadmap.md`
Expected: Shows updated content with "已跳过" notes

---

## Task 4: Update P0-P1 Optimizations

**Covers:** Mark implementation status

**Files:**
- Modify: `docs/architecture/optimizations/P0-P1-factor-and-selection-optimizations.md`

- [ ] **Step 1: Add status header to the document**

Add after line 6 (after "目标" section):

```markdown
---

## 实现状态（2026-06-12 更新）

| 优化项 | 状态 | 说明 |
|--------|------|------|
| P0-1 Winsorize + 缺失填充 | ⏭️ 跳过 | 个人使用不需要，当前评分够用 |
| P0-2 因子定义标准化 | ⚠️ 部分实现 | factor_farm.py 有基础实现 |
| P0-3 流动性过滤 | ✅ 已实现 | hard_filter.py 有成交额过滤 |
| P1-4 ICIR 加权 | ⏭️ 跳过 | 个人使用等权足够 |
| P1-5 分风格推荐 | ✅ 已实现 | 4 种风格已支持 |
| P1-6 合规输出 | ⏭️ 跳过 | 个人使用不对外发布 |
| P1-7 用户黑名单 | ✅ 已实现 | hard_filter.py 有黑名单 |

**结论**: 7 项优化中，3 项已实现，4 项跳过（个人使用不需要）。

---
```

- [ ] **Step 2: Verify file modified**

Run: `head -30 docs/architecture/optimizations/P0-P1-factor-and-selection-optimizations.md`
Expected: Shows new "实现状态" section

---

## Task 5: Add TARGET ARCHITECTURE Labels

**Covers:** Label aspirational docs

**Files:**
- Modify: `docs/architecture/designs/M1-infrastructure-and-config.md`
- Modify: `docs/architecture/designs/M2-skill-system.md`
- Modify: `docs/architecture/designs/M3-agent-architecture.md`
- Modify: `docs/architecture/designs/M3.5-agent-runtime-state.md`
- Modify: `docs/architecture/designs/M3.5-interrupt-mechanism.md`
- Modify: `docs/architecture/designs/M4-langgraph-graph.md`
- Modify: `docs/architecture/designs/M5-api-design.md`
- Modify: `docs/architecture/designs/M6-frontend-architecture.md`

- [ ] **Step 1: Add label to M1**

Add after line 7 (after "状态: Draft | 日期: 2026-06-07"):

```markdown

> ⚠️ **TARGET ARCHITECTURE** — 本文档描述目标架构，非当前实现。当前实际架构参见 `docs/ACTUAL_ARCHITECTURE.md`。
```

- [ ] **Step 2: Add label to M2**

Same location as M1.

- [ ] **Step 3: Add label to M3**

Same location as M1.

- [ ] **Step 4: Add label to M3.5 (agent-runtime-state)**

Same location as M1.

- [ ] **Step 5: Add label to M3.5 (interrupt-mechanism)**

Same location as M1.

- [ ] **Step 6: Add label to M4**

Same location as M1.

- [ ] **Step 7: Add label to M5**

Same location as M1.

- [ ] **Step 8: Add label to M6**

Same location as M1.

- [ ] **Step 9: Verify labels added**

Run: `grep -l "TARGET ARCHITECTURE" docs/architecture/designs/*.md`
Expected: 8 files found

---

## Task 6: Update Superpowers Specs

**Covers:** Mark implementation status

**Files:**
- Modify: `docs/superpowers/specs/01-overview.md`
- Modify: `docs/superpowers/specs/02-api-contracts.md`
- Modify: `docs/superpowers/specs/03-screening-narrative.md`
- Modify: `docs/superpowers/specs/04-dashboard-ai-zone.md`
- Modify: `docs/superpowers/specs/05-memory-page.md`

- [ ] **Step 1: Add status to 01-overview.md**

Add after line 7 (after "技术栈"):

```markdown

> **实现状态**: ⚠️ 部分实现 — 设计规范已采用，部分页面已实现。
```

- [ ] **Step 2: Add status to 02-api-contracts.md**

Add after title/date:

```markdown

> **实现状态**: ❌ 已过时 — 实际 API 与文档描述不同，参见 `docs/ACTUAL_ARCHITECTURE.md`。
```

- [ ] **Step 3: Add status to 03-screening-narrative.md**

Add after title/date:

```markdown

> **实现状态**: ✅ 已实现 — 前端 Screening 页面已包含叙事流功能。
```

- [ ] **Step 4: Add status to 04-dashboard-ai-zone.md**

Add after title/date:

```markdown

> **实现状态**: ✅ 已实现 — Dashboard 页面已包含 AI 认知简报和 Agent 健康度。
```

- [ ] **Step 5: Add status to 05-memory-page.md**

Add after title/date:

```markdown

> **实现状态**: ⚠️ 部分实现 — AIMemory 页面存在但功能不完整。
```

- [ ] **Step 6: Verify labels added**

Run: `grep -l "实现状态" docs/superpowers/specs/*.md`
Expected: 5 files found

---

## Task 7: Update README.md

**Covers:** Add reference to new documents

**Files:**
- Modify: `docs/architecture/README.md`

- [ ] **Step 1: Add references to new documents**

Add after line 43 (after "配套文档" section):

```markdown

## 个人使用文档

| 文档 | 内容 |
|------|------|
| [ACTUAL_ARCHITECTURE.md](../ACTUAL_ARCHITECTURE.md) | 当前实际架构（vs 目标架构） |
| [PERSONAL_USE_GUIDE.md](../PERSONAL_USE_GUIDE.md) | 每日操作手册 |
```

- [ ] **Step 2: Verify file modified**

Run: `tail -10 docs/architecture/README.md`
Expected: Shows new "个人使用文档" section

---

## Verification

After all tasks complete:

- [ ] **Step 1: Verify all new files exist**

Run: `ls docs/ACTUAL_ARCHITECTURE.md docs/PERSONAL_USE_GUIDE.md`
Expected: Both files exist

- [ ] **Step 2: Verify all modifications**

Run: `grep -r "TARGET ARCHITECTURE" docs/architecture/designs/ | wc -l`
Expected: 8

Run: `grep -r "实现状态" docs/superpowers/specs/ | wc -l`
Expected: 5

- [ ] **Step 3: Verify no code changes**

Run: `git diff --name-only`
Expected: Only .md files modified

---

## Summary

| Task | Files Created | Files Modified |
|------|---------------|----------------|
| 1 | 1 | 0 |
| 2 | 1 | 0 |
| 3 | 0 | 1 |
| 4 | 0 | 1 |
| 5 | 0 | 8 |
| 6 | 0 | 5 |
| 7 | 0 | 1 |
| **Total** | **2** | **16** |
