"""
实验1: 数据层验证 — BaoStock + yfinance + SQLite存储
目标: 验证数据获取→存储→查询的完整流程
"""
import sqlite3
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path

# ========== 实验1.1: BaoStock日K线获取 ==========
print("=" * 60)
print("实验1.1: BaoStock日K线获取")
print("=" * 60)

try:
    import baostock as bs
    lg = bs.login()
    print(f"BaoStock登录: {lg.error_msg}")

    # 获取贵州茅台(600519)最近30天日K线
    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=60)).strftime("%Y-%m-%d")

    rs = bs.query_history_k_data_plus(
        "sh.600519",
        "date,code,open,high,low,close,volume,amount,turn,pctChg",
        start_date=start_date,
        end_date=end_date,
        frequency="d",
        adjustflag="2"  # 前复权
    )

    data_list = []
    while (rs.error_code == '0') and rs.next():
        data_list.append(rs.get_row_data())

    df = pd.DataFrame(data_list, columns=rs.fields)
    print(f"获取到 {len(df)} 条日K线数据")
    print(f"日期范围: {df['date'].iloc[0]} ~ {df['date'].iloc[-1]}")
    print(f"列名: {list(df.columns)}")
    print(f"前3行:\n{df.head(3)}")

    bs.logout()
    print("✅ BaoStock日K线获取成功\n")
except Exception as e:
    print(f"❌ BaoStock失败: {e}\n")

# ========== 实验1.2: yfinance数据获取 ==========
print("=" * 60)
print("实验1.2: yfinance数据获取")
print("=" * 60)

try:
    import yfinance as yf

    # 获取贵州茅台A股(600519.SS)最近30天日K线
    ticker = yf.Ticker("600519.SS")
    df = ticker.history(period="1mo")
    print(f"获取到 {len(df)} 条日K线数据")
    print(f"日期范围: {df.index[0]} ~ {df.index[-1]}")
    print(f"列名: {list(df.columns)}")
    print(f"前3行:\n{df.head(3)}")

    # 获取美股AAPL作为对比
    aapl = yf.Ticker("AAPL")
    df_aapl = aapl.history(period="1mo")
    print(f"\nAAPL获取到 {len(df_aapl)} 条数据")
    print(f"✅ yfinance获取成功\n")
except Exception as e:
    print(f"❌ yfinance失败: {e}\n")

# ========== 实验1.3: SQLite数据库操作 ==========
print("=" * 60)
print("实验1.3: SQLite数据库操作")
print("=" * 60)

try:
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

    # 清理测试数据库
    db_path.unlink()
    print("\n✅ SQLite数据库操作成功\n")
except Exception as e:
    print(f"❌ SQLite失败: {e}\n")

# ========== 实验1.4: 增量更新逻辑验证 ==========
print("=" * 60)
print("实验1.4: 增量更新逻辑验证")
print("=" * 60)

try:
    # 模拟增量更新：已有数据 + 新数据
    existing_data = pd.DataFrame({
        "trade_date": ["2026-06-10", "2026-06-11"],
        "close": [1500.0, 1510.0]
    })

    new_data = pd.DataFrame({
        "trade_date": ["2026-06-11", "2026-06-12", "2026-06-13"],
        "close": [1510.0, 1525.0, 1530.0]
    })

    # 增量合并：只添加新日期的数据
    existing_dates = set(existing_data["trade_date"])
    truly_new = new_data[~new_data["trade_date"].isin(existing_dates)]

    print(f"已有数据: {len(existing_data)} 条")
    print(f"新数据: {len(new_data)} 条")
    print(f"真正新增: {len(truly_new)} 条")
    print(f"新增日期: {list(truly_new['trade_date'])}")

    # 合并
    merged = pd.concat([existing_data, truly_new]).sort_values("trade_date").reset_index(drop=True)
    print(f"合并后: {len(merged)} 条")
    print(f"数据:\n{merged}")

    print("\n✅ 增量更新逻辑验证成功\n")
except Exception as e:
    print(f"❌ 增量更新失败: {e}\n")

print("=" * 60)
print("实验1完成")
print("=" * 60)
