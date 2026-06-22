# AShare-X 最终优化方案

> 日期: 2026-05-09 | 4项优化 | 数据库优先 + A股适配 + 日频策略兼容

---

## 一、A股特色数据工具（数据库优先）

**原则**: SQLite缓存 → AkShare API降级 → 过期数据兜底

### 新增 `services/ashare_data_tools.py`

```python
class AShareDataTools:
    def get_lhb_detail(self, stock_code, date=None):
        """龙虎榜明细 — DB缓存(TTL=24h) → AkShare → 空"""
        # 1. 查 KlineCache 扩展表或 MarketSnapshot(lhb_{code}_{date})
        # 2. Miss → ak.stock_sina_lhb_detail_daily() 
        # 3. 回填DB，返回结构化dict

    def get_fund_flow(self, stock_code, days=5):
        """个股主力资金流 — DB缓存(TTL=5min盘中/24h盘后) → AkShare → 空"""
        # ak.stock_individual_fund_flow() → 近N日主力净流向
        # 日频策略：仅取昨日/最近交易日数据

    def get_limit_up_pool(self, date=None):
        """涨停板情绪池 — DB缓存(TTL=日频) → AkShare → 空"""
        # ak.stock_zt_pool_em() → 涨停股票列表+连板数+封单比
        # 日频策略：每日收盘后跑一次，存MarketSnapshot

    def get_hot_stocks(self):
        """人气热度 — DB缓存(TTL=1h) → 东财API → 空"""
        # EastMoney hot list → 热股排名
```

**关键适配**：
- 股票代码统一处理：`600519` → AkShare需要 `600519`(纯数字)，Baostock需要 `sh.600519`
- 日频策略：工具默认取昨日/最近交易日数据，不依赖实时行情
- 数据回填：每次API调用成功→自动写入对应缓存表

---

## 二、终端UI增强 (rich)

### 改造 `main.py` 的输出

```python
from rich.console import Console
from rich.table import Table
from rich.progress import Progress
from rich.panel import Panel

console = Console()

# 单股分析 → 富文本表格
def cmd_analyze(args):
    table = Table(title=f"🔍 {name}({code}) 深度分析")
    table.add_column("分析师", style="cyan")
    table.add_column("得分", style="magenta")
    table.add_column("信号", style="green")
    # ...
    console.print(table)

# 选股 → 进度条替代轮询
def cmd_screen(args):
    with Progress() as progress:
        task = progress.add_task("[cyan]三级漏斗选股...", total=3)
        # Stage 1
        progress.update(task, description="[yellow]Stage 1/3: 量化初筛...")
        stage1 = StockScreener._stage1_quant_filter(...)
        progress.advance(task)
        # ...
```

**适配**：`python main.py` 默认桌面模式保持简洁；`rich` 仅在无头CLI命令中激活

---

## 三、交易日历

### 新增 `services/trading_calendar.py`

```python
class TradingCalendar:
    def __init__(self):
        # 从 MarketSnapshot 加载缓存日历，或调用 ak.tool_trade_date_hist_sina()
        self._calendar = self._load_calendar()
    
    def is_trading_day(self, date=None) -> bool:
        """判断是否A股交易日（含节假日+调休）"""
    
    def next_trading_day(self, date=None) -> str:
        """获取下一个交易日"""
    
    def previous_trading_day(self, date=None) -> str:
        """获取上一个交易日（日频策略常用）"""
    
    def trading_days_between(self, start, end) -> List[str]:
        """获取区间内交易日列表"""
```

**日频策略适配**：
- `main.py daily` 用 `TradingCalendar.is_trading_day()` 替代 `weekday() < 5`
- scheduler 用 `next_trading_day()` 自动跳过节假日
- MarketDataProvider 用 `previous_trading_day()` 取最近有效数据

---

## 四、输出标准化 + 流式进度

### Pydantic 信号合约

```python
# shared/signals.py
from pydantic import BaseModel, Field
from typing import Literal

class AnalysisSignal(BaseModel):
    analyst: str
    signal: Literal["bullish", "bearish", "neutral"]
    confidence: float = Field(ge=0, le=1)
    score: float = Field(ge=0, le=100)
    reasoning: str = ""

class ScreeningResult(BaseModel):
    stock_code: str
    stock_name: str
    rank: int
    score: float
    signal: str
    confidence: float
    reason: str
```

### 流式进度

`api/routes/screening.py` 的轮询改为 SSE (Server-Sent Events)：

```python
@router.get("/run/stream")
async def run_screening_stream():
    async def generate():
        yield f"data: {json.dumps({'stage': 1, 'msg': '量化初筛'})}\n\n"
        stage1 = ss._stage1_quant_filter(...)
        yield f"data: {json.dumps({'stage': 2, 'msg': f'基本面过滤({len(stage1)}只)'})}\n\n"
        # ...
        yield f"data: {json.dumps({'stage': 'done', 'results': [...]})}\n\n"
    return StreamingResponse(generate(), media_type="text/event-stream")
```

前端 `Screening.jsx` 用 `EventSource` 替代 `setInterval` 轮询。

---

## 实施优先级

| 序号 | 优化项 | 工作量 | 影响 |
|------|--------|--------|------|
| 1 | 交易日历 | 30min | 高 — 防止节假日误触发 |
| 2 | rich终端UI | 1h | 中 — 改善CLI体验 |
| 3 | A股数据工具 | 2h | 高 — 新增龙虎榜/资金流数据 |
| 4 | Pydantic+SSE流式 | 1.5h | 中 — 改善前端体验 |

**总工时**: ~5小时
