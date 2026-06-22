# Module 3: Agent 架构与 Master Agent — 详细设计

**所属阶段**: Phase 3  
**依赖**: 模块2（Skill 执行系统完成）  
**核心问题**: 系统里到底有几个 Agent、各自职责边界在哪、Master Agent 如何规划和调度  
**状态**: Draft | **日期**: 2026-06-07

> ⚠️ **TARGET ARCHITECTURE** — 本文档描述目标架构，非当前实现。当前实际架构参见 `docs/ACTUAL_ARCHITECTURE.md`。

---

## 3.1 架构选择：层级控制而非多 Agent 平权

### 多 Agent 平权的常见问题
- Agent 间自由对话 → 无限循环或偏离意图
- 推理链不可追溯 → 推荐出错无法定位
- Token 成本失控 → 无意义内部对话消耗大量 LLM 额度

### 我们的选择：Master + Specialist 层级架构

```
Master Agent — 唯一的用户交互面
  ├── 规划权：解析意图 → 生成 ExecutionPlan
  ├── 调度权：按计划调用 Skill 或 Specialist Agent
  └── 最终解释权：收集结果 → LLM 汇总 → 回复用户

Specialist Agents — 无状态的领域推理器
  ├── 只被 Master 单向调用
  ├── 不互相调用
  └── 不直接接触用户
```

---

## 3.2 Agent 角色定义

### Master Agent（Planner + Orchestrator + Summarizer）

| 能力 | 描述 | 实现方式 |
|------|------|----------|
| 意图解析 | 判断用户意图（daily_analysis/stock_deep_dive/portfolio_check/reflection/chat） | LLM + Few-shot |
| 计划生成 | 基于意图 + 可用 Skill 清单，生成 ExecutionPlan | LLM 结构化输出 + 模板填充 |
| 调度执行 | 按计划顺序 + 依赖关系执行步骤 | 自定义执行引擎 / LangGraph |
| 结果汇总 | 收集所有步骤输出，LLM 生成最终回复 | LLM + 模板 |
| 状态保持 | 对话追踪、run_id 管理 | 内存 + agent_runs 表 |

**设计约束**:
- Master Agent 不直接操作数据，只通过 Skill 或子 Agent 获取
- Master Agent 不做复杂量化计算，它是"会思考的调度器"
- 所有推理依赖 LLM，Prompt 设计是核心

### Market Agent（市场感知 Specialist）

| 项目 | 内容 |
|------|------|
| 职责 | 判断当前市场状态、风格偏向、风险等级 |
| 输入 | 指数数据、行业板块数据（由 Master 通过 Data Skill 提前获取传入） |
| 输出 | `{regime, style_bias, risk_level, summary, confidence}` |

### Analyst Agent（个股分析 Specialist）

| 项目 | 内容 |
|------|------|
| 职责 | 对单只股票深度评分，输出推荐等级和理由 |
| 输入 | K 线、基本面、量化因子评分（Quant Skill 预先计算）+ 可选市场背景 |
| 输出 | `{total_score, signal, confidence, reasoning, debate_summary}` |
| 并发 | Master 可为候选池每只股票创建独立 Analyst Agent 并发执行 |

**输入来源说明（P0 补强）**：Analyst Agent 的输入**优先从 `state["step_results"]` 获取**，而非独立调用 Data Skill。具体映射：

| 输入项 | 来源 | State 路径 |
|--------|------|-----------|
| 因子评分 | `quant.screening_pipeline` 的输出 | `step_results[screening_step_id]["data"]["factor_scores"][stock_code]` |
| 大师评分 | `quant.screening_pipeline` 的输出 | `step_results[screening_step_id]["data"]["master_scores"][stock_code]` |
| 综合分 | `quant.screening_pipeline` 的输出 | `step_results[screening_step_id]["data"]["composite_scores"][stock_code]` |
| 市场状态 | `market_agent` 的输出 | `step_results[market_step_id]["data"]` 或 `state["market_state"]` |
| K 线/基本面 | 可选补充数据 | Analyst Agent 内部通过 ReAct 循环按需调用 `data.fetch_kline` 等 Code Skill |

