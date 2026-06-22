# Module 1: 基础设施与配置系统 — 详细设计

**所属阶段**: Phase 1  
**负责模块**: `backend/shared/`  
**依赖**: 无外部依赖  
**目标**: 为所有后续模块提供统一的配置、日志、数据库会话、错误处理基类  
**状态**: Draft | **日期**: 2026-06-07

> ⚠️ **TARGET ARCHITECTURE** — 本文档描述目标架构，非当前实现。当前实际架构参见 `docs/ACTUAL_ARCHITECTURE.md`。

---

## 1.1 设计目标

- 所有环境相关值通过 `.env` + `config.yaml` 管理，绝不硬编码
- 日志系统从第一天就结构化，方便追踪 Agent 调用链
- 数据库访问层极其轻量，仅提供 session 工厂 + 简单 CRUD 基类
- 所有异常分类处理，区分"可恢复"和"致命"错误

---

## 1.2 文件结构

```
backend/shared/
├── __init__.py          # 统一导出
├── config.py            # Config 单例，读取 YAML + .env
├── database.py          # SQLAlchemy engine, session factory, Base
├── models.py            # 旧表（StockInfo, KlineCache 等 8+ 张核心表，保留不动）
├── models_v2.py         # 新表（2026-06-07 新增 P0-4）：agent_runs, skill_executions, skill_registry, conversation_history 等 11 张
├── exceptions.py        # 自定义异常层次
└── logging_config.py    # 结构化日志配置
```

> **为什么分两个 models 文件**（2026-06-07 决议 P0-4）：新表与旧表共享同一个 `Base`（`from .database import Base`），但旧 `models.py` 已有 `Base.metadata` 注册的 StockInfo 等表。`Base.metadata.create_all()` 是幂等的（`CREATE TABLE IF NOT EXISTS`），所以 `models_v2.py` 共享 engine 后，新旧表均可正常创建。分文件避免合并时的命名空间冲突和未来迁移复杂性。

---

## 1.3 配置系统 (`config.py`)

### 设计要点

- **单例模式**: 全局只有一个 Config 实例
- **双层优先级**: 环境变量 > YAML 文件
- **键路径转换**: `llm.temperature` → 环境变量 `LLM_TEMPERATURE`
- **类型自动推断**: 环境变量字符串 → bool/int/float/str 自动转换

### 代码

```python
import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv


class Config:
    """单例配置管理：env 覆盖 yaml 值"""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._loaded = False
        return cls._instance

    def __init__(self):
        if self._loaded:
            return
        self._loaded = True

        # 1. 加载 .env
        load_dotenv(Path(__file__).parent.parent / ".env")

        # 2. 加载 YAML
        config_path = Path(__file__).parent.parent / "config.yaml"
        with open(config_path, encoding="utf-8") as f:
            self._yaml = yaml.safe_load(f)

    def get(self, key: str, default: Any = None) -> Any:
        """获取配置值，优先从环境变量"""
        env_key = key.upper().replace(".", "_")
        env_val = os.getenv(env_key)
        if env_val is not None:
            return self._cast(env_val)

        # 降级 YAML
        keys = key.split(".")
        val = self._yaml
        for k in keys:
            if isinstance(val, dict):
                val = val.get(k)
            else:
                return default
        return val if val is not None else default

    @staticmethod
    def _cast(value: str) -> Any:
        """扩展类型推断（list/json/科学计数法）"""
        low = value.lower()
        if low in ("true", "false"):
            return low == "true"
        if low in ("null", "none"):
            return None
        # JSON 列表/对象/数字（含科学计数法）
        if value.startswith(("[", "{")) or "e" in value.lower() or "." in value:
            try:
                import json
                return json.loads(value)
            except (ValueError, json.JSONDecodeError):
                pass
        try:
            return int(value)
        except ValueError:
            pass
        try:
            return float(value)
        except ValueError:
            pass
        return value

    # → P1 由 software-architect 于 2026-06-07 补强：测试用 reset
    @classmethod
    def reset_for_test(cls):
        """测试用例间清理单例，避免配置污染"""
        cls._instance = None

    # → 2026-06-07 补强 C-9：统一序列化工具，确保 Config 与缓存 key 计算行为一致
    @staticmethod
    def to_json_safe(value: Any) -> Any:
        """递归将 datetime/Decimal/UUID/date 等不可 JSON 序列化类型转字符串。

        Skill 缓存 key 计算（make_cache_key）与 Config._cast 之外的序列化场景
        均应使用本方法，确保 key 计算跨类型稳定。
        """
        from datetime import date, datetime
        from decimal import Decimal
        from uuid import UUID

        if isinstance(value, dict):
            return {k: Config.to_json_safe(v) for k, v in value.items()}
        if isinstance(value, (list, tuple, set)):
            return [Config.to_json_safe(v) for v in value]
        if isinstance(value, (datetime, date)):
            return value.isoformat()
        if isinstance(value, Decimal):
            return str(value)
        if isinstance(value, UUID):
            return str(value)
        return value


config = Config()
```

### config.yaml 范例片段

