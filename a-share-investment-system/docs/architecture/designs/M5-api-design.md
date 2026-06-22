# Module 5: API 层设计

**前置**: M3.5 (State 设计) + M4 (LangGraph 图设计)  
**用途**: 定义前端与后端的所有通信契约  
**原则**: REST 做操作，SSE 做推送，WebSocket 仅用于日志调试  
**状态**: Draft | **日期**: 2026-06-07

> ⚠️ **TARGET ARCHITECTURE** — 本文档描述目标架构，非当前实现。当前实际架构参见 `docs/ACTUAL_ARCHITECTURE.md`。

---

## 1. API 设计原则

1. **任务即对话**：每次分析请求都映射为一个任务 `run_id`，完整生命周期通过 SSE 流式返回
2. **单一入口**：核心操作统一经过 `/api/chat`，自然语言或快捷操作都转化为消息发送到此端点
3. **Human-in-the-loop 专用端点**：`/api/tasks/{run_id}/confirm` 恢复暂停的任务
4. **辅助数据拉取**：历史报告、单股详情、K 线、市场状态等通过独立 GET 端点提供
5. **无认证**：所有端点开放，绑定本地单用户实例
6. **错误一致**：非流式响应遵循 `{ok: bool, data: any, error: string}` 信封格式

---

## 2. 核心端点清单（12 个端点）

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/chat` | 通用对话入口，SSE 流式响应。**2026-06-07 补强 C-10**：在创建任务时生成 `run_id=uuid4().hex`，注入初始 State，**init 节点不重新生成** |
| POST | `/api/tasks/{run_id}/confirm` | 确认/取消中断，恢复任务执行 |
| **GET** | **`/api/tasks/{run_id}/status`** | **2026-06-07 补强 F-13（新增 MVP 端点）**：查询任务当前状态。返回 `{ok, data: {status, progress_steps, last_event_time, plan_summary?, interrupt_data?}}`，前端刷新页面后用此端点恢复 UI |
| GET | `/api/reports` | 获取历史报告列表 |
| GET | `/api/reports/{date}` | 获取某天报告详情（Markdown） |
| POST | `/api/reports/{date}/email` | 发送某天报告到邮箱（**历史补发**，不走 confirm 流程，详见 §3.5） |
| GET | `/api/stock/{code}` | 获取单只股票快照及最新分析摘要 |
| GET | `/api/stock/{code}/kline` | 获取日 K 线数据 |
| GET | `/api/market/status` | 获取最近一次市场状态（缓存） |
| GET | `/api/portfolio` | 获取当前持仓及汇总 |
| PUT | `/api/portfolio/holding` | 添加/更新持仓 |
| GET | `/api/health` | 健康检查 |

**舍弃**：原系统的 20+ 个端点精简至此。选股结果不再通过单独 API 获取，而是作为 SSE 流的一部分实时推送。

**并发限制**: 个人使用场景，同时最多 1 个执行中的 run。第 2 个请求拒绝（409），前端 toast 提示"已有任务正在执行"。

---

## 3. 端点详细规范

### 3.1 POST /api/chat

| 项目 | 内容 |
|------|------|
| 描述 | 通用对话入口，所有分析任务均通过此端点触发 |
| 请求头 | `Content-Type: application/json`, `Accept: text/event-stream` |
| 请求体 | `{message: str, session_id?: str}` |
| 响应 | `text/event-stream`，事件流见第 4 节 |
| 行为 | **2026-06-07 补强 C-10**：API 层在收到 `/api/chat` POST 请求时**立即生成 `run_id = uuid4().hex`**，构造 `initial_state = {"run_id": run_id, ...}`，调用 `graph.astream(initial_state, config={"configurable": {"thread_id": run_id}, ...})` 启动图执行。**init 节点不重新生成 run_id**，仅当 `state.get("run_id")` 为空时才 fallback 创建（恢复场景） |
| 错误 | 图启动失败时先推送 `error` 事件，然后关闭流 |

#### §3.1.0 服务启动时初始化 AsyncSqliteSaver（2026-06-07 修订：与 M3.5 §2.1 / M4 §6.1 一致）

```python
# backend/server.py
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from pathlib import Path

CHECKPOINT_DB = Path("data/langgraph_checkpoints.db")

# async with 上下文绑定 FastAPI lifespan
async with AsyncSqliteSaver.from_conn_string(
    f"sqlite+aiosqlite:///{CHECKPOINT_DB}",
    serde=JsonPlusSerializer(),
) as checkpointer:
    app.state.graph = compiled_graph.with_checkpointer(checkpointer)
