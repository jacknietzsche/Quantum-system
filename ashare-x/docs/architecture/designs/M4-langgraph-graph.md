# Module 4: LangGraph 节点图设计 — 通用任务执行图

**所属阶段**: Phase 3  
**前置**: M3 (Agent 架构) + M3.5 (State + Interrupt)  
**用途**: 定义通用计划执行图的结构和节点规范  
**状态**: Draft | **日期**: 2026-06-07

> ⚠️ **TARGET ARCHITECTURE** — 本文档描述目标架构，非当前实现。当前实际架构参见 `docs/ACTUAL_ARCHITECTURE.md`。

---

## 1. 设计目标

- **一个图，多种任务**：日频分析、个股深挖、复盘、闲聊均通过同一个图执行，差异由 `execution_plan` 决定
- **计划驱动**：图仅作为可靠的"计划执行器"，不包含业务分支逻辑
- **Human-in-the-loop 原生集成**：通过 `type: "confirm_plan" / "confirm_email" / "wait_for_user"` 步骤无缝暂停/恢复
- **可观测**：每个节点执行前后推送 SSE 事件

---

## 2. 节点总览

| 节点名 | 类型 | 功能 | 备注 |
|--------|------|------|------|
| `init` | 系统 | 初始化 State, 注入用户消息、config、run_id | — |
| `intent_parser` | Master Agent | 解析意图，填充 `user_intent`，处理简单闲聊 | 无需计划时直接生成回复并结束 |
| `plan_generator` | Master Agent | 生成 `execution_plan` | 若需确认计划，在计划最前面插入 confirm 节点 |
| `execution_loop` | 系统（循环控制） | 检查待执行步骤，更新 `current_step_index`，路由到对应节点 | 循环体 |
| `skill_executor` | Skill | 执行 `type: "skill"` 的步骤 | 调用 SkillExecutor |
| `agent_executor` | Agent | 执行 `type: "agent"` 的步骤 | 支持并发（Analyst Agent 批量，**用 LangGraph Send API 实现 fan-out/fan-in**，避免 20 只串行） |
| `interrupt_node` | 控制 | 执行 `type: "confirm_plan" / "confirm_email" / "wait_for_user"` 的步骤，暂停等待用户确认 | 使用 LangGraph interrupt |
| `summarize` | Master Agent | 汇总所有结果，生成最终回复 | 流式输出 |
| `error_handler` | 系统 | 处理不可恢复错误 | 记录日志，更新 status = failed |

### 2.1 Step Type 枚举规范

| 枚举值 | 含义 | 对应节点 | 备注 |
|--------|------|----------|------|
| `skill` | 调用 Skill | `skill_executor` | 幂等键生成 |
| `agent` | 调用子 Agent | `agent_executor` | 支持 batch fan-out |
| `confirm_plan` | 确认计划 | `interrupt_node` | 含 plan_summary |
| `confirm_email` | 确认发邮件 | `interrupt_node` | 含 preview_html |
| `wait_for_user` | 通用等待用户输入 | `interrupt_node` | 保留扩展 |

> **禁止使用 `type: "confirm"`**（已废弃，统一拆分）。Plan Generator 只能生成以上 5 种枚举值。

---

## 3. 图结构

```
Start → init → intent_parser
                │
                ├── need_plan=false → summarize
                │
                └── need_plan=true → plan_generator → execution_loop
                                                        │
                                              ┌─────────┼──────────┐
                                              │         │          │
                                         skill  →  agent  →  confirm
                                              │         │          │
                                              └─────────┼──── user_cancelled
                                                        │          │
                                                        └─ 无更多步骤 ┘
                                                        │
                                                    summarize → End
```

所有不可恢复异常流向 `error_handler` → End。

**关键设计点**:
- `execution_loop` 是唯一的业务推动者，从 `execution_plan` 中依次取步骤并路由
- `interrupt_node` 通过 LangGraph 暂停/恢复实现等待，恢复后回到 `execution_loop`
- 快速闲聊路径：`intent_parser` 发现 `general_chat` 时直接跳到 `summarize`，不生成计划

