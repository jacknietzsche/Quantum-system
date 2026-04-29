import sqlite3
import os


# 数据库路径
db_path = r"c:\Users\21471\WorkBuddy\quant system\local_db\a_stock_quant.db"

# 检查数据库文件是否存在
if not os.path.exists(db_path):
    print("数据库文件不存在: %s", db_path)
    exit(1)

print("数据库文件: %s", db_path)
print("文件大小: %.2f MB", os.path.getsize(db_path) / 1024 / 1024)

# 连接数据库
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# 检查表结构
print("数据库表:")
cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
tables = cursor.fetchall()
for table in tables:
    print("- %s", table[0])

# 检查每个表的结构
for table in tables:
    table_name = table[0]
    print("\n表 %s 的结构:", table_name)
    cursor.execute(f"PRAGMA table_info({table_name});")
    columns = cursor.fetchall()
    for column in columns:
        print("  - %s: %s", column[1], column[2])

# 检查股票数量
print("股票数量:")
cursor.execute("SELECT COUNT(*) FROM stocks;")
stock_count = cursor.fetchone()[0]
print("- 总股票数: %s", stock_count)

# 检查行情数据数量
print("行情数据数量:")
cursor.execute("SELECT COUNT(*) FROM daily_price;")
price_count = cursor.fetchone()[0]
print("- 总行情记录数: %s", price_count)

# 检查日期范围
print("行情数据日期范围:")
cursor.execute("SELECT MIN(trade_date), MAX(trade_date) FROM daily_price;")
date_range = cursor.fetchone()
print("- 最早日期: %s", date_range[0])
print("- 最晚日期: %s", date_range[1])

# 检查前10只股票
print("前10只股票:")
cursor.execute("SELECT code, name FROM stocks LIMIT 10;")
top_stocks = cursor.fetchall()
for stock in top_stocks:
    print("- %s: %s", stock[0], stock[1])

# 检查某只股票的行情数据
if stock_count > 0:
    sample_code = top_stocks[0][0]
    print("\n股票 %s 的行情数据:", sample_code)
    cursor.execute(f"SELECT trade_date, close, volume, turnover FROM daily_price WHERE code='{sample_code}' ORDER BY trade_date DESC LIMIT 10;")
    sample_data = cursor.fetchall()
    for data in sample_data:
        print("  - %s: 收盘价=%s, 成交量=%s, 换手率=%s", data[0], data[1], data[2], data[3])

# 关闭连接
conn.close()
print("数据库检查完成。")