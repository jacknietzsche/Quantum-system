import sqlite3
import os

import logging
logger = logging.getLogger(__name__)

# 数据库路径
db_path = r"c:\Users\21471\WorkBuddy\quant system\local_db\a_stock_quant.db"

# 检查数据库文件是否存在
if not os.path.exists(db_path):
    logger.info("数据库文件不存在: %s", db_path)
    exit(1)

# 连接数据库
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# 检查股票数量
cursor.execute("SELECT COUNT(*) FROM stocks;")
stock_count = cursor.fetchone()[0]
logger.info("股票数量: %s", stock_count)

# 检查行情数据数量
cursor.execute("SELECT COUNT(*) FROM daily_price;")
price_count = cursor.fetchone()[0]
logger.info("行情数据数量: %s", price_count)

# 检查日期范围
cursor.execute("SELECT MIN(trade_date), MAX(trade_date) FROM daily_price;")
date_range = cursor.fetchone()
logger.info("最早日期: %s", date_range[0])
logger.info("最晚日期: %s", date_range[1])

# 关闭连接
conn.close()