---

## 4. 节点详细规范

### 4.1 init

| 项目 | 内容 |
|------|------|
| 触发 | 任务创建（POST /api/chat/send 或 POST /api/daily/start）。**2026-06-07 补强 C-10**：`run_id` 由 API 层在 `POST /api/chat` 端点创建时生成 UUID，注入到初始 State，init 节点**不重新生成**（恢复时复用，初始时新建）。 |
| 状态写入 | `run_id`（API 层生成）、`status="planning"`, `messages=[user_msg]`, `config`, `trace_log=[]` |

```python
# M4 init 节点（与 API 层协作）
def init_node(state: State) -> dict:
    # run_id 来自 API 层注入；恢复时由 state 复用
    run_id = state.get("run_id") or uuid4().hex
    return {
        "run_id": run_id,
        "status": "planning",
        "messages": state.get("messages", []),
        "node_count": 0,
    }
```

> **注意**：`run_id` 写入 state 是节点内部显式赋值；LangGraph 内**不依赖 contextvar** 传递 run_id（contextvar 在 graph 节点函数之间不保证可见，必须以 state 为唯一信源）。

### 4.2 intent_parser

| 项目 | 内容 |
|------|------|
| LLM 调用 | 是，轻量请求 |
| 状态读取 | `messages[-1]`, `config.date`, 可用技能列表 |
| 状态写入 | `user_intent`（枚举）; 若 `general_chat` 则直接填充回复并设 `need_plan=False` |
| 错误 | LLM 失败重试一次，仍失败 → error_handler |

### 4.3 plan_generator

| 项目 | 内容 |
|------|------|
| LLM 调用 | 是，结构化输出 |
| 状态读取 | `user_intent`, `messages`, 可用技能列表, `config` |
| 状态写入 | `execution_plan` (list[Step]), `status="executing"` |
| 确认计划 | 若 `config.require_confirmation=true`，在计划首位插入 confirm 步骤 |
| 错误 | 结构化输出解析失败重试，仍失败 → error_handler |

### 4.4 execution_loop

| 项目 | 内容 |
|------|------|
| 纯逻辑 | 无 LLM 调用 |
| 行为 | `current_step_index += 1`; 若无更多步骤 → summarize; 否则按 step.type 路由；**递增 `state["node_count"]`，硬限 200（2026-06-07 补强 C-4 + P1-10），超过则写 `status="failed", status_reason="node_count_exceeded"` 终止**。`node_count` **只计主图 execution_loop 节点**，每次通过 execution_loop 递增 1；子图（如 analyst_agent 批量并发）内部节点不计入主图计数。子图由独立 `recursion_limit`（默认 50，仅子图编译时配置）控制。 |
| 状态写入 | `current_step_index`, `node_count` |
| SSE | 推送 `step_start` (step_id, description) |
| `status_change` 推送约束（C-6） | **仅推送外部可见状态转换**：`executing → waiting_user`、`waiting_user → executing`、任意状态 → `completed / failed / cancelled`。同一节点内部的中间态（如 `executing → executing` 推进步骤）不推送 `status_change`，避免高频事件；前端无需去重逻辑 |

### 4.5 skill_executor

| 项目 | 内容 |
|------|------|
| 功能 | 调用 SkillExecutor |
| 参数处理 | 解析 params 中的 `$step_id.field` 变量引用 |
| 状态写入 | `step_results[step_id]` 写入成功; 失败追加到 `errors` 并跳过 |
| SSE | 推送 `step_result` (success, summary) |
| 超时/重试 | SkillExecutor 内部处理，本节点只捕获不可恢复异常 |

#### §4.5.1 run_id / correlation_id 注入示例

**核心契约**：M2 `SkillExecutor.execute` 签名升级为 `(name, params, *, run_id, correlation_id)`，keyword-only 必传。M4 节点必须**从 state 显式注入**，禁止依赖 contextvar（在 LangGraph 内不适用）。

