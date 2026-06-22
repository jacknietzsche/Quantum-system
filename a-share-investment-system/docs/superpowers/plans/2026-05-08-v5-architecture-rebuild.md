# v5.0 架构重建实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development or executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** 完全重建项目为 3层+1横切 架构（shared/providers/services/api），删除所有旧模块，保留全部12个页面功能和45个API端点

**Architecture:** api → services → providers → shared，单向依赖，每文件≤200行，本地优先数据加载

**Tech Stack:** Python 3.10+, FastAPI, SQLAlchemy, Jinja2, LangGraph, pandas, akshare, uvicorn

---

## Phase 1: shared/ 基础设施（4个文件）

### Task 1.1: shared/exceptions.py

**Files:** Create `shared/exceptions.py`

```python
"""统一异常体系"""
class SystemBaseError(Exception):
    """所有自定义异常的基类"""
    def __init__(self, message: str, detail: dict = None):
        self.message = message
        self.detail = detail or {}
        super().__init__(message)

class DataSourceError(SystemBaseError): ...
class DataValidationError(SystemBaseError): ...
class DatabaseError(SystemBaseError): ...
class SkillExecutionError(SystemBaseError): ...
class LLMCallError(SystemBaseError): ...
class DecisionError(SystemBaseError): ...
class RiskRejectionError(SystemBaseError): ...
class WorkflowAbortError(SystemBaseError): ...
class WorkflowTimeoutError(SystemBaseError): ...
class ConfigError(SystemBaseError): ...
class DependencyNotFoundError(SystemBaseError): ...
```

### Task 1.2: shared/config.py

**Files:** Create `shared/config.py`

- 从 root `config/compat.py` 和 `config/config.yaml` 迁移配置逻辑
- 实现 `Config` 类：`get()`, `get_model()`, `get_api_key()`, `get_email_config()`
- 加载顺序: 环境变量 > .env > config/config.yaml

### Task 1.3: shared/dto.py

**Files:** Create `shared/dto.py`

- 从 root `core/dto.py` 迁移 8 个 frozen dataclass
- 添加 `@dataclass(frozen=True)` 装饰器
- 添加 `to_dict()` 方法用于序列化

### Task 1.4: shared/models.py

**Files:** Create `shared/models.py`

- 从 root `models.py` 迁移 11 张 ORM 表定义
- 关键表：`Portfolio`, `Watchlist`, `TradeRecord`, `StockInfo`, `KlineCache`, `MarketSnapshot`, `SystemLog`, `DailyReport`, `Order`, `Trade`, `DailyNAV`
- 包含 `init_db()`, `get_session()`, `get_engine()` 函数
- 数据库路径统一为 `data/investment.db`

---

## Phase 2: providers/ 数据层（5个文件）

### Task 2.1: providers/database.py

**Files:** Create `providers/database.py`

```python
"""数据库会话管理"""
from shared.models import Base, get_engine as _get_engine
from sqlalchemy.orm import sessionmaker

_engine = None
_Session = None

def init_db(db_path="data/investment.db"):
    global _engine, _Session
    _engine = _get_engine(db_path)
    Base.metadata.create_all(_engine)
    _Session = sessionmaker(bind=_engine)
    return _engine

def get_session():
    if _Session is None: init_db()
    return _Session()

def get_engine():
    if _engine is None: init_db()
    return _engine
```

### Task 2.2: providers/cache.py

**Files:** Create `providers/cache.py`

- 迁移 root `data/cache.py` 的 CacheManager
- 内存 TTL 缓存 + LLM 文件缓存
- `clear_all()` 清除内存和文件缓存（修复 v4.2 bug）

### Task 2.3: providers/market_data.py

**Files:** Create `providers/market_data.py`

- 封装 6 个数据源的降级链（akshare → tencent → sina → efinance → baostock → tickflow）
- 主要方法：`get_indices()`, `get_north_flow()`, `get_sectors()`, `get_stock_spot()`, `get_stock_kline()`, `get_stock_basic()`
- 内部 `_try_sources(method, *args)` 按优先级依次尝试
- 所有方法带超时保护（10s）
- 字段名归一化（中文→英文）

### Task 2.4: providers/llm.py

**Files:** Create `providers/llm.py`

