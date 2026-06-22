# S14 — API接口定义

> **职责**: 定义前后端之间的REST API和SSE事件协议。前后端据此并行开发。

## 14.1 端点清单

| 方法 | 路径 | 用途 | 请求体 | 响应 |
|------|------|------|--------|------|
| POST | `/api/analysis` | 启动个股分析 | `AnalysisRequest` | `AnalysisJob` |
| GET | `/api/analysis/{job_id}` | 查询分析状态 | — | `AnalysisJob` |
| DELETE | `/api/analysis/{job_id}` | 取消分析任务 | — | `{"ok": true}` |
| GET | `/api/stream/{job_id}` | SSE实时推送 | — | `text/event-stream` |
| GET | `/api/dashboard` | Dashboard数据 | — | `DashboardData` |
| GET | `/api/portfolio` | 持仓列表 | — | `PortfolioSummary` |
| POST | `/api/portfolio/rebalance` | 再平衡建议 | — | `RebalancePlan` |
| GET | `/api/screening` | 选股结果 | `?style=value/growth/momentum` | `ScreeningResult` |
| POST | `/api/screening/run` | 执行选股 | `ScreeningRequest` | `ScreeningJob` |
| GET | `/api/reports` | 报告列表 | `?limit=20&offset=0` | `ReportList` |
| GET | `/api/reports/{id}` | 报告详情 | — | `ReportDetail` |
| GET | `/api/settings` | 获取配置 | — | `AppSettings` |
| PUT | `/api/settings` | 更新配置 | `AppSettings` | `AppSettings` |
| GET | `/api/health` | 健康检查 | — | `{"status": "ok"}` |

## 14.2 请求/响应Schema

### 分析请求

```python
class AnalysisRequest(BaseModel):
    ticker: str                          # 股票代码，如 "600519"
    date: Optional[str] = None           # 分析日期，默认今天
    fast_mode: bool = False              # 快速模式（跳过辩论）
    enable_masters: bool = False         # 启用大师视角

class AnalysisJob(BaseModel):
    job_id: str                          # UUID
    ticker: str
    status: Literal["pending", "running", "completed", "failed", "cancelled"]
    created_at: str                      # ISO 8601
    started_at: Optional[str]
    completed_at: Optional[str]
    progress: float                      # 0-100
    result: Optional["AnalysisResult"]
    error: Optional[str]
```

### 分析结果

```python
class AnalysisResult(BaseModel):
    ticker: str
    stock_name: str
    date: str

    # 分析师报告
    market_report: str                   # Markdown
    fundamentals_report: str
    news_report: str
    sentiment_report: str

    # 辩论记录
    investment_debate: List[DebateMessage]
    risk_debate: List[DebateMessage]

    # 决策
    trading_plan: TradingPlan            # 引用S08的TradingPlan schema

    # 元数据
    token_usage: int
    execution_time_seconds: float
    agents_executed: List[str]
```

### DebateMessage（辩论消息）

```python
class DebateMessage(BaseModel):
    speaker: str                         # Agent名称
    role: Literal["bull", "bear", "aggressive", "conservative", "neutral", "manager"]
    round: int                           # 轮次（从1开始）
    content: str                         # Markdown格式的发言内容
    timestamp: str                       # ISO 8601
    token_usage: Optional[int]           # 该条消息消耗的token数
```

### Dashboard数据

```python
class DashboardData(BaseModel):
    # 市场概览
    market_state: str                    # BULL/BEAR/NEUTRAL/PANIC/OVERHEAT
    index_summary: dict                  # {sh: {price, change_pct}, sz: ..., cy: ...}

    # 持仓摘要
    total_assets: float
    cash: float
    stock_value: float
    daily_return_pct: float
    cumulative_return_pct: float

    # 最近决策
    recent_decisions: List[RecentDecision]

    # 系统状态
    token_used_today: int
    token_budget_remaining: int
    active_jobs: int

class RecentDecision(BaseModel):
    ticker: str
    stock_name: str
    action: str                          # Buy/Sell/Hold
    date: str
    return_pct: Optional[float]          # 已实现收益率
```

### 持仓

```python
class PortfolioHolding(BaseModel):
    stock_code: str
    stock_name: str
    quantity: int
    buy_price: float
    current_price: float
    market_value: float
    profit_loss: float
    profit_loss_pct: float
    weight: float                        # 占总资金比例
    holding_days: int
    status: Literal["HOLDING", "SOLD"]

class PortfolioSummary(BaseModel):
    total_assets: float
    cash: float
    stock_value: float
    holdings: List[PortfolioHolding]
    daily_nav: List[NavPoint]            # 最近30天净值

class NavPoint(BaseModel):
    date: str
    total_asset: float
    daily_return_pct: float
    cumulative_return_pct: float
```