```yaml
llm:
  provider: deepseek
  model: deepseek-chat
  temperature: 0.1

data:
  cache_ttl_minutes: 60
  primary_sources: ["tencent", "eastmoney"]

email:
  smtp_host: smtp.qq.com
  smtp_port: 465
  # 账号密码从环境变量读取: QQ_EMAIL, QQ_SMTP_PASSWORD

log:
  level: INFO
  file: logs/app.log
```

### 测试要点

| 测试项 | 期望结果 |
|--------|----------|
| `.env` 设 `LLM_TEMPERATURE=0.5`, YAML 设 `0.1` | `config.get("llm.temperature")` → `0.5` |
| `.env` 不设, YAML 设 `llm.temperature: 0.1` | `0.1` |
| `.env` 设 `DATA_CACHE_TTL_MINUTES=120` | `config.get("data.cache_ttl_minutes")` → `120` |
| 不存在的 key | `config.get("nonexistent")` → `None` |
| `config.get("nonexistent", "fallback")` | `"fallback"` |
| 环境变量 `ENABLE_FEATURE=true` → `_cast("true")` | `True` |

---

## 1.4 数据库基础 (`database.py`)

### 设计要点

- **SQLite 优先**: 个人用户场景足够, WAL 模式启用保证并发读
- **连接池**: SQLite 用 `StaticPool`, 生产用 `QueuePool`
- **Session 工厂**: `SessionLocal` 线程安全
- **依赖注入**: `get_db()` 生成器供 FastAPI Depends 使用

### 代码

```python
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, declarative_base

from .config import config

# → P0-3 由 software-architect 于 2026-06-07 补强：绝对路径 + 路径存在性兜底
_RAW_URL = config.get("database.url", "sqlite:///data/agent.db")
if _RAW_URL.startswith("sqlite:///./"):
    _REL = _RAW_URL[len("sqlite:///"):]
    DATABASE_URL = f"sqlite:///{Path(_REL).resolve()}"
else:
    DATABASE_URL = _RAW_URL

if DATABASE_URL.startswith("sqlite:///"):
    _DB_PATH = Path(DATABASE_URL[len("sqlite:///"):])
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(
    DATABASE_URL,
    # → P0-3：SQLite 必须 StaticPool（单连接复用，跨线程共享）
    poolclass=StaticPool if "sqlite" in DATABASE_URL else None,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {},
    echo=False,
    pool_pre_ping=True,
)


# SQLite 优化
@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_conn, connection_record):
    if "sqlite" in DATABASE_URL:
        cursor = dbapi_conn.cursor()
        # → P0-3 补强：4 项 PRAGMA 必备
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA foreign_keys=ON")    # FK 约束生效（依赖 P0-4 skill_executions.run_id FK）
        cursor.execute("PRAGMA busy_timeout=5000")  # 5s 锁等待，避免高频写时 SQLITE_BUSY
        cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    """依赖注入用 session 生成器"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

### 1.4.1 SQLite 文件布局（P1 修复 #9 by software-engineer）

> **背景**：争议 1 决议（REVIEW-M3-M6 §四）确定 checkpoint 落 SQLite 单表、文件路径 `data/langgraph_checkpoints.db`，与本节 `data/agent.db` **同一 SQLite 实例、不同物理文件**，避免表名冲突。

#### 文件清单

| 文件 | 表空间 | 用途 | 写入方 |
|------|--------|------|--------|
| `data/agent.db` | 业务表（`stock_info` / `agent_runs` / `skill_executions` / `daily_reports` / `reflections` / `user_prefs` 等） | 业务主数据 | `backend/shared/models.py`（SQLAlchemy `Base`） |
| `data/langgraph_checkpoints.db` | LangGraph checkpointer 内部表 | Agent run checkpoint / state 快照 | `SqliteSaver.from_conn_string(...)`（M3.5 §2.1） |

#### 与 launch.py 老表名空间冲突核对

- M1 §1.5 新表 `agent_runs`（以及 `skill_executions`、`reflections`、`user_prefs`）**是新引入的**，launch.py 现有 `shared.db_session` 管理的**老表**（`portfolio_holdings` / `backtest_results` / `factor_library` / `audit_log` / `task_queue`）的命名空间**不与新表重名**。
- 但 launch.py 老 `db_session` 默认连接的可能是另一个 SQLite 文件或同一文件的旧路径，**M0 阶段必须核对**：
  1. launch.py 实际写入的 SQLite 路径（grep `sqlite:///` 或 `create_engine` 调用）
  2. 确认 M1 §1.4 的 `database.url`（默认 `sqlite:///data/agent.db`）与之**同文件同表空间**——若是，需把 launch.py 老表的 owner 显式迁到 `data/agent.db`；若 launch.py 用的是独立文件（如 `data/legacy.db`），则**无冲突**但需在 §1.10 任务卡片 M1.8 迁移脚本里加一步"双写 legacy.db → agent.db"。
- **结论未确认前，M1 编码不阻塞**，但 M0 阶段必须给出明确答案并补一行 M1 §1.4 配置示例：`# TODO(M0): 确认与 launch.py shared.db_session 的 SQLite 路径一致性`。

#### 为什么分文件不分表

