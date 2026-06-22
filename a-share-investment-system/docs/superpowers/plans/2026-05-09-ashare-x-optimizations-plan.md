# AShare-X 最终优化实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 4项终端优化 — 交易日历、rich UI、A股数据工具、Pydantic+SSE流式

**Architecture:** 每项独立实现，数据库优先(AQLite缓存→API降级)，日频策略适配(T+1/最近交易日)

**Tech Stack:** rich, akshare, chinese_calendar, pydantic, SSE

**Spec:** `docs/superpowers/specs/2026-05-09-ashare-x-final-optimizations.md`

---

## 文件变更映射

```
services/trading_calendar.py    [新建] A股交易日历
services/ashare_data_tools.py   [新建] 龙虎榜/资金流/涨停池
shared/signals.py               [新建] Pydantic信号模型
main.py                         [修改] rich终端UI
api/routes/screening.py         [修改] SSE流式进度
electron/src/pages/Screening.jsx [修改] EventSource替代轮询
```

---

### Task 1: 交易日历

**Files:**
- Create: `services/trading_calendar.py`
- Modify: `main.py` (daily/schedule命令)

- [ ] **Step 1: 安装依赖**

```bash
pip install chinese-calendar
```

- [ ] **Step 2: 创建 `services/trading_calendar.py`**

```python
"""A股交易日历 — 数据库缓存 + AkShare降级"""
from datetime import datetime, timedelta
from services.base import ServiceResult, BaseService


class TradingCalendar(BaseService):
    """A股交易日历（含节假日+调休），数据库优先"""

    def __init__(self):
        super().__init__()
        self._cache = None

    def _ensure_cache(self):
        if self._cache is not None:
            return
        try:
            from chinese_calendar import is_workday
            self._using_chinese_calendar = True
        except ImportError:
            self._using_chinese_calendar = False

    def is_trading_day(self, date=None) -> bool:
        """判断是否A股交易日（排除周末+节假日+调休）"""
        self._ensure_cache()
        target = datetime.strptime(date, "%Y-%m-%d") if isinstance(date, str) else (date or datetime.now())
        if hasattr(target, 'date'):
            target = target.date() if hasattr(target, 'date') else target

        if self._using_chinese_calendar:
            from chinese_calendar import is_workday
            weekday = target.weekday()
            return weekday < 5 and is_workday(target)
        return target.weekday() < 5

    def previous_trading_day(self, date=None) -> str:
        """获取上一个交易日（日频策略核心）"""
        target = datetime.strptime(date, "%Y-%m-%d") if isinstance(date, str) else (date or datetime.now())
        if hasattr(target, 'date'):
            target = datetime.combine(target, datetime.min.time())
        target -= timedelta(days=1)
        while not self.is_trading_day(target):
            target -= timedelta(days=1)
        return target.strftime("%Y-%m-%d")

    def next_trading_day(self, date=None) -> str:
        """获取下一个交易日"""
        target = datetime.strptime(date, "%Y-%m-%d") if isinstance(date, str) else (date or datetime.now())
        if hasattr(target, 'date'):
            target = datetime.combine(target, datetime.min.time())
        target += timedelta(days=1)
        while not self.is_trading_day(target):
            target += timedelta(days=1)
        return target.strftime("%Y-%m-%d")

    def today_str(self) -> str:
        return datetime.now().strftime("%Y-%m-%d")
```

- [ ] **Step 3: 修改 `main.py` — `is_trading_day()` 替换**

在 `main.py` 顶部，删除旧函数，改为：
```python
from services.trading_calendar import TradingCalendar
_trading_cal = TradingCalendar()

def is_trading_day(date=None):
    return _trading_cal.is_trading_day(date)
```

在 `cmd_daily` 和 `cmd_schedule` 中使用 `_trading_cal.previous_trading_day()` 获取有效数据日期。

- [ ] **Step 4: 验证**

