#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试策略适配器的get_sell_signals方法
"""

import sys
from pathlib import Path

# 项目根目录
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from backtest.backtest_comprehensive_local import V16StrategyAdapter

# 创建策略实例
strategy = V16StrategyAdapter()

# 测试get_sell_signals方法
date = "2026-04-10"
data_dict = {"stocks": {"600519": {"close": 1800.0}}}
current_portfolio = {"600519": {"size": 100, "price": 1700.0}}

try:
    # 调用get_sell_signals方法，传递3个参数（不包括self）
    sell_signals = strategy.get_sell_signals(date, data_dict, current_portfolio)
    print(f"测试成功！卖出信号: {sell_signals}")
    print("方法签名正确，接受3个参数")
except TypeError as e:
    print(f"测试失败！错误信息: {e}")
    import inspect
    import backtest.backtest_comprehensive_local
    # 检查方法签名
    sig = inspect.signature(V16StrategyAdapter.get_sell_signals)
    print(f"方法签名: {sig}")
