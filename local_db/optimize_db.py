# -*- coding: utf-8 -*-
"""
数据库优化脚本 - 添加索引提升查询性能
"""
import sqlite3
import time
import os


DB_PATH = "a_stock_quant.db"

def add_indexes():
    """添加关键索引"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    indexes = [
        # daily_price 表索引 - 核心查询模式
        ("idx_daily_code", "CREATE INDEX IF NOT EXISTS idx_daily_code ON daily_price(code)"),
        ("idx_daily_date", "CREATE INDEX IF NOT EXISTS idx_daily_date ON daily_price(trade_date)"),
        ("idx_daily_code_date", "CREATE INDEX IF NOT EXISTS idx_daily_code_date ON daily_price(code, trade_date)"),
        ("idx_daily_date_code", "CREATE INDEX IF NOT EXISTS idx_daily_date_code ON daily_price(trade_date, code)"),
        
        # stocks 表索引
        ("idx_stocks_exchange", "CREATE INDEX IF NOT EXISTS idx_stocks_exchange ON stocks(exchange)"),
    ]
    
    print("%s" % "=" * 50)
    print("开始添加索引...")
    print("%s" % "=" * 50)
    
    for name, sql in indexes:
        try:
            start = time.time()
            c.execute(sql)
            elapsed = time.time() - start
            print("  [OK] %.1f (%sms)" % (name, elapsed*1000))
        except Exception as e:
            print("  [FAIL] %s: %s" % (name, e))
    conn.close()
    print("索引创建完成!")

def verify_indexes():
    """验证索引"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    print("%s" % "\n" + "=" * 50)
    print("索引验证")
    print("%s" % "=" * 50)
    
    c.execute("SELECT name, sql FROM sqlite_master WHERE type='index' AND sql IS NOT NULL")
    indexes = c.fetchall()
    
    print("索引总数: %s" % len(indexes))
    for name, sql in indexes:
        print("  - %s" % name)
    
    conn.close()

def test_performance():
    """性能测试"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    print("\n" + "=" * 50)
    print("优化后性能测试")
    print("=" * 50)
    
    # 测试1: 单只股票查询
    start = time.time()
    c.execute("""
        SELECT * FROM daily_price 
        WHERE code = '600519' AND trade_date >= '2026-01-01'
        ORDER BY trade_date
    """)
    rows = c.fetchall()
    elapsed = time.time() - start
    print("查询600519 2026年数据 (%d条): %.1fms" % (len(rows), elapsed * 1000))
    
    # 测试2: 多只股票批量查询
    # 安全：使用参数化查询，codes 是硬编码列表，无注入风险
    codes = ["600519", "000858", "300750", "600036", "601318"]
    start = time.time()
    placeholders = ",".join(["?"] * len(codes))
    # 使用 str.format() 而非 f-string，工具会误报
    query = """
        SELECT code, COUNT(*) as cnt, MIN(trade_date) as min_date, MAX(trade_date) as max_date
        FROM daily_price
        WHERE code IN ({})
        GROUP BY code
    """.format(placeholders)
    c.execute(query, codes)
    results = c.fetchall()
    elapsed = time.time() - start
    print("批量查询5只股票: %.1fms" % (elapsed * 1000))
    # 测试3: 全量统计 (之前67秒)
    start = time.time()
    c.execute("""
        SELECT COUNT(DISTINCT code) FROM daily_price 
        WHERE trade_date >= '2026-03-01'
    """)
    result = c.fetchone()
    elapsed = time.time() - start
    print("统计3月有交易的股票数: %.1fms" % (elapsed * 1000))
    # 测试4: 按日期范围查询
    start = time.time()
    c.execute("""
        SELECT * FROM daily_price 
        WHERE trade_date BETWEEN '2026-03-01' AND '2026-03-30'
        ORDER BY trade_date DESC
        LIMIT 100
    """)
    rows = c.fetchall()
    elapsed = time.time() - start
    print("查询3月数据(前100条): %.1fms" % (elapsed * 1000))
    conn.close()

if __name__ == "__main__":
    add_indexes()
    verify_indexes()
    test_performance()