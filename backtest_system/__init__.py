"""
A股量化回测系统 (Backtrader核心)
=====================================
模块化回测框架，对标聚宽/米筐专业量化平台

核心模块:
    - DataLoader: 数据加载（akshare在线 + CSV/HDF5本地）
    - StrategyAdapter: 策略适配（桥接已有策略到Backtrader）
    - BacktestEngine: 回测引擎（封装Backtrader核心）
    - QuantStateIntegrator: 因子分析与风险评估
    - ReportGenerator: 专业分析报告生成

版本: 1.0.0
"""

__version__ = "1.0.0"
__author__ = "Quant System"

from .config import BacktestConfig
from .data_loader import DataLoader
from .strategy_adapter import BacktraderStrategyAdapter
from .backtest_engine import BacktestEngine
from .quant_state_integrator import QuantStateIntegrator

__all__ = [
    "BacktestConfig",
    "DataLoader",
    "BacktraderStrategyAdapter",
    "BacktestEngine",
    "QuantStateIntegrator",
]
