# 量化系统架构设计

> 版本: v15 (统一架构)  
> 更新: 2026-04-01  
> 维护者: 软件架构师

---

## 1. 系统概览

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              量化系统架构 (v15)                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                          入口层 (Entry)                              │   │
│  │  run_v15_full.py | run_v15_local.py | run_portfolio_v2.py          │   │
│  │  dashboard_v15.py | run_simulation_trading.py | generate_combined  │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                    │                                        │
│                                    ▼                                        │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                      core/ (统一核心包)                             │   │
│  │  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐      │   │
│  │  │ config  │ │  data   │ │ strategy│ │  risk   │ │ report  │      │   │
│  │  │  配置   │ │  数据层 │ │  策略   │ │  风控   │ │  报告   │      │   │
│  │  └─────────┘ └─────────┘ └─────────┘ └─────────┘ └─────────┘      │   │
│  │       │           │           │           │           │            │   │
│  │       └───────────┴───────────┴───────────┴───────────┘            │   │
│  │                         │                                            │   │
│  │                    engine.py (回测引擎)                             │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                    │                                        │
│                                    ▼                                        │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                       数据源 (Data Sources)                         │   │
│  │   ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────┐  │   │
│  │   │ baostock │ │ akshare  │ │ efinance │ │ 新浪HTTP │ │腾讯HTTP│  │   │
│  │   └──────────┘ └──────────┘ └──────────┘ └──────────┘ └────────┘  │   │
│  │          │            │            │            │            │     │   │
│  │          └────────────┴────────────┴────────────┴────────────┘     │   │
│  │                           │                                         │   │
│  │                    local_db/ (本地SQLite)                          │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                    backtest_system/ (回测)                         │   │
│  │   Backtrader 核心 + v14/v15 策略适配器 + 报告生成                   │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. 核心模块 (core/)

| 模块 | 文件 | 职责 | 依赖 |
|------|------|------|------|
| **config** | config.py | 统一配置中心 (DataSourceConfig, SelectionConfig, TradeConfig) | dataclasses |
| **data** | data.py | 统一数据层 (五层fallback, 缓存, 批量获取) | baostock, akshare, efinance |
| **strategy** | strategy.py | 选股评分 (V15Scorer, StockFilter, MarketAnalyzer, LLMBroker) | pandas, numpy |
| **risk** | risk.py | 风险管理 (仓位计算, 止损止盈) | - |
| **report** | report.py | 报告生成 (HTML, JSON) | jinja2 |
| **engine** | engine.py | 回测引擎 + 策略适配器 | backtrader |

### 2.1 评分体系 (V15Scorer)

```
综合评分 = 基础因子(40%) + 增强因子(25%) + 市场环境(10%) + 因子引擎V2(25%)
                    │
                    ├── 基础因子: MACD, RSI, 布林带, KDJ, 成交量, ...
                    ├── 增强因子: 假突破过滤, 短期动量, K线形态, VWAP, 学术因子
                    ├── 市场环境: 北向资金, 融资融券, 大盘资金流, 行业板块强度
                    └── 因子引擎V2: 51个日频因子 (动量, 量价, 资金流, 波动率, ...)
```

### 2.2 数据源容错 (五层 fallback)

```
1. baostock.query_history_k_data_plus()  ← 主数据源
2. akshare.stock_zh_a_hist()
3. efinance.futures.get_k_history()
4. 新浪财经 HTTP API (直接请求)
5. 腾讯证券 HTTP API (直接请求)

特性:
  - 会话崩溃自动检测与重建
  - 指数退避重试 (3次: 2s, 4s, 6s)
  - 自适应降速机制
  - 24小时缓存 (real_data_cache/)
```

---

## 3. 目录结构