```python
# backend/agent/nodes/skill_executor.py
from services.skill_executor import SkillExecutor

def skill_executor_node(state: dict) -> dict:
    step = state["execution_plan"][state["current_step_index"]]
    
    # 1. 解析 $step_id.field 占位符
    params = _resolve_vars(step["params"], state["step_results"])
    
    # 2. 显式注入 run_id + correlation_id（争议 4 落地）
    correlation_id = f"{state['run_id']}:{step['step_id']}"
    
    # 3. 调用 SkillExecutor（实例方法，从 app.state 获取）
    executor = app.state.skill_executor
    result = await executor.execute(
        skill_name=step["target"],
        params=params,
        run_id=state["run_id"],
        correlation_id=correlation_id,
    )
    
    # 4. 写回 state
    return {
        "step_results": {
            step["step_id"]: result.to_dict(),
        },
        "trace_log": [
            {
                "step_id": step["step_id"],
                "skill": step["target"],
                "latency_ms": result.latency_ms,
                "tokens_used": result.tokens_used,
                "success": result.success,
            }
        ],
    }
```

**M2 §4 签名变更**（同步落地）：
```python
# services/skill_executor.py（实例方法，非静态）
class SkillExecutor:
    def execute(
        self,
        skill_name: str,
        params: dict,
        *,
        run_id: str,                  # keyword-only 必传
        correlation_id: str = None,   # 可选，不传则用 run_id
    ) -> SkillResult:
        ...
```

**日志关联**：所有 Skill 执行日志、错误日志、trace 都要带 `run_id` + `correlation_id`，便于跨 skill/agent 追踪问题。

→ 由 software-product-manager 于 2026-06-07 补强，依据 review 第 2 轮 P0-4。

#### §4.5.2 StepResult 结构约定

不同 step type 写入 `step_results` 的结构：

| step type | step_results value 结构 | 来源 |
|-----------|------------------------|------|
| `skill` | `SkillResult.to_dict()` → `{success, data, error, latency_ms, ...}` | `skill_executor_node` |
| `agent` | `{analysis_results: dict, failed_codes: list[str]}` | `agent_executor_node` / `collect_batch_results` |
| `confirm_plan` | `{action: str, params?: dict}` | `interrupt_node` (user_confirmation) |
| `confirm_email` | `{action: str}` | `interrupt_node` |

前端可通过 `step_results[step_id]` 按需解析，不需要按 step type 做 switch。

### 4.6 agent_executor

| 项目 | 内容 |
|------|------|
| 功能 | 调用子 Agent (Market/Analyst/Portfolio/Reflection) |
| 并发 | params 含 `batch: list` 时并发执行多个实例，结果合并；**MVP 用 LangGraph Send API（fan-out/fan-in）实现，单步耗时 < 30s 处理 20 只** |
| 状态写入 | `step_results[step_id]` |
| 错误 | 单股分析失败不影响整体，该股标记错误并继续；**SSE `step_result` 携带 `failed_codes: list[str]` 失败明细**，便于前端展示 |

#### §4.6.1 Send API 实现（Analyst Agent 批量）

**核心问题**：候选池 20 只股票，若串行执行 `analyst_agent` × 20 = 100s+，超 MVP 90s 硬指标。

**Send API 实现**（LangGraph 0.0.40+ 官方 fan-out/fan-in 模式）：

