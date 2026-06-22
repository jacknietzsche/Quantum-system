# Three Portfolio Modes + Persistence + Reset Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement 3 independent portfolio modes (limit_up/涨停狙击, momentum/中期趋势, value/长期价值) with DB persistence, portfolio-aware stock selection, buy/sell/hold signals, reset functionality, and professional investor-grade frontend.

**Architecture:** Add `portfolio_type` column to existing DB tables to segregate positions by strategy. Refactor PortfolioService and TradeExecutor to support type-aware operations. Rewrite the Portfolio frontend as a tabbed multi-portfolio view with CRUD + reset. Augment the StockScreener to accept portfolio context for buy/sell/hold signal generation.

**Tech Stack:** Python/FastAPI, SQLAlchemy/SQLite, Vue 3 + Element Plus + Pinia

---

### Database Schema Changes

All changes go to `shared/models.py`. The key change: add `portfolio_type` column to `Portfolio`, `TradeRecord`, `Order`, `Trade`, and `DailyNAV` tables.

`portfolio_type` values: `"limit_up"`, `"momentum"`, `"value"` — representing the 3 stock selection modes. (hybrid is a blend mode, not a separate portfolio.)

Portfolio table drops the `unique=True` on `date` in `DailyNAV` (since each portfolio will have its own NAV per date). Instead, use a composite unique on `(date, portfolio_type)`.

---

### Task 1: Database — Add portfolio_type Columns + Migration

**Files:**
- Modify: `shared/models.py` — add `portfolio_type` to Portfolio, TradeRecord, Order, Trade, DailyNAV
- Modify: `shared/models.py:init_db` — add migration logic for existing databases

**Details:**

1. Add to `Portfolio` model after `created_at`:
```python
portfolio_type = Column(String(20), default="value", index=True)  # limit_up / momentum / value
```

2. Add to `TradeRecord` model after `created_at`:
```python
portfolio_type = Column(String(20), default="value", index=True)
```

3. Add to `Order` model after `created_at`:
```python
portfolio_type = Column(String(20), default="value", index=True)
```

4. Add to `Trade` model after `created_at`:
```python
portfolio_type = Column(String(20), default="value", index=True)
```

5. Add to `DailyNAV` model:
   - Change `date` column to remove `unique=True`
   - Add `portfolio_type = Column(String(20), default="value", index=True)`
   - Add `__table_args__` with composite unique on `(date, portfolio_type)`:
```python
__table_args__ = (
    Index("idx_nav_date_type", "date", "portfolio_type", unique=True),
)
```

6. In `init_db()`, add migration calls for each table:
```python
# v5.2: portfolio_type segregation
for table_name in ("portfolio", "trade_records", "orders", "trades", "daily_nav"):
    _safe_add_column(conn, table_name, "portfolio_type",
                     f"ALTER TABLE {table_name} ADD COLUMN portfolio_type VARCHAR(20) DEFAULT 'value'")
```

---

### Task 2: Backend — PortfolioService Multi-Portfolio Support

**Files:**
- Rewrite: `services/portfolio.py` — full rewrite with multi-portfolio CRUD + reset + NAV tracking

**Details:**

Complete rewrite of `services/portfolio.py` with these methods:

```python
class PortfolioService:
    PORTFOLIO_TYPES = ["limit_up", "momentum", "value"]
    
    # ── Query ──
    def get_holdings(self, portfolio_type: str = None) -> dict
    def get_portfolio_summary(self, portfolio_type: str) -> dict
    def get_all_portfolios_summary(self) -> dict
    def get_trades(self, portfolio_type: str = None, limit: int = 50) -> dict
    def get_nav(self, portfolio_type: str, limit: int = 30) -> dict
    
    # ── CRUD ──
    def add_position(self, portfolio_type: str, stock_code: str, stock_name: str,
                     buy_price: float, quantity: int, buy_date: str = None,
                     buy_reason: str = "") -> dict
    def sell_position(self, portfolio_type: str, stock_code: str,
                      sell_price: float, sell_date: str = None,
                      sell_reason: str = "") -> dict
    def update_price(self, portfolio_type: str, stock_code: str, 
                     current_price: float) -> dict
    
    # ── Reset ──
    def reset_portfolio(self, portfolio_type: str = None) -> dict
    # If portfolio_type is None, reset ALL portfolios
    
    # ── Portoflio-Aware Screening ──
    def get_holdings_map(self, portfolio_type: str) -> dict
    # Returns {stock_code: {quantity, avg_cost, current_price, ...}} for a given type
    
    # ── NAV ──
    def record_nav(self, portfolio_type: str, date: str = None) -> dict
```