```

#### §3.1.1 session_id 语义说明

**产品决策**：MVP 阶段 `session_id` **仅作前端 cookie 标识**，服务端**不持久化、不参与 LangGraph state**。

- **作用**：前端 localStorage 缓存的对话气泡 ID，方便路由跳转后恢复 UI 显示
- **不参与**：LangGraph thread_id、State 字段、agent_runs 表主键
- **后端处理**：`session_id` 入参**只读不写**，仅记录到日志用于排查
- **服务端真实标识**：`run_id`（每次请求生成 UUID，绑定 LangGraph checkpoint）

**理由**：MVP 阶段多 session 切换、跨设备同步等场景需求不明朗，过早设计 session 持久化会增加 schema 复杂度。等 Phase 4 评估"多 session 历史"是否真有必要再补。

→ 由 software-product-manager 于 2026-06-07 补强，依据 review 第 2 轮 P0-2。

### 3.2 POST /api/tasks/{run_id}/confirm

| 项目 | 内容 |
|------|------|
| 描述 | 恢复因 interrupt_node 暂停的任务 |
| 路径参数 | `run_id: str` |
| 请求体 | `{action: "confirm"\|"cancel"\|"modify", params?: object}`（**action 支持第三种值 `"modify"`**，见 M3.5 §4.1）。`params` 字段在不同 confirm 类型下含义不同：`confirm_plan` 时含 `style/max_candidates`；`confirm_email` 时含 `to` 覆盖默认收件人。 |
| 响应 | **新 SSE 流**（见第 5 节关于恢复方案的说明） |
| 错误 | run_id 不存在或状态不对时返回 400 |

#### §3.2.1 中断相关端点（Phase 4 扩展预留 + 2026-06-07 补强 F-13 MVP 升级）

**MVP 阶段端点**：

| 方法 | 路径 | 用途 | MVP 状态 |
|------|------|------|----------|
| POST | `/api/tasks/{run_id}/confirm` | 恢复/取消中断任务 | ✅ MVP |
| **GET** | **`/api/tasks/{run_id}/status`** | **查询任务状态，前端刷新页面后恢复 UI 用（2026-06-07 补强 F-13 升 MVP）** | ✅ **MVP** |

**GET /api/tasks/{run_id}/status 详细规范**：

| 项目 | 内容 |
|------|------|
| 路径参数 | `run_id: str` |
| 响应（成功） | `{ok: true, data: {run_id, status, progress_steps: [{step_id, description, status, success?}], last_event_time, plan_summary?, interrupt_data?}}` |
| 响应（不存在） | 404 `{ok: false, error: "任务未找到"}` |
| 数据来源 | `agent_runs` 表（status, plan_json）+ `skill_executions` 表（progress_steps）+ `conversation_history` 表（interrupt_data 含 confirm 上下文） |
| 性能要求 | 1 次 DB 查询合并（< 100ms） |

**Phase 4 评估项**：

| 方法 | 路径 | 用途 | 状态 |
|------|------|------|------|
| GET | `/api/tasks/{run_id}/interrupts` | 查询任务当前中断状态（用于重连场景） | ❌ Phase 4 |
| POST | `/api/tasks/{run_id}/resume` | 别名，等价于 `/confirm`，与 LangGraph 术语对齐 | ❌ Phase 4 |
| POST | `/api/tasks/{run_id}/cancel` | 主动取消（含 `cancelling` 中间态，见 M3.5 §1.2） | ❌ Phase 4 |

→ 由 software-product-manager 于 2026-06-07 补强，依据 review 第 2 轮 P1 + F-13 解决方案。

→ 由 software-product-manager 于 2026-06-07 补强，依据 review 第 2 轮 P1。

### 3.3 GET /api/reports

| 项目 | 内容 |
|------|------|
| 查询参数 | `limit?=20`, `offset?=0` |
| 响应 | `{ok: true, data: {total, reports: [{date, market_regime, top_picks, email_sent}]}}` |

### 3.4 GET /api/reports/{date}

| 项目 | 内容 |
|------|------|
| 路径参数 | `date: str` (YYYY-MM-DD) |
| 响应 | `{ok: true, data: {date, markdown, email_sent}}` |

### 3.5 POST /api/reports/{date}/email

| 项目 | 内容 |
|------|------|
| 请求体 | `{to?: str}` 可选，默认使用系统配置 |
| 响应 | `{ok: true, message: "邮件已发送"}` |
| 实现 | **2026-06-07 补强 C-8 两条路径冲突**：本端点**仅用于历史报告补发**，内部仍调用 `comm.send_email` Skill 并写入 `skill_executions` 表（**不受 confirm 步骤限制**）；**日频流程中的邮件发送必须经过 confirm_email 步骤**，由计划引擎保障。两条路径共享**同一 idempotency 机制**——`idempotency_key` 基于 `report_date + email_to` 生成（如 `md5(f"report_email:{date}:{to}")`），重放请求直接返回历史结果不重复发送。 |

### 3.6 GET /api/stock/{code}

| 项目 | 内容 |
|------|------|
| 响应 | `{ok: true, data: {stock_code, stock_name, latest_price, pe_ratio, ..., latest_analysis?: {score, signal, reasoning}}}` |

### 3.7 GET /api/stock/{code}/kline

| 项目 | 内容 |
|------|------|
| 查询参数 | `days?=120` 或 `from?`, `to?` |
| 响应 | `{ok: true, data: {code, klines: [{date, open, close, high, low, volume}]}}` |

### 3.8 GET /api/market/status

| 项目 | 内容 |
|------|------|
| 响应 | `{ok: true, data: {regime, style_bias, risk_level, summary, updated_at}}` |

### 3.9 GET /api/portfolio

| 项目 | 内容 |
|------|------|
| 响应 | `{ok: true, data: {positions: [...], total_asset, cash, total_return_pct}}` |

### 3.10 PUT /api/portfolio/holding

| 项目 | 内容 |
|------|------|
| 请求体 | `{action: "buy"\|"sell", stock_code, price, quantity, date}` |
| 响应 | 更新后的持仓列表 |

### 3.11 GET /api/tasks/{run_id}/status

| 项目 | 内容 |
|------|------|
| 描述 | 查询任务最新状态，用于前端刷新后重连恢复或显示历史终态 |
| 路径参数 | `run_id: str` |
| 响应 | `{ok: true, data: {status, last_event_time, step_index, total_steps}}` |
| `status` 枚举 | `"planning" \| "executing" \| "waiting_user" \| "completed" \| "failed" \| "cancelled"` |
| `last_event_time` | ISO 时间戳，前端据此判断是否在 1h 可恢复窗口内 |
| 错误 | run_id 不存在返回 404 |

### 3.12 GET /api/health

| 项目 | 内容 |
|------|------|
| 响应 | `{status: "ok", version: "1.0.0"}` |

#### §3.11.1 端口配置

**默认端口**：`8765`（与 `launch.py` 的 `find_free_port(start=8765)` 一致）。

**环境变量覆盖**：`ASAREX_PORT`
```bash
# 启动时指定
ASAREX_PORT=9000 python -m backend.server

