# AShare-X 三文档联合审阅：编码落地前盲区审计

**日期**：2025-07-09
**场景**：编码落地前审查 — M2/M4/CODING-GUIDE 三文档联合审阅 + 3am on-call 盲区推演
**参与成员**：gstack-product-reviewer（产品评审员）、gstack-investigator（调查员）

---

## 📌 TL;DR（执行摘要）

- 整体结论：🔴 **不通过 — 不可直接进入编码阶段**
- 阻塞项数量：**14 项**（9 项来自产品评审 + 7 项来自调查员，去重合并后 14 项）
- 最危险的 5 个卡点：SkillResult 字段矛盾（B-1）、SkillExecutor 静态/实例矛盾（B-2）、AgentState 不完整（B-3）、idempotency_key 僵尸记录（I-A2）、conversation_history fire-and-forget 数据不一致（I-D1）
- 其中 3 项是两份审阅从不同维度独立命中的同一根因，问题叠加后严重度升级
- 建议：先锁 CODING-GUIDE P0 修复 → 再开始编码，否则第一天就会卡住

---

## 🎯 核心结论卡片

| 项目 | 内容 |
|------|------|
| Go / No-Go | 🔴 No-Go（14 项阻塞，必须先修文档再写代码） |
| 严重度分布 | 🔴 14 / 🟠 14 / 🟡 9（去重合并后） |
| 关键行动项 | 14 条 P0 + 14 条 P1 + 9 条 P2 |
| 建议负责人 | 架构负责人（文档修订）/ Tech Lead（最终决策） |
| 最大风险来源 | 两份文档间的字段/调用方式矛盾 + 异常路径静默失败 |

---

## 1. 各成员核心结论

### 🔍 产品评审员（gstack-product-reviewer）

以"明天要动手写代码的工程师"视角审阅三份文档，聚焦可测试性、开发者体验、接口契约完整性、配置与依赖四个维度。共发现 22 个问题（9🔴 / 10🟠 / 3🟡，报告标注 6🟡 含 D-5/D-6 实际为 3 项🟡）。

**核心判断**：三份文档在架构层面设计质量高，但从落地视角看有三个致命卡点——SkillResult 字段在 CODING-GUIDE 和 M2 间矛盾（`idempotency_override` 不存在于 M2 定义）、SkillExecutor 在 M4 和 M2/CODING-GUIDE 间调用方式矛盾（静态 vs 实例）、AgentState 定义严重不完整（缺少 10+ 个字段）。这三个问题不解决，第一天编码就会遇到 pydantic ValidationError 和运行时崩溃。

### 🔧 调查员（gstack-investigator）

以"半夜 3 点被叫起来排查问题的 on-call 工程师"视角推演了所有异常路径、资源泄漏、可观测性盲区和数据一致性问题。共发现 15 个问题（7🔴 / 5🟠 / 3🟡）。

**核心判断**：系统在正常路径下设计合理，但异常路径存在多处静默失败。最危险的三项——idempotency_key 进程崩溃后产生永久僵尸记录（静默返回空结果）、定时清理任务可能误删正在执行的 agent_run（级联删除导致数据丢失）、skill_registry 单点故障导致整个服务无法启动（无容错加载）。

### 🔴 双审交叉命中（独立验证，问题严重度升级）

以下 3 个问题被两位成员从不同维度独立发现，说明这些不是"可能的问题"而是"必然的生产事故"：

| 交叉问题 | 产品评审员视角 | 调查员视角 | 合并严重度 |
|---------|-------------|----------|----------|
| `_last_universe_snapshot` 跨 run 污染 | B-6：内存桥注入路径不明确 | A4+B2：进程级单例无 run_id 隔离，并发覆盖 | 🔴🔴 |
| `conversation_history` fire-and-forget | A-4：测试中断言 flaky | A1：异常静默吞没 + D1：race condition 导致 LLM 读到不完整历史 | 🔴🔴 |
| idempotency_key INSERT 模式 | A-2：并发竞态无测试方案 | A2：进程崩溃→僵尸记录→静默返回空结果 | 🔴🔴 |

---

## 2. 综合审查发现（去重合并后按严重度排序）

### 🔴 阻塞编码（14 项）