**为什么优先从 step_results 取**：`screening_pipeline` 已经为候选池计算了因子分和大师分，Analyst Agent 重复调用会造成：(1) 浪费 LLM token；(2) 数据不一致（两次调用可能拿到不同时间点的数据）。Analyst Agent 只在需要**补充数据**（如行业均值、资金流向）时才主动调用 Data Skill。

### Portfolio Agent（组合分析 Specialist）

| 项目 | 内容 |
|------|------|
| 职责 | 分析用户持仓整体健康度、风险暴露、集中度 |
| 输入 | 持仓列表（Master 通过 Data Skill 获取）+ 当前市场状态 |
| 输出 | `{total_asset, var, max_drawdown, sharpe_ratio, warnings}` |

### Reflection Agent（复盘 Specialist）

| 项目 | 内容 |
|------|------|
| 职责 | 对比历史推荐与实际走势，总结失败原因 |
| 输入 | 历史推荐记录 + 实际股价表现 |
| 输出 | `{accuracy, avg_return, failed_cases, improvement_suggestions}` |
| 定位 | 异步、非每日必须，用户随时触发（"帮我复盘一下"），Phase 2+ 支持每日收盘后自动触发 |

#### §3.2.1 持久化用户记忆

**参考 WorkBuddy memory/ 机制**——系统需要长期记住用户的偏好和配置，每次会话自动加载。

**数据库表**（在 `agent.db` 中新增）：

```sql
CREATE TABLE user_memory (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    category TEXT DEFAULT 'preference',  -- preference / fact / rule / history
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

**内置记忆项**：

| key | 类别 | 写入时机 | 读取者 |
|-----|------|---------|--------|
| `user.name` | fact | 用户首次对话 | Master Agent 问候 |
| `preferred_style` | preference | 用户说"我喜欢价值风格" | plan_generator 默认风格 |
| `excluded_stocks` | rule | 用户说"排除煤炭股" | hard_filter 黑名单 |
| `email_config` | preference | 邮箱配置页面 | comm.send_email |
| `max_candidates` | preference | 用户手动修改过 | screening_pipeline 默认值 |
| `last_analysis_date` | history | 每日分析完成 | Dashboard 显示 |

**注入时机**：Master Agent 每次生成计划时，从 `user_memory` 加载 `preference` 和 `rule` 类别的条目，合并到 `config` 中。

**维护方式**：用户在对话中说"以后都用这个"等关键词时，Master Agent 调用 `memory.store_user_preference` Skill 写入。

#### §3.2.2 自动改进日志（Learning System）

**参考 WorkBuddy self-improving-agent**——记录每次分析的偏差，自动累积改进建议。

**日志文件位置**：`trading-skills/.learnings/`

```
trading-skills/.learnings/
├── FACTOR_ERRORS.md     ← 因子评分偏差记录
├── ANALYST_ERRORS.md    ← Analyst Agent 分析偏差
├── DATA_SOURCE_ISSUES.md ← 数据源异常记录
└── FEATURE_REQUESTS.md  ← 用户请求但尚未实现的能力
```

**记录时机**：

| 触发场景 | 记录位置 | 记录内容 |
|---------|---------|---------|
| 因子评分与真实收益偏差 > 20% | FACTOR_ERRORS.md | 股票代码、预测分、实际收益、偏差分析 |
| Analyst Agent 推荐严重失误（strong_buy 但跌 > 10%） | ANALYST_ERRORS.md | 股票、推荐理由、实际走势、反思 |
| 数据源连续 3 次超时 | DATA_SOURCE_ISSUES.md | 数据源名称、失败模式、频率 |
| 用户说"能不能做 X"但系统不支持 | FEATURE_REQUESTS.md | 用户原始需求、优先级预估 |

**谁来写**：这些日志由 **Reflection Agent** 在每日复盘时自动生成。Master Agent 在计划中安排复盘步骤时，Reflection Agent 读取历史数据，输出偏差记录到日志文件。

**谁读**：用户主动要求复盘时，Reflection Agent 读取日志文件生成改进报告。

**与现有设计的集成**：日志文件是 Markdown 格式，放在 `trading-skills/.learnings/` 下——和你的 15 个交易技能在同一个目录结构中，统一管理。

#### §3.2.3 与现 `services/master_agents.py` 的接口映射 + 迁移方案

**老接口（现 `services/master_agents.py`，Phase 1 已落地）**：
```python
# 现有 4 个大师风格（livermore / buffett / 欧奈尔 / 投机）
def score_stock(stock_code: str, context: dict) -> dict:
    return {
        "master": str,        # 大师名称
        "score": float,       # 0-100 评分
        "reasoning": str,     # 文本解释
    }