```python
# backend/agent/nodes/agent_executor.py
from langgraph.constants import Send

def agent_executor_node(state: dict) -> list[Send]:
    """fan-out 节点：根据 step.params.batch 返回 N 个 Send"""
    step = state["execution_plan"][state["current_step_index"]]
    batch = step["params"].get("batch", [])
    
    if not batch:
        # 单实例（非批量）
        return [Send("analyst_subgraph", {"stock_code": step["params"]["stock_code"], "state": state})]
    
    # 批量：每个 stock_code 一个 Send
    return [
        Send("analyst_subgraph", {
            "stock_code": code,
            "state": state,
            "step_id": step["step_id"],
        })
        for code in batch
    ]

# analyst_subgraph 内部
def analyst_subgraph(state: dict) -> dict:
    """单只股票分析，失败不影响其他"""
    stock_code = state["stock_code"]
    try:
        result = AnalystAgent().run(stock_code, state["state"])
        return {"batch_results": {stock_code: result}}
    except Exception as e:
        # 记录失败，不抛出（fan-in 节点会聚合）
        return {
            "batch_results": {
                stock_code: {"error": str(e), "success": False}
            }
        }

# 聚合（fan-in）节点
def collect_batch_results(state: dict) -> dict:
    """fan-in：汇总所有 Send 返回的结果"""
    step = state["execution_plan"][state["current_step_index"]]
    results = state.get("batch_results", {})
    
    success = {k: v for k, v in results.items() if v.get("success", True)}
    failed_codes = [k for k, v in results.items() if not v.get("success", True)]
    
    # SSE 推送 step_result 携带 failed_codes
    _emit_sse(state["run_id"], "step_result", {
        "step_id": step["step_id"],
        "success": True,  # 整体成功（只要有 1 只成功）
        "summary": f"分析 {len(success)} 只成功，{len(failed_codes)} 只失败",
        "failed_codes": failed_codes,  # 关键：前端可见
    })
    
    return {
        "step_results": {step["step_id"]: {"analysis_results": success, "failed_codes": failed_codes}},
        "status": "executing",
    }
```

**耗时估算**（20 只 × 单只 5s，并发 10 路）：
- 串行：20 × 5s = 100s ❌
- 并发（10 路）：20 / 10 × 5s = 10s ✅
- 加上数据拉取 + 报告生成：日频全流程约 60-80s（满足 < 90s 硬指标）

→ 由 software-product-manager 于 2026-06-07 补强，依据 review 第 2 轮 P1。

### 4.7 interrupt_node

| 项目 | 内容 |
|------|------|
| 行为 | `status="waiting_user"` → 构造 `interrupt_data` → **追加 system 消息到 `messages`** → SSE 推送 → 调用 `interrupt()` 暂停 |
| 恢复 | 用户 API → `interrupt()` 返回 `user_confirmation` |
| confirm | 恢复 `status="executing"`，继续 execution_loop |
| cancel/timeout | 设 `status="cancelling"` → 清理 → `status="cancelled"`，`status_reason` 写"user_cancel" 或 "timeout_30m" |

#### §4.7.1 interrupt_node 实现细节

