# Module 2: Skill 执行系统 — 详细设计

**所属阶段**: Phase 2  
**依赖**: 模块1 (基础设施)  
**核心定位**: Skill 是**无状态工具函数**的标准化封装。Agent 不直接操作数据，只通过 Skill 获取和处理信息。  
**状态**: Draft | **日期**: 2026-06-07

> ⚠️ **TARGET ARCHITECTURE** — 本文档描述目标架构，非当前实现。当前实际架构参见 `docs/ACTUAL_ARCHITECTURE.md`。

---

## 1. 设计原则

- **Skill 不持有状态**。输入输出是可序列化的参数和结果，不依赖 Agent 上下文或会话状态。
- **Agent 不直接操作数据**。所有数据获取和计算能力都封装为 Skill，Agent 通过 Tool Calling 感知并调用。
- **横切关注点集中管理**。缓存、重试、超时、日志由 SkillExecutor 统一处理，Skill 实现只写业务逻辑。
- **可测试性**。每个 Skill 可独立单元测试，mock 底层数据源即可。

---

## 2. Skill 元数据规范 (`SkillSchema`)

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `name` | str | — | 唯一标识，采用 `category.action` 命名空间，如 `data.fetch_kline` |
| `description` | str | — | 给 LLM 看的功能说明，直接影响调用准确率 |
| `category` | str | — | `data` / `quant` / `report` / `communication` / `memory` |
| `input_schema` | dict | — | JSON Schema 定义参数及约束 |
| `output_schema` | dict | {} | 声明返回结构（可选） |
| `timeout_seconds` | int | 30 | 数据类 10s，量化类 60s，通信类 30s |
| `max_retries` | int | 1 | 可恢复错误的自动重试次数 |
| `cache_ttl_seconds` | int | 0 | 结果可缓存时间（0 表示不缓存） |
| `execution_mode` | str | `"sync"` | `"sync"` / `"async"`，决定执行器用哪种方式包装 |
| `version` | str | `"1.0.0"` | → P1 由 software-architect 于 2026-06-07 补强：Skill 语义版本，向后兼容追踪 |
| `side_effects` | list[str] | `[]` | → P1：声明副作用，逗号分隔 enum：`db_write / email_send / file_write / network_post / stateful_cache_invalidate`，注册时校验，**含副作用的 Skill 必加 idempotency_key** |
| `estimated_cost` | dict | `{}` | → P1：成本预估，`{"tokens_max": int, "latency_p95_ms": int, "external_calls": int}`，Master Agent 计划时纳入预算 |
| `deprecated_aliases` | list[str] | `[]` | → P1：老命名空间兼容别名，详见 §6.x |
| `autonomy_level` | str | `"medium"` | **Skill 自由度等级**：`high`（纯文本指令，LLM 自主发挥）`medium`（脚本+参数，推荐模式）`low`（特定脚本，严格按流程）——参考 WorkBuddy 设计理念 |

```python
class SkillType(str, Enum):
    """Skill 类型：决定执行路径"""
    CODE = "code"      # Python 函数，通过 SkillExecutor.execute() 调用
    PROMPT = "prompt"  # Markdown 文档，注入到 Agent system prompt


class SkillSchema(BaseModel):
    name: str
    description: str
    type: SkillType = SkillType.CODE      # 新增：code / prompt，决定执行路径
    category: Literal["data", "quant", "report", "communication", "memory"]
    input_schema: dict
    output_schema: dict = {}
    timeout_seconds: int = 30
    max_retries: int = 1
    cache_ttl_seconds: int = 0
    execution_mode: Literal["sync", "async"] = "sync"
    autonomy_level: Literal["high", "medium", "low"] = "medium"
    # → P1 补强字段
    version: str = "1.0.0"
    side_effects: list[str] = []
    estimated_cost: dict = {}
    deprecated_aliases: list[str] = []
```

**`type` 字段决定执行路径**：

| type | 注册方式 | 执行方式 | 返回值 | 示例 |
|------|---------|---------|--------|------|
| `code` | `SKILL_META` + Python 函数 | `SkillExecutor.execute()` 直接调用 | `SkillResult` (结构化数据) | `data.fetch_kline`, `quant.hard_filter` |
| `prompt` | `trading-skills/{name}/SKILL.md` | 注入到 Analyst Agent system prompt，LLM 读取参考 | LLM 生成的分析文本 | 利弗莫尔、T+0、炒家33篇 |

**autonomy_level 分级说明**：

| 等级 | 含义 | 适用 Skill 类型 | 控制方式 |
|------|------|----------------|---------|
| `high` | LLM 自主发挥，仅给知识参考 | Prompt Skill（交易方法论） | SKILL.md 全文注入到 system prompt，不约束输出格式 |
| `medium` | 推荐模式，允许参数变化 | Quant Skill（因子评分、大师评分） | 提供 Python 脚本 + 参数模板，LLM 可调整参数 |
| `low` | 严格按流程，确定性输出 | Data Skill（数据拉取）、Communication Skill（发邮件） | 固定签名的 Python 脚本，由 SkillExecutor 直接调用 |

---

## 3. 注册机制

- 使用**装饰器**模式集中注册。所有 Skill 在系统启动时自动收集到 `SkillRegistry`。
- 注册表是一个内存字典，key 为 `skill.name`，value 为 `SkillWrapper`（封装元数据和实际函数）。
- `SkillRegistry.list_skills()` 返回所有 Skill 的 JSON 描述数组，供 Master Agent Tool Calling 使用。
- **硬约束**：如果 Quant Skill 的参数中包含 `db_session` 类型，注册时直接拒绝。

```python
registry = SkillRegistry()

@registry.register(
    name="data.fetch_kline",
    description="获取指定股票的日K线数据",
    category="data",
    input_schema={...},
    timeout_seconds=10,
    execution_mode="sync",
)
def fetch_kline(stock_code: str, days: int = 60) -> list[dict]:
    # 实际实现...
    pass
```

---

## 4. 执行引擎 (`SkillExecutor`)

`SkillExecutor` 是唯一的 Skill 调用入口。职责链：