- 同一 SQLite 文件内，LangGraph checkpointer 自家会建若干 `checkpoints` / `checkpoint_writes` / `checkpoint_blobs` 表，与业务表混在一起，**DROP/迁移时易误伤**。
- 分文件后：业务 DB 可独立备份、`PRAGMA wal_checkpoint(TRUNCATE)` 单独触发；LangGraph 故障时也只污染 checkpoint 文件，不影响业务读写。
- 两文件**共享 WAL 模式**（`PRAGMA journal_mode=WAL`）依然成立，但**WAL 文件是 per-DB**（`agent.db-wal` / `langgraph_checkpoints.db-wal`），不会跨文件冲突。

### 1.4.2 checkpoint DB 目录预创建

在 FastAPI lifespan 中初始化 `AsyncSqliteSaver` 前，确保目录存在：
```python
CHECKPOINT_DB_DIR = Path(CHECKPOINT_DB).parent
CHECKPOINT_DB_DIR.mkdir(parents=True, exist_ok=True)
```
避免 `from_conn_string()` 因目录不存在而失败时泄漏文件描述符。

### 连接池策略（小结）

| 数据库 | Pool | 备注 |
|--------|------|------|
| SQLite（默认） | `StaticPool` | 单连接复用，必须 `check_same_thread=False` |
| PostgreSQL | `QueuePool` | `pool_size=5`, `max_overflow=10`（Phase 2+） |

### 测试要点

| 测试项 | 期望结果 |
|--------|----------|
| engine 创建 | SQLite 文件写入 `data/agent.db`（**绝对路径**，chdir 不影响） |
| WAL 模式 | PRAGMA journal_mode 返回 `wal` |
| FK 约束 | `skill_executions.run_id` 插入不存在的 run_id → 抛 `IntegrityError` |
| 多线程访问 | 两个线程同时 get_db() → 各自独立 session（StaticPool + check_same_thread=False） |
| 锁竞争 | 同一写连接并发时 busy_timeout 5s 内不报 SQLITE_BUSY |
| session CRUD | add → flush → query → 数据一致 |

---

## 1.5 ORM 模型 (`models.py`)

### 表清单（8 张核心表 + 4 张归档/历史兼容表 + 2 张 Phase 2 新增表）

**核心 8 张**（Phase 1 启用）：

| 表名 | 说明 | 来源 |
|------|------|------|
| `stock_info` | 股票主数据 | 原系统保留 |
| `kline_cache` | K 线缓存 | 原系统保留 |
| `portfolio` | 持仓（汇总态） | 原系统保留 |
| `daily_nav` | 每日净值 | 原系统保留 |
| `agent_runs` | Agent 运行记录 | **新增** |
| `skill_executions` | Skill 调用记录 | **新增** |
| `daily_reports` | 日频报告 | 重构 |
| `reflections` | 复盘记录 | **新增** |
| `skill_registry` | **Phase 2 新增** | **新增** |
| `conversation_history` | **Phase 2 新增** | **新增** |

**Phase 2 新增表说明**（2026-06-07 补强，依据 M1-M6 解决方案 P0/P1）：
- `skill_registry`：记录每个 Skill 的 `name / category / allowed_intents(JSON) / type('skill'|'agent')`。用于按 `user_intent` 过滤暴露给 LLM 的工具集，避免 30+ Skill 同时推送导致选择准确率下降（解决方案 C-3）。
- `conversation_history`：存储完整对话历史 `messages_json`，按 `run_id` 索引。解决 Interrupt 暂停/恢复时 Master summarize 节点缺少 system 消息的上下文丢失问题（解决方案 P0-4 / F-5）。

**被裁剪 6 类原表 → 替代方案清单**（M1 联合 PM 决议，2026-06-07）：

| 原表/类别 | 替代方案 | 类别 | 实施位置 |
|----------|----------|------|----------|
| `portfolio_holdings`（逐笔交易） | **日志 + JSON 文件**（`data/portfolio_trades.jsonl`，按日期 append-only） | (b) 业务可重建 | `backend/services/portfolio_logger.py` |
| `backtest_results`（回测结果） | **日志文件**（`logs/backtest/{run_id}.json`，每回测一个文件） | (b) 一次性产出 | `backend/services/backtest_logger.py` |
| `factor_library`（因子定义库） | **YAML 静态文件**（`config/factors/*.yaml`，随代码版本管理） | (b) 业务可重建 | `config/factors/` |
| `signal_history`（信号历史） | **确认可丢**（信号为中间态，记录到 `agent_runs.plan_json` 即可） | (c) 业务可丢失 | 无 |
| `audit_log`（操作审计） | **JSON Lines 日志**（`logs/audit/{date}.jsonl`，结构化 `who/when/action/result`） | (b) 日志可追溯 | `backend/shared/audit.py` |
| `task_queue`（后台任务队列） | **确认可丢**（LangGraph checkpointer 接管，任务状态已在 checkpoint 内） | (c) 业务可丢失 | 无（LangGraph 接管） |
| `user_preferences`（用户偏好） | **新增表承接**（`user_prefs`，8 字段：theme/refresh_interval/email_to/default_style/risk_tolerance/...） | (a) 新增表 | `backend/shared/models.py` → 9 张核心表（特例） |

