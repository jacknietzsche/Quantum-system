# 10. 附录

## A. 与原系统的模块映射

| 原模块 | 新模块 | 操作 |
|--------|--------|------|
| `providers/sources/*` | `backend/skills/data/` | 重构为 Skill 接口 |
| `services/screening/` | `backend/skills/quant/` | 封装为 screening Skill |
| `services/factor_farm.py` | `backend/skills/quant/factors.py` | 重构 |
| `services/debate_engine.py` | `backend/skills/quant/debate.py` | 重构 |
| `services/risk_engine.py` | `backend/skills/quant/risk.py` | 重构 |
| `services/master_agents.py` | `backend/skills/quant/masters.py` | 重构 |
| `agents_v2/` | `backend/agents/` | 重写为 Planner+Specialist |
| `graph_v2/` | `backend/workflow/` | 简化重构 |
| `api/routes/` (20 模块) | `backend/api/` (15 端点) | 精简 |
| `shared/models.py` (16 表) | `backend/shared/models.py` (8 表) | 精简 |
| `frontend/` | `frontend/` | 完全重写 |

## B. 关键决策记录

| 决策 | 理由 |
|------|------|
| 单一 Master Agent | 避免多 Agent 协调复杂性, Planner 模式更可控 |
| Skill 作为一等公民 | Agent 不直接操作数据, 便于测试和复用 |
| SQLite 继续使用 | 个人用户场景足够, 避免 PostgreSQL 运维成本 |
| 丢弃 CLI | 聚焦对话式 UI, 降低维护成本 |
| 丢弃 V1 Agent (`services/agents/`) | 架构过时, 与新设计冲突 |
| SSE 而非 WebSocket 主通信 | 单向流式响应足够, 更简单可靠 |

---

**上一节**: [09-roadmap.md](09-roadmap.md)
**返回**: [README.md](README.md)