```
quant system/
├── core/                          # v15 统一核心包 ⭐
│   ├── __init__.py
│   ├── config.py                  # 配置中心
│   ├── data.py                    # 统一数据层
│   ├── strategy.py                # 选股评分系统
│   ├── risk.py                    # 风险管理
│   ├── report.py                  # 报告生成
│   ├── engine.py                  # 回测引擎
│   ├── local_db_adapter.py        # 本地 SQLite 适配器
│   └── local_db_fetcher.py        # 本地数据库
│
├── backtest_system/               # 回测系统 (Backtrader)
│   ├── backtest_engine.py         # 回测核心
│   ├── data_loader.py             # 数据加载
│   ├── strategy_adapter.py        # 策略适配器
│   ├── v14_adapter.py             # v14 策略适配
│   ├── quant_state_integrator.py  # 状态集成
│   ├── report_generator.py        # 回测报告
│   ├── config.py                  # 回测配置
│   ├── cache/                     # 回测缓存
│   ├── reports/                   # 回测报告输出
│   └── templates/                 # 报告模板
│
├── local_db/                      # 本地 SQLite 数据库
│   ├── a_stock_quant.db           # 主数据库 (~53K股票, ~564万行情)
│   └── *.py                       # 数据库工具脚本
│
├── daily_reports_v14/             # v14/v15 选股报告
├── daily_reports_v15_local/       # v15 本地版报告
├── daily_reports_combined/        # 整合报告
├── portfolio_reports/             # 持仓报告
├── simulation_portfolio/          # 模拟交易数据
│
├── real_data_cache/               # 实时数据缓存 (47K+ pkl)
├── logs/                          # 日志文件
│
├── run_v15_full.py                # v15 选股入口
├── run_v15_local.py               # v15 本地数据库版
├── run_v14_full.py                # v14 选股入口 (兼容)
├── run_portfolio_v2.py            # v15 持仓管理
├── run_portfolio.py               # v14 持仓管理 (兼容)
├── run_simulation_trading.py      # 模拟交易
├── generate_combined_report.py    # 整合报告生成
├── dashboard_v15.py               # Streamlit 回测仪表盘
├── example_backtest_v15.py        # v15 回测示例
│
├── factor_engine_v2.py            # 因子引擎V2 (51因子)
├── anti_top_factors.py            # 防顶因子 (10因子)
├── disposition_effect_factors.py  # 处置效应因子
├── momentum_factors.py            # 动量因子
├── capital_flow_factors.py        # 资金流因子
├── volatility_sentiment_factors.py# 波动率/情绪因子
├── microstructure_reversal_factors.py  # 微观结构/反转因子
│
├── CLAUDE.md                      # 项目规范
├── ARCHITECTURE.md                # 本文件
└── README.md                      # 项目说明
```

---

## 4. 版本演进

| 版本 | 状态 | 入口 | 特性 |
|------|------|------|------|
| **v15** | ⭐ 当前 | run_v15_full.py | 统一架构 core/, 五层 fallback, 因子引擎V2, 防顶因子 |
| **v14** | 废弃 | - | 已迁移至 core/ |

---

## 5. 常用命令

```bash
# v15 选股分析 (推荐)
python run_v15_full.py --top 10 --workers 8

# v15 本地数据库版 (更快)
python run_v15_local.py --top 10

# 持仓管理
python run_portfolio_v2.py --date 2026-04-01 --capital 100000

# 模拟交易
python run_simulation_trading.py

# 回测仪表盘
streamlit run dashboard_v15.py

# v15 回测示例
python example_backtest_v15.py

# 整合报告
python generate_combined_report.py --date 2026-04-01
```

---

## 6. 扩展点

### 6.1 新增因子

```python
# 1. 实现因子接口
from core.strategy import BaseFactorEngine
import pandas as pd

class MyFactor(BaseFactorEngine):
    def calculate(self, df: pd.DataFrame) -> dict:
        # 计算因子逻辑
        return {"my_factor": value}

# 2. 注册到 V15Scorer
scorer.register_factor(MyFactor(), weight=0.1)
```

### 6.2 新增数据源

```python
# 在 core/data.py 中添加
def _fetch_from_new_source(self, code: str, days: int) -> pd.DataFrame:
    """新增数据源实现"""
    # 实现获取逻辑
    return df
```

### 6.3 新增风控规则

```python
# 在 core/risk.py 中添加
class MyRiskRule:
    def evaluate(self, portfolio: dict, signal: dict) -> bool:
        # 风控逻辑
        return True
```

---

## 7. 设计原则

1. **单一入口** - 所有功能通过 core/ 模块访问
2. **依赖注入** - 因子/过滤器通过接口注入，便于测试
3. **向后兼容** - 保留 v14 入口，但内部调用 core/
4. **防御编程** - 所有切片/除法/随机操作前检查边界
5. **可观测性** - 统一日志格式，关键路径记录

---

## 8. 性能优化

| 优化项 | 原始 | 优化后 | 提升 |
|--------|------|--------|------|
| 数据获取并行度 | 3 workers | 8 workers | ~2.7x |
| 因子计算批量 | 串行 | 4线程并行 | ~3x |
| 数据源缓存 | 无 | 24h TTL | ~50x |
| 本地数据库 | 无 | SQLite WAL | ~10x |

---

*文档版本: 1.0*