> **说明**：`user_prefs` 是唯一新增承接表。8 → 9 张的"例外"已在 PM/Architect 联合评审通过；其他 6 类**不增加表**。

**数据迁移方案**（7 天双写期，第 8 天 drop）：

```
Day 1-5：双写 + 双读（旧表 INSERT 同步写入新位置/新表；READ 优先新位置，MISS 回退旧表）
Day 6-7：双写 + 单读（仅读新位置，旧表停止读取）
Day 8   ：DROP 旧表（`DROP TABLE portfolio_holdings` 等）
```

迁移脚本存放：`backend/migrations/2026_06_phase1_cutover/`（Phase 1 启动前 1 周就绪）。

### 代码片段（关键模型）

> **存放位置**：`backend/shared/models_v2.py`（2026-06-07 决议 P0-4：与旧表 `models.py` 分离，共享同一 `Base`）。

**完整 schema 定义见 `CODING-GUIDE.md §4`**。以下为各表关键字段和索引速查：

| 表名 | 必填字段 | 索引 | 关键约束 |
|------|---------|------|---------|
| `agent_runs` | `run_id`, `goal`, `plan_json` | `run_id` (UNIQUE), `parent_run_id` (INDEX) | `status` 枚举约束，`parent_run_id` 自引用 |
| `skill_executions` | `run_id`, `skill_name`, `success`, `latency_ms` | `run_id` (INDEX), `skill_name` (INDEX), `idempotency_key` (UNIQUE) | `run_id` FK → `agent_runs.run_id` (CASCADE), `idempotency_key` 唯一约束 |
| `skill_registry` | `skill_name`, `category`, `type`, `allowed_intents` | `skill_name` (UNIQUE) | `type` 仅 `"skill"` 或 `"agent"` |
| `conversation_history` | `run_id`, `messages_json` | `run_id` (INDEX, FK CASCADE) | 写不阻塞图执行（fire-and-forget） |
| `daily_reports` | `report_date`, `markdown` | `report_date` (UNIQUE) | — |
| `reflections` | `trade_date`, `accuracy`, `avg_return` | `trade_date` (INDEX) | — |
| `user_prefs` | `key` | `key` (UNIQUE) | KV 存储 |
| `user_memory` | `key`, `value` | `key` (UNIQUE) | category 枚举: preference/fact/rule/history |

> **PK 约定**：所有表均以 `id INTEGER PRIMARY KEY AUTOINCREMENT` 开头（不在上表列出）。
> **时间戳约定**：所有表含 `created_at DATETIME DEFAULT CURRENT_TIMESTAMP`（省去表级罗列）。
> **完整字段定义**（含 Python SQLAlchemy Column 类型）请直接读 `backend/shared/models_v2.py`。

```python
from sqlalchemy import (
    Column, Integer, String, Float, Text, DateTime, Boolean, Index,
)
from sqlalchemy.sql import func

from .database import Base


class StockInfo(Base):
    """股票主数据（精简至 10 个核心字段）"""
    __tablename__ = "stock_info"

    id = Column(Integer, primary_key=True, autoincrement=True)
    stock_code = Column(String(10), unique=True, nullable=False, index=True)
    stock_name = Column(String(50), nullable=False)
    industry = Column(String(50), default="")
    latest_price = Column(Float, default=0.0)
    pe_ratio = Column(Float, default=0.0)
    pb_ratio = Column(Float, default=0.0)
    roe = Column(Float, default=0.0)
    total_market_cap = Column(Float, default=0.0)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())


class AgentRun(Base):
    """Agent 运行记录（2026-06-07 补强：依据 M1-M6 解决方案）"""
    __tablename__ = "agent_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(String(36), unique=True, nullable=False)
    goal = Column(Text, nullable=False)           # 用户原始意图
    plan_json = Column(Text, nullable=False)      # ExecutionPlan JSON
    status = Column(String(20), default="pending") # pending/running/completed/failed/cancelled
    # → 2026-06-07 补强 P0-2 + P0-4：checkpoint 双段保留（热 1h / 冷 7d）
    checkpoint_retention_hours = Column(Integer, default=24)
    # → 2026-06-07 补强 C-4：节点执行计数，防止无限循环
    node_count = Column(Integer, default=0)
    # → 2026-06-07 补强 F-8：错误/取消原因
    status_reason = Column(String(500), nullable=True)
    tokens_used = Column(Integer, default=0)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    created_at = Column(DateTime, default=func.now())


class SkillExecution(Base):
    """Skill 调用记录"""
    __tablename__ = "skill_executions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    # → P0-4 由 software-architect 于 2026-06-07 补强：FK 约束
    run_id = Column(
        String(36),
        ForeignKey("agent_runs.run_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    skill_name = Column(String(100), nullable=False, index=True)
    input_params = Column(Text)
    output_summary = Column(Text)
    success = Column(Boolean, nullable=False)
    latency_ms = Column(Integer, nullable=False)
    tokens_used = Column(Integer, default=0)
    cache_hit = Column(Boolean, default=False)
    # → P0-4 配套：幂等键（详见 M2 §4.1 幂等性约定）
    idempotency_key = Column(
        String(64),  # md5 hex
        unique=True,
        nullable=True,  # NULL 表示纯查询 Skill（无幂等需求）
        index=True,
    )
    replayed = Column(Boolean, default=False)  # 命中幂等键时标记 True
    # → 2026-06-07 补强 P0-1：记录步骤类型（skill/agent/confirm_*/...）便于审计
    step_type = Column(String(32), nullable=True)
    # → 2026-06-07 补强 P0-3：可选，引用外部存储的 universe_snapshot 等大 payload
    large_payload_ref = Column(String(128), nullable=True)
    created_at = Column(DateTime, default=func.now())


class SkillRegistry(Base):
    """Skill/Agent 注册表（2026-06-07 新增，依据解决方案 C-3）"""
    __tablename__ = "skill_registry"

    id = Column(Integer, primary_key=True, autoincrement=True)
    skill_name = Column(String(100), unique=True, nullable=False, index=True)
    category = Column(String(50), nullable=False)         # data/quant/report/communication/memory/agent
    # 允许调用的 user_intent 列表，JSON 数组
    allowed_intents = Column(Text, nullable=False, default="[]")
    description = Column(Text, nullable=True)
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=func.now())


class ConversationHistory(Base):
    """完整对话历史（2026-06-07 新增，依据解决方案 P0-4 / F-5）"""
    __tablename__ = "conversation_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(
        String(36),
        ForeignKey("agent_runs.run_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    messages_json = Column(Text, nullable=False)  # 完整 messages 数组 JSON
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
```

