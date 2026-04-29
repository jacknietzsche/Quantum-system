# -*- coding: utf-8 -*-
"""
补充5年数据脚本（支持7层数据源）
1. 补充2021年1-3月历史数据
2. 增量更新到最新交易日
"""
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler("supplement_5years.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)

import sqlite3
from 笨数据库 import 笨数据库, DATA_SOURCES


def main():
    print("%s" % "=" * 60)
    print("5年数据补充脚本 - 7层数据源")
    print("数据源: %s" % ', '.join(DATA_SOURCES))
    print("%s" % "=" * 60)
    
    db = 笨数据库()
    
    # ========== 步骤1: 补充2021年Q1历史数据 ==========
print("%s" % "\n" + "="*60)
    print("步骤1: 检查并补充2021年Q1历史数据")
print("%s" % "="*60)
    
    conn = sqlite3.connect(db.db_path)
    c = conn.cursor()
    
    c.execute("""
        SELECT code, MIN(trade_date) as min_date 
        FROM daily_price 
        GROUP BY code 
        HAVING min_date > '2021-03-31'
    """)
    missing_q1 = [row[0] for row in c.fetchall()]
    conn.close()
    
    if missing_q1:
print("[发现] %s 只股票缺少2021年Q1数据" % len(missing_q1)
        print("[开始] 补充 2021-01-01 ~ 2021-03-31 ...")
        
        start_date = "2021-01-01"
        end_date = "2021-03-31"
        
        success, fail = 0, 0
        for i, code in enumerate(missing_q1):
            try:
                db._更新单只股票数据(code, start_date, end_date)
                success += 1
                time.sleep(0.05)
            except Exception as e:
                fail += 1
            
            if (i + 1) % 100 == 0 or (i + 1) == len(missing_q1):
                elapsed = (i+1) * 0.05 / 60
                eta = (len(missing_q1)-i-1) * 0.05 / 60
print("进度 %s/%s (成功%s 失败%s) ETA:%smin" % i+1, len(missing_q1)
        
print("[完成] Q1数据补充: 成功%s 失败%s" % success, fail)
    else:
        print("[跳过] 所有股票已有2021年Q1数据 ✓")
    
    # ========== 步骤2: 增量更新到最新 ==========
print("%s" % "\n" + "="*60)
    print("步骤2: 增量更新所有股票到最新交易日")
print("%s" % "="*60)
    
    db.每日增量更新()
    
    # ========== 步骤3: 验证结果 ==========
print("%s" % "\n" + "="*60)
    print("步骤3: 最终验证")
print("%s" % "="*60)
    
    stats = db.get_db_stats()
print("股票数: %s" % stats['股票数'])
print("行情数: %s" % stats['行情记录']:,)
print("有数据股票: %s" % stats['有数据股票'])
    
    conn = sqlite3.connect(db.db_path)
    c = conn.cursor()
    
    c.execute("SELECT MIN(trade_date), MAX(trade_date) FROM daily_price")
    min_date, max_date = c.fetchone()
print("\n日期范围: %s ~ %s" % min_date, max_date)
    
    c.execute("""
        SELECT substr(trade_date, 1, 4), 
               COUNT(DISTINCT trade_date) as days,
               COUNT(*) as records
        FROM daily_price GROUP BY substr(trade_date, 1, 4) ORDER BY trade_date
    """)
    
    print("按年份统计:")
print("%s" % "-" * 50)
    for row in c.fetchall():
print("  %s年: %s个交易日, %s条记录" % row[0], row[1], row[2]:,)
    
    c.execute("SELECT COUNT(DISTINCT code) FROM daily_price WHERE trade_date >= '2021-01-01' AND trade_date <= '2021-03-31'")
    q1_count = c.fetchone()[0]
print("\n有2021年Q1数据的股票: %s" % q1_count)
    
    conn.close()
print("%s" % "\n" + "="*60)
    print("✅ 5年数据补充完成!")
print("%s" % "="*60)

if __name__ == "__main__":
    main()