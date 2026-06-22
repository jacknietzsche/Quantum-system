# Database Data Quality Fix + Date-Filtered Data Browser Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Fix database data quality issues (missing financial data, field name mismatches), add date-filtered data browsing to frontend, and verify stock screener data completeness.

**Root Causes Identified:**
1. **Field name mismatch**: AKShare `stock_individual_info_em()` returns Chinese field names (总市值, 行业) but `_save_stock_info` expects English names (total_market_cap, industry)
2. **Financial data pipeline broken**: `_pull_financial_reports()` exists using `ak.stock_financial_analysis_indicator()` but is **NEVER CALLED** from any refresh flow — so `roe`, `gross_margin`, `eps`, `bvps` stay 100% empty
3. **DragonTiger data never refreshed**: `_pull_dragon_tiger()` exists but not integrated into pipeline
4. **Screener results not persisted**: `screen_result` table stays empty, results only in memory

**Tech Stack:** Python/FastAPI, SQLAlchemy/SQLite, Vue 3 + Element Plus

---

### Critical Data Quality Issues (from DB scan)

| Column | Zero/Null Rate | Root Cause |
|--------|---------------|------------|
| `pb_ratio` | 100% (7854/7854) | AKShare returns Chinese field names (pbMRQ), mapper expects English |
| `roe` | 100% (7854/7854) | `_pull_financial_reports` never called |
| `gross_margin` | 100% (7854/7854) | `_pull_financial_reports` never called |
| `eps` | 100% (7854/7854) | `_pull_financial_reports` never called |
| `bvps` | 100% (7854/7854) | `_pull_financial_reports` never called |
| `total_market_cap` | 96% (7539/7854) | AKShare returns 总市值, mapper expects total_market_cap |
| `pe_ratio` | 63% (4966/7854) | AKShare returns 市盈率-动态, mapper expects pe_ratio |
| `turnover_rate` | 52% (4074/7854) | Some stocks have no turnover data |
| `fund_metric_hist` | 0 rows | `_pull_financial_reports` never called |
| `dragon_tiger` | 0 rows | `_pull_dragon_tiger` never called from pipeline |
| `screen_result` | 0 rows | Only stored in memory, never written to DB |

---

### Task 1: Fix Field Name Mapping in DataInitializer._save_stock_info

**Files:**
- Modify: `services/data_initializer.py` — `_save_stock_info()` method + add field name mapper

**Problem:** The `_save_stock_info` method at line 505-541 tries to get fields like `data.get("pe_ratio", ...)` but the AKShare adapter returns Chinese field names like `"市盈率-动态"`. Baostock returns English names. Different adapters use different conventions.

**Solution:** Add a comprehensive field name mapping dict and normalize all field names before saving:

```python
# Chinese → English field name mapping for AKShare/efinance responses
_FIELD_NAME_MAP = {
    "股票名称": "stock_name", "名称": "stock_name", "name": "stock_name",
    "最新价": "latest_price", "price": "latest_price", "现价": "latest_price",
    "涨跌幅": "change_pct", "涨幅": "change_pct",
    "市盈率-动态": "pe_ratio", "peTTM": "pe_ratio", "动态市盈率": "pe_ratio",
    "市净率": "pb_ratio", "pbMRQ": "pb_ratio",
    "总市值": "total_market_cap", "流通市值": "float_market_cap",
    "换手率": "turnover_rate", "换手": "turnover_rate",
    "成交量": "volume", "成交额": "amount",
    "行业": "industry", "所属行业": "industry",
    "毛利率": "gross_margin",
    "净利率": "net_margin",
    "roe": "roe", "净资产收益率": "roe",
    "eps": "eps", "每股收益": "eps",
    "bvps": "bvps", "每股净资产": "bvps",
    "资产负债率": "debt_to_equity", "debt_to_equity": "debt_to_equity",
    "净利润": "net_income",
    "总股本": "shares_outstanding",
    "流动比率": "current_ratio",
    "营业利润率": "operating_margin",
    "自由现金流": "free_cash_flow",
    "营业收入同比增长率": "revenue_growth_3y",
    "净利润同比增长率": "earnings_growth_3y",
    "流动资产": "current_assets",
    "总负债": "total_liabilities",
    "现金比率": "cash_ratio",
}
```