**函数签名**（LangGraph 节点函数标准形式）：
```python
# backend/agent/nodes/interrupt_node.py
from langgraph.types import interrupt, Command
from typing import Literal
from datetime import datetime

def interrupt_node(state: dict) -> Command[Literal["execution_loop", "summarize"]]:
    """
    Interrupt 节点：暂停等待用户确认（confirm_plan / confirm_email / wait_for_user，2026-06-07 补强 P0-1）。
    恢复点（不是重入点）—— interrupt() 之前的代码不会重跑。
    """
    # 幂等检查（M3.5 §8.1）
    if state.get("interrupt_consumed"):
        return Command(goto="execution_loop")

    step = state["execution_plan"][state["current_step_index"]]

    # 1. 构造 interrupt_data（2026-06-07 补强 P0-1 / F-6）
    interrupt_data = {
        "type": step["type"],            # confirm_plan / confirm_email / wait_for_user
        "message": step.get("description", "请确认是否继续"),
        "plan_summary": _format_plan_summary(state["execution_plan"]),
        "options": ["confirm", "cancel", "modify"],
        "params": step.get("params", {}),
    }

    # 1.1 追加 system 消息（2026-06-07 补强 P0-4 / F-5）
    system_msg_pause = {
        "role": "system",
        "content": f"系统提示：已向用户请求确认（类型：{step['type']}）。等待用户操作…",
        "timestamp": datetime.now().isoformat(),
    }

    # 2. 推送 SSE（M5 §4 事件）
    _emit_sse(state["run_id"], "waiting_confirmation", interrupt_data)

    # 3. 调用 LangGraph interrupt() 暂停
    user_confirmation = interrupt(interrupt_data)

    # 3.1 追加用户操作的 system 消息（2026-06-07 补强 C-5）
    action = user_confirmation.get("action", "cancel")
    user_action_msg = {
        "role": "system",
        "content": f"用户已执行：{action}",
        "timestamp": datetime.now().isoformat(),
    }

    # 4. 恢复后处理（不会重入第 1-3 步）
    if action == "confirm":
        return Command(
            goto="execution_loop",
            update={
                "user_confirmation": user_confirmation,
                "status": "executing",
                "interrupt_consumed": True,
                "messages": state.get("messages", []) + [system_msg_pause, user_action_msg],
            },
        )
    elif action == "modify":
        # MVP: 新 run_id + parent_run_id 关联（2026-06-07 修订 P0-3）
        # 不销毁旧 checkpoint，后端 API 层生成新 run_id，旧记录标记 cancelled
        return Command(
            goto="summarize",  # summarize 节点写入 cancelled 终态
            update={
                "user_confirmation": user_confirmation,
                "status": "cancelled",
                "status_reason": "用户修改参数后重新发起",
                "interrupt_consumed": True,
                "modify_params": user_confirmation.get("params", {}),
                "messages": state.get("messages", []) + [system_msg_pause, user_action_msg],
            },
        )
    else:  # cancel 或 timeout
        return Command(
            goto="summarize",
            update={
                "status": "cancelled",
                "status_reason": "user_cancel" if action == "cancel" else "timeout_30m",
                "interrupt_consumed": True,
                "messages": state.get("messages", []) + [system_msg_pause, user_action_msg],
            },
        )
```

**Import 路径**：
- `from langgraph.types import interrupt, Command`（LangGraph 0.0.40+ 稳定 API）
- 节点函数返回值类型 `Command[Literal[...]]`：LangGraph 用此确定下一节点

**与图注册**：
```python
# backend/agent/graph.py
from langgraph.graph import StateGraph
from backend.agent.nodes.interrupt_node import interrupt_node

workflow = StateGraph(AgentState)
workflow.add_node("interrupt_node", interrupt_node)
# 2026-06-07 补强 P0-1：路由条件按 5 个枚举值匹配
workflow.add_edge(
    "execution_loop", "interrupt_node",
    condition=lambda s: s["execution_plan"][s["current_step_index"]]["type"] in (
        "confirm_plan", "confirm_email", "wait_for_user"
    )
)
```

→ 由 software-product-manager 于 2026-06-07 补强，依据 review 第 2 轮 P0。

> **⚠️ interrupt() 恢复机制说明（实现注意事项）**：
> LangGraph 的 `interrupt()` 在首次执行时抛出 `GraphInterrupt` 异常暂停图；恢复时（通过 `Command(resume=...)`）**不会重入** `interrupt()` 调用点之前的代码——`interrupt()` 函数直接返回传入的 resume 值，节点函数从 `interrupt()` 之后继续执行。
>
> 因此 `interrupt_node` 的函数体按自然顺序写即可：1) 构造数据 → 2) 调用 `interrupt()` → 3) 读取返回值。不需要 `if/else` 判断"是首次还是恢复"。
>
> **测试时需要 mock**：`unittest.mock.patch("langgraph.types.interrupt", return_value={"action": "confirm"})`，验证节点在恢复后正确读取 user_confirmation 并路由到 execution_loop。

#### §4.7.2 测试建议

`interrupt()` 在生产中依赖 LangGraph runtime 的暂停/恢复机制。在 pytest 单元测试中：
- 使用 `unittest.mock.patch("langgraph.types.interrupt", return_value={"action": "confirm"})` 模拟恢复行为
- 详细测试示例见 CODING-GUIDE 附录 C 测试策略