```
1. 参数标准化
   → 调用 Skill 实现的 normalize_params()（如果有）
   → 确保语义等价的参数产生相同的标准化 key

2. 计算 idempotency_key（仅 side_effects 非空时）
   → key = md5(f"{run_id}:{step_id}:{json(normalized_params, sort_keys=True, default=str)}")
   → 查 skill_executions 表（FK → agent_runs.run_id）
   → 命中且未超时 → 标记 replayed=True 直接返回历史结果（短路后续步骤）

3. 查 L1 缓存
   → key = "skill:{name}:{md5(json(normalized_params, sort_keys=True, default=str))}"
   → 命中直接返回并标记 cache_hit

4. 校验参数
   → 用 input_schema 校验
   → 不合法直接抛 SkillExecutionError

5. 执行（按 execution_mode 分路径）
   → async: 直接 await，外层 asyncio.wait_for 有效
   → sync: 提交到自管 ThreadPoolExecutor（max_workers 显式配置，见 §4.2）
   → 外层 wait_for 兜底
   → 文档约定：同步 Skill 必须保证内部 IO 不会无限阻塞（如 requests 设 timeout）

6. 重试
   → 捕获可恢复异常（网络超时等），按 max_retries 重试

7. 写缓存
   → 成功后按 cache_ttl_seconds 写入 L1

8. 写 SkillExecution DB 记录（含 idempotency_key, replayed）
   → 产生 SkillExecution 行，关联 run_id（FK 约束）
   → 记录 latency_ms, tokens_used, cache_hit, replayed, idempotency_key
```

**SkillExecutor.execute 签名**（P0-4 由 software-architect 于 2026-06-07 改）：

```python
class SkillExecutor:
    def execute(
        self,
        skill_name: str,
        params: dict,
        *,
        run_id: str,                          # 必传 keyword-only
        correlation_id: str | None = None,    # 必传 keyword-only，缺省 f"{run_id}:{skill_name}"
        step_id: str | None = None,           # 幂等键需要
    ) -> SkillResult:
        ...
```

> **变更点**：原签名 `(skill_name, params)` 改为 `(skill_name, params, *, run_id, correlation_id)`，**必传 keyword-only**。LangGraph 节点调用时 `SkillExecutor.execute(name, params, run_id=state["run_id"], step_id=step.step_id)`。**禁隐式从 contextvar 读 run_id**（多 worker 下崩）。

**SkillResult 结构**：

```python
class SkillResult(BaseModel):
    success: bool
    data: Any = None
    error: str | None = None
    latency_ms: int
    tokens_used: int = 0
    cache_hit: bool = False
    replayed: bool = False                # → P0-4：命中幂等键时 True
    idempotency_key: str | None = None    # → P0-4
    idempotency_override: str | None = None  # Skill 覆盖默认幂等键（如 comm.send_email）
    normalized_params: dict | None = None
```

### 4.1 幂等性约定（P0-4 必读）

**目的**：Interrupt 恢复时同一 `step_id` 重跑、并发重试、用户重复点击确认，**不重复扣费/不重复发邮件/不重复写 DB**。

**生成规则（2026-06-07 修订 P1-5：统一算法 + Skill 覆盖机制）**：

```python
import hashlib, json
from backend.shared.config import Config

def make_idempotency_key(skill_name: str, normalized_params: dict) -> str:
    """统一幂等键生成算法。
    
    算法：md5(f"{skill_name}:{sorted_json}") 取前 16 位十六进制。
    不包含 run_id/step_id——同一参数在任何 run 中结果相同（纯查询不产生副作用）。
    """
    safe_params = Config.to_json_safe(normalized_params)  # 统一处理 datetime/Decimal/UUID
    payload = json.dumps(safe_params, sort_keys=True, ensure_ascii=False, default=str)
    raw = f"{skill_name}:{payload}".encode("utf-8")
    return hashlib.md5(raw).hexdigest()[:16]  # 16 字符
```

**Skill 覆盖机制**：特殊 Skill（如 `comm.send_email`）如需基于其他字段（如 `report_date + email_to`）计算幂等键，可以在 Skill 函数内部返回 `SkillResult(idempotency_override=...)`，`SkillExecutor` 检测到后以此值替代默认 key 写入数据库：

```python
# comm.send_email 示例
class SendEmailSkill:
    def execute(self, params: dict) -> SkillResult:
        # 自定义幂等键：report_date + email_to
        custom_key = hashlib.md5(
            f"report_email:{params['report_date']}:{params.get('to', '')}".encode()
        ).hexdigest()[:16]
        # ... 实际发邮件逻辑 ...
        return SkillResult(success=True, idempotency_override=custom_key, ...)
```

**DB 约束**：`skill_executions.idempotency_key VARCHAR(32) UNIQUE`（M1 §1.5 已建）。`SkillExecutor` 执行前先尝试 INSERT（status='running'）：
- **成功** → 正常执行，写入 output
- **唯一约束冲突** → 说明已执行过 → SELECT 历史记录，返回 `SkillResult(success=True, replayed=True, data=历史data)`

**强制必加 Skill 清单**（P0-4 由 software-architect 联合 PM 决议）：

| Skill | 副作用 | 不加的后果 |
|-------|--------|-----------|
| `comm.send_email` | 发送邮件 | 重复发邮件 = **生产事故** |
| `report.generate_markdown` | 写 Markdown 文件 | 报告覆盖、内容拼接错乱 |
| `data.refresh_stock_info` | 写 stock_info 表 | 重复刷新浪费 API 配额 |
| `memory.store_run` | 写 agent_runs | UNIQUE 冲突但仍是脏写 |
| `memory.store_reflection` | 写 reflections | 同上 |
| `quant.screening_pipeline` | 嵌套调用多个 Skill | 内层子 Skill 已幂等，pipeline 自身依赖外层 |

**仅靠 L1 缓存的纯查询 Skill**（无需 idempotency_key）：
`data.fetch_*` 全系列、`quant.calculate_factors`（纯计算）、`quant.factor_ranking`（纯计算）、`quant.hard_filter`（纯计算）。

**TTL 与失效**：幂等键**不设 TTL**——一旦写入即永久有效（DB UNIQUE 强制）。如需"重新执行"，调用方必须传**新 run_id**。

### 4.3 Skill 目录组织与脚本路由规则

每个 Skill 在 `backend/skills/{category}/` 下自包含一个目录，结构统一：