Key implementation details:
- All DB queries filter by `portfolio_type` when provided
- `get_holdings` returns: positions list + cash + total_asset + position_count (per portfolio_type)
- `get_portfolio_summary` returns total_asset, cash, stock_value, total_return_pct, position_count, day_return_pct
- `reset_portfolio` marks all HOLDING positions as SOLD with reason "手动重置", clears active orders, and records a reset NAV entry
- `add_position` checks for duplicate holdings (same stock_code + portfolio_type) and can add to existing position
- Uses `TradeRecord` to log all buy/sell actions

---

### Task 3: Backend — Portfolio API Routes

**Files:**
- Rewrite: `api/routes/portfolio.py` — full rewrite with all CRUD + reset endpoints

**Endpoints:**

```python
# GET /api/portfolio/holdings?type=limit_up  — 获取指定类型持仓
@router.get("/holdings")
def get_holdings(type: str = Query("value", enum=["limit_up", "momentum", "value"])):
    ...

# GET /api/portfolio/summary?type=limit_up  — 获取指定类型概览
@router.get("/summary")
def get_portfolio_summary(type: str = Query("value", enum=["limit_up", "momentum", "value"])):
    ...

# GET /api/portfolio/all-summaries  — 获取所有类型概览
@router.get("/all-summaries")
def get_all_summaries():
    ...

# POST /api/portfolio/holdings  — 新增持仓
@router.post("/holdings")
def add_holding(data: dict):
    # body: {portfolio_type, stock_code, stock_name, buy_price, quantity, buy_reason}
    ...

# PUT /api/portfolio/holdings/{stock_code}/sell  — 卖出持仓
@router.put("/holdings/{stock_code}/sell")
def sell_holding(stock_code: str, data: dict):
    # body: {portfolio_type, sell_price, sell_reason}
    ...

# POST /api/portfolio/reset  — 重置持仓
@router.post("/reset")
def reset_portfolio(data: dict):
    # body: {portfolio_type}  — if null/empty, reset all
    ...

# GET /api/portfolio/nav?type=limit_up  — 获取净值曲线
@router.get("/nav")
def get_nav(type: str = Query("value", enum=["limit_up", "momentum", "value"]),
            limit: int = Query(30)):
    ...
```

---

### Task 4: Frontend — Portfolio Types + API Client

**Files:**
- Create: `frontend/src/types/portfolio.ts` — Portfolio type definitions
- Modify: `frontend/src/api/legacy.ts` — Add new portfolio API methods

**Type definitions (`frontend/src/types/portfolio.ts`):**
```typescript
export type PortfolioType = 'limit_up' | 'momentum' | 'value'

export interface PortfolioConfig {
  label: string
  color: string
  icon: string
  desc: string
  initial_capital: number
}

export const PORTFOLIO_CONFIGS: Record<PortfolioType, PortfolioConfig> = {
  limit_up: { label: '涨停狙击', color: '#ef4444', icon: '🔥', desc: '短线博弈', initial_capital: 300000 },
  momentum: { label: '中期趋势', color: '#f59e0b', icon: '📈', desc: '顺势跟踪', initial_capital: 300000 },
  value: { label: '长期价值', color: '#10b981', icon: '💎', desc: '价值投资', initial_capital: 400000 },
}

export interface Position {
  stock_code: string
  stock_name: string
  buy_date: string
  buy_price: number
  quantity: number
  current_price: number
  cost_value: number
  current_value: number
  profit_loss: number
  profit_loss_pct: number
  industry: string
  trend: string
}

export interface PortfolioSummary {
  portfolio_type: PortfolioType
  total_asset: number
  cash: number
  stock_value: number
  position_count: number
  total_return_pct: number
  day_return_pct: number
}

export interface PortfolioHoldings {
  positions: Position[]
  cash: number
  total_asset: number
  position_count: number
  portfolio_type: PortfolioType
}

export interface NavPoint {
  date: string
  total_asset: number
  cash: number
  stock_value: number
  daily_return_pct: number
}
```

**API client additions (`frontend/src/api/legacy.ts`):**
```typescript
export const portfolioApi = {
  getHoldings: (type: string) => get('/api/portfolio/holdings', { type }),
  getSummary: (type: string) => get('/api/portfolio/summary', { type }),
  getAllSummaries: () => get('/api/portfolio/all-summaries'),
  addHolding: (data: any) => post('/api/portfolio/holdings', data),
  sellHolding: (code: string, data: any) => put(`/api/portfolio/holdings/${code}/sell`, data),
  reset: (data: any) => post('/api/portfolio/reset', data),
  getNav: (type: string, limit?: number) => get('/api/portfolio/nav', { type, limit }),
}
```