### 4.8 summarize

| 项目 | 内容 |
|------|------|
| LLM 调用 | 是，流式输出 |
| 状态读取 | 所有 `step_results`, `messages`, `market_state`, `analysis_results` |
| 状态写入 | `messages` 追加 assistant 回复, `status="completed"` |
| SSE | 流式推送 `agent_message`, 最后推送 `task_complete` |

### 4.9 error_handler

| 项目 | 内容 |
|------|------|
| 触发 | 任意节点抛不可恢复异常 |
| 行为 | **`status="failed"`**（**2026-06-07 补强 F-8**：终态枚举限定为 `completed \| failed \| cancelled`；删除原 `timeout` 终态，超时统一归为 `cancelled`，`status_reason="timeout_30m"`），`status_reason` 字段记录具体异常信息，**追加 system 消息 "任务已终止，状态：failed，原因：{status_reason}"**，写 `agent_runs` 表 |

```python
# error_handler 节点（F-8 实现）
def error_handler_node(state: dict) -> dict:
    exc = state.get("_last_exception")
    status_reason = f"{type(exc).__name__}: {str(exc)[:200]}" if exc else "unknown"
    system_msg = {
        "role": "system",
        "content": f"任务已终止，状态：failed，原因：{status_reason}",
        "timestamp": datetime.now().isoformat(),
    }
    return {
        "status": "failed",
        "status_reason": status_reason,
        "messages": state.get("messages", []) + [system_msg],
    }
```

---

## 5. SSE 事件流定义

| 事件名 | 时机 | 关键数据 |
|--------|------|----------|
| `status_change` | status 变化 | `status`, `run_id`, `status_reason` |
| `step_start` | 每一步开始 | `step_id`, `description`, `current_step_index`, `total_steps` |
| `step_result` | 每一步完成 | `step_id`, `success`, `summary` |
| `agent_message` | AI 流式输出 | `content` (文本片段) |
| `waiting_confirmation` | 需用户确认 | `type`, `message`, `options`, `plan_summary` |
| `error` | 错误 | `message`, `step_id` |
| `task_complete` | 任务结束 | `status`, `summary`, `status_reason` |

前端通过这些事件构建动态 UI，不拉取完整 State。

---

## 6. 任务提交流程（API → 图启动）

1. 用户请求 → API 构建初始 State
2. `graph.astream(initial_state, config)` 启动图执行 (非阻塞)
3. 循环消费 `updates` → 转化为 SSE 事件推送到前端
```python
# backend/api/sse.py — 安全 astream 包装
async def safe_astream_to_sse(graph, initial_state, config, run_id):
    """包装 astream，确保异常通过 SSE error 事件传达，不直接断流。"""
    try:
        async for event in graph.astream(initial_state, config=config):
            yield event  # 正常事件
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"astream 异常", extra={"run_id": run_id, "error": str(e)}, exc_info=True)
        
        # 推送 error 事件给前端
        yield {
            "event": "error",
            "data": {
                "message": str(e)[:200],
                "run_id": run_id,
                "fatal": True,
            }
        }
        # 再推送 task_complete(failed)
        yield {
            "event": "task_complete",
            "data": {
                "status": "failed",
                "status_reason": f"{type(e).__name__}: {str(e)[:100]}",
            }
        }
```
4. 遇到 `interrupt` → `astream` 暂停 → 结束流式消费 → 等待恢复
5. 恢复调用 `graph.ainvoke(None, config)` → 继续事件流

#### §6.1 图启动 config 完整示例（2026-06-07 修订：用 AsyncSqliteSaver）

**完整 config 必含三项**：`configurable.thread_id` + `checkpointer` + `recursion_limit`（防死循环）。

