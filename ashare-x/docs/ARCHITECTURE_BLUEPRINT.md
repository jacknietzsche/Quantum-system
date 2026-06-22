# A股智能投资系统 — 架构蓝图 v5.2

> **文档性质**: 项目最高架构权威。所有代码必须严格遵守此文档。  
> **最后更新**: 2026-05-08 (v5.3 — 东方财富热门股票 + 市场广度)  
> **设计原则**: 3层+1横切，单向依赖，SQLite优先，日频数据，5源降级

---

## 1. 架构总览

### 1.1 层级定义

```
┌──────────────────────────────────────────────┐
│  api/         路由层 — FastAPI endpoints      │
│  依赖: services + shared                     │
│  职责: 参数解析 → 调用service → 返回JSON       │
├──────────────────────────────────────────────┤
│  services/    业务层 — 核心逻辑               │
│  依赖: providers + shared                    │
│  职责: 业务编排、数据聚合、工作流调度          │
├──────────────────────────────────────────────┤
│  providers/   数据层 — 外部接入               │
│  依赖: shared                                │
│  职责: DB操作、HTTP调用、文件IO、缓存         │
├──────────────────────────────────────────────┤
│  shared/      横切共享 — 无业务依赖           │
│  职责: 配置、ORM模型、DTO、异常定义           │
└──────────────────────────────────────────────┘
```

### 1.2 依赖规则（硬约束）

```
允许: api → services → providers → shared
允许: 任意层 → shared
禁止: providers → services, providers → api
禁止: services → api
禁止: 同层横向依赖
禁止: 模块级全局可变状态
禁止: sys.path.insert()
禁止: 函数内延迟 import
```

### 1.3 设计原则

| # | 法则 | 实现 |
|---|------|------|
| L1 | 单向依赖 | api → services → providers → shared |
| L2 | 接口隔离 | 每层通过明确的函数签名通信，返回 DTO/dict |
| L3 | 单一职责 | 每文件 ≤ 200行，每个函数只做一件事 |
| L4 | 本地优先 | API 先读 SQLite/缓存立即返回，后台异步刷新 |
| L5 | 配置集中 | `shared/config.py` + `.env`，无 config.json |

---

## 2. 目录结构

```
a-share-investment-system/
│
├── shared/                         # 横切共享
│   ├── __init__.py
│   ├── config.py                   # Config 类
│   ├── models.py                   # 11 张 ORM 表
│   ├── dto.py                      # 8 个 frozen dataclass
│   └── exceptions.py               # 12 个异常类
│
├── providers/                      # 数据层
│   ├── __init__.py
│   ├── database.py                 # engine/session/init_db
│   ├── market_data.py              # 6源降级链封装
│   ├── llm.py                      # LLM 统一调用
│   ├── cache.py                    # 内存 TTL + 文件缓存
│   └── email_sender.py             # QQ邮箱 SMTP
│
├── services/                       # 业务层
│   ├── __init__.py
│   ├── market.py                   # 指数/北向/板块/热门股票
│   ├── watchlist.py                # 自选股 CRUD + 刷新
│   ├── portfolio.py                # 持仓管理 + 交易
│   ├── workflow.py                 # LangGraph 编排
│   ├── risk.py                     # 风控审计
│   └── data_mgmt.py                # 数据管理
│
├── api/                            # 路由层
│   ├── __init__.py
│   ├── app.py                      # FastAPI 工厂 + 生命周期
│   ├── deps.py                     # 依赖注入
│   └── routes/
│       ├── __init__.py
│       ├── dashboard.py            # 仪表盘 + 页面路由
│       ├── watchlist.py            # 自选股 API
│       ├── hot_stocks.py           # 热门股票 API
│       ├── portfolio.py            # 持仓 API
│       ├── workflow.py             # 工作流 API
│       ├── risk.py                 # 风控 API
│       ├── reports.py              # 报告 API
│       ├── email.py                # 邮箱 API
│       ├── config.py               # 配置 API
│       ├── skills.py               # 技能/模型 API
│       ├── dataman.py              # 数据管理 API
│       └── system.py               # 系统状态 API
│
├── templates/                      # Jinja2 HTML
│   ├── dashboard.html
│   └── watchlist.html
│
├── static/                         # 前端资源
│   ├── css/style.css
│   └── js/main.js
│
├── pyproject.toml
├── start.bat
└── .env
```

**总计: ~32 个 Python 文件，每个 ≤ 200 行**

---

## 3. Shared 层规范

### 3.1 `shared/config.py`