Add a helper method:
```python
def _normalize_fields(self, data: dict) -> dict:
    """Normalize field names from any adapter to English convention"""
    normalized = {}
    for k, v in data.items():
        if k in _FIELD_NAME_MAP:
            normalized[_FIELD_NAME_MAP[k]] = v
        else:
            normalized[k] = v  # Pass through unknown fields
    return normalized
```

Update `_save_stock_info` to call `data = self._normalize_fields(data)` at the start.

---

### Task 2: Integrate Financial Report Refresh into Data Pipeline

**Files:**
- Modify: `services/data_initializer.py` — `_populate_one()` and `refresh_full_universe()`

**Problem:** `_pull_financial_reports(code)` exists at line 637 but is NEVER called. Meanwhile, all critical financial fields (roe, gross_margin, eps, bvps) depend on it.

**Solution:** Add financial data refresh to the main population pipeline:

In `_populate_one()`, after saving stock info and klines, also pull financial reports:
```python
if has_data:
    try:
        self._pull_financial_reports(code)
    except Exception as _e:
        emit_log("WARNING", "data_init", f"财报跳过 {code}: {_e}")
```

Also add a dedicated method to batch-refresh financials for all stocks that have missing data:
```python
def refresh_financials_batch(self, max_stocks: int = 500) -> ServiceResult:
    """批量刷新财务数据 — 处理roe=0的股票"""
    from shared.models import StockInfo, get_session
    session = get_session()
    codes = [r.stock_code for r in session.query(StockInfo.stock_code)
             .filter((StockInfo.roe == 0) | (StockInfo.roe.is_(None)))
             .limit(max_stocks).all()]
    session.close()
    
    emit_log("INFO", "data_init", f"批量财报刷新: {len(codes)}只待处理")
    success = 0
    for code in codes:
        if self._pull_financial_reports(code):
            success += 1
    return ServiceResult.ok(data={"total": len(codes), "success": success})
```

Update `refresh_full_universe` to call `refresh_financials_batch` after the initial population.

---

### Task 3: Integrate DragonTiger Refresh into Pipeline

**Files:**
- Modify: `services/data_initializer.py` — `refresh_full_universe()` method

Add call to `_pull_dragon_tiger()` after full universe refresh:
```python
try:
    from services.trading_calendar import TradingCalendar
    tc = TradingCalendar()
    self._pull_dragon_tiger(tc.effective_data_date())
except Exception as _e:
    emit_log("WARNING", "data_init", f"龙虎榜刷新跳过: {_e}")
```

---

### Task 4: Backend — Date-Filtered Data Query API

**Files:**
- Modify: `api/routes/database.py` — Add `GET /api/db/data-by-date` endpoint

**New endpoint:**
```python
@router.get("/data-by-date")
def get_data_by_date(
    table: str = Query("stock_info", enum=["stock_info", "kline_cache", "fund_metric_hist", 
                                            "market_snapshot", "daily_nav", "portfolio",
                                            "trade_records", "style_signal", "screen_result",
                                            "dragon_tiger"]),
    date: str = Query(None, description="精确日期 YYYY-MM-DD"),
    date_from: str = Query(None, description="起始日期 YYYY-MM-DD"),
    date_to: str = Query(None, description="结束日期 YYYY-MM-DD"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    code: str = Query(None, description="股票代码过滤"),
):
    """按日期范围查询数据库表数据
    
    支持的数据表:
    - kline_cache: 使用 trade_date 字段过滤
    - fund_metric_hist: 使用 report_period 字段过滤
    - stock_info: 使用 updated_at 字段过滤
    - daily_nav: 使用 date 字段过滤
    - market_snapshot: 使用 trade_date 字段过滤
    - dragon_tiger: 使用 trade_date 字段过滤
    """
```

The implementation detects which date column to use based on the table:
- `kline_cache` → `trade_date`
- `fund_metric_hist` → `report_period`
- `stock_info` → `updated_at` (cast to date string for comparison)
- `daily_nav` → `date`
- `market_snapshot` → `trade_date`
- `dragon_tiger` → `trade_date`
- `portfolio` → `buy_date` or `sell_date`
- `trade_records` → `trade_date`
- `style_signal` → `created_at`
- `screen_result` → `created_at`