```python
# backend/agent/runner.py
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from pathlib import Path

# 启动时初始化（与 M3.5 §2.1、M5 §3.1 一致）
CHECKPOINT_DB = Path("data/langgraph_checkpoints.db")

# async with 上下文管理生命周期；绑定到 FastAPI lifespan
async with AsyncSqliteSaver.from_conn_string(
    f"sqlite+aiosqlite:///{CHECKPOINT_DB}",
    serde=JsonPlusSerializer(),
) as checkpointer:
    app.state.checkpointer = checkpointer

# 每次启动图的标准 config
config = {
    "configurable": {
        "thread_id": run_id,            # LangGraph 强制要求；checkpoint 主键
    },
    "checkpointer": checkpointer,       # 全进程共享单例
    "recursion_limit": 200,  # 与 execution_loop node_count 硬限一致（见 §4.4）
    "run_id": run_id,                   # 自定义追踪 ID（写入 trace_log）
}

# 启动（async 函数内调用）
async for updates in graph.astream(initial_state, config=config):
    yield updates  # 转为 SSE 事件

# 恢复（confirm 后）
from langgraph.types import Command
result = await graph.ainvoke(
    Command(resume=user_confirmation),
    config=config,
)
```

**Dev 模式切换**（仅本地调试）：
```python
if os.getenv("ASAREX_DEV_INMEMORY") == "1":
    import logging
    logging.getLogger(__name__).warning(
        "DEV MODE: 使用 MemorySaver，进程重启后所有 checkpoint 将丢失！"
        "生产环境请设置 ASAREX_DEV_INMEMORY=0 或删除此环境变量。"
    )
    from langgraph.checkpoint.memory import MemorySaver
    config["checkpointer"] = MemorySaver()
```

> **版本说明**（2026-06-07 决议 P0-2）：
> - 用 `AsyncSqliteSaver`，基于 `aiosqlite`，与 `graph.astream` 原生 async 兼容
> - 如果当前 LangGraph 版本 < 0.1（无 AsyncSqliteSaver），需要升级版本
> - 数据库连接字符串统一为 `sqlite+aiosqlite:///` 前缀（区别于业务库的 `sqlite:///`）
> - 所有 LangGraph 操作统一走 async 路径，不再出现 `asyncio.to_thread` 包装

**常见错误**：
- ❌ 忘记传 `configurable.thread_id` → LangGraph 抛 `ValueError: thread_id missing`
- ❌ 多进程/多 worker 共享 sqlite_saver 文件 → SQLite 锁竞争，必须保证**单进程单 sqlite_saver 实例**
- ❌ 自定义 serializer → 序列化 LangGraph 内部对象失败，必须用 `JsonPlusSerializer`

→ 由 software-product-manager 于 2026-06-07 补强，依据 review 第 2 轮 P0-1。

---

## 7. 状态清理与资源回收

- **Checkpoint 双段保留（2026-06-07 补强 P0-2，详见 M3.5 §2.2）**：
  - **热保留 1 小时**：LangGraph `SqliteSaver` 原生支持，用户中断后 1h 内可快速 `Command(resume=...)` 恢复
  - **冷保留 7 天**：业务库 `agent_runs.plan_json` + `skill_executions.output_result` + `conversation_history.messages_json` 持久化，可查询不可恢复
  - **每日 04:00 清理**：删除 `created_at < now() - 7 days` 的 `agent_runs` 记录（级联 skill_executions / conversation_history）
- 超时未恢复的暂停任务（`status="waiting_user"` 超 30 分钟）由定时扫描自动取消，写 `status="cancelled", status_reason="timeout_30m"`
- `universe_snapshot` 等大数据不持久化到 LangGraph checkpoint（transient reducer 排除），中断恢复时由 `skill_executions.output_result` 摘要重建

---

## 8. 日频分析计划示例