```python
class Config:
    """统一配置管理。加载顺序: 环境变量 > .env > config.yaml"""
    def __init__(self, config_dir: str = "config"):
        ...
    def get(self, key: str, default=None) -> Any: ...
    def get_model(self, role: str = "primary") -> dict: ...
    def get_api_key(self, provider: str) -> str: ...
    def get_email_config(self) -> dict: ...
```

### 3.2 `shared/models.py`

11 张 ORM 表：`Portfolio`, `TradeRecord`, `DailyReport`, `Watchlist`, `Order`, `Trade`, `DailyNAV`, `SystemLog`, `StockInfo`, `KlineCache`, `MarketSnapshot`

### 3.3 `shared/dto.py`

8 个 frozen dataclass：`StockSnapshot`, `MarketContext`, `AnalysisResult`, `DecisionResult`, `TradeSignal`, `RiskAssessment`, `PositionDetail`, `WorkflowRunResult`

### 3.4 `shared/exceptions.py`

12 个异常类：`SystemBaseError` → `DataSourceError`, `DataValidationError`, `DatabaseError`, `SkillExecutionError`, `LLMCallError`, `DecisionError`, `RiskRejectionError`, `WorkflowAbortError`, `WorkflowTimeoutError`, `ConfigError`, `DependencyNotFoundError`

---

## 4. Providers 层规范

### 4.1 `providers/database.py`

```python
def init_db(db_path: str = "data/investment.db") -> Engine: ...
def get_session() -> Session: ...
def get_engine() -> Engine: ...
```

### 4.2 `providers/market_data.py` — 多源日频数据 (v5.1)

**SQLite 优先原则**：所有请求先查本地 DB，没有再调外部源。外部获取成功后立即写入 DB。

**日频数据逻辑**：
- 17:00 前：最新有效日期 = 昨天
- 17:00 后：最新有效日期 = 今天
- trade_date 字段标记每行数据的交易日

**5 源降级链**（每源独立 8s 超时）：

```
Source 1: AKShare (akshare库, stock_zh_index_daily, stock_zh_a_spot_em)
    ↓ 失败/超时
Source 2: 腾讯财经 (HTTP GET qt.gtimg.cn, 批量50只)
    ↓ 失败/超时
Source 3: 新浪财经 (HTTP GET hq.sinajs.cn, 批量800只)
    ↓ 失败/超时
Source 4: efinance (efinance库, get_realtime_quotes)
    ↓ 失败/超时
Source 5: TickFlow (REST API, tk_89dc1988a3bb402482763eebe1b3d1af)
```

**核心接口**：

```python
class MarketDataProvider:
    def get_indices(self) -> dict: ...        # 4个主要指数日频数据
    def get_north_flow(self) -> dict: ...     # 北向资金净流入
    def get_sectors(self, top_n=10) -> list: ...  # 板块排名（含字段归一化）
    def get_stock_spot(self) -> DataFrame: ...     # 全市场快照
    def get_stock_kline(self, code, days=90) -> DataFrame: ...  # 个股K线
    def get_stock_basic(self, code) -> dict: ...     # 个股基本面

    # 内部: 每个源是独立方法，通过 _try_sources 按优先级调用
    def _try_sources(self, method_name, *args) -> Optional[Any]: ...
    def _source_akshare(self, method, *args) -> Any: ...
    def _source_tencent(self, method, *args) -> Any: ...
    def _source_sina(self, method, *args) -> Any: ...
    def _source_efinance(self, method, *args) -> Any: ...
    def _source_tickflow(self, method, *args) -> Any: ...
```

### 4.3 `providers/cache.py`

```python
class CacheManager:
    def get(self, key: str) -> Optional[Any]: ...
    def get_or_stale(self, key: str, stale_seconds=300) -> Optional[Any]: ...
    def set(self, key: str, value, ttl_seconds=60, stale_seconds=300): ...
    def invalidate(self, key: str = None): ...
    def llm_get(self, prompt: str, context: dict, category: str) -> Optional[str]: ...
    def llm_set(self, prompt: str, response: str, context: dict, category: str): ...
    def clear_all(self): ...  # 清除内存 + 文件缓存
```

### 4.4 `providers/llm.py`

```python
class LLMCaller:
    """多模型统一调用"""
    def call(self, model: str, prompt: str, **kwargs) -> dict: ...
    def call_with_fallback(self, prompt: str, **kwargs) -> dict: ...

# 支持的提供商: deepseek, siliconflow, chatanywhere, juguang, cherryin, openai, ollama
```

### 4.5 `providers/email_sender.py`