> **完整 8 表代码略**，见 `backend/shared/models.py` 完整实现。

### 表关系说明

```
agent_runs (1) ──── (N) skill_executions
     │
     ├─── (1:1) daily_reports (同一天)
     ├─── (1:N) conversation_history  (Phase 2 新增，对话消息追加)

daily_reports (1)
     └─── (N) reflections (可选, 可多次复盘同一天)

skill_registry           ←─ 独立配置表，由应用启动时填充，不与业务表 FK 关联
```

### 测试要点

| 测试项 | 期望结果 |
|--------|----------|
| `Base.metadata.create_all()` | 8 张表全部创建 |
| `stock_code UNIQUE` | 重复插入抛 `IntegrityError` |
| `agent_runs.run_id UNIQUE` | 重复 UUID 抛异常 |
| `skill_executions.run_id INDEX` | WHERE run_id= 走索引 |
| `daily_reports.report_date UNIQUE` | 同一天两条报错 |

---

## 1.6 异常层次 (`exceptions.py`)

### 设计要点

- **基类 `AShareXError`**: 所有应用异常的父类, 携带 `message` + `detail` dict
- **可恢复错误**: `DataSourceError` (重试), `DataNotReadyError` (等数据)
- **不可恢复**: `SkillExecutionError`, `AgentRuntimeError`, `ConfigurationError`
- FastAPI 全局异常处理器捕获 `AShareXError` → 4xx

### 1.6.1 数据源失败处理：手动更新 + 用户提醒（Q1.2 补强，2026-06-07）

**核心原则**：数据正确性 > 自动化。失败时**绝不自动 fallback 到次级源**（避免"用错误数据跑出错误推荐"），改为**明确告知用户 + 提供手动更新入口**。

**DataSourceError 的传播路径**：

```
Data Skill 调用 data.fetch_kline (akshare/efinance/tushare ...)
  → 失败（API 5xx / 网络超时 / 接口下线）
  → 抛 DataSourceError（recoverable=False，本场景不重试）
  → SkillExecutor 捕获 → 写入 skill_executions 表 success=False
  → 节点不写入 step_results（保留错误状态）
  → SSE 推送 error 事件 + 友好的中文提示
  → 前端显示明确错误卡（不是默默失败）
```

**前端错误卡设计**（M6 §4.2 错误处理升级）：

```vue
<!-- ErrorCard.vue 组件示意 -->
<el-alert type="error" :closable="false">
  <template #title>数据获取失败</template>
  <p>{{ error.message }}</p>
  <p>原因：{{ error.detail.provider }} 接口返回 {{ error.detail.status_code }}</p>
  <el-button @click="onManualUpdate">手动更新数据库</el-button>
  <el-button @click="onRetry">重试当前步骤</el-button>
</el-alert>
```

**手动更新入口**：

| 入口 | 行为 | 适用场景 |
|------|------|---------|
| **设置页面"数据管理"标签** | 列出所有数据源 + 最新更新时间 + 手动"刷新"按钮 | 用户怀疑数据陈旧 |
| **错误卡内"手动更新数据库"按钮** | 仅刷新当前失败的数据源 | 实时错误时直接修复 |
| **CLI 命令** `python -m backend.tools.refresh_data --source akshare` | 批量刷新 | 已知数据源问题时主动更新 |