Returns paginated results with total count.

Also add a metadata endpoint:
```python
@router.get("/table-info")
def get_table_info(table: str = Query(...)):
    """返回指定表的列信息（名称、类型、示例数据）"""
```

---

### Task 5: Frontend — Date-Filtered Data Browser in Database View

**Files:**
- Modify: `frontend/src/views/Database/index.vue` — Add date-filtered data viewer tab
- Modify: `frontend/src/api/legacy.ts` — Add new API methods

**API additions:**
```typescript
export const dbApi = {
  // ...existing methods
  getDataByDate: (params: any) => get('/api/db/data-by-date', params),
  getTableInfo: (params: any) => get('/api/db/table-info', params),
}
```

**New "Data Browser" tab in Database view:**
```
┌──────────────────────────────────────────────────────────┐
│ DATABASE                                                  │
│ [Table Info] [Stock Info] [Data Browser] <-- tabs        │
│ ┌──────────────────────────────────────────────────────┐ │
│ │ Table: [stock_info ▼]  Date: [2026-05-15 ☐]         │ │
│ │ From: [2026-05-01]  To: [2026-05-15]  [Query]       │ │
│ │ Code filter: [________]  Limit: [100]                │ │
│ ├──────────────────────────────────────────────────────┤ │
│ │ Results: 125 rows (showing 1-100)                    │ │
│ │ ┌───────┬────────┬────────┬──────┬──────┬──────────┐ │ │
│ │ │ code │ name   │ price  │ pe   │ roe  │ industry │ │ │
│ │ ├───────┼────────┼────────┼──────┼──────┼──────────┤ │ │
│ │ │000001│平安银行│ 12.50 │ 5.2  │ 12.3 │ 金融     │ │ │
│ │ └───────┴────────┴────────┴──────┴──────┴──────────┘ │ │
│ │ [Prev] Page 1/3 [Next]                               │ │
│ └──────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────┘
```

Key states:
- **Loading**: Skeleton/progress indicator
- **Empty**: "No data for this date range" with helpful message
- **Error**: Error message with retry option
- **Normal**: Paginated table with sortable columns

The Data Browser tab implementation:
1. Table selector dropdown (all tables from the API)
2. Date filter inputs (exact date OR date range)
3. Code filter input (text search)
4. Limit control
5. Query button
6. Results table with dynamic columns (auto-detected from column info)
7. Pagination controls

Since tables have different columns, the table needs to be dynamic — fetch column info first, then render columns based on the response.

---

### Task 6: Backend — Data Refresh API for Triggering Data Fixes

**Files:**
- Modify: `api/routes/database.py` — Add refresh endpoint

Add:
```python
@router.post("/refresh-financials")
def refresh_financials(max_stocks: int = Query(500)):
    """批量刷新财务数据"""
    from services.data_initializer import DataInitializer
    di = DataInitializer()
    result = di.refresh_financials_batch(max_stocks)
    return result.data if hasattr(result, 'data') else {"status": "ok", "message": "financial refresh triggered"}
```

---

### Task 7: Verify Screener Data Completeness After Fixes

**Files:**
- Script: Run verification after implementation

After the data pipeline fixes are applied, verify:
1. All stocks with latest_price > 0 have pe_ratio populated
2. Top 500 stocks by market cap have roe > 0  
3. KlineCache has sufficient data for indicator computation
4. DragonTiger has recent data

Print a report showing:
- Coverage rate before and after for each critical column
- Number of stocks usable by each screener style
- Required vs available data for Stage 1/2/3 of each style

---

### Implementation Order

1. Task 1: Fix field name mapping in `_save_stock_info`
2. Task 2: Integrate financial report refresh
3. Task 3: Integrate DragonTiger refresh
4. Task 4: Backend date-filtered data query API
5. Task 5: Frontend date-filtered data browser
6. Task 6: Backend data refresh API
7. Task 7: Verify screener data completeness

Backend tasks (1,2,3,4,6) are independent of frontend tasks (5). Can be parallelized.
