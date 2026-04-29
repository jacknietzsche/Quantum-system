# -*- coding: utf-8 -*-
"""验证数据库优化效果"""
import sqlite3
import time


db_path = "a_stock_quant.db"

def main():
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    
    print("%s" % "=" * 60)
    print("数据库优化验证")
    print("%s" % "=" * 60)
    
    # 1. 索引数量
    c.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='index' AND sql IS NOT NULL")
    print("索引数量: %s" % c.fetchone()[0])
    
    # 2. 性能测试
    tests = [
        ("单只股票查询", "SELECT * FROM daily_price WHERE code='600519' AND trade_date>='2026-01-01'"),
        ("批量10只股票", "SELECT code, COUNT(*) FROM daily_price WHERE code IN ('600519','000858','300750','6','00') GROUP BY code"),
        ("日期统计", "SELECT COUNT(DISTINCT code) FROM daily_price WHERE trade_date>='2026-03-01'"),
        ("成交量排序", "SELECT code, volume FROM daily_price WHERE trade_date='2026-03-28' ORDER BY volume DESC LIMIT 10"),
    ]
    
    for name, sql in tests:
        start = time.time()
        c.execute(sql)
        rows = c.fetchall()
        elapsed = (time.time() - start) * 1000
print("%s: %sms (%s行)" % name, elapsed:.1f, len(rows)
    
    conn.close()
    print("优化完成!")

if __name__ == "__main__":
    main()