| # | 严重度 | 类别 | 位置 | 问题描述 | 建议 | 来源 |
|---|--------|------|------|---------|------|------|
| 1 | 🔴 | DX/Contract | CODING-GUIDE §5 vs M2 §4 | **SkillResult 字段矛盾**：CODING-GUIDE 返回 `idempotency_override` 但 M2 的 SkillResult 无此字段→直接抛 pydantic ValidationError | 在 SkillResult 中新增字段，或统一用 `idempotency_key` | PR |
| 2 | 🔴 | DX/Contract | M4 §4.5.1 vs M2 §4 | **SkillExecutor 静态/实例矛盾**：M4 用静态调用 `SkillExecutor.execute(...)`，M2 和 CODING-GUIDE 是实例方法且依赖 `self._sync_pool`→运行时崩溃 | M4 改为实例调用；CODING-GUIDE 决策表新增"必须是实例方法"约束 | PR |
| 3 | 🔴 | DX/Contract | CODING-GUIDE §1 | **AgentState 缺少 10+ 字段定义**：`run_id`、`status`、`messages`、`step_results`、`trace_log`、`execution_plan`、`user_confirmation` 等字段全部未在 TypedDict 中声明 | 给出完整 AgentState TypedDict，含所有字段类型和 reducer | PR |
| 4 | 🔴 | Data/Recovery | CODING-GUIDE §5 | **idempotency_key 僵尸记录**：进程在 INSERT→commit→执行 Skill 之间崩溃，DB 留下 `status='running'` 的僵死记录，下次命中 IntegrityError 时返回 `output_summary=NULL`→静默返回空结果 | 增加 `started_at` 超时检测；IntegrityError 分支检查 `existing.status`；定时清理 orphaned 记录 | INV |
| 5 | 🔴 | Data/Recovery | CODING-GUIDE §9 + M3.5 §3.1 | **conversation_history fire-and-forget 三连击**：(a) 异常静默吞没无告警 (b) session 可能已关闭 (c) summarize 节点读 DB 时异步写入未完成→LLM 缺少关键上下文 | 改用后台任务队列+retry；summarize 节点读 `state["messages"]` 而非 DB；关键路径改 await | INV + PR |
| 6 | 🔴 | Data/Recovery | CODING-GUIDE §1 + M4 全篇 | **`_last_universe_snapshot` 跨 run 污染**：SkillExecutor 是进程单例，实例变量无 run_id 隔离，并发请求互相覆盖→下游 Skill 拿到错误数据 | 改为 `dict[str, dict]` 按 run_id 隔离；或放弃内存桥统一走 DB | INV + PR |
| 7 | 🔴 | Config/Ops | CODING-GUIDE §7 | **skill_registry 单点故障→服务无法启动**：`_discover_skills()` 无 try/except，单个 Skill 语法错误/缺字段 → 整个 lifespan 失败 → 服务不可用 | 每个 skill 加载包裹 try/except，失败 skip+log error，继续加载其余 | INV |
| 8 | 🔴 | Contract | M4/M5 | **`progress_steps` 结构完全未定义**：`GET /api/tasks/{run_id}/status` 响应结构不存在于任何文档中，前端无法渲染进度条 | 在 M4 或 M5 中定义完整 OpenAPI schema | PR |
| 9 | 🔴 | Contract | M4 §2 + §4.7.1 + §8 | **step.type 枚举不一致**：`interrupt_node` 检查 `("confirm_plan", "confirm_email", "wait_for_user")`，但 §2 节点表写 `type: "confirm"`，§8 示例用 `"confirm_plan"`/`"confirm_email"` | 新增 Step Type 枚举规范表，列出所有合法值，删除旧 `"confirm"` 引用 | PR |
| 10 | 🔴 | Config/DX | CODING-GUIDE §2 + M4 §6.1 | **缺依赖文件 + 无启动检查**：`aiosqlite` 和 `langgraph>=0.1` 无 requirements.txt；漏装 aiosqlite 时 SQLAlchemy 抛 `NoSuchModuleError` 不可读 | 附录给出完整 requirements.txt；lifespan 中 try/except 包裹并给出可操作错误消息 | PR |
| 11 | 🔴 | Config/DX | CODING-GUIDE §11 | **config.yaml × SKILL_META 优先级未定义**：两层配置的合并策略、总开关 vs 细粒度路由的优先级完全缺失 | 新增决策：config.yaml 是总开关（最高优先级），SKILL_META 是细粒度路由 | PR |
| 12 | 🔴 | Testing | M4 §4.7 + CODING-GUIDE §6 | **LangGraph interrupt/resume 无测试策略**：`interrupt()` 在 pytest 中会真正挂起线程，无 mock 方案 | CODING-GUIDE 新增测试策略附录，给出 monkeypatch 或官方 test harness 示例 | PR |
| 13 | 🔴 | Exception | CODING-GUIDE §2 + M5 §4 | **graph.astream 节点异常→SSE 流无 error 事件**：异常直接传播到 StreamingResponse→连接断开，前端只知"断了"不知原因 | astream 循环外包 try/except，异常时先 yield error 事件再 yield task_complete(failed) | INV |
| 14 | 🔴 | Data/Recovery | M1 §1.10.1 | **定时清理误删正在执行的 agent_run**：WHERE 条件只有 `created_at`，无 `status` 过滤，7 天后 `waiting_user` 或长时间运行的 run 被级联删除 | WHERE 加 `AND status NOT IN ('running', 'waiting_user', 'cancelling')` | INV |

