# -*- coding: utf-8 -*-
"""
实验6: 完整数据管道验证
目标: 验证 数据获取→存储→查询→技术指标计算→输出 的完整流程
"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import sqlite3
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta

print("=" * 60)
print("实验6: 完整数据管道验证")
print("=" * 60)

# ========== 实验6.1: 模拟完整管道 ==========
print("\n" + "=" * 60)
print("实验6.1: 模拟完整数据管道（生成→存储→查询→计算）")
print("=" * 60)

try:
    # Step 1: 生成模拟数据（模拟从API获取）
    np.random.seed(42)
    dates = pd.date_range(end=datetime.now(), periods=365, freq="B")
    base_price = 1500
    prices = [base_price]
    for i in range(364):
        change = np.random.normal(0, 0.02) * prices[-1]
        prices.append(max(prices[-1] + change, 100))

    raw_data = pd.DataFrame({
        "stock_code": ["sh.600519"] * 365,
        "trade_date": [d.strftime("%Y-%m-%d") for d in dates],
        "open": [p * (1 + np.random.uniform(-0.01, 0.01)) for p in prices],
        "high": [p * (1 + np.random.uniform(0, 0.02)) for p in prices],
        "low": [p * (1 - np.random.uniform(0, 0.02)) for p in prices],
        "close": prices,
        "volume": [np.random.randint(500000, 2000000) for _ in range(365)],
    })
    raw_data["amount"] = raw_data["close"] * raw_data["volume"]
    raw_data["change_pct"] = raw_data["close"].pct_change() * 100
    raw_data["turnover_rate"] = np.random.uniform(0.3, 1.0, 365)

    print(f"Step 1: 生成模拟数据 {len(raw_data)} 条")
    print(f"  日期范围: {raw_data['trade_date'].iloc[0]} ~ {raw_data['trade_date'].iloc[-1]}")
    print(f"  价格范围: {raw_data['close'].min():.2f} ~ {raw_data['close'].max():.2f}")

    # Step 2: 存入SQLite
    db_path = Path("experiments/test_pipeline.db")
    conn = sqlite3.connect(str(db_path))

    conn.execute("""
        CREATE TABLE IF NOT EXISTS kline_daily (
            stock_code TEXT NOT NULL,
            trade_date TEXT NOT NULL,
            open REAL, high REAL, low REAL, close REAL,
            volume REAL, amount REAL, change_pct REAL, turnover_rate REAL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (stock_code, trade_date)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_kline_date ON kline_daily (stock_code, trade_date)")

    raw_data.to_sql("kline_daily", conn, if_exists="replace", index=False)
    print(f"\nStep 2: 存入SQLite {len(raw_data)} 条")

    # Step 3: 从数据库查询
    df = pd.read_sql_query("""
        SELECT * FROM kline_daily
        WHERE stock_code = 'sh.600519'
        ORDER BY trade_date
    """, conn)
    print(f"\nStep 3: 从数据库查询 {len(df)} 条")

    # Step 4: 计算技术指标
    df["ma5"] = df["close"].rolling(5).mean()
    df["ma20"] = df["close"].rolling(20).mean()
    df["ma60"] = df["close"].rolling(60).mean()

    ema12 = df["close"].ewm(span=12).mean()
    ema26 = df["close"].ewm(span=26).mean()
    df["macd"] = ema12 - ema26
    df["macd_signal"] = df["macd"].ewm(span=9).mean()

    delta = df["close"].diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss
    df["rsi_14"] = 100 - (100 / (1 + rs))

    df["bb_mid"] = df["close"].rolling(20).mean()
    df["bb_std"] = df["close"].rolling(20).std()
    df["bb_upper"] = df["bb_mid"] + 2 * df["bb_std"]
    df["bb_lower"] = df["bb_mid"] - 2 * df["bb_std"]

    print(f"\nStep 4: 计算技术指标")
    latest = df.iloc[-1]
    print(f"  最新日期: {latest['trade_date']}")
    print(f"  收盘价: {latest['close']:.2f}")
    print(f"  MA5: {latest['ma5']:.2f}")
    print(f"  MA20: {latest['ma20']:.2f}")
    print(f"  MA60: {latest['ma60']:.2f}")
    print(f"  MACD: {latest['macd']:.4f}")
    print(f"  RSI(14): {latest['rsi_14']:.2f}")
    print(f"  Bollinger Upper: {latest['bb_upper']:.2f}")
    print(f"  Bollinger Lower: {latest['bb_lower']:.2f}")

    # Step 5: 生成分析报告
    report = f"""
=== 600519 贵州茅台 技术分析报告 ===
日期: {latest['trade_date']}
收盘价: {latest['close']:.2f}

均线系统:
  MA5:  {latest['ma5']:.2f} ({'上升' if latest['ma5'] > latest['ma20'] else '下降'})
  MA20: {latest['ma20']:.2f}
  MA60: {latest['ma60']:.2f}
  均线排列: {'多头排列' if latest['ma5'] > latest['ma20'] > latest['ma60'] else '非多头排列'}

MACD:
  DIF: {latest['macd']:.4f}
  DEA: {latest['macd_signal']:.4f}
  柱状: {latest['macd'] - latest['macd_signal']:.4f}
  信号: {'金叉' if latest['macd'] > latest['macd_signal'] else '死叉'}

RSI(14): {latest['rsi_14']:.2f}
  状态: {'超买' if latest['rsi_14'] > 70 else '超卖' if latest['rsi_14'] < 30 else '中性'}

布林带:
  上轨: {latest['bb_upper']:.2f}
  中轨: {latest['bb_mid']:.2f}
  下轨: {latest['bb_lower']:.2f}
  位置: {'上轨附近' if latest['close'] > latest['bb_upper'] * 0.98 else '下轨附近' if latest['close'] < latest['bb_lower'] * 1.02 else '中间'}

综合判断: {'看涨' if latest['ma5'] > latest['ma20'] and latest['macd'] > latest['macd_signal'] else '看跌' if latest['ma5'] < latest['ma20'] and latest['macd'] < latest['macd_signal'] else '中性'}
"""
    print(f"\nStep 5: 生成分析报告")
    print(report)

    conn.close()
    db_path.unlink()
    print("[PASS] 完整数据管道成功")
except Exception as e:
    print(f"[FAIL] 完整数据管道失败: {e}")
    import traceback
    traceback.print_exc()

# ========== 实验6.2: 增量更新模拟 ==========
print("\n" + "=" * 60)
print("实验6.2: 增量更新模拟")
print("=" * 60)

try:
    # 模拟已有数据
    existing_dates = pd.date_range("2026-01-01", "2026-06-10", freq="B")
    existing_data = pd.DataFrame({
        "stock_code": ["sh.600519"] * len(existing_dates),
        "trade_date": [d.strftime("%Y-%m-%d") for d in existing_dates],
        "close": np.random.uniform(1400, 1600, len(existing_dates)),
    })

    # 模拟新数据（6月11日-13日）
    new_dates = pd.date_range("2026-06-11", "2026-06-13", freq="B")
    new_data = pd.DataFrame({
        "stock_code": ["sh.600519"] * len(new_dates),
        "trade_date": [d.strftime("%Y-%m-%d") for d in new_dates],
        "close": np.random.uniform(1500, 1550, len(new_dates)),
    })

    # 增量合并
    existing_set = set(existing_data["trade_date"])
    truly_new = new_data[~new_data["trade_date"].isin(existing_set)]

    print(f"已有数据: {len(existing_data)} 条 (截至 {existing_data['trade_date'].max()})")
    print(f"新数据: {len(new_data)} 条")
    print(f"真正新增: {len(truly_new)} 条")
    print(f"新增日期: {list(truly_new['trade_date'])}")

    merged = pd.concat([existing_data, truly_new]).sort_values("trade_date").reset_index(drop=True)
    print(f"合并后: {len(merged)} 条")
    print(f"日期范围: {merged['trade_date'].iloc[0]} ~ {merged['trade_date'].iloc[-1]}")

    print("[PASS] 增量更新模拟成功")
except Exception as e:
    print(f"[FAIL] 增量更新模拟失败: {e}")

# ========== 实验6.3: 多股票批量查询 ==========
print("\n" + "=" * 60)
print("实验6.3: 多股票批量查询性能")
print("=" * 60)

try:
    import time

    db_path = Path("experiments/test_batch.db")
    conn = sqlite3.connect(str(db_path))

    conn.execute("""
        CREATE TABLE IF NOT EXISTS kline_daily (
            stock_code TEXT NOT NULL,
            trade_date TEXT NOT NULL,
            close REAL,
            PRIMARY KEY (stock_code, trade_date)
        )
    """)

    # 插入50只股票各250天数据
    stock_codes = [f"sh.60000{i:02d}" for i in range(50)]
    all_data = []
    for code in stock_codes:
        for j in range(250):
            all_data.append((code, f"2026-01-{(j%28)+1:02d}", np.random.uniform(10, 100)))

    conn.executemany("INSERT OR REPLACE INTO kline_daily VALUES (?, ?, ?)", all_data)
    conn.commit()

    # 批量查询
    start = time.time()
    for code in stock_codes:
        df = pd.read_sql_query(
            f"SELECT * FROM kline_daily WHERE stock_code = '{code}' ORDER BY trade_date",
            conn
        )
    elapsed = time.time() - start

    print(f"50只股票各250天数据:")
    print(f"  总数据量: {len(all_data)} 条")
    print(f"  批量查询耗时: {elapsed:.3f}秒")
    print(f"  平均每只: {elapsed/50*1000:.1f}ms")

    # 聚合查询
    start = time.time()
    stats = pd.read_sql_query("""
        SELECT stock_code, COUNT(*) as days, AVG(close) as avg_price
        FROM kline_daily
        GROUP BY stock_code
        ORDER BY avg_price DESC
        LIMIT 10
    """, conn)
    elapsed = time.time() - start
    print(f"\n聚合查询Top10:")
    print(f"  耗时: {elapsed:.3f}秒")
    print(f"  结果:\n{stats.to_string()}")

    conn.close()
    db_path.unlink()
    print("\n[PASS] 多股票批量查询成功")
except Exception as e:
    print(f"[FAIL] 多股票批量查询失败: {e}")

# ========== 实验6.4: 数据完整性检查 ==========
print("\n" + "=" * 60)
print("实验6.4: 数据完整性检查")
print("=" * 60)

try:
    # 模拟缺失数据
    all_trading_days = pd.date_range("2026-06-01", "2026-06-14", freq="B")
    stored_dates = ["2026-06-02", "2026-06-03", "2026-06-05", "2026-06-06", "2026-06-09", "2026-06-10"]

    all_days_set = set([d.strftime("%Y-%m-%d") for d in all_trading_days])
    stored_set = set(stored_dates)
    missing = sorted(all_days_set - stored_set)

    print(f"交易日: {len(all_days_set)} 天")
    print(f"已存储: {len(stored_set)} 天")
    print(f"缺失: {len(missing)} 天")
    print(f"缺失日期: {missing}")
    print(f"完整率: {len(stored_set)/len(all_days_set)*100:.1f}%")

    # 模拟补全
    new_data = []
    for date in missing:
        new_data.append(("sh.600519", date, 1500 + np.random.uniform(-50, 50)))
    print(f"\n补全数据: {len(new_data)} 条")
    for d in new_data:
        print(f"  {d[0]} {d[1]}: {d[2]:.2f}")

    print("\n[PASS] 数据完整性检查成功")
except Exception as e:
    print(f"[FAIL] 数据完整性检查失败: {e}")

print("\n" + "=" * 60)
print("实验6完成")
print("=" * 60)
