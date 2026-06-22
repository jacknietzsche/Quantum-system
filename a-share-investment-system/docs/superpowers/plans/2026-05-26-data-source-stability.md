# Data Source Stability Optimization Plan

> **For agentic workers:** Use subagent-driven-development to implement this plan task-by-task.

**Goal:** Fix remaining stability gaps in the data source acquisition layer: incorrect dispatch returns, missing source health API, stale cache warnings, and logging improvements.

**Architecture:** 5 independent tasks touching `providers/market_data.py`, `providers/source_base.py`, `services/data_bus.py`, and `api/routes/system.py`.

**Tech Stack:** Python 3.10+, FastAPI, urllib/httpx

---

### Corrections to Prior Analysis

The report is largely accurate. Key corrections based on actual project state:

| Claim | Reality |
|-------|---------|
| "No dynamic priority adjustment" | True — but not needed until we have 3+ stable sources |
| "Breaker cooldown 300s" | Already fixed to **60s** in previous session |
| "Tencent is first priority" | Tencent IS first in `_try_sources` list, but `_tx_spot()` now returns `_NOT_SUPPORTED` |
| "Rate limiter: 5 total, 3 scheduled" | Correct — hardcoded in `source_base.py` |
| "Failure threshold: 3, cooldown: 300s" | Cooldown already **60s** (was 300s) |
| `_source_baostock` / `_source_efinance` / `_source_tickflow` | These still return `None` for unhandled methods → **causes false breaker trips** |

---

### Task 1: Fix Source Dispatch Returns (`_NOT_SUPPORTED`)

**Files:**
- Modify: `providers/market_data.py`

**Problem:** Three source dispatch methods return `None` for methods they don't support. `_try_sources` treats `None` as "source failed" (records breaker failure), but `_NOT_SUPPORTED` means "skip without penalty". This causes unnecessary circuit breaker trips.

Current code:
```python
def _source_baostock(self, method, *args):
    try:
        import baostock as bs
    except ImportError:
        return None  # ← should be _NOT_SUPPORTED (import fail ≠ source fail)
    ...
    # falls through to implicit return None
```

Same pattern in `_source_efinance` and `_source_tickflow`.

- [ ] **Step 1: Fix `_source_baostock`**

Change:
```python
def _source_baostock(self, method, *args):
    try:
        import baostock as bs
    except ImportError:
        return _NOT_SUPPORTED
    ...
    return None  # end of method
```

Replace the final `return None` with `return _NOT_SUPPORTED` and the ImportError handler too.

- [ ] **Step 2: Fix `_source_efinance`**

Same pattern — final fallback `return None` → `return _NOT_SUPPORTED`.

- [ ] **Step 3: Fix `_source_tickflow`**

```python
def _source_tickflow(self, method, *args):
    if method == "fetch_kline":
        return self._tf_kline(*args)
    if method == "fetch_stock_spot":
        return self._tf_spot()
    if method == "fetch_basic":
        return self._tf_basic(*args)
    return _NOT_SUPPORTED  # was None
```

- [ ] **Step 4: Update the `_source_eastmoney` method**

Already checked earlier: `_source_eastmoney` returns `None` for `fetch_hot_stocks_em` failure. The `_source_eastmoney_hot` also has unhandled methods. Fix these too.

```python
def _source_eastmoney(self, method, *args):
    if method == "fetch_hot_stocks_em":
        return self._em_hot_stocks(*args)
    if method == "fetch_full_spot":
        return None  # delegates to akshare
    return _NOT_SUPPORTED  # was None
```

- [ ] **Step 5: Verify**

```bash
ruff check providers/market_data.py
python -c "import py_compile; py_compile.compile('providers/market_data.py', doraise=True)"
```

---

### Task 2: Info-Level Logging for Breaker Transitions

**Files:**
- Modify: `providers/market_data.py` (the `_CircuitBreaker` class)

**Problem:** Circuit breaker state transitions (CLOSED → OPEN, OPEN → HALF_OPEN, HALF_OPEN → CLOSED) are invisible in production logs. Only the `_try_sources` summary line (at `logger.warning` level) is visible, but it doesn't show individual breaker transitions.

- [ ] **Step 1: Add logging to `_CircuitBreaker.record_failure`**

```python
def record_failure(self):
    self._failures += 1
    self._last_fail_time = time.time()
    if self._failures >= self.FAIL_THRESHOLD:
        if self._state != "open":
            logger.info(
                "[CB] %s OPEN after %d failures (cooldown=%ds)",
                self.name, self._failures, self.COOLDOWN_SECONDS,
            )
        self._state = "open"
```

- [ ] **Step 2: Add logging to `_CircuitBreaker.record_success` when recovering from half_open**

```python
def record_success(self):
    self._failures = max(0, self._failures - 1)
    if self._state == "half_open":
        logger.info("[CB] %s CLOSED (recovered)", self.name)
    self._state = "closed"
```

- [ ] **Step 3: Add logging when breaker allows probe**

In `is_available()`:
```python
def is_available(self) -> bool:
    if self._state == "closed":
        return True
    if self._state == "open":
        if time.time() - self._last_fail_time > self.COOLDOWN_SECONDS:
            self._state = "half_open"
            logger.info("[CB] %s HALF_OPEN (probe allowed)", self.name)
            return True
        return False
    return True
```

- [ ] **Step 4: Remove the `print`/`logger` from `_try_sources` that summarizes everything**

The summary at `_try_sources` bottom is now redundant since individual transitions are logged. Keep it but change to debug level to reduce noise:

```python
logger.debug("[MarketData] %s: %s", method, " | ".join(parts))
```