- 从 root `decision/llm/caller.py` 迁移 LLMCaller
- 支持 providers: deepseek, siliconflow, chatanywhere, juguang, cherryin
- `call(model, prompt, **kwargs)` → dict
- `call_with_fallback(prompt, **kwargs)` → dict

### Task 2.5: providers/email_sender.py

**Files:** Create `providers/email_sender.py`

- 从 root `output/email_sender.py` 迁移
- QQ邮箱 SMTP SSL 发送
- `send(subject, body, to)` → bool

---

## Phase 3: services/ 业务层（6个文件）

### Task 3.1: services/market.py

**Files:** Create `services/market.py`

- `MarketService` 类，注入 `db_session`, `market_provider`, `cache_manager`
- `get_indices()`: 先读 market_snapshot → 命中返回+后台刷新 → 未命中返回空+后台
- `get_north_flow()`: 同上模式
- `get_hot_stocks(sort, limit)`: 先读 DAL缓存 → StockInfo表 → 返回空
- `get_sectors()`: 归一化板块数据（中文列名→英文）
- 辅助: `_store_snapshot(type, data)`, `_bg_refresh_indices()`, `_bg_refresh_north_flow()`

### Task 3.2: services/watchlist.py

**Files:** Create `services/watchlist.py`

- `WatchlistService` 类
- `get_all(refresh=False)`: 查询 Watchlist + StockInfo 联合数据
- `add(code, name, category, reason)`: 插入 + 后台拉取 K线/基本面
- `delete(code)`, `clear()`, `export_csv()`, `import_csv(csv_text)`

### Task 3.3: services/portfolio.py

**Files:** Create `services/portfolio.py`

- `PortfolioService` 类
- `get_holdings()`: 查询 Portfolio + StockInfo
- `get_trades(limit)`: 查询 TradeRecord
- `get_stock_info(code)`: 单只股票详情
- `search_stocks(query, limit)`: 搜索

### Task 3.4: services/workflow.py

**Files:** Create `services/workflow.py`

- `WorkflowService` 类，注入 `llm_caller`, `market_provider`, `db_session`
- 线程安全的状态管理（`_lock`, `_status` dict）
- `run_super(stock_code, progress_callback, abort_check)`: 调用 LangGraph 超级工作流
- `run_standard()`: 标准工作流
- `get_status()`, `cancel()`, `clear_logs()`
- 保留`super_workflow.py`（LangGraph图定义）+ `workflow.py`（标准工作流）作为遗留调用

### Task 3.5: services/risk.py

**Files:** Create `services/risk.py`

- `RiskService` 类
- `audit()`: 风控审计（无持仓→默认通过，有持仓→调用 RiskFirewall）
- `position_plan(risk_score)`: 仓位计算
- `get_review_stats()`: 决策复盘统计
- 保留`decision_review.py`和`skills.py`（RiskFirewall）作为遗留调用

### Task 3.6: services/data_mgmt.py

**Files:** Create `services/data_mgmt.py`

- `DataManagementService` 类
- `get_table_stats()`: 查询所有表行数+DB大小
- `get_provider_status()`: 6个Provider可用性检测
- `clear_cache()`: 清除全部缓存
- `refresh_stock(code)`: 强制刷新单只股票（基本面+K线+指标）
- `rebuild_db()`: 调用 build_stock_db.py
- `rescreen()`: 调用 screen_watchlist.py

---

## Phase 4: api/ 路由层（14个文件）

### Task 4.1: api/app.py

**Files:** Create `api/app.py`

- `create_app()` 工厂函数
- 注册 12 个路由模块
- 挂载 `/static` 和 Jinja2 templates
- startup 事件：缓存预热（market + risk）

### Task 4.2: api/deps.py

**Files:** Create `api/deps.py`

- `get_db()`, `get_config()`, `get_cache()`, `get_market_provider()`, `get_llm()`
- 每个函数返回对应服务的实例

### Task 4.3-4.14: api/routes/*.py（12个文件）

每个路由文件遵循统一模式：

```python
from fastapi import APIRouter, Depends, BackgroundTasks
from api.deps import get_db, get_config
from services.xxx import XxxService

router = APIRouter()

@router.get("/api/xxx")
async def get_xxx(db=Depends(get_db)):
    service = XxxService(db)
    return service.get_xxx()
```

**Task 4.3: `api/routes/dashboard.py`** — 4 endpoints: `/`, `/api/system/status`, `/api/market/indices`, `/api/market/north-flow`