```
backend/skills/data/fetch_kline/
├── SKILL.md              ← Skill 元数据描述（YAML frontmatter + 说明）
├── scripts/
│   ├── fetch_kline.py    ← 主实现
│   └── fetch_kline_test.py
└── references/           ← 可选：参考文档
    └── api_notes.md
```

**SKILL.md 格式**（参考 WorkBuddy SKILL.md + YAML frontmatter）：

```markdown
---
name: data.fetch_kline
description: 获取指定股票的日K线数据
category: data
version: 1.0.0
timeout_seconds: 10
execution_mode: sync
cache_ttl_seconds: 3600
input_schema:
  stock_code: {type: string, description: "6位股票代码"}
  days: {type: integer, default: 60, description: "最近N个交易日"}
output_schema:
  klines: {type: array, description: "K线数据列表"}
---
```

**按问题类型路由**（参考 WorkBuddy a-share-data 的脚本组织方式）：

一个 Data Skill 应当拆分为多个小脚本，而非一个大脚本处理所有场景：

```
backend/skills/data/                  backend/skills/quant/
├── fetch_kline/scripts/              ├── screening/scripts/
│   ├── fetch_realtime.py    ← 实时   │   ├── hard_filter.py  ← 硬过滤
│   ├── fetch_history.py     ← 历史   │   ├── factor_score.py ← 因子评分
│   └── fetch_technical.py   ← 技术   │   └── master_score.py ← 大师评分
└── fetch_fundamentals/               └── icir/scripts/
    └── scripts/                          └── calc_icir.py
        ├── fetch_income.py    ← 利润表
        ├── fetch_balance.py   ← 资产负债表
        └── fetch_cashflow.py  ← 现金流
```

**路由规则**（在 SKILL.md 中用 sections 标注）：

```markdown
## 路由规则

按用户问题类型选脚本：
- `fetch_realtime.py`：实时价格、指数、北向资金、龙虎榜、涨跌停
- `fetch_history.py`：历史K线、财务数据、分红记录
- `fetch_technical.py`：MA/MACD/KDJ/RSI/BOLL 等技术指标
```

`asyncio.to_thread` 默认使用全局 `ThreadPoolExecutor`（Python 3.8+ 默认 `max_workers=min(32, os.cpu_count()+4)`），**对单用户场景过大**。自管线程池：

```python
# backend/skills/engine.py
from concurrent.futures import ThreadPoolExecutor
import os

# → P0-1 由 software-architect 于 2026-06-07 补强：自管 + 显式 max_workers
# 默认 8（覆盖单用户 + LangGraph 节点 + SSE 推送），Phase 2+ 可上调
SKILL_THREAD_POOL_SIZE = int(os.getenv("SKILL_THREAD_POOL_SIZE", "8"))
_skill_executor_pool = ThreadPoolExecutor(
    max_workers=SKILL_THREAD_POOL_SIZE,
    thread_name_prefix="skill-worker",
)

class SkillExecutor:
    async def execute(self, ...):
        if wrapper.schema.execution_mode == "sync":
            loop = asyncio.get_running_loop()
            # 替换 asyncio.to_thread 为自管 pool
            return await asyncio.wait_for(
                loop.run_in_executor(_skill_executor_pool, _sync_call),
                timeout=wrapper.schema.timeout_seconds,
            )
```

**为什么不用 default executor**：默认池过大，且当 Skill 内部有阻塞 IO 时可能同时启动 30+ 线程，拖垮整个 FastAPI 进程。**自管池 + 显式 size + thread_name 便于 profiling**。

**优雅关闭**：FastAPI lifespan 中 `_skill_executor_pool.shutdown(wait=True, cancel_futures=False)`。

### 4.4 批量数据处理规范

当 Skill 需批量处理多只股票（如刷新全市场 K 线、批量查基本面），参考 WorkBuddy a-share-data 的批量模式：

```python
# backend/skills/data/fetch_universe.py
import asyncio

MAX_WORKERS = 8  # 默认并发数，与环境变量 SKILL_THREAD_POOL_SIZE 一致

async def batch_fetch(stock_codes: list[str]) -> dict:
    """
    批量拉取数据。

    规范:
    - max_workers=8~12, 默认 8（单用户场景足够）
    - 每只股票独立异常捕获，失败不阻断整批
    - 结果包含: 样本数、成功率、总耗时、失败代码清单
    """
    semaphore = asyncio.Semaphore(MAX_WORKERS)

    async def fetch_one(code: str) -> dict:
        async with semaphore:
            try:
                data = await fetch_single_stock(code)
                return {"code": code, "success": True, "data": data}
            except Exception as e:
                return {"code": code, "success": False, "error": str(e)}

    start = time.time()
    results = await asyncio.gather(*[fetch_one(c) for c in stock_codes])

    success = [r for r in results if r["success"]]
    failed = [r for r in results if not r["success"]]
    elapsed = time.time() - start

    return {
        "total": len(stock_codes),
        "success_count": len(success),
        "failed_count": len(failed),
        "failed_codes": [r["code"] for r in failed],
        "success_rate": len(success) / len(stock_codes) if stock_codes else 0,
        "elapsed_seconds": round(elapsed, 2),
        "results": success,
    }
```

**必须包含的输出字段**（供前端展示失败告警）：

| 字段 | 类型 | 说明 |
|------|------|------|
| `total` | int | 总处理数 |
| `success_count` | int | 成功数 |
| `failed_count` | int | 失败数 |
| `failed_codes` | list[str] | 失败股票代码清单（前端渲染告警条："3 只股票因数据缺失跳过"） |
| `success_rate` | float | 成功率 |
| `elapsed_seconds` | float | 总耗时 |

---

## 5. 缓存策略

| 层次 | 实现 | 用途 |
|------|------|------|
| L1 | 进程内存 OrderedDict (LRU) + TTL + max_size | 快速，无网络开销 |
| L2 | Redis（MVP 阶段不用） | 多进程或未来扩展 |

**L1 实现细节**（P0-2 + P0-3 由 software-architect 于 2026-06-07 补强）：

