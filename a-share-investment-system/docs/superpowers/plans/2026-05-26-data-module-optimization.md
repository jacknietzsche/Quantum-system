# Data Module Optimization Plan

> **For agentic workers:** Use subagent-driven-development to implement this plan task-by-task.

**Goal:** Fix session management, import hygiene, and error handling in the data layer (shared/models.py, shared/db_service.py, services/data_bus.py, services/data_mgmt.py).

**Architecture:** Four targeted tasks addressing the highest-risk issues first, each independently testable.

**Tech Stack:** Python 3.10+, SQLAlchemy 2.0, SQLite

---

### Correction to Prior Analysis

One claim in the review needs correction:

- **`datetime.now` in model defaults** — `default=datetime.now` (no parens) is the **correct** SQLAlchemy pattern. The callable is evaluated at INSERT time, not class-loading time. `default=datetime.now()` (with parens) would be the bug. The existing code is fine.

Actual P0 issues discovered during investigation:
- `services/data_bus.py` `_session` property: each access creates a new `Session` without closing the previous one → **session leak**
- `providers/market_data.py` `_CircuitBreaker.COOLDOWN_SECONDS` was 300s → already fixed to 60s
- `services/data_initializer.py` had `from models import` (broken) → already fixed to `from shared.models import`

---

### Task 1: Fix Session Leak in DataBus

**Files:**
- Modify: `services/data_bus.py` (session management)
- Test: Visual inspection / ruff check

**Problem:** The `_session` property creates a new session on every access:

```python
@property
def _session(self):
    from shared.models import get_session
    return get_session()  # ← never closed, leaked on each access
```

Each call to `self._session` in `get_stock_basic()`, `read_snapshot()`, `write_snapshot()` etc. leaks a session.

- [ ] **Step 1: Replace property with context-managed helper**

```python
# Add at top of data_bus.py imports
from contextlib import contextmanager

# Add helper method
@contextmanager
def _db_session(self):
    session = get_session()
    try:
        yield session
    finally:
        session.close()
```

- [ ] **Step 2: Replace all `self._session` usages with `self._db_session()`**

Each pattern like:
```python
session = self._session
try:
    ...
finally:
    session.close()
```
Becomes:
```python
with self._db_session() as session:
    ...
```

- [ ] **Step 3: Remove the `_session` property**

Delete the `_session` property entirely — no more leak source.

- [ ] **Step 4: Verify ruff + compile**

Run: `ruff check services/data_bus.py` and `python -c "import py_compile; py_compile.compile('services/data_bus.py', doraise=True)"`

---

### Task 2: Standardize Session Patterns in db_service.py

**Files:**
- Modify: `shared/db_service.py`

**Problem:** Functions take `session: Session` as first parameter (good), but a few functions like `health_check()` manage their own session internally, creating inconsistency.

- [ ] **Step 1: Make `health_check()` accept an optional session**

```python
def health_check(session: Session | None = None) -> dict:
    """database health check"""
    if session is None:
        from shared.models import get_session
        session = get_session()
        close_session = True
    else:
        close_session = False
    try:
        ...
    finally:
        if close_session:
            session.close()
```

- [ ] **Step 2: Add `# noqa: PLC0415` to deferred imports in db_service.py**

```python
from sqlalchemy import func, select  # noqa: PLC0415
```

- [ ] **Step 3: Verify ruff**

Run: `ruff check shared/db_service.py`

---

### Task 3: Fix Import Hygiene in data_initializer.py

**Files:**
- Modify: `services/data_initializer.py`

**Problem:** Verified regression — 11 `from models import` statements that fail at runtime (`No module named 'models'`). The imports must use `from shared.models import`.

- [ ] **Step 1: Verify all imports use `from shared.models import`**

Run: `grep -n 'from models import' services/data_initializer.py` — should return zero matches.

- [ ] **Step 2: Verify StockInfo fallback returns full count**

Run: 
```python
from services.data_initializer import DataInitializer
di = DataInitializer()
pool = di._get_pool_from_stockinfo()
assert len(pool) == 6986, f"Expected 6986, got {len(pool)}"
```

---

### Task 4: Clean Up Print Statements

**Files:**
- Modify: `services/data_mgmt.py`
- Modify: `providers/market_data.py`

**Problem:** 4 `print` statements in data_mgmt.py and 2 in market_data.py bypass the logging system.

- [ ] **Step 1: Replace `print` in data_mgmt.py**

Search for `print(` lines and replace with `emit_log()` or `logger.info()`:

```python
# In data_mgmt.py:
# Before:
print(f"Table {name}: {count} rows")
# After:
emit_log("INFO", "data_mgmt", f"Table {name}: {count} rows")
```

- [ ] **Step 2: Replace `print` in market_data.py**

The `[MarketData]` line in `_try_sources`:
```python
# Before:
print(f"[MarketData] {method}: {' | '.join(parts)}")
# After:
logger.warning("[MarketData] %s: %s", method, " | ".join(parts))
```

- [ ] **Step 3: Verify ruff**

Run: `ruff check services/data_mgmt.py providers/market_data.py`

---

### Execution Order

| Task | Priority | Risk | Est. Time |
|------|----------|------|-----------|
| Task 1: Session leak fix | P0 | Medium | 20 min |
| Task 2: Session pattern | P1 | Low | 10 min |
| Task 3: Import verification | P0 | Low | 5 min |
| Task 4: Print cleanup | P2 | Low | 10 min |

Task 1 has the highest blast radius — test thoroughly. Tasks 2-4 are mechanical and safe.
