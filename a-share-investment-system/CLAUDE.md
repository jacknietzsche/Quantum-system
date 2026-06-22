# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Status

This project is being **rewritten** from a monolithic FastAPI+Vue3 screening system into an **Agent-driven quant investment system**. The legacy code lives at the project root; the new architecture is documented in `docs/architecture/`. New development follows the Quant Agent design (M1-M6), not the legacy structure.

## Architecture Docs (单点入口)

Start here before any code work:
- `docs/architecture/README.md` — 文档索引, 所有模块交叉引用
- `docs/architecture/ALIGNMENT_AUDIT.md` — 模块间接口对齐问题, 编码前必须先修
- `docs/architecture/01-overview.md` — 架构原则 + 分层 + 技术栈
- `docs/architecture/08-deployment.md` — 新目录结构

## New Architecture (核心模式)

**分层**: 前端(Vue 3 SPA) ↔ API层(FastAPI, 11端点) ↔ Agent编排层(Master+Specialist Agents) ↔ Skill执行层(Data/Quant/Report/Comm/Memory) ↔ 数据层(13数据源适配器利旧 + SQLite + 内存缓存)

**Agent模式**: 层级控制, 非多Agent平权。Master Agent是唯一用户入口, 做规划+调度+汇总; Specialist Agent是单向调用的领域推理器, 不互调, 不接触用户。

**Skill是一等公民**: 所有能力封装为 Skill, 通过 SkillExecutor 统一执行(缓存/重试/超时/追踪横切)。Quant Skill 硬约束禁止直接访问 DB。

**计划驱动**: LangGraph 图是通用执行器, 不包含业务分支; Master Agent 生成的 ExecutionPlan 决定执行路径。

**Human-in-the-loop**: 通过 `type: confirm_plan / confirm_email / wait_for_user` 步骤 + LangGraph interrupt 实现。

**SSE 实时反馈**: 每个节点执行前后推送事件, 前端用 fetch+ReadableStream 消费。

## Key Architecture Principles

1. **AI as orchestrator**: Master Agent plans, calls Skills, summarizes results. Not a participant.
2. **Skill as first-class citizen**: All capabilities as Skills with unified Tool Calling interface.
3. **Human-in-the-loop**: Analysis only after user trigger; confirm at key decision points.
4. **Observability built-in**: Every Agent Run traced; every Skill call logs latency/tokens/result.
5. **Daily-first, simple**: No real-time, no tick-level; fixed flow with clear exceptions.

## Tech Stack

- **Backend**: Python 3.11+ / FastAPI / SQLAlchemy 2.0 / SQLite / LangGraph
- **Frontend**: Vue 3 + TypeScript + Element Plus + ECharts + Pinia + Vite
- **Data Sources**: 13 adapters (Tencent, AKShare, Baostock, EastMoney, Sina, Tushare, etc.) — legacy `providers/` reused
- **LLM**: DeepSeek / SiliconFlow / ChatAnywhere / OpenRouter via `llm_clients/` factory
- **Email**: aiosmtplib (QQ SMTP)

## Development Phases (from roadmap)

| Phase | Focus | Tasks |
|-------|-------|-------|
| P1 | Infrastructure | shared/config, database, models, exceptions, logging |
| P2 | Skill System | SkillSchema/Registry/Executor, Data+Quant+Report+Comm Skills |
| P3 | Agent + Workflow | Master/Market/Analyst/Portfolio/Reflection Agents, LangGraph graph |
| P4 | API + Frontend | 11 REST endpoints, SSE streaming, Vue 3 SPA |
| P5 | Test + Release | Unit/integration/smoke tests, docs, MVP launch |

## State Design (核心数据契约)

State 是扁平字典, 5 组字段:

| 组 | 关键字段 |
|----|----------|
| 会话 | messages[], user_intent, user_confirmation |
| 任务 | run_id, execution_plan[], current_step_index, step_results{}, status |
| 领域 | market_state{}, universe_snapshot[], candidate_pool[], analysis_results{} |
| 控制 | config{}, interrupt_data{} |
| 观测 | trace_log[] |

State `status` 枚举: `planning → executing → waiting_user → completed / failed / cancelled`
`execution_plan` step type 枚举: `skill / agent / confirm_plan / confirm_email / wait_for_user` (禁止通用 `confirm`)

## API Endpoints (11 个)

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/chat` | 通用对话入口, SSE 流式 |
| POST | `/api/tasks/{run_id}/confirm` | 确认中断, 返回新 SSE 流 |
| GET | `/api/reports` | 报告列表 |
| GET | `/api/reports/{date}` | 报告详情(Markdown) |
| POST | `/api/reports/{date}/email` | 发送邮件 |
| GET | `/api/stock/{code}` | 股票快照 |
| GET | `/api/stock/{code}/kline` | K 线 |
| GET | `/api/market/status` | 市场状态 |
| GET | `/api/portfolio` | 持仓 |
| PUT | `/api/portfolio/holding` | 添加/更新持仓 |
| GET | `/api/health` | 健康检查 |

## Database (8 张核心表)

`stock_info`, `kline_cache`, `portfolio`, `daily_nav` (保留) + `agent_runs`, `skill_executions`, `daily_reports`, `reflections` (新增)

## Commands

```bash
# Backend dev
cd backend && uvicorn main:app --reload --port 8765

# Frontend dev
cd frontend && npm run dev      # :5173, proxies /api -> :8765

# Build frontend for production
cd frontend && npm run build     # output -> backend/static/

# Tests
cd backend && pytest tests/ -v
pytest tests/test_skill_executor.py -v   # single file

# Lint
ruff check backend/
ruff format backend/ --check
mypy backend/
```

## Legacy Code Reference

旧代码在根目录 (`api/routes/`, `services/`, `providers/sources/`, `shared/` 等), 仅供:
- 数据源适配器 (`providers/sources/`) — 重构为 Data Skill
- 量化计算 (`services/factor_farm.py`, `services/master_agents.py`) — 重构为 Quant Skill
- LLM 客户端 (`llm_clients/`) — 直接复用
- 配置 (`config/config.yaml`) — 适配新格式

**不要**在新代码中引用旧 `api/routes/`, `services/agents/`, `services/screening/`。
