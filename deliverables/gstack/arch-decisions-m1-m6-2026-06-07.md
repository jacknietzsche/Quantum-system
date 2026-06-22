# M1-M6 编码决策闭环报告（第二回合：12 条决议）

**日期**: 2026-06-07  
**场景**: 编码就绪度审查 → 12 条模糊点全部闭环  
**参与成员**: 软件工坊主理人 沽思航（Gu）  

---

## 📌 TL;DR

- 整体结论：🟢 **编码就绪** — 12 条遗留模糊点全部给出明确实现方案，7 份设计文档已修订，CODING-GUIDE.md 已生成
- 阻塞项数量：0（P0 级 4 条 × 全部拍板）
- 下一步：Phase 3 编码实施 — 从 `models_v2.py` DDL、`AsyncSqliteSaver` 初始化、`skill_executor.py` 线程池集成开始

---

## 🎯 核心结论卡片

| 项目 | 内容 |
|------|------|
| Go / No-Go | 🟢 **Go**（文档 + 决策完全就绪） |
| 严重度分布 | 🔴 4 P0 / 🟠 6 P1 / 🟢 2 P2（**全部闭环**） |
| 关键行动项 | 9 条编码任务 |
| 建议负责人 | software-engineer |

---

## 1. 各文档修订索引（第二回合）

| 文件 | 修订处 | 决议 |
|------|--------|------|
| `M3.5-agent-runtime-state.md` | §2.1 / §2.3 / §3.1 / §4.1 | P0-1 _drop_universe + 内存桥 / P0-2 AsyncSqliteSaver / P0-3 新 run_id / P1-9 async conversation_history |
| `M4-langgraph-graph.md` | §4.4 / §4.7.1 / §6.1 | P1-10 node_count 主图200 / P0-3 modify→cancelled / P0-2 AsyncSqliteSaver |
| `M1-infrastructure-and-config.md` | §1.2 / §1.5 / §1.10 | P0-4 models_v2.py 共享 engine |
| `M2-skill-system.md` | §4.1 (idempotency) / §5 (cache) | P1-5 统一 key 算法 + 覆盖机制 / P2-12 一级 category 粒度 |
| `M3-agent-architecture.md` | §3.4.1 / §3.4.2 | P1-7 SKILL_META 注册 / P1-8 run_in_executor 线程池 / P2-11 allowed_intents |
| `M5-api-design.md` | §3.1.0 / §5 | P0-2 AsyncSqliteSaver / P1-6 SSE 时序图 |
| `M6-frontend-architecture.md` | §3.1 / §4.4 | P0-2 canResume + 1h 窗口（第一轮已修） |
| **`docs/architecture/CODING-GUIDE.md`** | **新建** | 12 条决议 + 12 段代码骨架 + 决策速查表 |

---

## 2. 12 条决议速查

| # | 问题 | 方案 | 关键伪代码行 |
|---|------|------|-------------|
| P0-1 | `universe_snapshot` 排除 | `_drop_universe` reducer + SkillExecutor 内存桥 | `return None` |
| P0-2 | SqliteSaver async 兼容 | `AsyncSqliteSaver` + `sqlite+aiosqlite:///` | `async with AsyncSqliteSaver.from_conn_string(...)` |
| P0-3 | modify 销毁旧 checkpoint | 新 run_id + `parent_run_id` 关联，旧 cancelled | `old_run.status = "cancelled"` |
| P0-4 | 新模型位置 | `models_v2.py` + 共享 `Base` | `from .database import Base` |
| P1-5 | idempotency_key 算法 | `md5(f"{name}:{json}")[:16]` + Skill 覆盖 | `_build_idempotency_key()` |
| P1-6 | SSE 生命周期 | 老 SSE 自然关 → 新 SSE 接班 | `oldEventSource.close()` |
| P1-7 | skill_registry 数据源 | `SKILL_META` 代码注解 → 启动自动入库 | `importlib.import_module` |
| P1-8 | 同步线程池 | `run_in_executor(self._sync_pool)` | `loop.run_in_executor(pool, func)` |
| P1-9 | conversation_history | `asyncio.create_task()` 异步写入 | `asyncio.create_task(write_hist())` |
| P1-10 | node_count 计数 | 主图 200 步硬限，子图独立 50 | `if node_count > 200: fail` |
| P2-11 | allowed_intents 位置 | `SKILL_META`，不入 config.yaml | `"allowed_intents": ["daily_analysis"]` |
| P2-12 | 缓存 category 粒度 | 一级分类（data/quant/report/comm/memory） | `invalidate_category("data")` |

---

## 3. 编码起点建议

按依赖顺序：

1. **`models_v2.py`** — 11 张新表 DDL（先落库才能写其他模块）
2. **`server.py` lifespan** — `AsyncSqliteSaver` + SkillExecutor 线程池初始化
3. **`skill_executor.py`** — idempotency 检查 + 缓存失效 + 内存桥
4. **`skill_engine.py`** — `_discover_skills()` + `SKILL_META` 注册 + `filter_by_intent()`
5. **`agent/state.py`** — `AgentState`（含 `_drop_universe` reducer）
6. **`agent/graph.py`** — LangGraph 图注册（node_count 硬限 200）
7. **`api/routes.py`** — SSE 确认恢复（时序图实现）
8. **前端 `chat.ts`** — `canResume` + 1h 窗口 + SSE 生命周期管理

---

## 📚 产出索引

- **编码参考文档**: `docs/architecture/CODING-GUIDE.md`（477 行，含 12 段代码骨架 + 决策速查表）
- **设计文档修订**: 7 份设计文档均已按 12 条决议更新
- **一份完整报告**: `deliverables/gstack/arch-fix-m1-m6-2026-06-07.md`（224 行，两轮总计 25 项 + 12 条决议映射）

---

> 本报告由软件工坊主理人汇编，12 条决议均依据用户给出的明确方案落地。编码阶段可随时回查 `CODING-GUIDE.md`。