### 🟠 需要补充说明（14 项）

| # | 严重度 | 类别 | 位置 | 问题描述 | 建议 | 来源 |
|---|--------|------|------|---------|------|------|
| 15 | 🟠 | Testing | M4 §5 | SSE 流式事件断言无工具/fixture，工程师不知道如何验证节点发出了正确的 SSE 事件 | CODING-GUIDE 给出 `async for event in sse_generator()` 测试 fixture 示例 | PR |
| 16 | 🟠 | DX | 全篇 | 无模块依赖图，至少 15 个文件路径但循环依赖风险高（skill_executor ↔ graph 等） | CODING-GUIDE 附录新增 Mermaid 依赖图，标注禁止的反向依赖 | PR |
| 17 | 🟠 | DX | CODING-GUIDE §7 | SKILL_META 缺失时静默跳过无警告，开发者忘记写 META→Skill 永不注册→零提示 | `_discover_skills()` 中对无 META 的模块 emit `logging.WARNING` | PR |
| 18 | 🟠 | Contract | M4 §5 + M5 | SSE 事件无 TypeScript 类型定义，前端需手写联合类型，字段命名风格不明确 | CODING-GUIDE 或 M5 提供 `sse-events.ts` 完整类型定义 | PR |
| 19 | 🟠 | Contract | M4 §4.5.1 + §4.1 | `trace_log` 条目结构未定义，各节点写入字段不一致，前端渲染时间线无依据 | AgentState 完整定义中声明 `trace_log: list[TraceEntry]` 和 TraceEntry TypedDict | PR |
| 20 | 🟠 | Contract | CODING-GUIDE §6 | `graph.astream` yield 事件形状未文档化，updates→SSE 转换中间件伪代码缺失 | 明确 astream 原始输出格式 + SSE 转换中间件伪代码 | PR |
| 21 | 🟠 | Config | CODING-GUIDE §2 + M4 §6.1 | checkpoint DB 路径硬编码 `data/langgraph_checkpoints.db`，Docker 部署不可配 | 改为 `Path(os.getenv("ASAREX_CHECKPOINT_DB", "data/langgraph_checkpoints.db"))` | PR |
| 22 | 🟠 | Config | M2 §4.2 vs CODING-GUIDE §8 | 线程池大小配置不一致：M2 从环境变量读取，CODING-GUIDE 硬编码 8 | CODING-GUIDE 改为 `int(os.getenv("SKILL_THREAD_POOL_SIZE", "8"))` | PR |
| 23 | 🟠 | Resource | CODING-GUIDE §8 | ThreadPoolExecutor(max_workers=8) + 无界队列，8 线程全阻塞在 120s API 超时时请求无限排队→雪崩 | 搭配 `asyncio.wait_for` + `asyncio.Semaphore` 限制并发，超限返回 503 | INV |
| 24 | 🟠 | Observability | CODING-GUIDE §10 | node_count>200 硬限→SSE 看不到 status_reason，日志无当前计数，运维排查无依据 | status_change 事件增加 status_reason；logger.warning 含 node_count | INV |
| 25 | 🟠 | Observability | M1 §1.9.2 | /api/health 的 checkpoint 检查是静态类型标签，不验证连接存活/WAL 堆积/上次写入时间 | 改为实际探测 `SELECT 1`；增加 `db_size_mb` 和 `last_write_age_s` | INV |
| 26 | 🟠 | Data/Recovery | CODING-GUIDE §3 | parent_run_id 链：清理旧记录导致链路断裂，用户看到不完整的修改历史 | 清理时跳过被其他记录的 parent_run_id 引用的行 | INV |
| 27 | 🟠 | Exception | CODING-GUIDE §9 + M4 §4.7.1 | fire-and-forget 写入时 db_session 可能是 FastAPI request-scoped（已 close），写入必然失败 | `_write()` 内部新建独立 session，不依赖外层 Depends | INV（与 #5 关联） |
| 28 | 🟠 | Contract | M4 §4.5.1 + §4.6.1 | step_results value 结构不统一：有的用 `result.to_dict()`，有的用自定义 dict，前端需按 type switch | 定义 StepResult 基类和子类型（SkillStepResult/AgentStepResult） | PR |