**Task 4.4: `api/routes/watchlist.py`** — 6 endpoints: `/api/watchlist`, `/api/watchlist/add`, `/api/watchlist/delete`, `/api/watchlist/batch-add`, `/api/watchlist/clear`, `/api/watchlist/rescreen`

**Task 4.5: `api/routes/hot_stocks.py`** — 1 endpoint: `/api/hot-stocks`

**Task 4.6: `api/routes/portfolio.py`** — 6 endpoints: `/api/portfolio`, `/api/trades`, `/api/stock-info/{code}`, `/api/stock-info`, `/api/stock-info/rebuild`, `/api/stock/search`

**Task 4.7: `api/routes/workflow.py`** — 4 endpoints: `/api/workflow/status`, `/api/workflow/run`, `/api/workflow/cancel`, `/api/workflow/clear-logs`

**Task 4.8: `api/routes/risk.py`** — 4 endpoints: `/api/risk/audit`, `/api/risk/position`, `/api/strategy/monitor`, `/api/review/stats`

**Task 4.9: `api/routes/reports.py`** — 2 endpoints: `/api/reports`, `/api/reports/{filename}` (GET+DELETE)

**Task 4.10: `api/routes/email.py`** — 3 endpoints: `/api/email/config` (GET+POST), `/api/email/test`, `/api/email/send_report`

**Task 4.11: `api/routes/config.py`** — 4 endpoints: `/api/config`, `/api/config/model-role`, `/api/config/api-key`, `/api/config/test-api`

**Task 4.12: `api/routes/skills.py`** — 2 endpoints: `/api/skills`, `/api/models`

**Task 4.13: `api/routes/dataman.py`** — 8 endpoints: `/api/dataman/tables`, `/api/dataman/providers`, `/api/dataman/cache/clear`, `/api/dataman/stock/refresh`, `/api/dataman/db/rebuild`, `/api/dataman/rescreen`, `/api/dataman/watchlist/export`, `/api/dataman/watchlist/import`

**Task 4.14: `api/routes/system.py`** — 1 endpoint: `/api/system/logs`

---

## Phase 5: 清理与验证

### Task 5.1: Update start.bat

**Files:** Modify `start.bat`

```bat
%PYTHON_CMD% api/app.py
```

### Task 5.2: Delete old modules

删除以下旧目录和文件（~60 items）：
- `core/`, `data/`, `analysis/`, `decision/`, `workflow/`, `output/`, `interface/`
- Root旧文件: `web_app.py`, `data_fetcher.py`, `data_bus.py`, `data_access_layer.py`, `models.py`, `config_manager.py`, `config.json`, `llm_cache.py`, `skills.py`, `skill_analyzer.py`, `analysis_card.py`, `blackboard.py`, `unified_agent.py`, `multi_model_voter.py`, `debate_engine.py`, `decision_review.py`, `signal_extractor.py`, `super_workflow.py`, `workflow.py`, `optimizations.py`, `report_generator.py`, `email_report.py`, `performance.py`, `advanced_tools.py`, `main.py`, `orchestrator.py`, `scheduler.py`, `daily_runner.py`, `simulator.py`, `screen_watchlist.py`, `portfolio_optimizer.py`, `build_stock_db.py`
- 保留: `templates/`, `static/`, `config/`, `openclaw-skill/`, `scripts/`

### Task 5.3: End-to-end verification

- 启动: `python api/app.py`
- 验证: 所有 45 个端点返回 200
- 验证: 所有 12 个页面 section 正常渲染
- 验证: 仪表盘即时加载（无"加载中..."）
- 验证: 数据管理页 3 面板正常

---

## 验证命令

```bash
# 导入测试
python -c "
from shared.config import Config
from shared.models import init_db
from shared.dto import MarketContext, DecisionResult
from providers.database import get_session
from providers.cache import CacheManager
from providers.market_data import MarketDataProvider
print('ALL IMPORTS OK')
"

# 服务器测试
python api/app.py
# → http://localhost:8000

# 端点测试
for ep in / /api/system/status /api/market/indices /api/watchlist /api/portfolio \
  /api/hot-stocks /api/dataman/tables /api/risk/audit /api/workflow/status; do
  curl -s -o /dev/null -w "%{http_code} $ep\n" http://localhost:8000$ep
done
```