**为什么不做自动热切换（2026-06-07 决议）**：
- 个人使用场景下，数据准确性 > 选股速度
- 自动切换可能导致"用户用了一份他不知情的次级数据"——这比直接报错更危险
- 次级源（如 efinance）的数据可能与主源（akshare）有细微差异（如复权方式），会导致后续选股结果不可复现
- **手动模式强迫用户意识到"数据失败了"**，是更安全的默认

**错误信息格式**（`DataSourceError.detail`）：

```python
raise DataSourceError(
    "数据获取失败：akshare 接口不可用",
    detail={
        "provider": "akshare",
        "endpoint": "stock_zh_a_hist",
        "status_code": 503,
        "retry_after_seconds": 60,
        "next_steps": [
            "点击'手动更新数据库'切换数据源",
            "或等待 60 秒后点击'重试'",
            "或检查网络连接"
        ],
    }
)
```

**SSE 事件**：

```json
{
  "event": "error",
  "data": {
    "code": "ASX-DATA-001",
    "message": "akshare 接口不可用（HTTP 503）",
    "fatal": false,
    "step_id": "s3",
    "recoverable_action": "manual_refresh",
    "detail": { ... }
  }
}
```

**与 M5 附录 A 错误码体系对齐**：`ASX-DATA-001` 是新增的错误码（上游 5xx），与 `ASX-DATA-002`（接口下线）/ `ASX-DATA-003`（限流）区分。

### 代码

```python
class AShareXError(Exception):
    """应用基异常"""
    def __init__(self, message: str, detail: dict | None = None):
        self.message = message
        self.detail = detail or {}
        super().__init__(message)


class DataSourceError(AShareXError):
    """数据源错误（可恢复）"""
    pass


class DataNotReadyError(AShareXError):
    """数据未就绪（如 17:00 前请求）"""
    pass


class SkillExecutionError(AShareXError):
    """Skill 执行失败"""
    pass


class AgentRuntimeError(AShareXError):
    """Agent 运行时错误"""
    pass


class ConfigurationError(AShareXError):
    """配置错误"""
    pass
```

### 测试要点

| 测试项 | 期望结果 |
|--------|----------|
| `raise DataSourceError("API timeout")` | `isinstance(e, AShareXError)` → `True` |
| FastAPI route 抛 `DataNotReadyError` | 返回 4xx JSON `{error, detail}` |
| `raise ConfigurationError("missing key")` | 不捕获则 500 |

---

## 1.7 结构化日志 (`logging_config.py`)

### 设计要点

- **JSON 格式**: 文件输出用 JSON Lines, 方便 log aggregator 解析
- **控制台格式**: 人类可读, 带时间/级别/消息
- **额外字段**: `run_id` / `skill_name` 可通过 `extra=` 注入
- **第三方降噪**: SQLAlchemy / urllib3 日志级别提至 WARNING

### 代码

```python
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from .config import config


class StructuredFormatter(logging.Formatter):
    """JSON 格式日志"""

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        # 可选额外字段
        for field in ("run_id", "skill_name"):
            if hasattr(record, field):
                log_entry[field] = getattr(record, field)
        if record.exc_info and record.exc_info[1]:
            log_entry["exception"] = str(record.exc_info[1])
        return json.dumps(log_entry, ensure_ascii=False)


def setup_logging() -> logging.Logger:
    """配置根日志器（幂等：重复调用不会累积 handler）"""
    log_level = config.get("log.level", "INFO")
    log_file = config.get("log.file", "logs/app.log")

    Path(log_file).parent.mkdir(parents=True, exist_ok=True)

    root_logger = logging.getLogger()

    # → P0-2 由 software-architect 于 2026-06-07 补强：去重守卫
    # uvicorn/pytest 多次 reload 时 setup_logging 可能被多次调用
    if getattr(root_logger, "_asharex_configured", False):
        # 仅刷新 level，不重复 addHandler
        root_logger.setLevel(getattr(logging, log_level.upper()))
        return root_logger

    # 文件 handler — JSON
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(StructuredFormatter())

    # 控制台 handler — 可读（统一时区，见 P1）
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(
        logging.Formatter(
            "%(asctime)s [%(levelname)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S %Z",
        )
    )
    # → P1：控制台时区显示 Asia/Shanghai
    import time as _time
    class _ShanghaiFormatter(logging.Formatter):
        def formatTime(self, record, datefmt=None):
            from datetime import datetime, timezone, timedelta
            tz = timezone(timedelta(hours=8))
            dt = datetime.fromtimestamp(record.created, tz=tz)
            return dt.strftime(datefmt or "%Y-%m-%d %H:%M:%S %Z")
    console_handler.setFormatter(
        _ShanghaiFormatter("%(asctime)s [%(levelname)s] %(message)s")
    )

    root_logger.setLevel(getattr(logging, log_level.upper()))
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    # 降低第三方库日志等级
    logging.getLogger("sqlalchemy").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)

    # → P1：首次启动打印"loaded keys"摘要（运维可观测性）
    root_logger._asharex_configured = True
    root_logger.info(
        "asharex logging initialized",
        extra={
            "log_level": log_level,
            "log_file": log_file,
            "loaded_keys_summary": _summarize_loaded_keys(),
        },
    )
    return root_logger


def _summarize_loaded_keys() -> dict:
    """启动时打印所有加载的配置 key（脱敏）

    → 2026-06-07 补强 F-12：遍历扁平化后的所有键，匹配敏感关键词列表
    """
    from .config import config
    # 敏感关键词：键名（.路径或环境变量名）包含这些子串则脱敏
    sensitive_keywords = ("password", "token", "secret", "key", "credential")
    out: dict = {}

    def _flatten(d: dict, prefix: str = "") -> list[tuple[str, object]]:
        """递归扁平化嵌套 dict 为 (path, value) 列表"""
        items: list[tuple[str, object]] = []
        for k, v in d.items():
            path = f"{prefix}.{k}" if prefix else k
            if isinstance(v, dict):
                items.extend(_flatten(v, path))
            else:
                items.append((path, v))
        return items

    yaml_data = getattr(config, "_yaml", {}) or {}
    for path, val in _flatten(yaml_data):
        path_lower = path.lower()
        if any(kw in path_lower for kw in sensitive_keywords):
            out[path] = "***"
        else:
            out[path] = type(val).__name__
    return out
```

