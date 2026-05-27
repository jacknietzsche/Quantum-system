#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检查数据库中各股票的数据覆盖范围
找出需要获取近5年数据的股票
"""

import sqlite3
import pandas as pd
from datetime import datetime, timedelta
import sys
import os

def check_data_coverage(db_path: str):
    """检查数据库中各股票的数据覆盖范围"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    print("=" * 60)
    print("数据库数据覆盖情况检查")
    print("=" * 60)
    
    # 1. 总体统计
    cursor.execute("SELECT COUNT(*) FROM daily_price")
    total_records = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(DISTINCT code) FROM daily_price")
    total_stocks = cursor.fetchone()[0]
    
    cursor.execute("SELECT MIN(trade_date), MAX(trade_date) FROM daily_price")
    date_range = cursor.fetchone()
    
    print(f"\n【总体统计】")
    print(f"  总记录数: {total_records:,}")
    print(f"  股票数量: {total_stocks:,}")
    print(f"  日期范围: {date_range[0]} 到 {date_range[1]}")
    
    # 2. 按数据量分组统计
    print(f"\n【按数据量分组统计】")
    
    conditions = [
        (0, 50, "不足50条"),
        (50, 100, "50-100条"),
        (100, 250, "100-250条"),
        (250, 500, "250-500条"),
        (500, 1000, "500-1000条"),
        (1000, 999999, "1000条以上")
    ]
    
    for min_val, max_val, label in conditions:
        cursor.execute("""
            SELECT COUNT(DISTINCT code)
            FROM (
                SELECT code, COUNT(*) as cnt
                FROM daily_price
                GROUP BY code
                HAVING cnt >= ? AND cnt < ?
            )
        """, (min_val, max_val))
        
        count = cursor.fetchone()[0]
        print(f"  {label}: {count} 只股票")
    
    # 3. 数据量最少的10只股票
    print(f"\n【数据量最少的10只股票】")
    cursor.execute("""
        SELECT code, COUNT(*) as cnt, MIN(trade_date), MAX(trade_date)
        FROM daily_price
        GROUP BY code
        ORDER BY cnt ASC
        LIMIT 10
    """)
    
    for row in cursor.fetchall():
        print(f"  {row[0]}: {row[1]}条, {row[2]} 到 {row[3]}")
    
    # 4. 数据量最多的10只股票
    print(f"\n【数据量最多的10只股票】")
    cursor.execute("""
        SELECT code, COUNT(*) as cnt, MIN(trade_date), MAX(trade_date)
        FROM daily_price
        GROUP BY code
        ORDER BY cnt DESC
        LIMIT 10
    """)
    
    for row in cursor.fetchall():
        print(f"  {row[0]}: {row[1]}条, {row[2]} 到 {row[3]}")
    
    # 5. 需要获取近5年数据的股票
    print(f"\n【需要获取近5年数据的股票（数据量<1000条）】")
    cursor.execute("""
        SELECT code, COUNT(*) as cnt, MAX(trade_date)
        FROM daily_price
        GROUP BY code
        HAVING cnt < 1000
        ORDER BY cnt ASC
        LIMIT 20
    """)
    
    stocks_need_data = cursor.fetchall()
    print(f"  共有 {len(stocks_need_data)} 只股票需要获取数据（显示前20只）:")
    for row in stocks_need_data:
        print(f"  {row[0]}: 当前{row[1]}条, 最新日期{row[2]}")
    
    conn.close()
    
    print("\n" + "=" * 60)
    print("检查完成!")
    print("=" * 60)


if __name__ == "__main__":
    db_path = "local_db/a_stock_quant.db"
    
    if not os.path.exists(db_path):
        print(f"错误: 数据库文件不存在: {db_path}")
        sys.exit(1)
    
    check_data_coverage(db_path)