```python
# backend/skills/cache.py
import json
import hashlib
from collections import OrderedDict
from threading import Lock
from typing import Any

class LRUCache:
    """线程安全 LRU + TTL"""
    def __init__(self, max_size: int = 512, default_ttl: int = 60):
        self._max_size = max_size
        self._default_ttl = default_ttl
        self._data: OrderedDict[str, tuple[float, Any]] = OrderedDict()
        self._lock = Lock()

    def get(self, key: str) -> Any | None:
        import time
        with self._lock:
            if key not in self._data:
                return None
            expires_at, value = self._data[key]
            if time.time() > expires_at:
                del self._data[key]
                return None
            # LRU: 移到末尾
            self._data.move_to_end(key)
            return value

    def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        import time
        with self._lock:
            expires_at = time.time() + (ttl or self._default_ttl)
            if key in self._data:
                self._data.move_to_end(key)
            self._data[key] = (expires_at, value)
            # LRU 淘汰
            while len(self._data) > self._max_size:
                self._data.popitem(last=False)

# 全局 L1 缓存
_L1_CACHE = LRUCache(max_size=512, default_ttl=60)
```

> **设计约束**：L1 缓存（LRUCache）的 `threading.Lock` **仅在同步路径（由 ThreadPoolExecutor 保证）中访问**。async 路径（如纯异步 Skill）应使用独立缓存实例或 `asyncio.Lock`。跨线程+async 混用同一锁可能导致死锁。

**缓存 Key 设计**（P0-2 防御性序列化 + 2026-06-07 补强 C-9 统一 Config.to_json_safe）：

```python
def make_cache_key(skill_name: str, normalized_params: dict) -> str:
    # → P0-2 + C-9：调用 Config.to_json_safe 统一处理 datetime/Decimal/UUID/date
    #   再用 json.dumps(sort_keys=True, ensure_ascii=False)
    safe_params = Config.to_json_safe(normalized_params)
    payload = json.dumps(safe_params, sort_keys=True, ensure_ascii=False, default=str)
    digest = hashlib.md5(payload.encode("utf-8")).hexdigest()
    return f"skill:{skill_name}:{digest}"
```

> **为什么 default=str**：`DataSkill.normalize_params` 可能把 `datetime.date(2026,6,7)` 转出来（旧版 `fetch_kline(days=60)` → `start_date=date(2026,4,8)`），裸 `json.dumps` 抛 `TypeError`。`default=str` 兜底为 ISO 字符串，跨类型稳定。

**缓存失效（2026-06-07 补强 F-9 + P2-12）**：采用 **TTL + 懒删除**策略，不使用索引。每个缓存条目记录 `category` 和过期时间，获取时先判过期；数据更新 Skill 执行后，直接调用 `cache.invalidate_category(category)` 函数（封装在 `SkillExecutor` 中），该函数扫描内存字典并删除同 category 的键（数据量小，5000 键以内，性能可接受）。**不依赖数据库索引**。

**缓存 category 粒度（2026-06-07 决议 P2-12）**：使用 Skill 命名空间的第一级作为 category（`data`, `quant`, `report`, `communication`, `memory`），`invalidate_category("data")` 使所有 `data.*` Skill 缓存失效。未来如需细粒度（如只刷新 K 线缓存）可扩展为 `invalidate_category("data.kline")`，但不属于 MVP 范围。一级粒度在 MVP 阶段足够。

**参数标准化**: 每个 Data Skill 在注册时可提供 `normalize_params` 函数，引擎在计算缓存 key 前调用。例如 `fetch_kline(days=60)` 标准化为 `fetch_kline(start_date='2026-04-08', end_date='2026-06-07')`。

---

## 6. Skill 分类与清单

### Data Skills

封装所有 `providers/sources/` 的原始数据获取。不做任何计算，只拿数据。

| Skill 名称 | 功能 | 主要参数 | 复用 |
|------------|------|----------|------|
| `data.fetch_kline` | 日 K 线 | stock_code, days/start_date/end_date, freq='D' | `providers/market_data.py` |
| `data.fetch_fundamentals` | 基本面 | stock_code, fields=['pe','pb','roe',...] | `providers/market_data.py` |
| `data.fetch_index` | 指数行情 | index_code='000001.SH', days=60 | `providers/market_data.py` |
| `data.fetch_money_flow` | 资金流向 | stock_code, days=5 | `providers/sources/eastmoney.py` |
| `data.fetch_sectors` | 行业板块 | date | `providers/sources/board_rank.py` |
| `data.fetch_hot_stocks` | 热榜 | limit=50 | `providers/sources/hot_rank.py` |
| `data.fetch_dragon_tiger` | 龙虎榜 | date | `providers/sources/lhb.py` |
| `data.refresh_stock_info` | 刷新股票基础信息 | stock_codes | `services/stock_populator.py` |
| `data.check_data_freshness` | 检查数据新鲜度 | date | `services/data_bus.py` |
| `data.fetch_universe_snapshot` | 全市场快照 | date, fields | 新增聚合 Skill，合并多个源 |

### Quant Skills

封装因子计算、筛选、打分、辩论、风险评估。

| Skill 名称 | 功能 | 主要参数 | 复用 |
|------------|------|----------|------|
| `quant.calculate_factors` | 多因子值 | stock_code, factor_list | `services/factor_farm.py` |
| `quant.hard_filter` | 18 条件硬过滤 | universe | `services/hard_filter.py` |
| `quant.factor_ranking` | 因子排名 | universe, factor_name | `services/factor_farm.py` |
| `quant.master_score` | 大师风格评分 | stock_code, master_name; 输出含 `style_diversity_score` | `services/master_agents.py` |
| `quant.debate_analysis` | LLM 多空辩论 | stock_code, context | `services/debate_engine.py` |
| `quant.risk_score` | 风险评分 | stock_code | `services/risk_engine.py` |
| `quant.market_regime` | 市场状态诊断 | date | `services/market_perception.py` |
| `quant.screening_pipeline` | 完整选股漏斗 | style, max_candidates=10 | `services/screening/pipeline.py` |

#### §6.0.1 `quant.screening_pipeline` 内部调用链（P0 补强）

`screening_pipeline` 是选股的核心编排 Skill，**内部按顺序调用其他 Quant Skill**，自身不包含业务逻辑。调用链如下：