```python
class EmailSender:
    def send(self, subject: str, body: str, to: list = None) -> bool: ...
    def send_report(self, report_path: str) -> bool: ...
```

---

## 5. Services 层规范

### 5.1 `services/market.py`

```python
class MarketService:
    """市场数据服务 — 本地优先"""
    def __init__(self, db_session, market_provider, cache): ...
    def get_indices(self, background_refresh=True) -> dict: ...
    def get_north_flow(self, background_refresh=True) -> dict: ...
    def get_hot_stocks(self, sort="turnover", limit=100) -> list: ...
    def get_sectors(self) -> list: ...

    # 内部: 先读 market_snapshot 表 → 命中立即返回 → 后台异步刷新
```

### 5.2 `services/watchlist.py`

```python
class WatchlistService:
    def __init__(self, db_session, market_provider): ...
    def get_all(self) -> list: ...
    def add(self, code, name, category="股票", reason="") -> dict: ...
    def delete(self, code) -> bool: ...
    def clear(self) -> int: ...
    def export_csv(self) -> str: ...
    def import_csv(self, csv_text) -> dict: ...
```

### 5.3 `services/portfolio.py`

```python
class PortfolioService:
    def __init__(self, db_session): ...
    def get_holdings(self) -> list: ...
    def get_trades(self, limit=50) -> list: ...
    def get_stock_info(self, code) -> dict: ...
    def search_stocks(self, query, limit=20) -> list: ...
```

### 5.4 `services/workflow.py`

```python
class WorkflowService:
    """LangGraph 工作流编排"""
    def __init__(self, db_session, llm_caller, market_provider): ...
    def run_super(self, stock_code=None, progress_callback=None, abort_check=None) -> dict: ...
    def run_standard(self) -> dict: ...
    def get_status(self) -> dict: ...
    def cancel(self) -> bool: ...
    def clear_logs(self): ...
```

### 5.5 `services/risk.py`

```python
class RiskService:
    def __init__(self, db_session): ...
    def audit(self) -> dict: ...      # 风控审计
    def position_plan(self, risk_score) -> dict: ...  # 仓位规划
    def get_review_stats(self) -> dict: ...  # 决策复盘统计
```

### 5.6 `services/data_mgmt.py`

```python
class DataManagementService:
    def __init__(self, db_session, cache_manager): ...
    def get_table_stats(self) -> dict: ...
    def get_provider_status(self) -> dict: ...
    def clear_cache(self) -> dict: ...
    def refresh_stock(self, code) -> dict: ...
    def rebuild_db(self) -> dict: ...
    def rescreen(self) -> dict: ...
```

---

## 6. API 层规范

### 6.1 `api/app.py`

```python
def create_app() -> FastAPI:
    """应用工厂。注册所有路由、挂载静态文件、配置生命周期"""
    ...
    # 注册 12 个路由模块
    # 挂载 /static 和 /templates
    # @app.on_event("startup") → 预热缓存
```

### 6.2 `api/deps.py`

```python
def get_db() -> Session: ...          # 数据库会话
def get_config() -> Config: ...       # 配置
def get_cache() -> CacheManager: ...  # 缓存
def get_market_provider() -> MarketDataProvider: ...  # 市场数据
def get_llm() -> LLMCaller: ...       # LLM
```

### 6.3 路由文件模板

每个路由文件遵循统一模式：

```python
# api/routes/xxx.py
from fastapi import APIRouter, Depends
from api.deps import get_db, get_config
from services.xxx import XxxService

router = APIRouter()

@router.get("/api/xxx")
async def get_xxx(db=Depends(get_db)):
    service = XxxService(db)
    return service.get_xxx()
```

### 6.4 路由 → 端点完整映射

| 路由文件 | 端点数 | 端点路径 |
|---------|--------|---------|
| `dashboard.py` | 4 | `/`, `/api/system/status`, `/api/market/indices`, `/api/market/north-flow` |
| `watchlist.py` | 6 | `/api/watchlist` (GET+POST add/delete/batch-add/clear/rescreen) |
| `hot_stocks.py` | 1 | `/api/hot-stocks` |
| `portfolio.py` | 6 | `/api/portfolio`, `/api/trades`, `/api/stock-info/*`, `/api/stock/search` |
| `workflow.py` | 4 | `/api/workflow/status`, `/run`, `/cancel`, `/clear-logs` |
| `risk.py` | 4 | `/api/risk/audit`, `/risk/position`, `/strategy/monitor`, `/review/stats` |
| `reports.py` | 2 | `/api/reports`, `/api/reports/{filename}` |
| `email.py` | 3 | `/api/email/config`, `/email/test`, `/email/send_report` |
| `config.py` | 4 | `/api/config`, `/config/model-role`, `/config/api-key`, `/config/test-api` |
| `skills.py` | 2 | `/api/skills`, `/api/models` |
| `dataman.py` | 8 | `/api/dataman/*` |
| `system.py` | 1 | `/api/system/logs` |
| **总计** | **45** | |