---

### Task 5: Frontend — Pinia Portfolio Store

**Files:**
- Create: `frontend/src/stores/portfolio.ts` — Pinia store for portfolio state management

**Store responsibilities:**
- Hold current portfolio type, holdings data, summaries, nav data
- Fetch holdings/summary/nav from API
- CRUD operations (add/sell/reset)
- Auto-refresh support
- Error handling and loading states

```typescript
export const usePortfolioStore = defineStore('portfolio', () => {
  const activeType = ref<PortfolioType>('value')
  const holdings = ref<PortfolioHoldings | null>(null)
  const summaries = ref<Record<PortfolioType, PortfolioSummary> | null>(null)
  const nav = ref<NavPoint[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)
  
  async function fetchHoldings(type?: PortfolioType) { ... }
  async function fetchAllSummaries() { ... }
  async function fetchNav(type: PortfolioType, limit?: number) { ... }
  async function addPosition(data: any) { ... }
  async function sellPosition(code: string, data: any) { ... }
  async function resetPortfolio(type?: PortfolioType) { ... }
  
  return { activeType, holdings, summaries, nav, loading, error, ... }
})
```

---

### Task 6: Frontend — Portfolio View Complete Rewrite

**Files:**
- Rewrite: `frontend/src/views/Portfolio/index.vue` — Full rewrite with tabs, CRUD, reset, ECharts NAV

**UI Layout:**
```
┌─────────────────────────────────────────────────┐
│ PORTFOLIO                        [Reset Button] │
│ ┌──────────┬──────────┬──────────┐              │
│ │ 涨停狙击   │ 中期趋势  │ 长期价值  │  <- Tabs   │
│ │ AUM: 30w  │ AUM: 30w │ AUM: 40w │  <- Summary │
│ │ +5.2%     │ +3.1%    │ +8.7%    │             │
│ └──────────┴──────────┴──────────┘              │
│ ┌──────────────────────────────────────────────┐│
│ │ [Add Position]                    NAV Chart  ││
│ │ ┌──────┬──────┬────┬────┬─────┬─────┬──────┐││
│ │ │ Code │ Name │Cost│Px │Value│P&L% │Action│││
│ │ ├──────┼──────┼────┼────┼─────┼─────┼──────┤││
│ │ │000001│平安  │12.3│13.5│13.5w│+9.8%│[Sell]│││
│ │ └──────┴──────┴────┴────┴─────┴─────┴──────┘││
│ └──────────────────────────────────────────────┘│
└─────────────────────────────────────────────────┘
```

**Components used:**
- Element Plus: `el-tabs`, `el-table`, `el-button`, `el-dialog` (for add/sell forms), `el-form`, `el-input`, `el-message-box` (for confirm)
- ECharts: NAV line chart showing total_asset over time
- StockDetail for stock analysis popup

**Key states:**
- **Loading**: Skeleton/spinner while fetching holdings
- **Empty**: "NO POSITIONS — Add your first position or run screening" with CTA button
- **Error**: Error message with retry button
- **Normal**: Table with positions + NAV chart

**Add Position Dialog:**
- Stock code input (with search/autocomplete from StockInfo)
- Quantity input
- Buy price input (defaults to latest price)
- Buy reason textarea (optional)
- Submit/Cancel buttons

**Sell Confirmation:**
- Shows stock name, code, current value
- Sell price input (defaults to current price)
- Sell reason textarea (optional)
- Confirm with warning

**Reset:**
- Button in header area
- Confirmation dialog: "Are you sure you want to reset [portfolio_type]? This will mark all positions as sold and clear trade history."
- Option: reset current type only, or ALL portfolios
- Loading state during reset
- Success message with undo info (data is sold, not deleted)

---

### Task 7: Backend — Portfolio-Aware Stock Screening

**Files:**
- Modify: `services/stock_screener.py` — Add portfolio context to screening pipeline
- Modify: `api/routes/screening.py` — Accept portfolio_type parameter

**Details:**

Add to `StockScreener`:
```python
def run(self, stock_universe=None, market_regime="NEUTRAL", top_n=None,
        portfolio_holdings: dict = None) -> ServiceResult:
    """
    portfolio_holdings: {stock_code: {quantity, avg_cost, current_price, ...}}
    When provided, recommendations will include:
    - "已持有" badge for stocks already in portfolio
    - Adjusted signal based on position (buy/hold/sell)
    - Portfolio concentration warnings
    """
```

