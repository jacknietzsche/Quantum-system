# -*- coding: utf-8 -*-
"""
高级数据库优化脚本 - SQLite 性能调优
"""
import sqlite3
import os
import time
import logging

DB_PATH = "a_stock_quant.db"
LOG_FILE = "optimize.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


def apply_pragmas():
    """应用SQLite性能优化参数"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    logger.info("应用SQLite优化参数...")
    
    pragmas = [
        # 核心优化
        ("PRAGMA journal_mode = WAL", "WAL日志模式（提升并发读写）"),
        ("PRAGMA synchronous = NORMAL", "同步模式（平衡安全与性能）"),
        ("PRAGMA cache_size = -2000", "2GB缓存（约2000页）"),
        ("PRAGMA temp_store = MEMORY", "临时表存内存"),
        ("PRAGMA mmap_size = 268435456", "256MB内存映射"),
        ("PRAGMA page_size = 4096", "4KB页大小"),
        ("PRAGMA auto_vacuum = INCREMENTAL", "增量自动vacuum"),
    ]
    
    for pragma, desc in pragmas:
        try:
            c.execute(pragma)
            result = c.execute("PRAGMA " + pragma.split("=")[0].strip()).fetchone()
            logger.info(f"  {desc}: {result[0]}")
        except Exception as e:
            logger.warning(f"  {desc}: {e}")
    
    conn.close()


def add_advanced_indexes():
    """添加高级索引优化"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    logger.info("添加高级索引...")
    
    # 高级索引列表
    indexes = [
        # 1. 覆盖索引 - 避免回表查询
        ("idx_daily_cover_date", 
         "CREATE INDEX IF NOT EXISTS idx_daily_cover_date ON daily_price(trade_date, code, open, high, low, close, volume)"),
        
        # 2. 按月份查询的优化（用于月线数据）
        ("idx_daily_month", 
         "CREATE INDEX IF NOT EXISTS idx_daily_month ON daily_price(substr(trade_date, 1, 7), code)"),
        
        # 3. 成交量排序索引（用于选股）
        ("idx_daily_volume_desc", 
         "CREATE INDEX IF NOT EXISTS idx_daily_volume_desc ON daily_price(trade_date DESC, volume DESC)"),
        
        # 4. 涨跌幅排序索引（用于热门股）
        ("idx_daily_pct_desc", 
         "CREATE INDEX IF NOT EXISTS idx_daily_pct_desc ON daily_price(trade_date DESC, pct_chg DESC)"),
        
        # 5. stocks表 - 名称模糊搜索
        ("idx_stocks_name", 
         "CREATE INDEX IF NOT EXISTS idx_stocks_name ON stocks(name)"),
        
        # 6. 复合索引 - 用于聚合查询
        ("idx_daily_agg", 
         "CREATE INDEX IF NOT EXISTS idx_daily_agg ON daily_price(trade_date, code, close, volume)"),
    ]
    
    for name, sql in indexes:
        try:
            start = time.time()
            c.execute(sql)
            elapsed = time.time() - start
            logger.info(f"  [OK] {name} ({elapsed:.1f}s)")
        except Exception as e:
            logger.warning(f"  [FAIL] {name}: {e}")
    
    conn.commit()
    conn.close()


def run_analyze():
    """执行ANALYZE更新统计信息"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    logger.info("执行ANALYZE更新统计信息...")
    start = time.time()
    c.execute("ANALYZE")
    conn.commit()
    elapsed = time.time() - start
    logger.info(f"  ANALYZE完成 ({elapsed:.1f}s)")
    
    conn.close()


def run_vacuum():
    """执行VACUUM优化空间"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    logger.info("执行VACUUM优化...")
    start = time.time()
    c.execute("VACUUM")
    elapsed = time.time() - start
    logger.info(f"  VACUUM完成 ({elapsed:.1f}s)")
    
    # 检查优化后大小
    size = os.path.getsize(DB_PATH)
    logger.info(f"  数据库大小: {size/10**9:.2f} GB")
    
    conn.close()


def test_performance():
    """性能测试对比"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # 启用SQLite优化
    c.execute("PRAGMA cache_size = -2000")
    c.execute("PRAGMA mmap_size = 268435456")
    
    logger.info("\n" + "=" * 50)
    logger.info("性能测试")
    logger.info("=" * 50)
    
    tests = [
        # 测试1: 单只股票日期范围查询
        ("单只股票查询", 
         "SELECT * FROM daily_price WHERE code = '600519' AND trade_date >= '2026-01-01' ORDER BY trade_date"),
        
        # 测试2: 多只股票批量查询
        ("批量5只股票", 
         "SELECT code, COUNT(*), MIN(trade_date), MAX(trade_date) FROM daily_price WHERE code IN ('600519','000858','300750','600036','601318') GROUP BY code"),
        
        # 测试3: 日期统计
        ("日期统计", 
         "SELECT COUNT(DISTINCT code) FROM daily_price WHERE trade_date >= '2026-03-01'"),
        
        # 测试4: 按日期排序
        ("日期排序查询", 
         "SELECT * FROM daily_price WHERE trade_date BETWEEN '2026-03-01' AND '2026-03-30' ORDER BY trade_date DESC LIMIT 100"),
        
        # 测试5: 成交量排序（选股常用）
        ("成交量排序", 
         "SELECT code, volume FROM daily_price WHERE trade_date = '2026-03-28' ORDER BY volume DESC LIMIT 20"),
        
        # 测试6: 涨跌幅排序
        ("涨跌幅排序", 
         "SELECT code, pct_chg FROM daily_price WHERE trade_date = '2026-03-28' AND pct_chg > 0 ORDER BY pct_chg DESC LIMIT 20"),
        
        # 测试7: 复杂聚合
        ("月聚合统计", 
         "SELECT substr(trade_date,1,7) as month, COUNT(*), AVG(close) FROM daily_price WHERE code='600519' GROUP BY month"),
        
        # 测试8: 多条件查询
        ("多条件查询", 
         "SELECT * FROM daily_price WHERE trade_date >= '2026-03-01' AND volume > 10000000 AND pct_chg > 5"),
    ]
    
    for name, sql in tests:
        # 预热
        c.execute(sql)
        c.fetchall()
        
        # 正式测试
        start = time.time()
        c.execute(sql)
        rows = c.fetchall()
        elapsed = time.time() - start
        logger.info(f"  {name}: {elapsed*1000:.1f}ms ({len(rows)}行)")
    
    conn.close()


def show_index_info():
    """显示索引信息"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    logger.info("\n" + "=" * 50)
    logger.info("索引信息")
    logger.info("=" * 50)
    
    c.execute("""
        SELECT name, tbl_name, sql 
        FROM sqlite_master 
        WHERE type='index' AND sql IS NOT NULL
    """)
    
    for row in c.fetchall():
        logger.info(f"  {row[0]} on {row[1]}")
    
    conn.close()


def main():
    logger.info("=" * 60)
    logger.info("  SQLite 数据库高级优化")
    logger.info("=" * 60)
    
    # 1. 应用优化参数
    apply_pragmas()
    
    # 2. 添加高级索引
    add_advanced_indexes()
    
    # 3. 执行ANALYZE
    run_analyze()
    
    # 4. 执行VACUUM
    run_vacuum()
    
    # 5. 显示索引信息
    show_index_info()
    
    # 6. 性能测试
    test_performance()
    
    logger.info("\n优化完成!")


if __name__ == "__main__":
    main()