```
screening_pipeline(universe, style, max_candidates=10):
  ┌─────────────────────────────────────────────────────────────────────┐
  │ 1. quant.hard_filter(universe, style)                              │
  │    → candidates (~200只，按风格过滤 + 负面排除)                     │
  │                                                                     │
  │ 2. quant.calculate_factors(candidates)                             │
  │    → factor_scores: {stock_code: {PTV: 0.12, LTR: -0.05, ...}}    │
  │                                                                     │
  │ 3. quant.factor_ranking(factor_scores)                             │
  │    → ranked_candidates: 按综合因子分排序的候选列表                  │
  │                                                                     │
  │ 4. quant.master_score(top_candidates, master_names=ALL)            │
  │    → master_scores: {stock_code: {cathie_wood: 65, ...}}           │
  │                                                                     │
  │ 5. 综合排序（本步骤是 pipeline 内部逻辑，非独立 Skill）            │
  │    → composite_score = 0.4 × factor_zscore + 0.4 × master_norm    │
  │                      + 0.2 × risk_adjustment                       │
  │    → 行业发散约束（Q7.4 补强）                                    │
  │    → top N = sorted by composite_score, take max_candidates        │
  │                                                                     │
  │ 输出: {candidate_pool: [stock_code, ...],                          │
  │        composite_scores: {stock_code: score},                      │
  │        factor_scores: {...}, master_scores: {...},                 │
  │        industry_distribution: {industry: count, ...},              │
  │        market_regime_gate: {passed, reason?}}                      │
  └─────────────────────────────────────────────────────────────────────┘
```

#### §6.0.2 行业发散约束（Q7.4 补强，2026-06-07）

**目标**：避免 top 10 中 5 只都是"新能源"导致组合过度集中。

**算法**（pipeline 步骤 5 内部逻辑）：

```python
def apply_industry_diversification(
    ranked_candidates: list[dict],  # [{stock_code, composite_score, industry}, ...]
    max_per_industry: int = 3,       # MVP 硬编码，Phase 2 可放 config.yaml
    max_candidates: int = 10,
) -> list[dict]:
    """贪心选股：每个行业最多 max_per_industry 只，按 composite_score 降序逐个加入。
    
    跳过但保留：被跳过的候选记录在 alternative_pool 中，供前端"备选"标签展示。
    """
    selected = []
    industry_count = {}
    alternative_pool = []
    
    for cand in ranked_candidates:
        if len(selected) >= max_candidates:
            break
        industry = cand.get("industry", "unknown")
        if industry_count.get(industry, 0) < max_per_industry:
            selected.append(cand)
            industry_count[industry] = industry_count.get(industry, 0) + 1
        else:
            alternative_pool.append(cand)
    
    return {
        "selected": selected,
        "alternative_pool": alternative_pool,
        "industry_distribution": industry_count,
    }
```

**与 hard_filter 的边界**：`hard_filter` 已经按"风格"过滤（价值/成长/质量/趋势/特殊），这里再按"行业"打散。**两层职责分离**：风格过滤是"我想要什么类型的股票"，行业发散是"我不要所有鸡蛋在一个篮子"。

**前端展示**：
- 推荐卡片上显示"行业分布：新能源 2 / 白酒 1 / 银行 1"
- `alternative_pool` 折叠面板："3 只因行业集中度被替换的备选"
- 配置项 `max_per_industry` 暂不放 config.yaml（MVP 硬编码 3），Phase 2 评估放 user_prefs

#### §6.0.3 市场状态门控（Q7.5 补强，2026-06-07）

**目标**：极端行情（如 fear_index > 80）暂停选股并明确提示用户。

**触发条件**（`quant.market_regime` Skill 输出 + 复合门控）：

| 条件 | 阈值 | 行为 |
|------|------|------|
| `fear_index` (VIX 代理) | `> 80` | 暂停选股，提示"市场情绪极度恐慌，建议观望" |
| `regime` | `== "panic"` | 同上 |
| `risk_level` | `== "extreme"` | 暂停选股，提示"市场风险等级为极端，建议减仓" |
| `market_state.industries_limit_down_ratio` | `> 0.3` | 暂停选股，提示"超 30% 行业跌停，流动性枯竭" |

**实现位置**：`screening_pipeline` 步骤 1 之前，先调 `quant.market_regime` 检查门控：

```python
def market_regime_gate(market_state: dict) -> dict:
    """市场状态门控：极端行情下暂停选股。
    
    返回: {passed: bool, reason?: str, severity: "info"|"warning"|"block"}
    - passed=True, severity="info": 正常放行
    - passed=True, severity="warning": 放行但前端顶部黄色提示条
    - passed=False, severity="block": 阻塞，screening_pipeline 直接返回空
    """
    fear = market_state.get("fear_index", 0)
    if fear > 80:
        return {"passed": False, "severity": "block", "reason": f"市场恐慌指数{fear} > 80，建议观望"}
    if fear > 60:
        return {"passed": True, "severity": "warning", "reason": f"市场恐慌指数{fear}较高，建议控制仓位"}
    return {"passed": True, "severity": "info"}
```

**用户体感**：
- **block 级别**：screening_pipeline 不跑，summarize 节点明确告诉用户"今日市场极度恐慌，未执行选股"，推荐"明日再观察"
- **warning 级别**：screening_pipeline 继续，但前端顶部显示"⚠️ 市场情绪偏紧，仓位建议 ≤ 50%"，推荐卡片有"保守提示"标签

**为什么是门控而不是熔断**：熔断是"系统强制停止"，门控是"提示用户后让用户决定"。个人用户场景下，用户应该看到原因后选择继续或放弃，而不是被系统拒绝。**前端 ConfirmationCard 提供"继续"和"放弃"两个选项**。

**与 Reflection Agent 的联动**：每次触发门控，Reflection Agent 在下次复盘时把"门控触发频率"作为一项指标，统计一个月内有多少天被门控。

#### §6.0.4 ICIR 衰减监测 + 因子权重动态调整（Q7.6 补强，2026-06-07）

**背景**：ICIR 是历史数据计算的，市场风格会切换（2020 成长股跑赢 → 2022 价值股跑赢）。旧因子持续占权重会让选股结果失去时效性。

**监测机制**（每日 `screening_pipeline` 启动时跑）：

