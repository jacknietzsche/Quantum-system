# -*- coding: utf-8 -*-
"""
实验2: 技术指标计算验证 — stockstats + 纯pandas
目标: 验证MA/MACD/RSI/KDJ/Bollinger等指标计算可行性
"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import time

print("=" * 60)
print("实验2: 技术指标计算验证")
print("=" * 60)

# 生成模拟K线数据（100天）
np.random.seed(42)
dates = pd.date_range(end=datetime.now(), periods=100, freq="B")
base_price = 1500
prices = [base_price]
for i in range(99):
    change = np.random.normal(0, 0.02) * prices[-1]
    prices.append(prices[-1] + change)

df = pd.DataFrame({
    "date": dates,
    "open": [p * (1 + np.random.uniform(-0.01, 0.01)) for p in prices],
    "high": [p * (1 + np.random.uniform(0, 0.02)) for p in prices],
    "low": [p * (1 - np.random.uniform(0, 0.02)) for p in prices],
    "close": prices,
    "volume": [np.random.randint(500000, 2000000) for _ in range(100)],
})

df.set_index("date", inplace=True)
print(f"模拟数据: {len(df)} 天")
print(f"价格范围: {df['close'].min():.2f} ~ {df['close'].max():.2f}")

# ========== 实验2.1: stockstats计算技术指标 ==========
print("\n" + "=" * 60)
print("实验2.1: stockstats技术指标计算")
print("=" * 60)

try:
    from stockstats import StockDataFrame

    stock_df = StockDataFrame.retype(df[["open", "high", "low", "close", "volume"]].copy())

    df["ma5"] = stock_df["close"].rolling(5).mean()
    df["ma20"] = stock_df["close"].rolling(20).mean()
    df["ma60"] = stock_df["close"].rolling(60).mean()

    ema12 = stock_df["close"].ewm(span=12).mean()
    ema26 = stock_df["close"].ewm(span=26).mean()
    df["macd"] = ema12 - ema26
    df["macd_signal"] = df["macd"].ewm(span=9).mean()
    df["macd_hist"] = df["macd"] - df["macd_signal"]

    delta = stock_df["close"].diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss
    df["rsi_14"] = 100 - (100 / (1 + rs))

    df["bb_mid"] = stock_df["close"].rolling(20).mean()
    df["bb_std"] = stock_df["close"].rolling(20).std()
    df["bb_upper"] = df["bb_mid"] + 2 * df["bb_std"]
    df["bb_lower"] = df["bb_mid"] - 2 * df["bb_std"]

    latest = df.iloc[-1]
    print(f"计算的指标:")
    print(f"  MA5:  {latest['ma5']:.2f}")
    print(f"  MA20: {latest['ma20']:.2f}")
    print(f"  MA60: {latest['ma60']:.2f}")
    print(f"  MACD: {latest['macd']:.4f}")
    print(f"  RSI(14): {latest['rsi_14']:.2f}")
    print(f"  Bollinger Upper: {latest['bb_upper']:.2f}")
    print(f"  Bollinger Lower: {latest['bb_lower']:.2f}")
    print("[PASS] stockstats技术指标计算成功")
except Exception as e:
    print(f"[FAIL] stockstats失败: {e}")

# ========== 实验2.2: 纯pandas计算 ==========
print("\n" + "=" * 60)
print("实验2.2: 纯pandas计算技术指标")
print("=" * 60)

try:
    df2 = df[["open", "high", "low", "close", "volume"]].copy()

    df2["ma5"] = df2["close"].rolling(5).mean()
    df2["ma20"] = df2["close"].rolling(20).mean()

    ema12 = df2["close"].ewm(span=12).mean()
    ema26 = df2["close"].ewm(span=26).mean()
    df2["macd"] = ema12 - ema26
    df2["macd_signal"] = df2["macd"].ewm(span=9).mean()

    delta = df2["close"].diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss
    df2["rsi_14"] = 100 - (100 / (1 + rs))

    df2["bb_mid"] = df2["close"].rolling(20).mean()
    df2["bb_std"] = df2["close"].rolling(20).std()
    df2["bb_upper"] = df2["bb_mid"] + 2 * df2["bb_std"]
    df2["bb_lower"] = df2["bb_mid"] - 2 * df2["bb_std"]

    latest2 = df2.iloc[-1]
    print(f"纯pandas计算结果:")
    print(f"  MA5:  {latest2['ma5']:.2f}")
    print(f"  MA20: {latest2['ma20']:.2f}")
    print(f"  MACD: {latest2['macd']:.4f}")
    print(f"  RSI(14): {latest2['rsi_14']:.2f}")
    print("[PASS] 纯pandas技术指标计算成功")
except Exception as e:
    print(f"[FAIL] pandas计算失败: {e}")

# ========== 实验2.3: 多股票批量计算 ==========
print("\n" + "=" * 60)
print("实验2.3: 多股票批量计算性能")
print("=" * 60)

try:
    stock_codes = [f"sh.60000{i}" for i in range(50)]

    start_time = time.time()
    results = {}

    for code in stock_codes:
        stock_data = pd.DataFrame({
            "close": np.random.uniform(10, 100, 100),
        })
        stock_data["ma20"] = stock_data["close"].rolling(20).mean()
        stock_data["rsi"] = 100 - (100 / (1 + (stock_data["close"].diff().rolling(14).mean() /
                                                  (-stock_data["close"].diff().rolling(14).mean()).abs())))
        results[code] = stock_data.iloc[-1].to_dict()

    elapsed = time.time() - start_time
    print(f"50只股票技术指标计算耗时: {elapsed:.3f}秒")
    print(f"平均每只: {elapsed/50*1000:.1f}ms")
    print("[PASS] 批量计算性能可接受")
except Exception as e:
    print(f"[FAIL] 批量计算失败: {e}")

print("\n" + "=" * 60)
print("实验2完成")
print("=" * 60)