# launch.py 内部
import os
PORT = int(os.getenv("ASAREX_PORT", "8765"))
find_free_port(start=PORT)
```

**前端代理配置**：详见 M6 §7.1（Vite 读 `VITE_API_PORT` 环境变量）。

**与 Nginx/Caddy 反代（未来扩展）**：
- MVP 直连 FastAPI，无需反代
- 若引入反代，SSE 流必须设置 `X-Accel-Buffering: no` 禁用 buffer
- WebSocket（若未来引入）需配置 `Upgrade` / `Connection` 头透传

→ 由 software-product-manager 于 2026-06-07 补强，依据 review 第 2 轮 P1-1。

---

## 4. SSE 事件流规范

所有 `/api/chat` 交互返回 SSE 流。

| 事件名 | 时机 | data 字段 | M6 Pinia 字段（1:1 映射） |
|--------|------|-----------|---------------------------|
| `run_start` | 任务启动 | `{run_id, intent}` | `chatStore.currentRunId`, `chatStore.taskStatus = "running"` |
| `status_change` | 状态变更 | `{status, step_index?}` | `chatStore.taskStatus` |
| `step_start` | 步骤开始 | `{step_id, description, index, total}` | `chatStore.progressSteps` 追加 |
| `step_result` | 步骤完成 | `{step_id, success, summary, data?, failed_codes?}` | 更新对应 `progressSteps` 条目；`failed_codes` 渲染为告警 |
| `agent_message` | Master Agent 输出文本（流式增量） | `{content}` | `chatStore.streamingContent` 追加（打字机） |
| `waiting_confirmation` | 需要用户确认 | `{type, message, options, context?, plan_summary?}` | `chatStore.confirmationData` 写入；UI 展示确认卡片 |
| `error` | 错误 | `{message, step_id?}` | 错误提示 toast |
| `task_complete` | 任务完成 | `{status, summary?}` | `chatStore.taskStatus = "completed"`；关闭 EventSource |

**前端处理**（M6 §4.2）：
- `agent_message` 累积到对话气泡，打字机效果
- `waiting_confirmation` 时展示确认卡片，用户操作后调用确认 API
- `task_complete` 后关闭 EventSource
- `step_result.failed_codes` 必须渲染为可见告警（不是默默失败）

**前后端契约保证**：M5 本节事件名与 M6 §3.1 Pinia store 字段**一一对应**，任一方变更需同步另一方（修改时在文档 PR 标题注明 "M5↔M6 SSE contract"）。

→ 由 software-product-manager 于 2026-06-07 补强，依据 review 第 2 轮 P1。

---

## 5. 确认恢复的 SSE 方案（2026-06-07 决议 P1-6：完整生命周期时序）

**挑战**: LangGraph 在 interrupt 时暂停 `astream`，无法在当前 SSE 连接上继续推送。

**MVP 方案**: 确认接口返回**新 SSE 流**。

### 时序图

```
用户                    前端                     后端                     LangGraph
 |                       |                        |                          |
 |--发送消息------------>|                        |                          |
 |                       |--POST /api/chat------->|                          |
 |                       |                        |--graph.astream()-------->|
 |                       |                        |                          |--执行节点1,2,3...
 |                       |                        |<--yield events-----------|
 |                       |<--SSE events-----------|                          |
 |                       |                        |                          |--到达 interrupt_node
 |                       |                        |                          |--yield Interrupt信号
 |                       |                        |<--GraphInterrupt---------|
 |                       |<--waiting_confirmation |                          |
 |                       |    (old SSE closes)    |                          |
 |                       |                        |                          |
 |--点击"确认"---------->|                        |                          |
 |                       |--POST /confirm-------->|                          |
 |                       |   (Accept: text/event-stream)                     |
 |                       |                        |--graph.ainvoke(resume)-->|
 |                       |                        |                          |--从 checkpoint 恢复
 |                       |                        |                          |--继续执行后续节点
 |                       |                        |<--yield events-----------|
 |                       |<--new SSE events-------|                          |
 |                       |                        |                          |--执行完成
 |                       |                        |<--task_complete----------|
 |                       |<--task_complete--------|                          |
 |                       |   (new SSE closes)     |                          |