```

**新 schema（§3.2 各 Specialist 输出）**：
```python
# 新版统一输出
{
    "total_score": float,
    "signal": "strong_buy"|"buy"|"hold"|"sell"|"strong_sell",
    "confidence": float,        # 0-1
    "reasoning": str,
    "debate_summary": {         # 多大师投票/辩论
        "bull_thesis": str,
        "bear_thesis": str,
        "verdict": str,
        "consensus_score": float,
    }
}
```

**映射表**：

| 现接口字段 | 新 schema 字段 | 适配方式 |
|------------|----------------|----------|
| `master` | 推入 `debate_summary` 内部，按 master 分组 | 包装层聚合 |
| `score` | 归一化到 `total_score`（÷100） | 包装层 |
| `reasoning` | 直接并入 `reasoning` + `bull_thesis/bear_thesis` | 拼接 |
| **（新）** | `signal` | 包装层根据 score 阈值映射（≥80 strong_buy, ≥65 buy, ≥50 hold, ≥35 sell, else strong_sell） |
| **（新）** | `confidence` | 包装层用 `score / 100` 近似（MVP 简化） |
| **（新）** | `debate_summary` | 包装层调 4 个大师函数聚合，老 reasoning 当 thesis 素材 |

**迁移方案（3 阶段、共 10 个工作日）**：

| 阶段 | 天数 | 任务 | 产出 |
|------|------|------|------|
| **Stage 1：适配层 Wrapper** | 5d | 新建 `services/agent_adapters.py`，对老 4 个大师函数做包装，输出新 schema；Analyst Agent 内部**先用包装层**，确保日频流程跑通 | `agent_adapters.py` + 单测覆盖 4 个大师 |
| **Stage 2：新 LLM 推理** | 3d | 在 Analyst Agent 内**逐步加入 LLM 辩论环节**（bull/bear prompt），`debate_summary` 从 LLM 生成；老 wrapper 退化为兜底 | Analyst Agent LLM 推理版本 |
| **Stage 3：彻底替换** | 2d | 老 `score_stock` 标记 deprecated；6 个月后删除 | 旧函数降级 WARN 日志 |

**MVP 范围**：仅 Stage 1（包装层），LLM 辩论推到 Phase 4。

→ 由 software-product-manager 于 2026-06-07 补强，依据 review 第 2 轮 P0-3。

---

## 3.3 ExecutionPlan — 计划数据契约

```
ExecutionPlan:
  plan_id: str
  intent: str                    # 解析后的用户意图
  steps: list[PlanStep]
  created_at: datetime

PlanStep:
  step_id: str                   # 序号
  type: "skill" | "agent" | "confirm_plan" | "confirm_email" | "wait_for_user"  # 5 个枚举值（2026-06-07 补强 P0-1），每种 confirm 类型都是独立枚举值
  intent: str                    # 本步目标（供 Agent 或 LLM 理解）
  target: str                    # skill_name 或 agent_name（agent 类型时不可为 "master"）
  params: dict                   # 输入参数；confirm_* 类型时为该确认用的 payload
  depends_on: list[str]          # 前置 step_id 列表
  timeout_seconds: int           # 步骤级超时
