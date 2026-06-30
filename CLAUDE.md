# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A-share (Chinese stock market) quantitative trading system. Python 3.11, packaged via `pyproject.toml` with editable install (`pip install -e ".[dev]"`).

## Commands

```bash
# Install (editable mode + dev tools)
pip install -e ".[dev]"

# Daily stock selection (primary workflow)
python run_v15_full.py --top 10 --workers 8
python run_v15_local.py --top 10          # faster, uses local DB

# Portfolio management
python run_portfolio_v2.py --date 20260401 --capital 100000

# Backtest
python run_backtest.py                     # comprehensive local backtest
streamlit run dashboard_v15.py             # interactive dashboard

# Factor calculation (batch, long-running)
python fetch_and_calculate_factors.py      # fetch 5yr data + calculate factors
python calculate_factors_all_history.py    # multi-process parallel calculation

# Testing
pytest tests/ -v                           # all tests
pytest tests/unit/ -v                      # unit tests only

# Linting
ruff check .                               # check
ruff format .                              # auto-format
```

## Architecture

Layered design with `core/` as the central package:

```
Entry scripts (run_*.py)
    |
    v
core/
  config.py          QuantConfig - single source of truth for all settings
  logging_config.py  Centralized logging (setup_logging + get_logger)
  data.py            UnifiedDataFetcher - 5-layer fallback: baostock→akshare→efinance→Sina HTTP→Tencent HTTP
  strategy.py        V15Scorer/V16Scorer, StockFilter, MarketAnalyzer
  risk.py            RiskChecker, StopLossManager, PositionManager
  engine.py          BacktestEngine (Backtrader wrapper) with A-share cost model
  factor_engine_v2.py FactorEngineV2 - orchestrates 51 factors from factors/
  report.py          HTML report generators (Plotly charts)
  local_db_adapter.py LocalDBAdapter (SQLite singleton)
  db_manager.py      DBManager (connection pool, schema)
  cache_manager.py   Memory + disk (pickle, 24h TTL) caching
  record_manager.py  Error/result logging to .learnings/.workbuddy

factors/             51 daily-frequency factors across 10 categories
backtest_system/     Backtrader-based backtesting framework (own config with different cost assumptions)
local_db/            SQLite DB (~2.7GB, WAL mode), DB management scripts
tests/               pytest test suite (unit/ + integration/)
output/              Generated output files
docs/reports/        Historical report documents
```

### Scoring Pipeline

`V15Scorer` combines: base factors (20%) + enhanced factors (35%) + market environment (15%) + FactorEngineV2 adjustment_coef (30%). Anti-top filters penalize topping patterns.

### Data Flow

1. `UnifiedDataFetcher` fetches with 5-layer fallback + exponential backoff + adaptive throttling
2. Data stored in `local_db/a_stock_quant.db` (SQLite WAL, ~53K stocks, ~5.64M price records)
3. `FactorEngineV2` calculates 51 factors → stored in `stock_factors` table
4. Scoring → risk check → report generation

### Key DB Tables

- `stocks`: code, name, exchange, list_date, delist_date
- `daily_price`: code, trade_date, OHLCV, amount, turnover, pct_chg
- `stock_factors`: code, trade_date, adjustment_coef, 10 category scores

## Logging

All modules use centralized logging via `core/logging_config`:

```python
from core.logging_config import get_logger
logger = get_logger(__name__)
```

Entry scripts call `setup_logging()` once at startup. Library modules only call `get_logger()`.

## Known Pitfalls

- **numpy.datetime64 has no strftime** — always use `pd.Timestamp(x).strftime()` for dates from pandas/numpy operations
- **bare `except:` swallows all errors** — always use `except Exception as e:` and log the error
- **Variable name typos in data.py cause silent 0% success** — verify after edits (historical bug: `bs__code` vs `bs_code`)
- **IPO filter threshold must match data request days** — if fetching N days of data, IPO filter must be < N
- **akshare/eastmoney APIs rate-limit aggressively** — the 5-layer fallback exists for a reason; don't remove fallback sources
- **Index fund codes (920000-939999) trigger Tencent API limits** — filtered in `core/data.py`
- **Long file writes with HTML templates can corrupt** — after writing files >200 lines, run `python -c "import ast; ast.parse(open('file.py').read())"` to verify syntax
- **backtest_system config differs from core** — TradeConfig has lower commission/slippage (intentional for backtesting)
- **Language**: documentation, comments, and many identifiers are in Chinese