```bash
python -c "
from services.trading_calendar import TradingCalendar
tc = TradingCalendar()
print(f'Today trading: {tc.is_trading_day()}')
print(f'Previous trading: {tc.previous_trading_day()}')
print(f'Next trading: {tc.next_trading_day()}')
"
```

- [ ] **Step 5: Commit**

```bash
git add services/trading_calendar.py main.py
git commit -m "feat: add A-share trading calendar with holiday detection"
```

---

### Task 2: rich终端UI

**Files:**
- Modify: `main.py`

- [ ] **Step 1: 安装rich**

```bash
pip install rich
```

- [ ] **Step 2: 改造 `cmd_analyze` — 富文本表格**

在 `main.py` 替换 `cmd_analyze` 函数：

```python
def cmd_analyze(args):
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from services.quant_analyzers import QuantAnalyzers
    from services.factor_farm import FactorFarm
    from services.market_perception import MarketPerception

    console = Console()
    code = args.code
    qa = QuantAnalyzers()
    ff = FactorFarm()

    with console.status(f"[cyan]分析 {code}..."):
        regime = MarketPerception().perceive({
            "breadth": {"up": 2000, "down": 2000, "total": 5000, "limit_up": 30, "limit_down": 25},
            "indices": {},
        })
        f = {"roe": 18, "debt_to_equity": 35, "gross_margin": 55, "eps": 5.2, "bvps": 28,
             "price": 120, "pe_ratio": 23, "earnings_growth_3y": 12, "cash_to_assets": 15}
        buffett = qa.buffett_analyze(code, f)
        graham = qa.graham_analyze(code, f)
        lynch = qa.lynch_analyze(code, f)
        factors = ff.get_top_factors(5)

    # 表头
    reg = regime.data
    console.print(Panel(f"📊 市场: {reg['regime']} | 仓位: {reg['adaptive_params']['target_position_pct']:.0%}",
                        style="bold blue"))

    # 估值表格
    table = Table(title=f"{code} 估值分析")
    table.add_column("分析师", style="cyan")
    table.add_column("得分", style="magenta")
    table.add_column("信号")
    for name, r in [("巴菲特", buffett), ("格雷厄姆", graham), ("林奇", lynch)]:
        sig_style = "green" if r["signal"] == "bullish" else ("red" if r["signal"] == "bearish" else "yellow")
        table.add_row(name, str(r["score"]), f"[{sig_style}]{r['signal']}[/{sig_style}]")
    console.print(table)

    # 因子
    ft = Table(title="Top 5 有效因子")
    ft.add_column("因子", style="cyan"); ft.add_column("IC", style="magenta"); ft.add_column("类别")
    for f_item in factors.data.get("factors", [])[:5]:
        ft.add_row(f_item["name"], f"{f_item.get('ic_mean', 0):.3f}", f_item.get("category", ""))
    console.print(ft)
    return 0
```

- [ ] **Step 3: 改造 `cmd_screen` — 进度条**

```python
def cmd_screen(args):
    from rich.console import Console
    from rich.table import Table
    from rich.progress import Progress
    from services.stock_screener import StockScreener

    console = Console()
    ss = StockScreener()

    with Progress() as progress:
        task = progress.add_task("[cyan]三级漏斗选股...", total=3)
        progress.update(task, description="[yellow]Stage 1/3: 量化初筛...")
        result = ss.run(top_n=args.top or 8)

        d = result.data
        progress.update(task, advance=1, description=f"[yellow]Stage 2/3: 基本面过滤({d['stage1_passed']}只)...")
        progress.update(task, advance=1, description=f"[yellow]Stage 3/3: 深度分析({d['stage2_passed']}只)...")
        progress.update(task, advance=1, description="[green]完成!")

    console.print(f"\n全市场 {d['total_screened']} → 推荐 {d['stage3_recommended']} 只\n")

    table = Table(title="选股结果")
    table.add_column("#", style="dim")
    table.add_column("股票", style="cyan")
    table.add_column("得分", style="magenta")
    table.add_column("信号")
    table.add_column("逻辑", style="dim")

    for r in d.get("recommendations", []):
        sig = r["signal"]
        sig_style = "green" if sig == "买入" else ("yellow" if sig == "持有" else "dim")
        table.add_row(str(r["rank"]), f"{r['stock_name']}({r['stock_code']})",
                       str(r["score"]), f"[{sig_style}]{sig}[/{sig_style}]",
                       r.get("reason", "")[:40])
    console.print(table)
    return 0
```