```

**`step.type` 枚举的 forward-compatible 约束**：

- **MVP 阶段**仅支持上述 5 个值（`skill` / `agent` / `confirm_plan` / `confirm_email` / `wait_for_user`），`plan_generator` 用 LangChain `with_structured_output` + 枚举约束，LLM 只能输出这 5 个值之一。
- **关于 `confirm_plan` 与 `confirm_email` 的拆分**（2026-06-07 补强 P0-1）：原 M3 中 `type: "confirm"` + 二级 `confirm_type` 字段的设计在 LLM 结构化输出时存在嵌套枚举冲突，LLM 难稳定生成。改为**每种 confirm 行为一个独立枚举值**，`params` 字段直接存放该确认类型所需的上下文参数（如 `confirm_plan` 的 `params` 含 `plan_summary`；`confirm_email` 的 `params` 含 `to/subject/preview`）。后续若新增 `confirm_risk_warning` 等，也是直接扩枚举，不需二级字段。
- **未来扩展值**（如 `graph` / `subgraph` / `parallel`）**MVP 阶段明确禁用**——`plan_validator` 在 §3.3 末尾校验逻辑中**直接拒绝**任何不在枚举内的 `type` 值，错误信息 `"step.type='{value}' not supported in MVP, allowed: [skill, agent, confirm_plan, confirm_email, wait_for_user]"`。
- **预留扩展路径**：当 Phase 4 需要引入新类型时，需在 M3 文档先增补枚举值 + 配套执行引擎实现，**禁止运行时动态添加**——保证 schema 的可追溯性。

→ 由 software-product-manager 于 2026-06-07 补强，依据 review 第 2 轮 P1。

**计划生成的可靠性保证**:
- LLM 严格使用结构化输出（`with_structured_output`），skill/agent 名称枚举约束
- 生成计划后做校验：所有 target 必须在已注册列表中；依赖关系无环
- 标准意图（如"开始每日分析"）用模板填充参数，LLM 只做参数提取
- 校验失败时返回错误并请求重新规划

---

## 3.4 子 Agent 调用方式

**关键决策**: 子 Agent 不作为 Skill。Skill 是无状态函数，子 Agent 内部会调 LLM 推理，有独立 Prompt 和上下文窗口。

```
计划步骤的执行:
  step.type == "skill"
    → SkillExecutor.execute(step.target, step.params)

  step.type == "agent"
    → AgentNode.run(step.target, step.params)
    → AgentNode 内部封装 LLM 调用 + 独立 Prompt

  step.type == "confirm_plan"
    → 暂停执行，SSE 推送 "confirm_plan" 类型等待用户确认计划
    → params 含 plan_summary、max_candidates 等

  step.type == "confirm_email"
    → 暂停执行，SSE 推送 "confirm_email" 类型等待用户确认发送邮件
    → params 含 to、subject、preview_html

  step.type == "wait_for_user"
    → 类似 confirm，但无预设确认内容（如 "请输入想分析的股票代码"）
```

**Analyst Agent 并发**: 对于候选池批量分析，Master 生成一个含 N 个 analyst 步骤的计划，执行引擎识别后并行调度。每个实例是独立的 LLM 调用。

**LangGraph Send API（fan-out/fan-in）实现**：批量并发**必须**用 LangGraph 的 `Send` API 实现节点级 fan-out / fan-in，不能简单地在 `execution_loop` 节点内 `asyncio.gather` 调 N 个 sub-graph——后者会丢失 LangGraph 的 checkpoint 追踪、step_results 合并、cancel 传播等机制。代码模式如下：

```python
# M4 execution_loop 节点内（伪代码）
from langgraph.constants import Send

def analyst_fanout(state: State) -> list[Send]:
    """对 candidate_pool 中每只股票 dispatch 一个 sub-graph"""
    return [
        Send("analyst_subgraph", {
            "stock_code": code,
            "run_id": state["run_id"],
            "market_state": state["market_state"],
            "current_step_index": state["current_step_index"],
        })
        for code in state["candidate_pool"]
    ]
