# AShare-X Quant Agent — 技术架构文档

**版本**: 1.0 | **状态**: Draft | **日期**: 2026-06-07

---

## 文档目录

| # | 文档 | 内容 |
|---|------|------|
| 1 | [01-overview.md](01-overview.md) | 架构总览 — 原则、分层、技术栈 |
| 2 | [02-agent-architecture.md](02-agent-architecture.md) | Agent 架构详设 — 5 种 Agent 角色定义、通信协议 |
| 3 | [03-skill-system.md](03-skill-system.md) | Skill 系统设计 — 定义规范、27 个 Skill 清单、执行引擎 |
| 4 | [04-workflow-engine.md](04-workflow-engine.md) | 工作流引擎 — 3 条 LangGraph 工作流定义 |
| 5 | [05-database-design.md](05-database-design.md) | 数据库设计 — 8 张核心表 Schema、表关系 |
| 6 | [06-api-design.md](06-api-design.md) | API 设计 — 15 个端点清单、核心端点详设 |
| 7 | [07-frontend-architecture.md](07-frontend-architecture.md) | 前端架构 — 页面结构、核心组件、状态管理 |
| 8 | [08-deployment.md](08-deployment.md) | 部署与运维 — 目录结构、配置管理 |
| 9 | [09-roadmap.md](09-roadmap.md) | 开发路线图 — 5 个 Phase、25 个任务拆分 |
| 10 | [10-appendix.md](10-appendix.md) | 附录 — 模块映射、关键决策记录 |

## 模块详细设计

| 模块 | 文档 | 状态 |
|------|------|------|
| M1 | [基础设施与配置系统](designs/M1-infrastructure-and-config.md) | ⚠️ TARGET ARCHITECTURE |
| M2 | [Skill 执行系统](designs/M2-skill-system.md) | ⚠️ TARGET ARCHITECTURE |
| M3 | [Agent 架构与 Master Agent](designs/M3-agent-architecture.md) | ⚠️ TARGET ARCHITECTURE |
| M3.5 | [Agent 执行运行时 — State 设计 + Interrupt 机制](designs/M3.5-agent-runtime-state.md) | ⚠️ TARGET ARCHITECTURE |
| M4 | [LangGraph 节点图设计](designs/M4-langgraph-graph.md) | ⚠️ TARGET ARCHITECTURE |
| M5 | [API 层设计](designs/M5-api-design.md) | ⚠️ TARGET ARCHITECTURE |
| M6 | [前端架构与交互设计](designs/M6-frontend-architecture.md) | ⚠️ TARGET ARCHITECTURE |
| **M7** | **[AI 认知架构](designs/M7-cognitive-architecture.md)** | **🆕 未来方向** |

## 量化优化

| 文档 | 内容 |
|------|------|
| [P0/P1 因子与选股优化](optimizations/P0-P1-factor-and-selection-optimizations.md) | Winsorize/ICIR/分风格推荐等 7 项优化 |

## 配套文档

- [项目上下文摘要](../project-context/CONTEXT.md) — 新 AI 实例快速理解
- [量化优化方案](optimizations/P0-P1-factor-and-selection-optimizations.md) — P0/P1 因子与选股引擎优化

## 个人使用文档

| 文档 | 内容 |
|------|------|
| [ACTUAL_ARCHITECTURE.md](../ACTUAL_ARCHITECTURE.md) | 当前实际架构（vs 目标架构） |
| [PERSONAL_USE_GUIDE.md](../PERSONAL_USE_GUIDE.md) | 每日操作手册 |
