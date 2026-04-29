#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
调试因子引擎
"""

import pandas as pd
import numpy as np
from factor_engine_v2 import FactorEngineV2

np.random.seed(42)
n = 800
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

# 单独测试行为金融学因子模块
print("[单独测试行为金融学因子模块]")
try:
    from behavioral_classic_factors import BehavioralClassicFactorCalculator
    bc_calc = BehavioralClassicFactorCalculator()
    bc_result = bc_calc.calculate_all(df)
print("  CGO: %s" % bc_result.get("cgo_20d", 0)
print("  VNSP: %s" % bc_result.get("vnsp_20d", 0)
print("  CDE: %s" % bc_result.get("cde_20d", 0)
print("  ΔDE: %s" % bc_result.get("dde_20d", 0)
print("  动量: %s" % bc_result.get("momentum_raw", 0)
print("  长期反转: %s" % bc_result.get("lt_rev_raw", 0)
print("  质量因子: %s" % bc_result.get("quality_score", 0)
print("  低波因子: %s" % bc_result.get("low_vol_score", 0)
print("  复合调整系数: %s" % bc_result.get("composite_adjustment", 1.0)
except Exception as e:
print("  错误: %s" % e)
    import traceback

    traceback.print_exc()

print("[运行完整因子引擎]")
result = engine.calculate(df)

print("\n[综合调整系数] %.4f" % result["adjustment_coef"])

print("\n[各大类评分]")
for cat, score in result['category_scores'].items():
    w = engine.WEIGHTS.get(cat, 0)
    bar = '#' * int(score * 30)
    print("  %s: %.4f (w=%.0f) |%s" % (cat.ljust(20), score, w*100, bar))

# 检查所有类别
print("\n[所有类别]")
for cat in engine.WEIGHTS.keys():
    if cat in result['category_scores']:
print("  %s: 存在" % cat)
    else:
print("  %s: 缺失" % cat)

print("\n[因子总数] %s" % len(result["all_factors"])

# 检查是否有行为金融学因子
print("\n[行为金融学因子检查]")
behavioral_factors = [k for k in result['all_factors'].keys() if 'cgo' in k.lower() or 'vnsp' in k.lower() or 'cde' in k.lower() or 'dde' in k.lower()]
print("  找到 %s 个行为金融学因子" % len(behavioral_factors)
for factor in behavioral_factors[:10]:  # 显示前10个
print("    %s: %s" % factor, result["all_factors"][factor])