```

### 关键规则

1. **老 SSE 流自然关闭**：LangGraph 抛出 `GraphInterrupt` 时，后端 `StreamingResponse` 的 generator 遇到 `break` 或 `return` 结束，前端收到 `waiting_confirmation` 后 EventSource 自动关闭（`onerror` 触发）。
2. **确认请求返回新 SSE**：`POST /confirm` 返回一个新的 `StreamingResponse`，前端用新的 `fetch` + `ReadableStream` 接收。
3. **前端竞态防护**：创建新 EventSource 之前先显式关闭旧的（`oldEventSource.close()`），保证同一 `run_id` 只有一个活跃连接。
4. **cancel/timeout 路径**：用户点击取消 → `action: "cancel"` → `graph.ainvoke(Command(resume={"action": "cancel"}))` → 图结束 → SSE 推送 `task_complete(status="cancelled")` 后关闭。
  3. 用户确认 → POST /api/tasks/{run_id}/confirm (Accept: text/event-stream)
  4. 创建新 EventSource 指向确认返回的流
  5. 关闭旧的 EventSource
```

---

## 6. 错误处理

| 场景 | HTTP 状态码 | 响应体 |
|------|-------------|--------|
| 参数错误 | 400 | `{ok: false, error: "...", detail?: {...}}` |
| 数据未就绪 | 400 | `{ok: false, error: "数据尚未更新"}` |
| 任务不存在 | 404 | `{ok: false, error: "任务未找到"}` |
| 内部错误 | 500 | `{ok: false, error: "..."}` |

SSE 流内错误通过 `error` 事件传达，不会中断流（除非致命错误终止任务）。

---

## 7. 与原系统的对比