- [ ] **Step 4: 验证**

```bash
python main.py analyze 600519
python main.py screen --top 5
```

预期：彩色表格输出 + 进度条动画

- [ ] **Step 5: Commit**

```bash
git add main.py
git commit -m "feat: add rich terminal UI with colored tables and progress bars"
```

---

### Task 3: A股数据工具（龙虎榜/资金流/涨停池）

**Files:**
- Create: `services/ashare_data_tools.py`

- [ ] **Step 1: 创建 `services/ashare_data_tools.py`**

```python
"""A股特色数据工具 — 龙虎榜/主力资金/涨停板 — 数据库优先"""
from datetime import datetime, timedelta
from services.base import ServiceResult, BaseService
from services.trading_calendar import TradingCalendar


class AShareDataTools(BaseService):
    """A股特色数据：龙虎榜、主力资金、涨停池。日频策略适配"""

    def __init__(self, db_path: str = "data/investment.db"):
        super().__init__()
        self.db_path = db_path
        self._calendar = TradingCalendar()

    # ════════════════════════════════════════════
    #  龙虎榜
    # ════════════════════════════════════════════

    def get_lhb_detail(self, stock_code: str, date: str = None) -> ServiceResult:
        """
        龙虎榜明细 — DB缓存(24h) → AkShare → 降级空
        返回: 买入/卖出席位、净买入额、知名游资标记
        """
        date = date or self._calendar.previous_trading_day()

        # 1. DB缓存
        cached = self._read_cache("lhb", stock_code, date)
        if cached:
            return ServiceResult.ok(data=cached)

        # 2. AkShare
        try:
            import akshare as ak
            df = ak.stock_sina_lhb_detail_daily(date=date.replace("-", ""))
            if df is not None and not df.empty:
                # 筛选该股票
                stock_rows = df[df["code"] == stock_code]
                if not stock_rows.empty:
                    result = {
                        "date": date,
                        "stock_code": stock_code,
                        "entries": stock_rows.head(20).to_dict("records"),
                        "buy_amount": float(stock_rows[stock_rows["type"] == "买"].sum(numeric_only=True).get("amount", 0) or 0),
                        "sell_amount": float(stock_rows[stock_rows["type"] == "卖"].sum(numeric_only=True).get("amount", 0) or 0),
                    }
                    self._write_cache("lhb", stock_code, date, result)
                    return ServiceResult.ok(data=result)
        except Exception as e:
            pass

        return ServiceResult.ok(data={"date": date, "stock_code": stock_code, "entries": [], "note": "无龙虎榜数据"})

    # ════════════════════════════════════════════
    #  主力资金流
    # ════════════════════════════════════════════

    def get_fund_flow(self, stock_code: str, days: int = 5) -> ServiceResult:
        """
        个股主力资金近N日净流向 — DB缓存(盘后24h) → AkShare → 降级空
        日频策略: 默认取近5个交易日数据
        """
        end_date = self._calendar.previous_trading_day()
        start_date = self._calendar.previous_trading_day(
            (datetime.strptime(end_date, "%Y-%m-%d") - timedelta(days=days * 2)).strftime("%Y-%m-%d")
        )

        # 1. DB
        cache_key = f"fundflow_{stock_code}_{start_date}_{end_date}"
        cached = self._read_snapshot(cache_key)
        if cached:
            return ServiceResult.ok(data=cached)

        # 2. AkShare
        try:
            import akshare as ak
            df = ak.stock_individual_fund_flow(stock=stock_code, market="sh" if stock_code.startswith("6") else "sz")
            if df is not None and not df.empty:
                recent = df.tail(days)
                result = {
                    "stock_code": stock_code,
                    "data": recent.to_dict("records"),
                    "net_flow_5d": float(recent["net_amount"].sum() if "net_amount" in recent.columns else 0),
                    "main_force_direction": "流入" if recent["net_amount"].sum() > 0 else "流出" if "net_amount" in recent.columns else "未知",
                }
                self._write_snapshot(cache_key, result)
                return ServiceResult.ok(data=result)
        except Exception:
            pass

        return ServiceResult.ok(data={"stock_code": stock_code, "net_flow_5d": 0, "note": "数据暂不可用"})

    # ════════════════════════════════════════════
    #  涨停板情绪池
    # ════════════════════════════════════════════

    def get_limit_up_pool(self, date: str = None) -> ServiceResult:
        """
        涨停板情绪池 — 涨停数/连板数/封单比 → 市场情绪温度计
        日频策略: 每日收盘后调用
        """
        date = date or self._calendar.previous_trading_day()
        cache_key = f"zt_pool_{date}"
        cached = self._read_snapshot(cache_key)
        if cached:
            return ServiceResult.ok(data=cached)

        try:
            import akshare as ak
            df = ak.stock_zt_pool_em(date=date.replace("-", ""))
            if df is not None and not df.empty:
                result = {
                    "date": date,
                    "total": len(df),
                    "boards": df["连板数"].value_counts().to_dict() if "连板数" in df.columns else {},
                    "top_stocks": df.head(10)[["代码", "名称", "连板数", "封单金额"]].to_dict("records") if "连板数" in df.columns else [],
                    "sentiment": "极热" if len(df) > 100 else ("热" if len(df) > 50 else ("温" if len(df) > 20 else "冷")),
                }
                self._write_snapshot(cache_key, result)
                return ServiceResult.ok(data=result)
        except Exception:
            pass

        return ServiceResult.ok(data={"date": date, "total": 0, "note": "数据暂不可用"})

    # ════════════════════════════════════════════
    #  缓存辅助
    # ════════════════════════════════════════════

    def _read_cache(self, category: str, stock_code: str, date: str):
        try:
            from models import MarketSnapshot, get_session
            key = f"{category}_{stock_code}_{date}"
            session = get_session(self.db_path)
            row = session.query(MarketSnapshot).filter_by(snapshot_type=key).first()
            session.close()
            if row and row.data_json:
                import json
                age = (datetime.now() - row.updated_at).total_seconds()
                if age < 86400:
                    return json.loads(row.data_json)
        except Exception:
            pass
        return None

    def _write_cache(self, category: str, stock_code: str, date: str, data: dict):
        try:
            from models import MarketSnapshot, get_session
            import json
            key = f"{category}_{stock_code}_{date}"
            session = get_session(self.db_path)
            row = session.query(MarketSnapshot).filter_by(snapshot_type=key).first()
            if row:
                row.data_json = json.dumps(data, ensure_ascii=False, default=str)
                row.updated_at = datetime.now()
            else:
                session.add(MarketSnapshot(snapshot_type=key, data_json=json.dumps(data, ensure_ascii=False, default=str), updated_at=datetime.now()))
            session.commit()
            session.close()
        except Exception:
            pass

    def _read_snapshot(self, key: str):
        try:
            from models import MarketSnapshot, get_session
            import json
            session = get_session(self.db_path)
            row = session.query(MarketSnapshot).filter_by(snapshot_type=key).first()
            session.close()
            if row and row.data_json:
                age = (datetime.now() - row.updated_at).total_seconds()
                if age < 86400:
                    return json.loads(row.data_json)
        except Exception:
            pass
        return None

    def _write_snapshot(self, key: str, data: dict):
        try:
            from models import MarketSnapshot, get_session
            import json
            session = get_session(self.db_path)
            row = session.query(MarketSnapshot).filter_by(snapshot_type=key).first()
            if row:
                row.data_json = json.dumps(data, ensure_ascii=False, default=str)
                row.updated_at = datetime.now()
            else:
                session.add(MarketSnapshot(snapshot_type=key, data_json=json.dumps(data, ensure_ascii=False, default=str), updated_at=datetime.now()))
            session.commit()
            session.close()
        except Exception:
            pass
```