### 使用示例

```python
logger = logging.getLogger(__name__)
logger.info("开始选股流程", extra={"run_id": "abc123", "skill_name": "screening"})
# → {"timestamp":"...", "level":"INFO", "message":"开始选股流程", "run_id":"abc123", ...}
```

### 测试要点

| 测试项 | 期望结果 |
|--------|----------|
| 启动后文件存在 | `logs/app.log` 生成 |
| JSON 格式可解析 | 每行 `json.loads()` 成功 |
| extra 字段注入 | `run_id` 出现在 JSON 中 |
| SQLAlchemy 日志 | `WARNING` 以下不输出 |

---

## 1.8 初始化入口 (`__init__.py`)

```python
from .config import config
from .logging_config import setup_logging
from .database import engine, Base, SessionLocal, get_db
from .exceptions import (
    AShareXError,
    DataSourceError,
    DataNotReadyError,
    SkillExecutionError,
    AgentRuntimeError,
    ConfigurationError,
)

__all__ = [
    "config",
    "setup_logging",
    "engine",
    "Base",
    "SessionLocal",
    "get_db",
    "AShareXError",
    "DataSourceError",
    "DataNotReadyError",
    "SkillExecutionError",
    "AgentRuntimeError",
    "ConfigurationError",
]
```

---

## 1.9 运维可观测性（必备基建） → 由 software-architect/PM 于 2026-06-07 补强

基建层必须**第一天**就具备"启动失败可观测"能力，否则 on-call 半夜被叫起来不知道哪个 key 缺了。

### 1.9.1 `python -m backend.main --validate-config` dry-run 模式

```bash
$ python -m backend.main --validate-config
{
  "ok": true,
  "missing_required": [],
  "type_errors": [],
  "loaded_keys": {
    "llm.provider": {"value": "deepseek", "source": "yaml", "type": "str"},
    "database.url": {"value": "sqlite:////abs/path/agent.db", "source": "yaml", "type": "str"},
    "qq_smtp_password": {"value": "***", "source": "env", "type": "str"}
  }
}
```

| 退出码 | 含义 |
|--------|------|
| 0 | 全部 OK，可启动 |
| 1 | 缺失必填 key（`missing_required` 非空） |
| 2 | 类型错误（`type_errors` 非空，例如 `cache_ttl_minutes` 配成字符串） |

### 1.9.2 `/healthz` 端点（M5 API 暴露）

```
GET /api/health  →  200 {status:"ok", version, checks: {
    "config": "ok|missing_keys",
    "database": "ok|connect_fail",
    "skill_registry": "ok|<N>_skills_loaded",
    "checkpoint": "ok|connect_fail|noop",
    "checkpoint_db_size_mb": 12.3,
    "checkpoint_last_write_age_s": 45
}}
```

**checkpoint 健康检查实现**（不是静态类型标签）：
```python
async def _check_checkpoint(app) -> dict:
    try:
        result = await app.state.checkpointer.aquery("SELECT 1")
        # 检查 DB 文件大小
        db_path = Path(os.getenv("ASAREX_CHECKPOINT_DB", "data/langgraph_checkpoints.db"))
        size_mb = db_path.stat().st_size / (1024 * 1024) if db_path.exists() else 0
        return {
            "status": "ok",
            "db_size_mb": round(size_mb, 2),
            "last_write_age_s": _get_last_write_age(db_path),
        }
    except Exception as e:
        return {"status": "connect_fail", "error": str(e)}
```

### 1.9.3 启动日志首行（§1.7 已实现 `_summarize_loaded_keys`）

启动日志首行 JSON 必含 `loaded_keys_summary` 字段（脱敏），运维 grep 即可定位缺哪个 key。

### 1.9.4 必备配置 schema 校验

`config.yaml` 顶层 schema（JSON Schema 子集，启动时校验）：

