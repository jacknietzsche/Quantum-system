# -*- coding: utf-8 -*-
"""
实验1.3: SQLite数据库操作验证
"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import sqlite3
import pandas as pd
from pathlib import Path

print("=" * 60)
print("实验1.3: SQLite数据库操作")
print("=" * 60)

db_path = Path("experiments/test_data.db")
conn = sqlite3.connect(str(db_path))

# 创建K线表
conn.execute("""
    CREATE TABLE IF NOT EXISTS kline_daily (
        stock_code TEXT NOT NULL,
        trade_date TEXT NOT NULL,
        open REAL,
        high REAL,
        low REAL,
        close REAL,
        volume REAL,
        amount REAL,
        change_pct REAL,
        turnover_rate REAL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (stock_code, trade_date)
    )
""")

# 创建索引
conn.execute("""
    CREATE INDEX IF NOT EXISTS idx_kline_date
    ON kline_daily (stock_code, trade_date)
""")

# 插入测试数据
test_data = [
    ("sh.600519", "2026-06-10", 1500.0, 1520.0, 1495.0, 1510.0, 1000000, 1.51e9, 1.2, 0.5),
    ("sh.600519", "2026-06-11", 1510.0, 1530.0, 1505.0, 1525.0, 1200000, 1.82e9, 0.99, 0.6),
    ("sh.600519", "2026-06-12", 1525.0, 1540.0, 1520.0, 1535.0, 1100000, 1.69e9, 0.66, 0.55),
]

conn.executemany("""
    INSERT OR REPLACE INTO kline_daily
    (stock_code, trade_date, open, high, low, close, volume, amount, change_pct, turnover_rate)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
""", test_data)

conn.commit()
print(f"插入 {len(test_data)} 条测试数据")

# 查询数据
result = pd.read_sql_query(
    "SELECT * FROM kline_daily WHERE stock_code = 'sh.600519' ORDER BY trade_date",
    conn
)
print(f"查询到 {len(result)} 条数据")
print(f"数据:\n{result}")

# 查询统计
stats = pd.read_sql_query("""
    SELECT
        stock_code,
        COUNT(*) as total_days,
        MIN(trade_date) as start_date,
        MAX(trade_date) as end_date,
        AVG(close) as avg_close
    FROM kline_daily
    GROUP BY stock_code
""", conn)
print(f"\n统计:\n{stats}")

conn.close()
db_path.unlink()
print("\n[PASS] SQLite数据库操作成功")