---

## 7. 数据流规范 (v5.1)

### 7.1 SQLite 优先 + 日频数据

```
请求 → Service
       → SELECT * FROM market_snapshot WHERE trade_date = 最新有效日期
       → 命中: 立即返回 (≤50ms)
       → 未命中:
            → SELECT * FROM market_snapshot ORDER BY trade_date DESC LIMIT 1
            → 命中: 返回昨日前天数据 + "昨日数据"
            → 未命中:
                 → 5源降级链逐个尝试 (每源8s超时)
                 → 成功: INSERT INTO market_snapshot → 返回
                 → 全部失败: 返回空 + "数据暂不可用"
```

### 7.2 日频日期判断

```python
def _latest_trade_date():
    now = datetime.now()
    if now.hour >= 17:
        return today       # 17:00后，今日数据已出
    else:
        return yesterday   # 17:00前，最新有效数据是昨天
```

### 7.3 外部源超时保护

每个外部数据源调用在独立线程中执行，超时 8s：
```python
with ThreadPoolExecutor(max_workers=1) as executor:
    future = executor.submit(source_fn)
    return future.result(timeout=8)
```

### 7.4 字段归一化

```python
SECTOR_FIELD_MAP = {
    "板块名称": "name", "涨跌幅": "change_pct", "换手率": "turnover",
    "排名": "rank", "最新价": "price", "成交额": "amount",
}
```

---

## 8. 前端兼容性

保持与现有 `static/js/main.js`、`static/css/style.css`、`templates/dashboard.html` 100% 兼容：
- 所有 API 路径不变
- 所有响应 JSON 格式不变
- 所有字段名不变

---

## 9. 迁移计划

### Phase 1: 基础设施 (shared/)
1. 创建 `shared/config.py`
2. 创建 `shared/models.py`（从 root `models.py` 迁移）
3. 创建 `shared/dto.py`
4. 创建 `shared/exceptions.py`

### Phase 2: 数据层 (providers/)
5. 创建 `providers/database.py`
6. 创建 `providers/cache.py`
7. 创建 `providers/market_data.py`
8. 创建 `providers/llm.py`
9. 创建 `providers/email_sender.py`

### Phase 3: 业务层 (services/)
10-15. 创建 6 个 service 模块

### Phase 4: 路由层 (api/)
16. 创建 `api/app.py` + `api/deps.py`
17-28. 创建 12 个路由文件

### Phase 5: 清理 ✅ 已完成

项目当前结构（v5.2）：

```
a-share-investment-system/
├── shared/          (4 files)  config, models, dto, exceptions
├── providers/       (5 files)  database, cache, market_data, llm, email_sender
├── services/        (6 files)  market, watchlist, portfolio, workflow, risk, data_mgmt
├── api/             (14 files) app, deps, 12 routes
├── templates/       dashboard.html + watchlist.html
├── static/          css/style.css + js/main.js
├── models.py        ORM 兼容保留
├── super_workflow.py  工作流引擎（遗留）
├── workflow.py        标准工作流（遗留）
├── decision_review.py 决策复盘（遗留）
├── build_stock_db.py  股票数据库构建
├── screen_watchlist.py 自选股筛选
├── orchestrator.py    投资编排器
├── scheduler.py       告警管理
├── advanced_tools.py  策略监控
├── optimizations.py   回测/压力测试
├── data/investment.db SQLite 数据库
├── start.bat
└── pyproject.toml
```

**已删除**: 7个旧包目录(core/data/analysis/decision/workflow/output/interface) + 22个旧.py文件

---

## 10. 验证标准

- [x] `python api/app.py` 启动成功
- [x] 所有 24 GET + 10 POST 端点返回 200
- [x] 所有 12 个页面 section 正常渲染
- [x] 仪表盘数据即时加载 — 4个实时指数 ~500ms
- [x] 数据管理页面 3 面板功能正常
- [x] 删除旧模块后服务器正常启动 (52 routes)
- [x] 5源降级链: 腾讯→新浪→efinance→TickFlow→AKShare
- [x] SQLite 优先 + 日频17:00判断 + trade_date 标记