After the pipeline generates recommendations, overlay portfolio-aware logic:
```python
def _apply_portfolio_context(self, recommendations: List[Dict], 
                              holdings: dict) -> List[Dict]:
    """Augment recommendations with portfolio awareness"""
    for rec in recommendations:
        code = rec["stock_code"]
        if code in holdings:
            holding = holdings[code]
            rec["in_portfolio"] = True
            rec["holding_qty"] = holding["quantity"]
            rec["holding_pnl_pct"] = holding.get("profit_loss_pct", 0)
            
            # Adjust signal based on portfolio context
            current_signal = rec.get("signal", "观望")
            score = rec.get("score", 50)
            
            if current_signal == "买入" and score < 60:
                rec["signal"] = "持有"  # Already held, not good enough to add
                rec["signal_note"] = "已持仓，评分不足加仓"
            elif current_signal == "观望" and score < 40:
                rec["signal"] = "卖出"  # Held but score dropped
                rec["signal_note"] = "评分下降，考虑减仓"
            elif holding.get("profit_loss_pct", 0) < -10:
                rec["signal"] = "卖出"  # Stop loss triggered
                rec["signal_note"] = f"止损: {holding['profit_loss_pct']:.1f}%"
        else:
            rec["in_portfolio"] = False
    
    return recommendations
```

Add to screening API route `run_screening` and `run_screening_stream`:
```python
@router.get("/run")
def run_screening(
    style: str = Query("hybrid", enum=["limit_up", "momentum", "value", "hybrid"]),
    portfolio_type: str = Query(None, enum=["limit_up", "momentum", "value"])
):
    """
    portfolio_type: if provided, load holdings from this portfolio
    and overlay buy/sell/hold signals
    """
```

---

### Task 8: Frontend — Portfolio-Aware Screening Display

**Files:**
- Modify: `frontend/src/views/Screening/index.vue` — Show portfolio badges
- Modify: `frontend/src/types/screening.ts` — Add portfolio fields

**Changes to Screening view:**
1. Add a portfolio context selector (dropdown or auto-match based on current screening style)
2. Each recommendation card shows portfolio status:
   - "已持仓" badge (green) if stock is in the current portfolio
   - "止损中" badge (red) if position is at loss
   - Quick "加仓" / "减仓" signal indicators
3. "Add to Portfolio" button on each recommendation (opens add position dialog)

**Type changes:**
```typescript
export interface Recommendation {
  // ... existing fields
  in_portfolio?: boolean
  holding_qty?: number
  holding_pnl_pct?: number
  signal_note?: string
}
```

---

### Task 9: Sidebar — Add Portfolio Sub-Menu

**Files:**
- Modify: `frontend/src/layouts/BasicLayout.vue` — Replace single Portfolio menu with sub-menu

Change the portfolio sidebar item from single link to a sub-menu with 3 modes:
```html
<el-sub-menu index="portfolio">
  <template #title>
    <el-icon><Briefcase /></el-icon>
    <span>持仓</span>
  </template>
  <el-menu-item index="/portfolio/limit_up">🔥 涨停狙击</el-menu-item>
  <el-menu-item index="/portfolio/momentum">📈 中期趋势</el-menu-item>
  <el-menu-item index="/portfolio/value">💎 长期价值</el-menu-item>
</el-sub-menu>
```

---

### Task 10: Router — Portfolio Routes

**Files:**
- Modify: `frontend/src/router/index.ts` — Add portfolio sub-routes

```typescript
{
  path: '/portfolio/limit_up',
  name: 'PortfolioLimitUp',
  component: () => import('@/views/Portfolio/index.vue'),
  meta: { title: '涨停狙击 · 持仓', portfolioType: 'limit_up' },
},
{
  path: '/portfolio/momentum',
  name: 'PortfolioMomentum',
  component: () => import('@/views/Portfolio/index.vue'),
  meta: { title: '中期趋势 · 持仓', portfolioType: 'momentum' },
},
{
  path: '/portfolio/value',
  name: 'PortfolioValue',
  component: () => import('@/views/Portfolio/index.vue'),
  meta: { title: '长期价值 · 持仓', portfolioType: 'value' },
},
```

The Portfolio view reads `route.meta.portfolioType` to determine which portfolio to display. If going to `/portfolio` directly, redirect to `/portfolio/value` (default).

---

### Task 11: Frontend — Build & Verify

**Files:**
- Build: Run `npm run build` in frontend/ directory
- Verify: Start server and check all features

**Steps:**
1. Navigate to each portfolio tab → loads correct holdings
2. Add a position → appears in table → persists on refresh
3. Sell a position → disappears from holdings → appears in trades
4. Reset portfolio → all positions marked sold → portfolio empty
5. Run screening → recommendations show portfolio context badges
6. NAV chart renders correctly with historical data
