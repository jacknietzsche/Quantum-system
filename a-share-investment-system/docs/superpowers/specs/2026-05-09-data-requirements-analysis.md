# AShare-X 数据需求全景分析

## 数据分层

```
实时层 (≤5分钟TTL)    → MarketSnapshot表 + API直取
日频层 (日级更新)      → StockInfo表 + KlineCache表  
基本面层 (24h TTL)     → StockInfo扩展字段
历史层 (永久)          → MemoryBank JSON文件
```

## 各模块数据需求详表

### 1. MarketPerception (5维市场感知)

| 数据 | 字段 | 期限 | 来源 | 最小量 |
|------|------|------|------|--------|
| 市场广度 | up/down/total/limit_up/limit_down | 当日 | API(腾讯/新浪) → MarketSnapshot | 1条 |
| 指数数据 | 上证/深证/创业板/中证500 price+change_pct | 当日 | API → MarketSnapshot | 1条 |
| 北向资金 | net_buy_amount | 当日 | API → MarketSnapshot | 1条 |

### 2. StockScreener (三级漏斗选股)

| 数据 | 字段 | 期限 | 来源 | 最小量 |
|------|------|------|------|--------|
| 股票池 | stock_code/name/industry | 静态 | StockInfo表 | ≥20只 |
| 行情快照 | price/change_pct/turnover_rate/market_cap | 当日 | StockInfo.latest_price | 每只1条 |
| 估值 | pe/pb/roe/gross_margin | 最新季报 | StockInfo | 每只1条 |
| 技术面 | trend/volatility/ma5-60/rsi/macd | 60日计算 | StockInfo(计算字段) | 每只1条 |
| 扩展基本面 | eps/bvps/debt_to_equity/net_income/revenue_growth_3y | 最新年报 | StockInfo(扩展) | 每只1条 |

### 3. QuantAnalyzers (6大师量化分析)

| 数据 | 字段 | 期限 | 来源 | 最小量 |
|------|------|------|------|--------|
| 估值基础 | roe/debt_to_equity/gross_margin/eps/bvps/price | 当前 | StockInfo | 1条 |
| 格雷厄姆 | current_assets/total_liabilities/shares/pe | 最新季报 | StockInfo(扩展) | 1条 |
| 林奇PEG | pe_ratio/earnings_growth_3y | 最新+3年 | StockInfo | 3年EPS序列 |
| 巴菲特深度 | net_income/depreciation/capex/operating_margin/current_ratio | 5年 | StockInfo(扩展)+KlineCache | 5年财务 |
| 三阶段DCF | owner_earnings/shares_outstanding/earnings_growth_3y | 当前 | StockInfo(扩展) | 1条 |
| 护城河分析 | roe(5年序列)/gross_margin(5年序列) | 5年 | 需历史StockInfo或KlineCache | 5年数据 |

### 4. FactorFarm (29因子IC评估)

| 数据 | 字段 | 期限 | 来源 | 最小量 |
|------|------|------|------|--------|
| OHLCV | open/high/low/close/volume/amount | ≥60日 | KlineCache | 60行 |
| 前向收益 | close.shift(-5)/close-1 | T+5日 | KlineCache | 60+5行 |

### 5. TechnicalEnsemble (5策略技术集成)

| 数据 | 字段 | 期限 | 来源 | 最小量 |
|------|------|------|------|--------|
| OHLCV | open/high/low/close/volume | ≥126日 | KlineCache | 60行(min), 200行(full) |
| 趋势(ADX) | high/low/close | 14日 | KlineCache | 14行 |
| 均值回归 | close(50日) | 50日 | KlineCache | 50行 |
| 动量 | close(126日) | 126日 | KlineCache | 63行(min) |
| Hurst指数 | close | 60日 | KlineCache | 60行 |

### 6. RiskEngine (三层风控)

| 数据 | 字段 | 期限 | 来源 | 最小量 |
|------|------|------|------|--------|
| 组合持仓 | stock_code/current_value/industry | 当前 | Portfolio表 | ≥1只 |
| 价格历史 | close(多只股票) | 100日 | KlineCache | 每只≥20行 |
| 市场环境 | regime/total_score | 当日 | MarketPerception | 1条 |
| 个股风险 | debt_to_equity/pledge_ratio/cash_ratio/turnover | 当前 | StockInfo | 1条 |

### 7. DebateEngine (多空辩论)

| 数据 | 字段 | 期限 | 来源 | 最小量 |
|------|------|------|------|--------|
| 分析师报告 | analysis_prompt(来自Skill输出) | 本次运行 | 内存 | ≥2份 |
| 市场环境 | regime/pe/roe/industry/pl_pct | 当前 | 内存传递 | 1条 |
| 历史记忆 | situation/decision/outcome | 全历史 | MemoryBank(BM25) | ≥5条记忆 |