- [ ] **Step 5: Verify**

```bash
ruff check providers/market_data.py
```

---

### Task 3: Expose Source Health API

**Files:**
- Modify: `api/routes/system.py`

**Problem:** `MarketDataProvider.get_source_status()` exists but is not exposed via any API endpoint. Ops can't see which sources are healthy.

- [ ] **Step 1: Add `/api/system/sources` endpoint**

```python
@router.get("/sources")
def source_status():
    """数据源健康状态"""
    from providers.market_data import MarketDataProvider
    provider = MarketDataProvider()
    return provider.get_source_status()
```

- [ ] **Step 2: Also add data bus stats endpoint (fast path)**

Expose `get_stats()` from `DatabaseBackedDataBus` so we can see cache hit rates:

```python
@router.get("/cache-stats")
def cache_stats():
    """数据总线缓存命中统计"""
    from services.data_bus import DatabaseBackedDataBus
    bus = DatabaseBackedDataBus()
    return bus.get_stats().data
```

- [ ] **Step 3: Verify**

```bash
ruff check api/routes/system.py
```

---

### Task 4: Stale Cache Warning in DataBus

**Files:**
- Modify: `services/data_bus.py`

**Problem:** When all API sources fail, `_get_or_fetch` returns stale cached data silently. No warning is logged, so operators don't know the system is running on stale data.

- [ ] **Step 1: Add stale cache warning**

In `_get_or_fetch`, the stale path:
```python
# Step 3: API失败 → 返回过期缓存
stale = self._read_snapshot(snapshot_type, ttl=None)
if stale is not None:
    self._stats["stale_served"] += 1
    if self._stats["stale_served"] % 5 == 1:  # throttle: warn every 5th
        logger.warning(
            "[DataBus] serving stale cache for %s (stale count: %d)",
            snapshot_type, self._stats["stale_served"],
        )
return stale
```

- [ ] **Step 2: Add `import logging` and `logger` to data_bus.py**

```python
import logging
logger = logging.getLogger(__name__)
```

- [ ] **Step 3: Verify**

```bash
ruff check services/data_bus.py
```

---

### Task 5: Source Priority Fine-Tune

**Files:**
- Modify: `providers/market_data.py:238-245`

**Problem:** The `_try_sources` source order is:
```python
sources = [
    ("tencent", ...),    # → kline works, spot → _NOT_SUPPORTED
    ("sina", ...),       # → spot works (200), indices 403
    ("baostock", ...),   # → unstable (socket disconnect)
    ("efinance", ...),   # → unknown stability
    ("tickflow", ...),   # → unstable
    ("akshare", ...),    # → heavy (loads pandas/numpy each call)
]
```

Since Tencent spot is dead and Sina spot works, Sina should be tried BEFORE Tencent for `fetch_stock_spot` and `fetch_full_spot`. But the source list is shared across ALL methods.

The simplest fix: keep the list order but let the `_NOT_SUPPORTED` mechanism handle it (Tencent returns `_NOT_SUPPORTED` for spot, so Sina will be tried immediately). This ALREADY works thanks to previous fixes.

The only remaining issue is that `_source_baostock` and `_source_efinance` need to return `_NOT_SUPPORTED` for methods they don't handle (already Task 1). Once that's done, the fallthrough works correctly.

- [ ] **Step 1: Verify fallthrough timing**

Run and measure that Tencent → _NOT_SUPPORTED → Sina doesn't have unnecessary delays:

```python
from providers.market_data import MarketDataProvider
m = MarketDataProvider()
import time; t0 = time.time()
spot = m.get_stock_spot()
elapsed = time.time() - t0
print(f"spot: {type(spot).__name__}, {elapsed:.1f}s")
assert elapsed < 5, f"Too slow: {elapsed:.1f}s"
```

- [ ] **Step 2: If still slow, add short-circuit for tencent spot**

If Tencent's `_NOT_SUPPORTED` still takes noticeable time (due to import or connection setup), add a fast-path skip:

```python
def _source_tencent(self, method, *args):
    if method in ("fetch_stock_spot", "fetch_full_spot"):
        return _NOT_SUPPORTED  # fast skip, no setup
    ...
```

(Already implemented in previous session — verify it works.)

---

### Execution Order

| Task | What | Risk | Est. Time |
|------|------|------|-----------|
| **1** | Fix source dispatch returns | Low | 15 min |
| **2** | Info-level breaker logging | Low | 10 min |
| **3** | Source health API | Low | 10 min |
| **4** | Stale cache warning | Low | 10 min |
| **5** | Priority fallthrough verify | Low | 5 min |

All tasks are independent and safe — none changes query behavior, only logging/dispatch correctness.

Current known-source status for context:

| Source | Spot | Kline | Basic | Indices | Status |
|--------|------|-------|-------|---------|--------|
| Tencent | 🔴 `_NOT_SUPPORTED` | ✅ Works | 🔴 N/A | ✅ Works | **Partial** |
| Sina | ✅ Works | ✅ Works | ✅ Works | 🔴 403 | **Good for spot** |
| Baostock | ❌ Unstable | ✅ Works | ✅ Works | ❌ Unstable | **Unstable** |
| EFinance | ⚠️ Unknown | ⚠️ Unknown | ⚠️ Unknown | ⚠️ Unknown | **Unknown** |
| AKShare | ✅ Works | ✅ Works | ✅ Works | ✅ Works | **Heavy but works** |

The immediate stability fix (already done in prior session) was making Sina the effective primary for spot data via `_NOT_SUPPORTED` for Tencent. Tasks 1-4 here add observability and prevent false breaker trips.
