#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试更新后的因子引擎
"""

import pandas as pd
import numpy as np
from factor_engine_v2 import FactorEngineV2


np.random.seed(42)
n = 800  # 增加数据长度以满足长期因子计算需求
close = 10.0 * np.cumprod(1 + np.random.normal(0.0005, 0.022, n))
high = close * (1 + np.random.uniform(0, 0.03, n))
low = close * (1 - np.random.uniform(0, 0.03, n))
open_ = close * (1 + np.random.normal(0, 0.012, n))
volume = np.random.uniform(1e7, 5e8, n)
amount = volume * close
pctChg = (close / np.roll(close, 1) - 1) * 100
pctChg[0] = 0
turn = np.random.uniform(0.5, 5.0, n)

df = pd.DataFrame({
    'open': open_, 'close': close, 'high': high, 'low': low,
    'volume': volume, 'amount': amount, 'pctChg': pctChg, 'turn': turn
})

engine = FactorEngineV2()
print("[模块状态]")
for m in engine.get_module_info():
    status = '[ON]' if m['enabled'] else '[OFF]'
print("  %s %s: %s (权重:%s)" % status, m["name"], m["description"], m["weight"])

result = engine.calculate(df)
print("\n[综合调整系数] %.4f" % result["adjustment_coef"])

print("\n[各大类评分]")
for cat, score in result['category_scores'].items():
    w = engine.WEIGHTS.get(cat, 0)
    bar = '#' * int(score * 30)
    print("  %s: %.4f (w=%.0f) |%s" % (cat.ljust(20), score, w*100, bar))

print("\n[风险摘要]")
risk = result['risk_summary']
print("  总体信号: %s" % risk["overall_signal"])
print("  预警(%s): %s" % risk["warning_count"], risk["warnings"] or "无")
print("  正面(%s): %s" % risk["positive_count"], risk["positives"] or "无")

print("\n[因子总数] %s" % len(result["all_factors"])
print("[PASS] FactorEngineV2 测试通过")