### 选股

```python
class ScreeningRequest(BaseModel):
    style: Literal["value", "growth", "momentum", "quality"]
    max_results: int = 20
    min_score: float = 60.0              # 最低综合评分
    exclude_st: bool = True
    exclude_new: bool = True             # 排除次新（上市<60天）
    min_turnover: float = 5000000        # 最低日成交额（元）

class ScreeningResult(BaseModel):
    run_id: str
    style: str
    total_screened: int
    stage1_passed: int                   # 硬性过滤后
    stage2_passed: int                   # 多因子评分后
    recommendations: List[ScreenStock]
    created_at: str

class ScreenStock(BaseModel):
    stock_code: str
    stock_name: str
    score: float                         # 综合评分
    pe_ratio: Optional[float]
    pb_ratio: Optional[float]
    roe: Optional[float]
    revenue_growth: Optional[float]
    momentum_20d: Optional[float]
    industry: str
```

### 报告

```python
class ReportList(BaseModel):
    reports: List[ReportSummary]
    total: int
    limit: int
    offset: int

class ReportSummary(BaseModel):
    id: str
    ticker: str
    stock_name: str
    date: str
    action: str
    confidence: float

class ReportDetail(BaseModel):
    id: str
    ticker: str
    stock_name: str
    date: str
    full_report: str                     # Markdown格式完整报告
    trading_plan: TradingPlan
    debate_summary: str
    token_usage: int
    execution_time_seconds: float
```

### 配置

```python
class AppSettings(BaseModel):
    # LLM配置
    llm_provider: str                    # deepseek/qwen/glm
    llm_quick_model: str                 # 日常分析模型
    llm_deep_model: str                  # 深度推理模型

    # 预算配置
    daily_token_budget: int              # 每日token预算
    per_stock_budget: int                # 单股分析预算

    # 辩论配置
    investment_debate_rounds: int        # 多空辩论轮次
    risk_debate_rounds: int              # 风险辩论轮次

    # 功能开关
    enable_masters: bool                 # 启用大师视角
    enable_memory: bool                  # 启用记忆系统
    fast_mode_threshold: float           # 快速模式触发阈值（0-1）

    # 数据源配置
    data_provider_priority: List[str]    # 数据源优先级
```

## 14.3 SSE事件类型

```python
# SSE事件类型定义（与S10 Section 10.5对齐）
class SSEEvent:
    """所有SSE事件的基类"""
    type: str

class AgentStatusEvent(SSEEvent):
    type: Literal["agent.status"]
    agent: str                           # Agent内部名
    status: Literal["pending", "in_progress", "completed", "error"]
    message: Optional[str]               # 状态描述

class AgentMessageEvent(SSEEvent):
    type: Literal["agent.message"]
    agent: str
    content: str                         # Markdown内容
    round: Optional[int]                 # 辩论轮次
    role: Optional[str]                  # bull/bear/aggressive等

class ReportChunkEvent(SSEEvent):
    type: Literal["report.chunk"]
    section: str                         # market_report/fundamentals_report等
    content: str                         # 文本片段（追加到已有内容）

class AgentTokenEvent(SSEEvent):
    type: Literal["agent.token"]
    agent: str
    tokens: int                          # 本次消耗token数
    total_tokens: int                    # 累计消耗

class JobCompletedEvent(SSEEvent):
    type: Literal["job.completed"]
    result: AnalysisResult

class JobFailedEvent(SSEEvent):
    type: Literal["job.failed"]
    error: str
    partial_result: Optional[AnalysisResult]  # 已完成的部分结果
```

### SSE事件流示例

```
event: agent.status
data: {"type":"agent.status","agent":"market_analyst","status":"in_progress","message":"获取K线数据"}

event: agent.status
data: {"type":"agent.status","agent":"market_analyst","status":"completed"}

event: agent.message
data: {"type":"agent.message","agent":"bull_researcher","content":"看涨论据...","round":1,"role":"bull"}

event: report.chunk
data: {"type":"report.chunk","section":"market_report","content":"## 技术面分析\n..."}

event: agent.token
data: {"type":"agent.token","agent":"market_analyst","tokens":1200,"total_tokens":1200}

event: job.completed
data: {"type":"job.completed","result":{...}}
```

## 14.4 错误码体系