# 上游节点用 {"analyst_subgraph": analyst_fanout} 配置条件边 → 自动 fan-in 回汇总节点
```

Send API 的关键收益：(1) 每个 sub-graph 独立 checkpoint，崩溃后能 resume；(2) sub-graph 内的 `interrupt()` 可被主图传播到 SSE；(3) `cancel` 信号自动 propagate 到所有 in-flight Send。

#### §3.4.1 Skill / Agent 按 `user_intent` 过滤（2026-06-07 补强 C-3 + F-7 + F-10）

**核心问题**：MVP 阶段 30+ Skill + 4 个 Agent 同时暴露给 LLM 时，工具选择准确率明显下降（context 过长、LLM 混淆相似工具）。

**解决**：从 `skill_registry` 表（见 M1 §1.5 Phase 2 新增表）按 `user_intent` 动态过滤。

```python
# backend/agent/tools/filter.py
def filter_tools_for_intent(user_intent: str, db_session) -> list[dict]:
    """根据 user_intent 从 skill_registry 查询允许的工具描述。"""
    rows = db_session.query(SkillRegistry).filter(
        SkillRegistry.enabled == True,
        or_(
            SkillRegistry.allowed_intents == "[]",  # 空数组 = 全局可用
            SkillRegistry.allowed_intents.contains(f'"{user_intent}"'),
        )
    ).all()
    return [
        {
            "name": r.skill_name,
            "category": r.category,
            "type": "agent" if r.category == "agent" else "skill",
            "description": r.description,
        }
        for r in rows
    ]
```

**Agent 白名单约束（F-7）**：`category='agent'` 的条目，其 `target` 限定为 4 个 Specialist Agent（market_agent / analyst_agent / portfolio_agent / reflection_agent），**禁止等于 `"master"`**——`plan_generator` 的结构化输出 schema 中 `target` 字段对 `type='agent'` 步骤额外约束 enum 不含 master。

**Agent 与 Skill 的 Prompt 区分（F-10）**：过滤后的工具列表中每个工具带 `"type": "skill" | "agent"` 标签。Master Agent 的 Prompt 中明确：
- `type="skill"` → **计算/查询/数据获取**（无 LLM 推理，纯函数）
- `type="agent"` → **综合推理/多步分析**（内部调 LLM，有独立 Prompt）

**数据库初始化（2026-06-07 决议 P1-7 + P2-11）**：`skill_registry` 表的数据来源是**每个 Skill Python 模块中的 `SKILL_META` 字典**（不解析 SKILL.md，不放在 config.yaml）。

```python
# backend/skills/data/fetch_kline.py
SKILL_META = {
    "name": "data.fetch_kline",
    "description": "获取个股日 K 线",
    "category": "data",
    "type": "skill",
    # allowed_intents：允许调用的 user_intent 列表
    "allowed_intents": ["daily_analysis", "stock_deep_dive"],
    "input_schema": {"stock_code": "str", "days": "int"},
    "output_schema": {"klines": "list[Kline]"},
}
```

启动时 `SkillRegistry._discover_skills()` 遍历 `backend/skills/` 下所有子目录，`importlib.import_module` 读取 `SKILL_META`，注册到内存，同时 **UPSERT** 写入 `skill_registry` 表（幂等更新）。`allowed_intents` 字段在 SKILL_META 中配置，不允许 LLM 自行修改。

**为什么不是 `config.yaml`**：`config.yaml` 若枚举每个 Skill 会导致配置膨胀到 30+ 条目，且 Skill 变更时需要同时改配置文件。将 `allowed_intents` 写在 Skill 模块自身的代码中更贴近单一职责原则。

#### §3.4.2 单进程线程池约束（F-11，2026-06-07 补强）

**MVP 阶段硬约束**：

- **`uvicorn --workers 1`**：禁止多 worker 启动（SQLite 单文件 + LangGraph checkpointer 不支持并发进程）。
- **线程池大小固定为 8**（`SKILL_THREAD_POOL_SIZE=8`）。
- **同步 Skill 调用路径（2026-06-07 决议 P1-8）**：
  ```python
  # SkillExecutor 内部
  self._sync_pool = ThreadPoolExecutor(max_workers=8)

  # LangGraph node (async def) 内调用
  async def skill_executor_node(state: dict) -> dict:
      result = await SkillExecutor.execute(skill_name, params, ...)
      # SkillExecutor.execute 内部：
      #   loop = asyncio.get_event_loop()
      #   future = loop.run_in_executor(self._sync_pool, sync_skill_func, params)
      #   return await future
  ```
  - 使用 `concurrent.futures.ThreadPoolExecutor` 显式线程池，而非 `asyncio.to_thread`（后者使用默认线程池，不可控）。
  - 线程池生命周期绑定 FastAPI `lifespan`：`async def lifespan(app): self._sync_pool = ...; yield; self._sync_pool.shutdown(wait=True)`。
  - LangGraph 节点函数是 `async def`，`await SkillExecutor.execute()` 不会阻塞事件循环。

- **config.yaml 中标注**：
  ```yaml
  runtime:
    workers: 1                # MVP 强制 1
    skill_thread_pool_size: 8 # 同步 Skill 线程池
  ```
- **多 worker 支持**列入 Phase 4 评估项，届时引入 Redis 锁 + 分布式 checkpoint（如 LangGraph Postgres checkpointer）+ SSE 跨进程转发。

---

## 3.5 对话状态与上下文管理

```
状态存储位置:
  MVP: 内存 + agent_runs 表（持久化）
  服务重启 → 历史对话不可用，但 agent_runs 保留
  未来扩展: Redis 存储活跃会话

