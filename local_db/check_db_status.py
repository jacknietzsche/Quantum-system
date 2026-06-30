#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检查数据库状态
"""

import sqlite3
import os

import logging
logger = logging.getLogger(__name__)

# 数据库路径
db_path = "a_stock_quant.db"

logger.info("检查数据库: %s", os.path.abspath(db_path))
logger.info("文件存在: %s", os.path.exists(db_path))

if os.path.exists(db_path):
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    
    # 检查stocks表
    logger.info("检查stocks表:")
    c.execute("SELECT COUNT(*) FROM stocks")
    count = c.fetchone()[0]
    logger.info("stocks表记录数: %s", count)
    
    if count > 0:
        c.execute("SELECT code, name FROM stocks LIMIT 10")
        logger.info("前10条记录:")
        for row in c.fetchall():
            logger.info("  %s: %s", row[0], row[1])
    
    # 检查daily_price表
    logger.info("检查daily_price表:")
    c.execute("SELECT COUNT(*) FROM daily_price")
    count = c.fetchone()[0]
    logger.info("daily_price表记录数: %s", count)
    
    if count > 0:
        c.execute("SELECT MIN(trade_date), MAX(trade_date) FROM daily_price")
        date_range = c.fetchone()
        logger.info("日期范围: %s ~ %s", date_range[0], date_range[1])
        
        c.execute("SELECT COUNT(DISTINCT code) FROM daily_price")
        stock_count = c.fetchone()[0]
        logger.info("有数据的股票数: %s", stock_count)
    
    conn.close()
else:
    logger.info("数据库文件不存在")
