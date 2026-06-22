# Data Module Upgrade — 4 Bug Fixes

> 2026-05-09 | Log spam + false success + no holiday check + no source memory

## Changes

1. providers/market_data.py: aggregated failure logging, source health tracking
2. services/data_initializer.py: trading day check, source health, accurate success
3. services/stock_screener.py: auto-trigger respects trading day
