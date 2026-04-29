"""
A股量化系统 - 统一核心架构 (v15)
=====================================
回测-实盘一体化、模块化低耦合、工业级架构。

核心模块:
    - core.config      : 统一配置中心（交易成本/仓位管理/风控/报告/回测）
    - core.data        : 统一数据层（五源fallback + 共享缓存）
    - core.engine      : 统一核心引擎层（Backtrader回测引擎）
    - core.strategy    : 策略与因子层（v14评分体系 + 策略适配器 + 因子引擎）
    - core.risk        : 风控与持仓模块（风控检查 + 持仓管理 + 止损止盈）
    - core.report      : 统一报告输出（回测报告 + 每日持仓报告 + Plotly图表）

对外入口:
    - run_v15_full.py      : 每日选股 + 报告生成
    - run_portfolio_v2.py   : 模拟持仓调仓
    - example_backtest_v15.py : 回测示例

版本: 15.0.0
"""

__version__ = "15.0.0"
__author__ = "Quant System"