### 8. MemoryBank (BM25记忆)

| 数据 | 字段 | 期限 | 来源 | 最小量 |
|------|------|------|------|--------|
| 决策记录 | stock_code/name/regime/pe/roe/industry/pl_pct | 全历史 | memory_data.json | ≥5条 |
| 决策结果 | verdict/confidence/return_pct/correct | 全历史 | memory_data.json | ≥5条 |

### 9. PortfolioOptimizer (组合优化)

| 数据 | 字段 | 期限 | 来源 | 最小量 |
|------|------|------|------|--------|
| 当前持仓 | stock_code/quantity/avg_cost/current_value | 当前 | Portfolio表 | ≥1只 |
| 信号列表 | stock_code/action/confidence | 本次运行 | 内存 | ≥1条 |
| 风控报告 | position_limits/max_single_pct | 本次运行 | RiskEngine输出 | 1条 |
| 现金 | cash | 当前 | TradeExecutor.PositionTracker | 1值 |

### 10. TradeExecutor (交易执行)

| 数据 | 字段 | 期限 | 来源 | 最小量 |
|------|------|------|------|--------|
| 订单信号 | stock_code/direction/quantity/confidence | 本次运行 | PortfolioOptimizer输出 | ≥1条 |
| 实时价格 | stock_code→price | 当日 | API → StockInfo.latest_price | 每只1条 |
| 持仓状态 | stock_code/quantity/avg_cost | 当前 | PositionTracker | 每只1条 |
| 熔断状态 | daily_pnl/weekly_pnl/monthly_pnl | 滚动 | KillSwitch内部 | 最近20日 |

### 11. DataInitializer (数据填充)

| 数据 | 字段 | 期限 | 来源 | 最小量 |
|------|------|------|------|--------|
| 股票池 | 32只默认蓝筹code | 静态 | 硬编码列表 | 32只 |
| 基本面 | 全字段(见StockInfo 33字段) | 最新 | API 6源降级 | 每只1次 |
| K线 | OHLCV+amount+change_pct | 90日 | API 6源降级 | 每只90行 |
| 技术指标 | MA5-60/RSI/volatility/max_dd/trend | 从K线计算 | 本地计算 | 每只1组 |

## 数据存储映射

```
StockInfo表 (33字段):
├─ 基础: stock_code, stock_name, category, industry
├─ 行情: latest_price, change_pct, turnover_rate, volume, amount
├─ 估值: pe_ratio, pb_ratio, roe, gross_margin, net_margin, net_profit
├─ 市值: total_market_cap, float_market_cap
├─ 技术: ma5, ma10, ma20, ma60, rsi_14, macd, atr_14, volatility_20d, max_drawdown_60d, trend, ma_alignment
├─ 扩展: eps, bvps, debt_to_equity, net_income, shares_outstanding, current_ratio, operating_margin, free_cash_flow, revenue_growth_3y, cash_ratio
└─ 时间: updated_at, last_kline_date

KlineCache表 (9字段):
├─ stock_code, trade_date
├─ open, high, low, close, volume, amount, change_pct
└─ turnover_rate

MarketSnapshot表 (3字段):
├─ snapshot_type (indices/north_flow/sectors/lhb_xxx/fundflow_xxx)
├─ data_json (JSON blob)
└─ updated_at

Portfolio表 (已有)
DailyNAV表 (已有)
Order表 (已有)
Trade表 (已有)
```

## 最小数据初始化

首次启动所需的最小数据集:

```
1. StockInfo: ≥20只股票 (DataInitializer默认32只)
2. KlineCache: 每只≥90日 (DataInitializer自动填充)
3. MarketSnapshot: 至少1条indices + 1条north_flow
4. memory_data.json: 空文件可运行 (降级到无记忆模式)

初始化耗时: 32只×并行3线程 ≈ 3-8分钟 (取决于API可用性)
```

## 数据刷新策略

| 数据层 | 刷新频率 | 触发条件 |
|--------|---------|---------|
| 实时行情 | 盘中5分钟 | 前端轮询/选股触发 |
| 日K线 | 每日17:00后 | launch.py启动时检测last_kline_date≠今天 |
| 基本面 | 每日1次 | StockInfo.updated_at > 24h |
| 技术指标 | K线更新后 | _compute_and_save_indicators自动触发 |
| 市场快照 | 5分钟 | API调用时检查MarketSnapshot.updated_at |