- [ ] **Step 2: 验证**

```bash
python -c "
from services.ashare_data_tools import AShareDataTools
adt = AShareDataTools()
print('LHB:', adt.get_lhb_detail('600519').data.get('note', 'has data'))
print('FundFlow:', adt.get_fund_flow('600519').data.get('note', 'has data'))
print('ZTPool:', adt.get_limit_up_pool().data.get('note', 'has data'))
"
```

- [ ] **Step 3: Commit**

```bash
git add services/ashare_data_tools.py
git commit -m "feat: add A-share data tools (LHB/fund flow/limit-up pool) with DB-first caching"
```

---

### Task 4: Pydantic信号模型 + SSE流式进度

**Files:**
- Create: `shared/signals.py`
- Modify: `api/routes/screening.py`
- Modify: `electron/src/pages/Screening.jsx`

- [ ] **Step 1: 创建 `shared/signals.py`**

```python
"""Pydantic信号模型 — 标准化输出合约"""
from pydantic import BaseModel, Field
from typing import Literal, Optional


class AnalysisSignal(BaseModel):
    analyst: str
    signal: Literal["bullish", "bearish", "neutral"]
    confidence: float = Field(ge=0, le=1, default=0.5)
    score: float = Field(ge=0, le=100, default=50)
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

- [ ] **Step 2: 在 `api/routes/screening.py` 添加SSE端点**

```python
import asyncio, json
from fastapi.responses import StreamingResponse

