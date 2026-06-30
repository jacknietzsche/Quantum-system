# A股量化回测系统 v1.0

> 基于 Backtrader 的专业量化回测框架，对标聚宽/米筐，无缝对接 v14 量化选股系统

## 📐 系统架构

```
backtest_system/
├── __init__.py                  # 包入口
├── config.py                    # 全局配置（交易成本/仓位/风险/因子）
├── data_loader.py               # 数据加载（akshare/baostock/CSV/HDF5）
├── strategy_adapter.py          # 策略适配器（桥接已有策略→Backtrader）
├── backtest_engine.py           # 回测引擎（封装Backtrader核心）
├── quant_state_integrator.py    # 因子分析与风险评估
├── report_generator.py          # HTML交互式报告生成
├── v14_adapter.py              # v14策略专用适配器（可选）
└── templates/                   # 模板文件
```

## 🚀 快速开始

### 1. 安装依赖

```bash
pip install backtrader pandas numpy plotly jinja2 scipy scikit-learn
# 可选数据源
pip install akshare baostock
```

### 2. 适配你的策略

你的策略只需要实现两个方法：

```python
class MyExistingStrategy:
    def __init__(self, params: dict):
        """初始化，接收参数字典"""
        self.my_param = params.get("my_param", 10)

    def get_buy_signals(self, date: str, data: dict) -> list:
        """
        返回当日拟买入股票代码列表
        - date: "2025-01-15"
        - data: {"date": "...", "stocks": {"600519": {"close": 1800, ...}}, "market": {...}}
        - return: ["600519", "000001"]
        """
        buy_list = []
        for code, info in data["stocks"].items():
            if self._should_buy(code, info):
                buy_list.append(code)
        return buy_list

    def get_sell_signals(self, date: str, data: dict, current_portfolio: dict) -> list:
        """
        返回当日拟卖出股票代码列表
        - current_portfolio: {"600519": {"size": 100, "price": 1800, "pnl_pct": 5.2}}
        """
        sell_list = []
        for code in current_portfolio:
            if self._should_sell(code, data):
                sell_list.append(code)
        return sell_list
```

### 3. 运行回测

```python
from backtest_system import (
    BacktestConfig, DataLoader, BacktestEngine,
    ReportGenerator, QuantStateIntegrator,
)

# 配置
config = BacktestConfig()

# 加载数据
loader = DataLoader(start_date="20250101", end_date="20260327")
data_dict = loader.load_multi(["600519", "000001", "601318"])

# 创建你的策略
my_strategy = MyExistingStrategy({"my_param": 20})

# 运行回测
engine = BacktestEngine(config)
result = engine.run_backtest(
    existing_strategy=my_strategy,
    data_dict=data_dict,
    initial_cash=1_000_000,
)

# 因子分析
qs = QuantStateIntegrator(config.factor)
factor_result = qs.analyze_factors(factors_df, returns_df)

# 生成报告
reporter = ReportGenerator(config.report)
html_path = reporter.generate(
    backtest_result=result,
    factor_analysis=factor_result,
)
print(f"报告已生成: {html_path}")
```

## 🔗 与 v14 量化系统结合

### 方式1: 一键运行器

```python
from backtest_system.v14_adapter import V14BacktestRunner

runner = V14BacktestRunner()
report = runner.run(
    stock_pool=["600519", "000001", "601318", "000858", "002714"],
    start_date="20250101",
    end_date="20260327",
    cash=1_000_000,
    top_n=5,
)
```

### 方式2: 从 v14 报告直接回测

```python
from backtest_system.v14_adapter import V14BacktestRunner

runner = V14BacktestRunner()
report = runner.run_from_v14_report(
    json_report_path="daily_reports_v14/v14_report_2026-03-25.json",
    cash=1_000_000,
)
```

### 方式3: 直接使用 V14StrategyAdapter

```python
from backtest_system.v14_adapter import V14StrategyAdapter

v14_strategy = V14StrategyAdapter(
    data_fetcher=fetcher,    # RealDataFetcher 实例
    rebalance_days=20,
    top_n=5,
)

# 传入回测引擎
engine = BacktestEngine(config)
result = engine.run_backtest(
    existing_strategy=v14_strategy,
    data_dict=data_dict,
)
```

## ⚙️ 配置参数

所有参数在 `config.py` 中集中管理：

```python
config = BacktestConfig()

# 交易成本
config.trade.commission_rate = 0.0002    # 手续费 万分之二
config.trade.stamp_duty_rate = 0.001     # 印花税 千分之一
config.trade.slippage_rate = 0.001       # 滑点 千分之一

# 仓位管理
config.portfolio.max_position_pct = 0.10     # 单票上限 10%
config.portfolio.max_total_position = 0.80   # 总仓位上限 80%
config.portfolio.initial_cash = 1_000_000    # 初始资金

# 风险参数
config.risk.risk_free_rate = 0.025           # 无风险利率
config.risk.confidence_level = 0.95          # VaR 置信度

# 因子分析
config.factor.ic_method = "spearman"         # IC 计算方法
config.factor.n_groups = 5                   # 分层数量
```

## 📊 报告内容

生成的 HTML 报告包含：

| 模块 | 内容 |
|------|------|
| 回测概览 | 收益率、Sharpe、最大回撤、交易次数、胜率 |
| 收益分析 | 净值曲线（策略vs基准）、回撤图、年度收益 |
| 风险指标 | VaR、CVaR、波动率、Sortino、偏度、峰度 |
| 交易明细 | 交易流水表、已平仓盈亏表 |
| 因子分析 | IC/IR、分层回测、因子衰减、风格暴露 |

## 🧪 运行示例

```bash
# 完整示例（含模拟数据，无需联网）
python example_my_strategy_backtest.py
```

示例包含三个场景：
1. **自定义策略回测**：双均线策略 + 因子分析 + 报告生成
2. **v14 策略集成**：v14 评分系统对接回测框架
3. **参数优化**：多参数组合对比

## 📁 目录结构

```
quant system/
├── backtest_system/              # 回测系统（本模块）
│   ├── __init__.py
│   ├── config.py
│   ├── data_loader.py
│   ├── strategy_adapter.py
│   ├── backtest_engine.py
│   ├── quant_state_integrator.py
│   ├── report_generator.py
│   ├── v14_adapter.py
│   ├── cache/                    # 数据缓存
│   └── reports/                  # 生成的报告
├── example_my_strategy_backtest.py   # 示例脚本
└── ...                            # v14 量化系统其他模块
```

## 🔧 技术栈

| 库 | 用途 |
|----|------|
| `backtrader` | 回测引擎核心 |
| `akshare` | A股在线数据 |
| `baostock` | 备用数据源 |
| `pandas` | 数据处理 |
| `numpy` | 数值计算 |
| `plotly` | 交互式图表 |
| `jinja2` | HTML模板 |
| `scipy` | 统计分析 |
| `scikit-learn` | 因子中性化 |