上下文窗口管理:
  滑动窗口 + 摘要策略
  超过 N 轮 → 早期消息压缩为 LLM 摘要
  每日分析任务完成后可重置上下文
```

#### §3.5.1 run_id 注入契约（争议 4 落地）

**核心结论**：`run_id` 由 init 节点创建（`run_id=uuid4().hex`），**所有下游节点通过 `state["run_id"]` 显式读取，不依赖 `contextvar`**。

**为什么不用 contextvar**：
- LangGraph 图执行是**单进程多协程**模式（asyncio），多个 `run_id` 在同一进程内并发时，`contextvars.ContextVar` 会被覆盖或被错误地继承——尤其在 `Send` API fan-out 后 sub-graph 的协程切换时，contextvar 行为**不可预测**。
- `contextvar` 在 LangGraph **checkpoint 序列化时不被持久化**——意味着即使在 init 节点设了 `ctx.run_id`，恢复时已失效，下游节点取到 `Token.MISSING`。
- 图内**不启用** contextvar，**仅在 CLI/批处理入口（如 `launch.py` 的 `cli.py` 子命令）作为兜底**——CLI 单进程单 run，不存在并发覆盖问题，contextvar 可让全局工具函数（如 `logger`）无需显式传参。

**伪代码（init + 节点读取）**：
```python
# M4 init 节点
def init_node(state: State) -> dict:
    run_id = state.get("run_id") or uuid4().hex   # 恢复时复用，初始时新建
    return {
        "run_id": run_id,
        "status": "planning",
        "messages": state.get("messages", []),
    }

# M4 execution_loop 节点（M3 §3.4 的 Send API fan-out 也照此传）
def execution_loop_node(state: State) -> dict:
    step = state["execution_plan"][state["current_step_index"]]
    result = SkillExecutor.execute(
        skill_name=step.target,
        params=step.params,
        run_id=state["run_id"],                                # 显式从 state 读取
        correlation_id=f"{state['run_id']}:{step.step_id}",   # 约定格式
    )
    return {"step_results": {step.step_id: result.dict()}}
```

**与 M2 SkillExecutor 签名的协作**：`SkillExecutor.execute(skill_name, params, *, run_id: str, correlation_id: str = None)` 已在 M2 改名为 keyword-only 必传参数——图内调用方**必须**从 `state["run_id"]` 传，不允许用默认值或 None。

**contextvar 兜底范围**（仅限以下场景）：
- `backend/cli.py` 的 `cli run-once --run-id xxx` 子命令：CLI 单 run 顺序执行，无并发覆盖
- 测试 fixtures：`tests/conftest.py` 中 `set_run_id_context("test-run-001")` 给单元测试用
- `services/logger.py` 的 `get_logger()`：作为**读取**方 fallback（`ctx.run_id` 取不到时返回 "no-run-id"，**不主动写入**）

**禁止范围**：
- ❌ LangGraph 图内任何节点函数体内 `ctx.run_id = ...`（init 节点也不允许）
- ❌ `SkillExecutor.execute` 内部用 `ctx.run_id`（必须用调用方传入的 run_id 参数）
- ❌ FastAPI request handler 内设 ctx 后传给后台任务（HTTP 请求结束 ctx 销毁，后台任务会拿到 None）

→ 由 software-engineer 于 2026-06-07 补强，依据 review 第 2 轮 P0-5。

---

## 3.6 Human-in-the-loop 实现

| 场景 | 实现方式 |
|------|----------|
| 分析前确认 | Master 生成计划后不立即执行，先输出"计划如下...确认开始？" |
| 参数修改 | 用户在确认时指定风格/日期等，Master 更新计划再执行 |
| 邮件确认 | 报告生成后询问"是否发送到邮箱？"，计划中预留 confirm 步骤 |
| 用户中止 | 前端"停止"按钮，设取消令牌，执行引擎优雅中断 |

通用模式: `type: "confirm"` 步骤 → SSE 推送确认 → 等待用户 HTTP 返回 → 继续

---

## 3.7 流式响应（SSE 事件定义）

```
前端看到的实时进度:

[思考]   正在解析意图...
[计划]   生成执行计划: 1.拉取行情 → 2.市场分析 → 3.选股 → 4.报告
[执行]   正在获取全市场 K 线... (skill: data.fetch_kline)
[结果]   市场状态: 震荡偏多 (Market Agent)
[对话]   AI 回复正在生成...
[最终]   完整回复（流式 typewriter）
```

**关键原则**: 前端不能收到 10 秒空白后突然弹出整段结果。

---

## 3.8 错误处理与降级策略

| 失败场景 | 降级策略 |
|----------|----------|
| Data Skill 失败 | 尝试备用数据源，或告知用户"数据暂时不可用，基于缓存继续" |
| Quant Skill 个股失败 | 跳过该股票，继续分析池中其他股票 |
| Quant Skill 整体筛选失败 | 回退到更基础的筛选逻辑 |
| LLM 调用失败 | 自动重试（可配置次数），彻底失败则告知用户建议稍后重试 |
| 步骤不可恢复失败 | 保留已完成的步骤结果，输出部分结论 |
| 用户取消 | 检查取消令牌 → 优雅中断 → 保存中间结果 |

---

## 3.9 落地任务拆分（Phase 3）

| 任务 ID | 内容 | 产出 | 测试要点 |
|---------|------|------|----------|
| T3.1 | Master Agent 框架 | 意图解析 + 计划生成 Prompt + 执行循环 | 正确解析 4 种意图；计划步骤全部使用已注册 Skill |
| T3.2 | Market Agent | 独立 LLM 推理节点 | 输入 3 种模拟市场数据 → regime 符合预期 |
| T3.3 | Analyst Agent | 单股分析节点，含并发调度 | 20 只并发 → 全部返回结构化结果；错误股票跳过不影响；**端到端耗时 < 90s**（含数据拉取+LLM 推理） |
| T3.4 | Portfolio Agent | 持仓分析节点 | 空持仓返回无警告；高集中度返回警告 |
| T3.5 | Reflection Agent | 复盘节点 | 历史推荐对比实际 → accuracy 数值正确 |
| T3.6 | Human-in-the-loop | confirm 步骤 + 暂停/恢复 | 计划暂停后等待用户输入再继续；超时自动取消 |
| T3.7 | SSE 流式推送 | 所有执行过程推送到前端 | 每个步骤 start/result 事件；前端流畅渲染 |
| T3.8 | 端到端测试 | 模拟完整日频流程 | 从用户输入到报告生成的全链路通过；**日频全流程 P95 耗时 < 90s**（用户可接受阈值） |

→ 由 software-product-manager 于 2026-06-07 补强，依据 review 第 2 轮 P1。


---

### 附录 A：Analyst Agent Tool Calling 与 Prompt Skill 系统（整合自 ADDENDUM-analyst-tool-calling.md）

Analyst Agent 在分析过程中可调用外部工具增强分析能力，支持可插拔的 Prompt Skill 注入。

**两种 Skill 的定义区分**：

| 维度 | Code Skill | Prompt Skill |
|------|-----------|-------------|
| 本质 | Python 函数 | Markdown 文档 |
| 注册方式 | `SKILL_META` + `SkillRegistry` | `trading-skills/{name}/SKILL.md` |
| 执行方式 | `SkillExecutor.execute()` | 注入到 Analyst Agent system prompt |
| 谁调用 | execution_loop | Analyst Agent (LLM 推理时参考) |
| 示例 | `quant.hard_filter`, `data.fetch_kline` | 利弗莫尔交易原则、T+0 策略 |

**Analyst Agent ReAct 推理循环**：

```
收到基础数据（因子分、大师分、K线摘要）
→ LLM 决定: "需要行业均值" / "需要资金流向" / "需要参考利弗莫尔原则"
→ 调对应 tool（Code Skill 或 Prompt Skill）
→ 拿到结果继续推理
→ 重复直至输出最终 AnalysisResult
```

**可调用工具集**：
- 数据类 Code Skill：`data.fetch_fundamentals`, `data.fetch_money_flow`, `data.fetch_dragon_tiger`, `data.fetch_sectors`
- Prompt Skill：从 `trading-skills/` 目录自动发现，运行时注入

**工具调用与 step_results 的关系（P1 补强）**：

Analyst Agent 的数据来源分**两层**：

| 层级 | 来源 | 何时使用 | 示例 |
|------|------|---------|------|
| **基础层（预加载）** | `state["step_results"]` 中上游 Skill 的输出 | 每次分析必用 | 因子分、大师分、综合分、市场状态 |
| **补充层（按需调用）** | ReAct 循环中主动调用 Code Skill | 需要额外数据时 | 行业均值、资金流向、龙虎榜 |

基础层数据在 Analyst Agent 初始化时直接注入 system prompt（避免浪费 LLM tool call token）。补充层由 LLM 在 ReAct 循环中按需决定是否调用。

**禁止调用**：Analyst Agent **不得**重新调用 `quant.*` 系列 Skill——量化计算已由 `screening_pipeline` 完成，重复调用会引入数据不一致。

**添加新 Prompt Skill 的流程**：
1. 在 `trading-skills/` 下新建目录 + `SKILL.md`
2. 重启系统（或调用 `PromptSkillRegistry.reload()`）
3. Analyst Agent 自动可用，**不需要改代码**

---

## 3.10 设计风险与对策

| 风险 | 影响 | 对策 |
|------|------|------|
| LLM 计划不可靠 | 执行错误或幻觉 | 结构化输出 + 名称枚举约束 + 计划校验 + 模板覆盖 80% 场景 |
| 并发 Agent 成本激增 | Token 消耗过大 | 候选池上限 20 只；Analyst Agent Prompt 精简，只传关键特征 |
| 上下文撑爆 | Token 超限 | 滑动窗口 + 摘要；子 Agent 输出只保留摘要 |
| 同步 Skill 超时 | 线程泄漏 | `execution_mode` 字段区分 sync/async；同步 Skill 用 `to_thread` |

#### §3.10.1 Analyst Agent 辩论策略（Q7.3 补强，2026-06-07）

**决策**：**所有候选股全跑辩论**（不设 top N 门槛）。

**理由**：
- 个人使用场景，用户不在乎 token 成本
- 仅对 top 5 跑辩论会丢失 6-20 名候选股的"多空对抗"信息
- 对所有候选公平辩论，更利于 Reflection Agent 复盘时发现"为什么排序靠后的反而走势更强"

**实现**：
- Analyst Agent ReAct 循环中**对每只股票**调 `quant.debate_analysis`
- 20 只并发（Send API fan-out 限速 10 路）→ 总耗时约 2-3 轮辩论
- 单只辩论超时 60s 不阻断整体（M3.5 §A.1 step 级降级）

**成本估算**（假设每只 6 次 LLM 调用 × 800 token）：
- 20 只 × 6 = 120 次 LLM 调用
- Token 消耗：~96,000 tokens / 每日分析
- 月成本（DeepSeek-chat）：~2-3 元（个人可接受）

**不做 top N 门槛的副作用**：
- 报告生成时间从 60s 延长到 80s（仍满足 90s 硬指标）
- LLM 调用失败时扇出 20 个 sub-graph 的错误处理压力增大（M4 §4.6.1 已实现 try/except 容错）

---

**依赖关系**: Phase 3 → Phase 2 (Skill 系统)
**下一方向**: 模块4 — 工作流引擎（LangGraph 图设计）或 模块5 — API 设计