```json
[
  {"step_id": "s1",  "type": "skill",  "target": "data.check_data_freshness",  "description": "检查数据新鲜度"},
  {"step_id": "s2",  "type": "skill",  "target": "data.refresh_stock_info",    "description": "刷新股票基础数据", "depends_on": ["s1"]},
  {"step_id": "s3",  "type": "skill",  "target": "data.fetch_universe_snapshot","description": "获取全市场快照", "depends_on": ["s2"]},
  {"step_id": "s4",  "type": "agent",  "target": "market_agent",              "description": "分析当前市场状态"},
  {"step_id": "c1",  "type": "confirm_plan",  "target": null,                "description": "确认是否开始选股",
   "params": {"plan_summary": ["1.选股", "2.深度分析", "3.报告"], "max_candidates": 10}},
  {"step_id": "s5",  "type": "skill",  "target": "quant.screening_pipeline",  "description": "全市场筛选", "depends_on": ["c1", "s3"]},
  {"step_id": "s6",  "type": "agent",  "target": "analyst_agent",             "description": "深度分析候选股", "depends_on": ["s5"], "batch": true},
  {"step_id": "s7",  "type": "skill",  "target": "report.generate_markdown",  "description": "生成分析报告", "depends_on": ["s4","s6"]},
  {"step_id": "c2",  "type": "confirm_email", "target": null,                "description": "是否发送报告到邮箱？",
   "params": {"to": "user@example.com", "subject": "今日 A 股分析 2026-06-07", "preview_html": "<p>...</p>"}},
  {"step_id": "s8",  "type": "skill",  "target": "comm.send_email",           "description": "发送邮件", "depends_on": ["c2"]}
]
```

> **2026-06-07 补强 P0-1**：原 `type: "confirm"` 已拆为 `confirm_plan` 与 `confirm_email` 两个枚举值，分别携带不同的 `params` 上下文。

---

## 9. 设计决策记录

| 决策 | 结论 | 理由 |
|------|------|------|
| Confirm Plan 位置 | Market Analysis 之后 | 用户确认前看到市场诊断，决策质量更高；token 成本极低 |
| 候选池门槛 | `config.max_candidates` 控制（默认 10），不额外加 Quant 裁剪 | 量化筛选已在 Skill 内部完成；10 只 × 800 token 成本可控 |
| 报告输出粒度 | MVP 只生成 Markdown，邮件发送时自动转 HTML | 省掉 `report.generate_html`；Markdown→HTML 是标准操作 |
| 子图 | 初期不引入 | 所有步骤可通过顺序计划完成；子图接口 MVP 阶段不稳定 |
| 图数量 | 一个通用图 | `execution_plan` 差异覆盖所有工作流；单图 checkpoint 统一 |

---

### 附录 A：节点函数完整签名（整合自 INTERFACES.md）

| 节点 | 签名 | Pre 条件 | Post 条件 |
|------|------|---------|----------|
| `init` | `(state) → dict` | `messages` 非空 | `status="planning"` |
| `intent_parser` | `(state) → dict` | `messages` 非空 | 返回 `user_intent` |
| `plan_generator` | `(state) → dict` | `user_intent` 非空 | `status="executing"`, `execution_plan` 非空 |
| `execution_loop` | `(state) → Command` | `0 <= index < len(steps)`, `node_count < 200` | 路由到 skill/agent/confirm/summarize |
| `skill_executor` | `(state) → dict` | step.type == "skill", params $ref 已解析 | `step_results[step_id]` 写入 |
| `agent_executor` | `(state) → Send[]` | step.type == "agent", target != "master" | 批量返回 `Send` |
| `interrupt_node` | `(state) → Command` | type in confirm_plan/confirm_email/wait_for_user, interrupt_consumed == False | `status="waiting_user"` |
| `summarize` | `(state) → dict` | 所有 step 已完成或跳过 | `status` 为终态 |
| `error_handler` | `(state) → dict` | 无 | `status="failed"` |

**完整异常清单见 `docs/architecture/designs/M5-api-design.md` §7。**
**全量接口定义（含返回类型、异常、不变量）见 `backend/agent/nodes/` 中各节点源码注释。**

---

**上一节**: [M3.5 Interrupt 机制](M3.5-interrupt-mechanism.md)  
**下一方向**: 模块5 — API 层设计

<!-- Modified by software-engineer: 2026-06-07 -->