```python
def monitor_factor_icir_decay(
    factor_library: dict,  # {factor_name: {current_icir, peak_icir, decay_date, history: [...]}}
    decay_threshold: float = 0.5,  # ICIR 较峰值下降 50% 视为衰减
    min_history_days: int = 60,
) -> dict:
    """监测因子 ICIR 衰减，输出权重调整建议。
    
    返回: {
        "healthy_factors": [...],     # 正常因子，权重 1.0
        "decayed_factors": [...],     # 衰减因子，权重 0.3
        "dead_factors": [...],        # 失效因子（连续 30 天 ICIR < 0），权重 0
        "new_factors": [...],         # 新因子（history < 60d），权重 0.5 保守起见
    }
    """
    ...
```

**衰减判定规则**：

| 状态 | 条件 | 权重 |
|------|------|------|
| `healthy` | `current_icir >= peak_icir * 0.5` | 1.0 |
| `decayed` | `peak_icir * 0.3 <= current_icir < peak_icir * 0.5` | 0.3 |
| `dead` | `current_icir < 0` 连续 30 天 | 0.0（从综合排序中移除） |
| `new` | history < 60 天 | 0.5（数据不足，保守起见） |

**权重应用到综合排序**：

`compute_composite_score` 的 `factor_zscore` 计算中：

```python
# 原算法：w_i = |ICIR_i|（等 ICIR 加权）
# 新算法：w_i = |ICIR_i| × factor_status_weight（衰减因子再降权）
factor_status_weight = {
    "healthy": 1.0,
    "decayed": 0.3,
    "dead": 0.0,    # 彻底不参与
    "new": 0.5,
}[factor_status]
```

**事件记录**：

每次监测结果写入 `factor_ic_history` 表 + `trading-skills/.learnings/FACTOR_ERRORS.md`：

```markdown
## 2026-06-07 因子权重调整

### 衰减因子（权重从 1.0 → 0.3）
- `MOM_60D`：峰值 ICIR 0.45 → 当前 0.21（2026-04 起持续衰减）
- `PE_RATIO`：峰值 ICIR 0.38 → 当前 0.17（与价值股跑赢有关）

### 失效因子（权重 0）
- `ROA`：连续 45 天 ICIR < 0

### 新增因子
- `RATING_UPGRADE`：history 25 天，权重 0.5
```

**前端展示**：
- 选股报告末尾"因子健康度"小节：列出 33 个因子的健康状态
- 衰减/失效因子带"⚠️"图标，hover 显示 ICIR 历史曲线
- "查看因子库健康详情"链接到 Dashboard 的 Factor Health 面板（Phase 2）

**重算频率**：每次 `screening_pipeline` 启动时跑（每日 1 次），耗时 < 1s。

**与 M2 §10 决策的更新**：原"每次日频分析时重算"扩展为"重算 + 衰减监测 + 权重动态调整"。

**综合排序算法（§6.0.1 步骤 5 详细定义）**：

这是选股 Pipeline 的"最后一公里"——将因子分、大师分、风险调整合成为最终排序。

```python
def compute_composite_score(factor_scores: dict, master_scores: dict, risk_score: dict) -> float:
    """综合评分算法

    权重分配：
    - 因子分 40%：截面 z-score 标准化后 ICIR 加权合成
    - 大师分 40%：所有大师评分归一化后等权均值
    - 风险调整 20%：risk_score 越低（越安全）加分越多
    """
    # 1. 因子分 → 截面 z-score → ICIR 加权
    #    factor_zscore = Σ(w_i × zscore(factor_i)) / Σ(w_i)
    #    w_i = |ICIR_i| （ICIR 从 factor_farm.library 读取，无 ICIR 时等权）
    #    zscore 在候选池内截面标准化（非时间序列）

    # 2. 大师分 → 归一化到 [0,1] → 等权均值
    #    master_norm = mean(master_score / 100 for each master)
    #    同时计算 style_diversity_score（见下）

    # 3. 风险调整 → risk_score 越低越安全
    #    risk_adjustment = 1 - (risk_score / 100)  # risk_score 0-100，0=最安全

    # 4. 综合
    composite = 0.4 * factor_zscore + 0.4 * master_norm + 0.2 * risk_adjustment
    return composite
```

**`style_diversity_score` 说明（P1 补强）**：

`quant.master_score` 输出中包含 `style_diversity_score`，衡量 N 个大师评分的分散度：

```python
def compute_style_diversity(master_scores: dict[str, float]) -> float:
    """大师评分分散度

    高分散度 → 多风格视角验证通过（价值+成长+动量同时看好）→ 更可信
    低分散度 → 所有大师看同一面（可能只是某个因子主导）→ 需警惕
    """
    scores = list(master_scores.values())
    if len(scores) < 2:
        return 0.0
    # 标准差 / 均值（变异系数），归一化到 [0, 1]
    mean_s = sum(scores) / len(scores)
    if mean_s == 0:
        return 0.0
    std_s = (sum((s - mean_s) ** 2 for s in scores) / len(scores)) ** 0.5
    cv = std_s / mean_s  # 变异系数
    # cv > 0.5 视为高分散度（归一化为 1.0），cv < 0.1 视为低分散度（归一化为 0.0）
    return min(1.0, max(0.0, (cv - 0.1) / 0.4))
```