### 🟡 优化建议（9 项）

| # | 严重度 | 类别 | 位置 | 问题描述 | 建议 | 来源 |
|---|--------|------|------|---------|------|------|
| 29 | 🟡 | Testing | CODING-GUIDE §8 + M2 §4.2 | 同步 Skill 在 pytest-asyncio 中 mock 指导缺失，线程池跨线程 mock 不可见 | conftest.py 替换为 max_workers=1 的池，说明跨线程 mock 注意事项 | PR |
| 30 | 🟡 | Testing | M2 §5 | LRU 缓存用 `threading.Lock` 在 async 环境下可能死锁（协程持锁+await 切换） | 改为 `asyncio.Lock` 或明确 L1 缓存只在同步路径访问 | PR |
| 31 | 🟡 | DX | 全篇 | 代码骨架缺少大量 import（hashlib/importlib/json/uuid4/datetime/Annotated 等） | 每个代码骨架顶部补充 `# 需要的 import` 注释清单 | PR |
| 32 | 🟡 | DX | CODING-GUIDE §5 | 幂等检查伪代码是伪 SQL 字符串，不能直接在 SQLAlchemy 中运行 | 改为可运行的 SQLAlchemy 2.0 Core 语法 | PR |
| 33 | 🟡 | Contract | M4 | step_results value 结构不统一（已在 #28 说明，此处为关联项） | 同 #28 | PR |
| 34 | 🟡 | Config | CODING-GUIDE §2 + §10 + M4 §4.4 | recursion_limit 50 vs 200 矛盾：graph config 传 50，execution_loop 数到 200，两个限制互相打架 | 统一为 recursion_limit=200（LangGraph 兜底）+ node_count=200（业务控制） | PR |
| 35 | 🟡 | Config | M4 §6.1 | MemorySaver 降级无警告，新手设 `ASAREX_DEV_INMEMORY=1` 后忘记→重启数据全丢 | MemorySaver 分支加 `logging.warning("DEV MODE: 重启后所有 checkpoint 将丢失")` | INV |
| 36 | 🟡 | Resource | M4 §6.1 + M3.5 §2.1 | AsyncSqliteSaver lifespan pre-yield 异常时可能泄漏文件描述符（影响较小，进程退出回收） | lifespan 先 `mkdir -p` 确保目录存在；对 from_conn_string 外层 try/except | INV |
| 37 | 🟡 | Resource | M1 §1.10.1 + M3.5 §2.2 | SQLite DELETE 后无 VACUUM→磁盘空间不回收，checkpoint DB 持续增长 | 定期执行 PRAGMA optimize 或 VACUUM；建库时开启 auto_vacuum=INCREMENTAL | INV |

---

## ✅ 行动清单

### P0 — 编码前必须解决（不改文档无法写代码）

| # | 行动 | 负责方 | 期望完成 | 对应问题 |
|---|------|--------|---------|---------|
| 1 | 在 M2 SkillResult 中新增 `idempotency_override: str \| None = None` 字段，或统一用 `idempotency_key` | 架构负责人 | 本周 | #1 |
| 2 | M4 §4.5.1 改为实例调用方式，CODING-GUIDE 决策表新增约束条目 | 架构负责人 | 本周 | #2 |
| 3 | 在 CODING-GUIDE §1 给出完整 AgentState TypedDict（含所有字段类型+reducer+注释） | 架构负责人 | 本周 | #3 |
| 4 | CODING-GUIDE §5 幂等逻辑增加 `started_at` 超时检测 + IntegrityError 分支 status 检查 | Tech Lead | 本周 | #4 |
| 5 | conversation_history 写入改为后台任务队列+retry；summarize 节点改读 `state["messages"]` | Tech Lead | 本周 | #5, #27 |
| 6 | `_last_universe_snapshot` 改为 `dict[str, dict]` 按 run_id 隔离，或彻底放弃内存桥走 DB | Tech Lead | 本周 | #6 |
| 7 | `_discover_skills()` 每个 skill 加载包裹 try/except，失败 skip+log error | Tech Lead | 本周 | #7 |
| 8 | 在 M4 或 M5 中定义 `GET /api/tasks/{run_id}/status` 完整 OpenAPI schema（含 progress_steps） | 架构负责人 | 本周 | #8 |
| 9 | M4 新增 Step Type 枚举规范表，统一所有 `confirm`/`confirm_plan`/`wait_for_user` 引用 | 架构负责人 | 本周 | #9 |
| 10 | CODING-GUIDE 附录给出完整 requirements.txt；lifespan 中加 try/except + 可操作错误消息 | Tech Lead | 本周 | #10 |
| 11 | CODING-GUIDE 新增 config.yaml × SKILL_META 优先级决策（总开关 > 细粒度路由） | 架构负责人 | 本周 | #11 |
| 12 | CODING-GUIDE 新增测试策略附录，含 interrupt/resume mock 示例 + 幂等竞态 asyncio.gather 示例 | Tech Lead | 本周 | #12, #15 |
| 13 | astream 循环外包 try/except，异常时 yield SSE error 事件 + task_complete(failed) | Tech Lead | 本周 | #13 |
| 14 | M1 §1.10.1 清理 SQL 加 `AND status NOT IN ('running', 'waiting_user', 'cancelling')` | Tech Lead | 本周 | #14 |