| 维度 | 原系统 (20+ 路由模块, 120+ 端点) | 新系统 (11 端点) |
|------|----------------------------------|------------------|
| 选股触发 | GET /api/screening/run, /run/stream, /by-category, /status, /results, /abort... | POST /api/chat (自然语言) |
| 选股结果 | 独立 API 查询 | SSE 流实时推送 |
| 报告管理 | list, detail, download, send-email, delete | list, detail, email |
| 持仓管理 | holdings, summary, add, sell, reset, nav, trades, holdings-map... | portfolio (GET), holding (PUT) |
| 数据库管理 | 29 个端点 | 无（依赖自动流程） |
| 日志 | recent, server-log, errors, clear | 无（独立日志文件） |

## §7 部署与端口

**`launch.py` 启动流程**：
```python
# launch.py (现状已实现)
def find_free_port(start: int) -> int:
    """从 start 开始找第一个 free port（仅占一个端口）"""
    ...

PORT = find_free_port(start=8765)  # 单端口
subprocess.run(["uvicorn", "backend.server:app", "--port", str(PORT)])
```

**与本 API 设计的协调**：
- `launch.py` 只起**单端口**（不是 11 个端点各占一端口），浏览器访问 `http://localhost:8765/api/...` 即可
- 前端构建产物（M6 §7）放入 `backend/static/`，FastAPI `app.mount("/", StaticFiles(directory="backend/static"))` 服务
- 默认端口 8765，可通过 `ASAREX_PORT` 环境变量覆盖（详见 §3.11.1）

**MVP 部署形态**：单端口 + 单进程 + 本地直连，无需 Nginx/反代。

→ 由 software-product-manager 于 2026-06-07 补强，依据 review 第 2 轮 P1-1。

---

## 8. 下一步

API 层设计已足够细化，可进入 **模块6：前端架构与交互设计**。

---

### 附录 A：错误处理体系（整合自 ERROR-CODES.md）

**错误码格式**: `ASX-{LAYER}-{NUMBER}`

| LAYER | 覆盖范围 | 示例 |
|-------|---------|------|
| `CONFIG` | 启动期配置错误 | `ASX-CONFIG-001` 必填配置缺失 |
| `DATA` | 数据源错误 | `ASX-DATA-001` 上游5xx |
| `SKILL` | Skill 执行错误 | `ASX-SKILL-001` Skill 不存在 |
| `AGENT` | Agent 运行时错误 | `ASX-AGENT-001` Agent 内部异常 |
| `LLM` | LLM 服务错误 | `ASX-LLM-001` LLM 不可用 |

**错误响应格式（非流式）**：
```json
{"ok": false, "error": {"code": "ASX-SKILL-001", "message": "Skill 不存在", "http_status": 404, "detail": {}}}
```

**SSE 流式错误事件**：
```json
{"event": "error", "data": {"code": "ASX-SKILL-002", "message": "执行超时", "fatal": true, "step_id": "step_5"}}
```

**完整错误码表见 `backend/shared/exceptions.py` + `backend/api/error_codes.py`。**

### 附录 B：端到端 Happy Path 走查（整合自 RUNBOOK.md）

**日频分析完整流程（13 步）**：

| 步 | 节点 | SSE 事件 | 关键数据 |
|----|------|---------|---------|
| 1 | POST /api/chat | `run_start` | `run_id`, intent |
| 2 | init → plan_generator | `status_change(executing)` | 8 步 ExecutionPlan |
| 3 | data.check_freshness (Skill) | `step_result` | 数据是否最新 |
| 4 | market_agent (Agent) | `step_result` | marketState 更新 |
| 5 | **confirm_plan** | `waiting_confirmation` | 等待用户确认 |
| 6 | 用户确认 → POST /confirm | 新 SSE 流 | 后续步骤继续 |
| 7 | quant.screening_pipeline (Skill) | `step_result` | Top 10 候选 |
| 8 | analyst_agent × 10 (Agent) | `step_result` | 10 份分析报告 |
| 9 | report.generate_markdown (Skill) | `step_result` | 报告生成 |
| 10 | **confirm_email** | `waiting_confirmation` | 等待确认发送 |
| 11 | comm.send_email (Skill) | `step_result` | 邮件已发送 |
| 12 | summarize (Agent) | `agent_message` | 最终回复 |
| 13 | — | `task_complete` | 任务完成 |

**异常路径**：
- **用户取消**: waiting_user → `task_complete(status=cancelled)`
- **数据源超时**: 跳过该 step，用缓存继续
- **SSE 断开**: MVP **不做 SSE 断线重连**。断网后后端继续执行（checkpoint 保存），用户刷新页面后 `GET /api/tasks/{run_id}/status` 查询状态。若 <1h 且 waiting_user → 显示 ConfirmationCard 恢复