| HTTP状态码 | 业务错误码 | 含义 | 前端行为 |
|-----------|-----------|------|----------|
| 200 | — | 成功 | — |
| 400 | — | 请求参数错误 | 提示用户修改 |
| 404 | — | 资源不存在 | 提示不存在 |
| 409 | ANALYSIS_RUNNING | 该股票已有分析任务在运行 | 提示等待或取消 |
| 429 | — | 请求过于频繁 | 自动重试 |
| 500 | INTERNAL_ERROR | 服务端内部错误 | 显示错误信息 |
| 503 | LLM_UNAVAILABLE | LLM API不可用 | 提示稍后重试 |

### 错误响应格式

```python
class ErrorResponse(BaseModel):
    error: str                           # 错误类型
    message: str                         # 用户友好消息
    detail: Optional[str]                # 技术细节（开发模式）
```

```json
{
    "error": "ANALYSIS_RUNNING",
    "message": "600519 正在分析中，请等待完成或取消当前任务",
    "detail": "job_id: abc-123, started_at: 2026-06-13T10:30:00Z"
}
```

## 14.5 认证与安全

**本地使用，无需复杂认证**：
- 默认无认证（localhost访问）
- 可选：API Key认证（用于远程访问）
- `.env`中的`API_KEY`环境变量控制
- 无认证时，仅允许127.0.0.1访问

## 14.6 速率限制

| 端点 | 限制 | 说明 |
|------|------|------|
| `/api/analysis` | 1次/秒 | 防止重复提交 |
| `/api/screening/run` | 1次/分钟 | 选股是重量级操作 |
| `/api/stream/{job_id}` | — | SSE长连接，无限制 |
| 其他GET端点 | 10次/秒 | 读操作无严格限制 |

## 14.7 WebSocket 端点（实时日志与系统状态）

> SSE（14.3）用于**单次分析任务**的流式推送（请求-响应模型）；WebSocket 用于**持续性的**系统级推送（服务端主动、无对应 HTTP 请求）。两者分工不同，不互相替代。

### 端点清单

| 端点 | 方向 | 用途 | 生命周期 |
|------|------|------|----------|
| `ws://127.0.0.1:8765/ws/logs` | 服务端→客户端 | 实时系统日志推送（WARNING 及以上） | 连接保持期间持续 |
| `ws://127.0.0.1:8765/ws/progress` | 双向 | 后台任务进度（选股/数据刷新等长任务） | 任务期间 |

### `/ws/logs` 协议

服务端在产生日志时主动推送 JSON 帧；客户端可发心跳保持连接。

**服务端推送帧**：
```json
{
  "ts": "2026-06-14T10:30:01.234",
  "level": "WARNING",
  "module": "data_bus",
  "message": "tencent.py 连续失败 3 次，切换到 sina.py"
}
```

**客户端心跳**（可选，防代理超时断开）：
```json
{"type": "ping"}
```
服务端收到 ping 后回 `{"type":"pong"}`，30 秒无心跳则服务端可主动关闭。

**连接管理**：
- 服务端维护 `_ws_clients: set[WebSocket]`，日志广播时遍历发送，发送失败的连接自动移除。
- 级别过滤：默认只推 `WARNING`/`ERROR`，客户端可在连接时通过 query param `?level=DEBUG` 调整。
- 不做消息补偿（断连期间的日志丢失），重要错误同时落盘文件日志供事后查询。

### `/ws/progress` 协议（后台长任务）

与 SSE 的区别：SSE 绑定单个 `job_id` 且任务结束即关闭；`/ws/progress` 是全局频道，可同时接收多个后台任务（如全市场选股 + 数据库维护）的进度。

**推送帧**：
```json
{
  "task_id": "screen_20260614_1030",
  "task_type": "screening",
  "progress": 0.45,
  "current": 2260,
  "total": 5000,
  "message": "正在扫描第 3 批"
}
```

**客户端控制帧**（双向）：
```json
{"type": "subscribe", "task_id": "screen_20260614_1030"}
{"type": "unsubscribe", "task_id": "screen_20260614_1030"}
```

### 为什么日志用 WebSocket 而非 SSE

| 维度 | SSE (/api/stream) | WebSocket (/ws/logs) |
|------|-------------------|----------------------|
| 模型 | 请求-响应（绑定 job_id） | 持续推送（无对应请求） |
| 生命周期 | 任务结束即关闭 | 连接保持期间持续 |
| 方向 | 单向（服务端→客户端） | 双向（客户端可发心跳/订阅） |
| HTTP 兼容 | 是（纯 HTTP） | 需协议升级 |
| 适用 | 单次分析的可视化 | 系统级日志、多任务进度 |

> 实现：FastAPI 原生支持 WebSocket（`@app.websocket`）。参考 `ConnectionManager` 模式管理连接集合。

---

**依赖**: S3(架构), S4(Agent), S8(风险), S10(前端)
**被依赖**: S10(前端), S12(路线图)