**前端展示建议**：`style_diversity_score > 0.6` 时在推荐卡片上显示"多风格验证"标签；`< 0.3` 时显示"单一视角"警告。
```

**因子截面标准化说明**：

`quant.calculate_factors` 计算的是每只股票的原始因子值（如 PTV=0.12, LTR=-0.05）。这些值不能直接比较或加总——不同因子的量纲和分布不同。`quant.factor_ranking` 负责在候选池内做截面标准化：

1. 对每个因子，在候选池内计算 z-score：`z_i = (x_i - mean) / std`
2. 按 ICIR 加权合成：`factor_composite = Σ(|ICIR_k| × z_k) / Σ(|ICIR_k|)`
3. 无 ICIR 数据的因子默认权重 1.0（等权）

**为什么不在 `calculate_factors` 内做标准化**：`calculate_factors` 是单股计算，不知道候选池的分布。标准化必须在池内截面进行，由 `factor_ranking` 或 `screening_pipeline` 在拿到全部候选的因子值后统一处理。

**与现有代码的衔接**：`services/factor_farm.py` 的 `FactorFarm.compute_all_factors()` 返回原始因子值，`build_factor_score()` 当前硬编码返回 50.0。改造路径：
1. MVP：`screening_pipeline` 内部实现截面标准化 + ICIR 加权（复用 `FactorFarm.compute_all_factors` 的原始输出）
2. Phase 2：将标准化逻辑下沉到 `factor_ranking` Skill，`FactorFarm.build_factor_score()` 改为调用 `factor_ranking`

**Quant Skill 硬约束**：不得直接访问 DB。所有数据必须通过 Data Skill 预加载后传入。注册时校验参数类型，拒绝含 `db_session` 的注册。

### Report Skills

| Skill 名称 | 功能 | 主要参数 | 说明 |
|------------|------|----------|------|
| `report.generate_markdown` | Markdown 报告 | recommendations, market_state, date | MVP 只做这一个 |
| `report.generate_html` | HTML 报告 | markdown, css_theme | Phase 4+ |
| `report.generate_pdf` | PDF 报告 | html | Phase 4+ |

### Communication Skills

| Skill 名称 | 功能 | 主要参数 | 说明 |
|------------|------|----------|------|
| `comm.send_email` | 发送邮件 | to, subject, html_body | 内部 Markdown→HTML 转换 |

### Memory Skills

| Skill 名称 | 功能 | 主要参数 |
|------------|------|----------|
| `memory.store_run` | 存储运行记录 | run_id, goal, result |
| `memory.store_reflection` | 存储复盘结果 | date, predictions, actuals |
| `memory.retrieve_predictions` | 检索历史预测 | date_range |
| `memory.get_similar_market` | 查找相似市场 | current_regime, top_k=3 |

### 6.x 老命名空间 → 新命名空间映射表（P1 由 software-architect/PM 于 2026-06-07 补强 + 2026-06-07 补强 F-14）

**背景**：原 23+ 个老 SKILL.md 命名空间混乱（驼峰、动作名词、混合前缀），Agent 装饰器注册期一旦失忆，LLM 调用 100% 失败且报错对用户不可读。

**映射表**（30 天兼容期，期内别名降级 + 启动 warn）：

| 老名 (`deprecated_aliases`) | 新名（canonical） | category 变化 | 备注 |
|------------------------------|-------------------|---------------|------|
| `livermore` | `quant.master_score` | - | 参数 `master='livermore'` |
| `wells_fargo` | `quant.master_score` | - | 参数 `master='wells_fargo'` |
| `lynch` | `quant.master_score` | - | 参数 `master='lynch'` |
| `buffett` | `quant.master_score` | - | 参数 `master='buffett'` |
| `getKline` | `data.fetch_kline` | - | |
| `getFundamentals` | `data.fetch_fundamentals` | - | |
| `getIndex` | `data.fetch_index` | - | |
| `getMoneyFlow` | `data.fetch_money_flow` | - | |
| `getSectors` | `data.fetch_sectors` | - | |
| `getHotStocks` | `data.fetch_hot_stocks` | - | |
| `getDragonTiger` | `data.fetch_dragon_tiger` | - | |
| `fetchKLine` | `data.fetch_kline` | - | 与 `getKline` 同名（大小写） |
| `runScreening` | `quant.screening_pipeline` | - | |
| `calculateFactor` | `quant.calculate_factors` | - | |
| `hardFilter` | `quant.hard_filter` | - | |
| `factorRanking` | `quant.factor_ranking` | - | |
| `masterScore` | `quant.master_score` | - | |
| `debateAnalysis` | `quant.debate_analysis` | - | |
| `riskScore` | `quant.risk_score` | - | |
| `marketRegime` | `quant.market_regime` | - | |
| `generateMarkdown` | `report.generate_markdown` | - | |
| `sendEmail` | `comm.send_email` | - | |
| `storeRun` | `memory.store_run` | - | |
| `getSimilarMarket` | `memory.get_similar_market` | - | |
| `refreshStockInfo` | `data.refresh_stock_info` | - | |

**别名存储位置（2026-06-07 补强 F-14）**：

别名映射**全部集中在 `backend/skills/aliases.py` 文件**中的 `ALIAS_MAP` 字典常量，**随代码仓库版本管理**（不在数据库，避免数据库迁移时丢失映射）。所有相关文档（M2 §6.x、M3 §3.4 步骤类型、M4 §8 计划示例）均指向该文件：

```python
# backend/skills/aliases.py
"""老命名空间 → 新命名空间 映射表（单一信源）。

新增/删除别名时，只需修改本文件，SkillRegistry 启动时自动加载。
"""
ALIAS_MAP: dict[str, str] = {
    "livermore": "quant.master_score",
    "wells_fargo": "quant.master_score",
    # ... 完整列表见 M2 §6.x
}
```

> **为什么不在数据库**：映射表与代码版本强绑定（部署时同步），用代码常量更可靠；数据库版本在迁移时容易遗漏，且启动期加载失败会导致所有别名降级。

```python
# backend/skills/registry.py
class SkillRegistry:
    def register(self, name, deprecated_aliases=None, **kwargs):
        ...
        if deprecated_aliases:
            for alias in deprecated_aliases:
                # 双向绑定：alias → 新 Skill
                self._alias_map[alias] = name
            # → 启动时统一 warn 一次（不打每条调用）
            import logging
            logging.getLogger(__name__).warning(
                f"Skill '{name}' registered with {len(deprecated_aliases)} deprecated aliases: "
                f"{deprecated_aliases}. Aliases will be REMOVED in 30 days."
            )

    def resolve(self, name: str) -> str:
        if name in self._alias_map:
            return self._alias_map[name]
        return name