### P1 — 编码启动后第一周需补充

| # | 行动 | 负责方 | 期望完成 |
|---|------|--------|---------|
| 15 | CODING-GUIDE 附录新增 Mermaid 模块依赖图 | 架构负责人 | Week 1 |
| 16 | `_discover_skills()` 中无 SKILL_META 的模块加 WARNING 日志 | Tech Lead | Week 1 |
| 17 | CODING-GUIDE 或 M5 提供 `sse-events.ts` 完整 TypeScript 类型 | 架构负责人 | Week 1 |
| 18 | AgentState 中声明 `trace_log: list[TraceEntry]` 和 TraceEntry TypedDict | Tech Lead | Week 1 |
| 19 | CODING-GUIDE §6 补充 astream 原始输出格式 + SSE 转换中间件伪代码 | Tech Lead | Week 1 |
| 20 | checkpoint DB 路径 + 线程池大小 + recursion_limit 三处配置统一 | Tech Lead | Week 1 |
| 21 | ThreadPoolExecutor 增加 `asyncio.wait_for` 超时 + `asyncio.Semaphore` 限流 | Tech Lead | Week 1 |
| 22 | status_change SSE 事件增加 status_reason 字段 | Tech Lead | Week 1 |
| 23 | /api/health 的 checkpoint 检查改为实际探测 SELECT 1 | Tech Lead | Week 1 |
| 24 | parent_run_id 清理逻辑增加引用检查 | Tech Lead | Week 1 |
| 25 | step_results 定义 StepResult 基类和子类型 | 架构负责人 | Week 1 |
| 26 | 代码骨架补充完整 import 清单 | Tech Lead | Week 1 |

### P2 — 后续迭代优化

| # | 行动 | 负责方 |
|---|------|--------|
| 27 | 同步 Skill mock 指导 + conftest.py 示例 | Tech Lead |
| 28 | LRU 缓存锁改为 asyncio.Lock 或明确访问路径 | Tech Lead |
| 29 | 幂等检查伪代码改为可运行 SQLAlchemy 2.0 Core 语法 | Tech Lead |
| 30 | MemorySaver 分支加 logging.warning | Tech Lead |
| 31 | lifespan pre-yield 异常路径加 try/except + 目录预创建 | Tech Lead |
| 32 | SQLite 定期 VACUUM 或 auto_vacuum=INCREMENTAL | Tech Lead |
| 33 | ThreadPoolExecutor metrics 暴露（队列深度/活跃线程数） | Tech Lead |

---

## ⚠️ 待完善 / 已知局限

- **两份审阅均为文档级静态分析**，未对实际代码仓库进行验证（假设文档准确反映代码意图）
- **SSE 中间件实现**在文档中完全缺失，审阅基于"文档承诺的行为"而非实际代码行为
- **前端契约（TypeScript 类型、API schema）**在三份文档中均未涉及，审阅只能指出缺失而非审查内容
- **M5（部署/运维文档）**本次未纳入审阅范围，部署相关配置和监控项可能有额外盲区
- **LangGraph 版本行为**（如 `interrupt()` 在 pytest 中的实际行为、`astream` yield 的事件形状）依赖于 LangGraph 具体版本，建议编码前锁定版本号并验证 test harness

---

## 📚 成员产出索引

- **gstack-product-reviewer**（产品评审员）原始产出：M2/M4/CODING-GUIDE 三文档联合审阅，22 个发现，按 A/B/C/D 四维度 + 🔴🟠🟡 三级严重度分类
- **gstack-investigator**（调查员）原始产出：AShare-X 架构盲区分析，15 个发现，按异常路径/资源生命周期/可观测性/数据一致性四维度

---

> 本报告由软件工坊 AI 协作生成，关键决策请由工程负责人复核。三份审阅从不同视角独立推演，交叉命中的问题（3 项）需要特别重视——它们代表"独立验证"而非"重复报告"。