| 路径 | 类型 | 必填 | 默认 |
|------|------|------|------|
| `llm.provider` | enum: deepseek/openai/qwen | 是 | - |
| `llm.model` | str | 是 | - |
| `llm.temperature` | float [0,2] | 否 | 0.1 |
| `database.url` | str (sqlite:/// or postgresql://) | 是 | sqlite:///./data/agent.db |
| `log.level` | enum: DEBUG/INFO/WARNING/ERROR | 否 | INFO |
| `screening.timeout_seconds` | int (10-120) | 否 | 60 |
| `screening.max_candidates` | int (1-50) | 否 | 10 |
| `email.smtp_host` | str | 通讯 Skill 启用时必填 | - |
| `email.smtp_port` | int | 通讯 Skill 启用时必填 | 465 |

---

## 1.10 开发任务卡片

| 任务 ID | 内容 | 产出 | 测试要点 |
|---------|------|------|----------|
| M1.1 | 创建目录结构 | `backend/shared/` 完整文件 | 导入无报错 |
| M1.2 | 实现 Config | `config.py` | .env 覆盖 YAML；环境变量类型转换；`reset_for_test()` |
| M1.3 | 实现 database.py | engine + session + Base | SQLite WAL + StaticPool + FK ON + busy_timeout |
| M1.4 | 编写 ORM 模型 | `models.py`（8 旧表保留）+ `models_v2.py`（11 新表，共享 engine + Base）。**2026-06-07 决议 P0-4**：新旧分离，`models_v2.py` 中新增表包括 `agent_runs` / `skill_executions` / `skill_registry` / `conversation_history` 等。 | 表创建；索引正常；FK 约束生效；新旧表不冲突 |
| M1.5 | 定义异常层次 | `exceptions.py` | 捕获层次正确 |
| M1.6 | 结构化日志 | `logging_config.py` | JSON 格式输出；handler 幂等；UTC 存+Shanghai 显示 |
| M1.7 | 启动初始化 + 运维 | `backend/main.py --validate-config` + `/healthz` + loaded keys 日志 | dry-run 退出码；启动首行 JSON 正确 |
| M1.8 | 数据迁移脚本 | `backend/migrations/2026_06_phase1_cutover/` | 7 天双写脚本 + 第 8 天 drop |
| M1.9 | **Phase 2 新增** skill_registry 初始化 | 启动时加载 Skill/Agent 名单到 `skill_registry` 表。**每个 Skill 独立 try/except**：单个 Skill 导入失败（语法错误/缺字段）不阻塞其他 Skill 加载和服务启动，失败 Skill 记录 ERROR 日志并在 `/api/health` 的 `skill_registry.failed_skills` 中暴露。 | 启动后 `SELECT COUNT(*)` 包含全部注册 Skill |
| M1.10 | **Phase 2 新增** conversation_history 写入 | Interrupt/恢复/summarize 节点追加 system 消息到该表 | SELECT messages_json 包含 system 角色消息 |

## 1.10.1 Phase 2 数据库清理任务（2026-06-07 新增，依据 P0-2 方案）

| 任务 | 频率 | 行为 |
|------|------|------|
| `cleanup_old_agent_runs` | 每日凌晨 04:00 | 删除 `created_at < now() - 7 days` **且 `status NOT IN ('running', 'waiting_user', 'cancelling')`** 的 `agent_runs` 记录（级联删除关联 `skill_executions` / `conversation_history`）。
清理前先查询：
```sql
SELECT run_id, status FROM agent_runs 
WHERE created_at < datetime('now', '-7 days') 
  AND status IN ('running', 'waiting_user');
```
若返回非空结果，记录 WARNING 日志并**跳过这些 run**。 |

**parent_run_id 链保护**：被其他 `agent_runs.parent_run_id` 引用的记录不删除：
```sql
DELETE FROM agent_runs 
WHERE created_at < datetime('now', '-7 days')
  AND status NOT IN ('running', 'waiting_user', 'cancelling')
  AND run_id NOT IN (SELECT DISTINCT parent_run_id FROM agent_runs WHERE parent_run_id IS NOT NULL);
```

| LangGraph checkpoint 清理 | 每日 | `SqliteSaver` 自带清理 OR 手动 `DELETE FROM checkpoints WHERE thread_id NOT IN (SELECT run_id FROM agent_runs)` |
| `vacuum_checkpoint_db` | 每周日 03:00 | `PRAGMA optimize;` 或 `VACUUM;`（注意：VACUUM 锁库，需低峰期执行，临时空间 = DB 文件大小） |

**替代方案**：建库时开启 `PRAGMA auto_vacuum=INCREMENTAL`，每次 DELETE 后 `PRAGMA incremental_vacuum`，避免全库锁。

**为什么是 7 天**：与 `checkpoint_retention_hours` 冷保留周期一致（详见 M3.5 §2.2）。热保留 1h（LangGraph 原生支持）+ 冷保留 7d（数据库可查不可恢复）。

## 1.10 依赖清单

| 包 | 用途 | 版本 |
|----|------|------|
| `pyyaml` | YAML 解析 | >=6.0 |
| `python-dotenv` | .env 加载 | >=1.0 |
| `sqlalchemy` | ORM + engine | >=2.0 |

---

**下一模块**: M2 — Skill 执行引擎 (`backend/skills/engine.py`)