```

**降级路径**（30 天后）：
1. **Day 0-7**：完全透传，alias 调用与新名等价，仅启动 warn。
2. **Day 8-21**：alias 调用记录 `DeprecationWarning` 日志，调用方监控能看见。
3. **Day 22-30**：alias 调用返回 `SkillExecutionError("alias_removed_use_<new_name>")`，明确指引。
4. **Day 30+**：`_alias_map` 在 `__init__` 中 raise `RuntimeError("deprecated aliases removed; update caller")`，**配置开关 `ENABLE_DEPRECATED_ALIASES=true` 保留 2 minor 版本逃生**（如 6-8 周）。

**M2 装饰器示例**：
```python
@registry.register(
    name="data.fetch_kline",
    deprecated_aliases=["getKline", "fetchKLine"],
    description="获取日K线",
    ...
)
```

---

## 7. 与 Agent 的集成

- Master Agent 通过 LangGraph 的 Tool 绑定获取 Skill 列表
- Master Agent 生成计划时，`type: "skill"` 的步骤指定 `target: skill_name`
- `skill_executor` 节点在图中调用 `SkillExecutor.execute()`
- 结果存入 `step_results[step_id]`，返回给 Master Agent 做下一轮推理

---

## 8. 可观测性

每个 Skill 调用记录：
- `run_id`, `skill_name`, `input_params`（摘要）
- `success`, `latency_ms`, `tokens_used`, `cache_hit`
- 写入 `skill_executions` 表，同时输出结构化日志

---

## 9. 迁移策略

| 顺序 | 内容 | 工作量 |
|------|------|--------|
| 1 | 定义 `SkillSchema` + `SkillRegistry` + `SkillExecutor` | 纯数据结构，无外部依赖 |
| 2 | 实现 3-4 个 Data Skill（K线、基本面、指数、快照） | 包装现有 providers |
| 3 | 实现 `quant.hard_filter` + `quant.master_score` | 包装现有 services |
| 4 | 实现 `report.generate_markdown` | 新增，Jinja2 模板 |
| 5 | 实现 `comm.send_email` | 新增，smtplib |
| 6 | 实现 Memory Skills | 操作 agent_runs 表 |
| 7 | 集成测试：Data → Quant → Report 调用链 | 验证全流程 |

---

## 10. 设计决策记录

| 决策 | 结论 | 理由 |
|------|------|------|
| execution_mode 区分 | sync 用 to_thread，async 直接 await | 解决同步阻塞 Skill 超时无法终止线程的问题 |
| 缓存 key 标准化 | Skill 内部提供 `normalize_params`，引擎不感知 | 语义等价的参数产生相同 key |
| Quant Skill 禁 DB | 强制 Data Skill 预加载 | 测试只需 mock Data Skill，不依赖数据库 |
| 并发上限 | 由 `config.max_candidates` 控制（默认 10） | 直接限制池大小，不增加额外裁剪节点 |
| 线程池自管（P0-1） | `_skill_executor_pool = ThreadPoolExecutor(max_workers=8)` | 替代默认全局池，避免阻塞 IO 时启动 30+ 线程拖垮 FastAPI |
| 缓存防御性序列化（P0-2） | `json.dumps(default=str)` 兜底 datetime/Decimal/UUID | 避免跨类型参数 cache key 计算崩溃 |
| L1 缓存 LRU（P0-3） | `OrderedDict + max_size=512` | 防止长跑进程内存膨胀，TTL+LRU 双保险 |
| 幂等键（P0-4） | `md5(run_id+step_id+normalized_params)`，DB UNIQUE | 强制覆盖含副作用 Skill，禁隐式从 contextvar 读 run_id |
| 命名空间映射（P1） | 30 天兼容期 + 启动 warn + 2 minor 版本逃生开关 | 必加的迁移平滑度，杜绝 LLM 100% 失败 |
| ICIR 重算频率 | 每次日频分析时重算（读 factor_ic_history 表最近 60 日，耗时 < 1s） | 日频场景下，按天重算成本极低；事件记录到 trading-skills/.learnings/FACTOR_ERRORS.md |
| 因子正交化 | MVP 不做 PCA 正交化；用 style_diversity_score 做后置去重 | 33 个因子的相关性矩阵在 factor_farm.library 维护（仅监控，不参与评分） |

---

## 11. Phase 2 任务卡片

| 任务 ID | 内容 | 产出 | 依赖 |
|---------|------|------|------|
| T2.1 | SkillSchema + SkillRegistry + SkillExecutor | 执行引擎核心 | M1 |
| T2.2a | Market Perception + Screening Pipeline Skills | `quant.market_regime`, `quant.screening_pipeline` | T2.1 |
| T2.2b | 单股评分 + 辩论 Skills | `quant.master_score`, `quant.debate_analysis` | T2.1 |
| T2.3 | Data Skills (9 个) | 10+ Data Skill 实现 | T2.1 |
| T2.4 | `report.generate_markdown` | Markdown 报告渲染 | T2.2a, T2.2b |
| T2.5 | `comm.send_email` | 邮件发送 | T2.4 |
| T2.6 | Memory Skills (4 个) | 运行记录 + 复盘存储 | M1 (models) |
| T2.7 | 集成测试 | Data→Quant→Report 链路 | T2.2 ~ T2.5 |

---

### 附录 A：P0/P1 量化优化方案（整合自 optimizations/P0-P1-*.md）

**见独立文件 `docs/architecture/optimizations/P0-P1-factor-and-selection-optimizations.md`，以下为摘要：**

| 优先级 | 优化 | 核心动作 | 预计工时 |
|--------|------|---------|---------|
| P0-1 | Winsorize + 行业中性化 + 缺失填充 | 新增 `factor_normalizer.py`，对因子值做 1%/99% 缩尾 + 行业中位数填缺失 | 6h |
| P0-2 | E/P 替代 PE 倒数 + 对数收益率 | 统一因子定义：`calc_ep_ratio()` 和 `calc_log_return()` | 4h |
| P0-3 | 硬过滤精简（18→6条件）+ 自适应截断 | 仅保留排除性条件，质量条件转为评分因子 | 3h |
| P1-4 | ICIR 加权替代等权 | 新增 `icir_calculator.py`，60日滚动 Rank IC | 8h |
| P1-5 | 分风格推荐（价值/成长/质量/趋势/特殊） | 5 组大师独立评分，用户可选风格 | 6h |
| P1-7 | 用户黑名单 + 可配置过滤 | `user_blacklist` 表 + API + 过滤集成 | 4h |

**依赖关系**: T2.4 → T2.2a, T2.5 → T2.4, T2.7 → 全部