@router.get("/run/stream")
async def run_screening_stream():
    async def generate():
        from services.stock_screener import StockScreener
        ss = StockScreener()

        yield f"data: {json.dumps({'stage': 1, 'msg': '加载全市场股票池...'}, ensure_ascii=False)}\n\n"
        await asyncio.sleep(0.1)

        result = ss.run()
        d = result.data

        yield f"data: {json.dumps({'stage': 3, 'msg': f'完成! 全市场{d[\"total_screened\"]}→推荐{d[\"stage3_recommended\"]}只', 'results': d}, ensure_ascii=False)}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")
```

- [ ] **Step 3: 更新前端 `Screening.jsx` 使用 EventSource**

```jsx
const runScreening = () => {
  setStatus({ running: true, progress: 0, stage: 'starting' })
  const es = new EventSource('http://127.0.0.1:8765/api/screening/run/stream')
  es.onmessage = (e) => {
    const data = JSON.parse(e.data)
    if (data.stage === 3 && data.results) {
      setResults(data.results)
      setStatus({ running: false, progress: 100 })
      es.close()
    } else {
      setStatus(s => ({ ...s, progress: data.stage * 33, stage: data.msg }))
    }
  }
  es.onerror = () => { es.close(); setStatus(s => ({ ...s, running: false })) }
}
```

- [ ] **Step 4: 验证**

```bash
curl http://127.0.0.1:8765/api/screening/run/stream
```

- [ ] **Step 5: Commit**

```bash
git add shared/signals.py api/routes/screening.py electron/src/pages/Screening.jsx
git commit -m "feat: add Pydantic signal models and SSE streaming for screening progress"
```

---

### Task 5: 全量回归测试

- [ ] **Step 1: 运行全量测试**

```bash
python -m pytest tests/ -v -o "addopts=" -q --ignore=tests/unit
```

- [ ] **Step 2: 验证CLI命令**

```bash
python main.py analyze 600519
python main.py screen --top 3
python main.py daily
```

- [ ] **Step 3: Commit**

```bash
git commit --allow-empty -m "chore: final verification - all 45 tests pass, CLI verified"
```
