# DB自动填充 + 字段扩展 实施计划

> **Goal:** StockScreener检测空DB自动触发多源数据填充，扩展StockInfo支持所有agent字段

**Architecture:** StockScreener._load_universe() → 检测空 → DataInitializer.populate() → MarketDataProvider 6源降级 → 回填StockInfo+KlineCache

**Files:** models.py (+10 fields), services/data_initializer.py (new), services/stock_screener.py (auto-trigger)

## Task 1: StockInfo 扩展10字段 + DB迁移

- Modify: `models.py` StockInfo class
- Add: eps, bvps, debt_to_equity, net_income, shares_outstanding, current_ratio, operating_margin, free_cash_flow, revenue_growth_3y, cash_ratio

## Task 2: DataInitializer 多源填充服务

- Create: `services/data_initializer.py`
- Uses MarketDataProvider 6源降级链获取数据
- populate_stock_list(): 获取全A股列表
- populate_stock_info(code): 获取单只股票基本面+技术面
- populate_klines(code): 获取K线数据
- batch_populate(codes, max_workers=3): 批量填充

## Task 3: StockScreener 自动触发

- Modify: `services/stock_screener.py` _load_universe()
- 检测空 → 调 DataInitializer 自动填充 → 重新加载
