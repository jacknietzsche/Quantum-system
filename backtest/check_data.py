import os
import sys
import pandas as pd
from datetime import datetime

# 添加本地数据库路径到系统路径
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), 'local_db'))
from 笨数据库 import 笨数据库

import logging
logger = logging.getLogger(__name__)

# 数据库路径
db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'local_db', 'a_stock_quant.db')

# 输出文件
output_file = "data_check_output.txt"

# 初始化数据库连接
db = 笨数据库(db_path)

# 获取股票列表
symbols = db.get_all_codes()

# 检查前10只股票的数据
start_date = "2021-03-24"
end_date = "2026-04-09"

# 写入输出
with open(output_file, 'w', encoding='utf-8') as f:
    f.write(f"总股票数量: {len(symbols)}\n")
    f.write(f"检查日期范围: {start_date} ~ {end_date}\n\n")
    f.write("检查前10只股票的数据:\n\n")
    
    for symbol in symbols[:10]:
        try:
            # 获取股票数据
            df = db.get_price(symbol, start_date, end_date)
            f.write(f"股票 {symbol}:\n")
            f.write(f"  数据长度: {len(df)}\n")
            if not df.empty:
                f.write(f"  列名: {list(df.columns)}\n")
                f.write(f"  最早日期: {df['date'].min()}\n")
                f.write(f"  最晚日期: {df['date'].max()}\n")
                f.write(f"  平均换手率: {df['turn'].mean():.2f}%\n")
                f.write(f"  平均成交额: {df['amount'].mean():,.2f} 元\n")
                f.write(f"  最新价格: {df['close'].iloc[-1]:.2f} 元\n")
            else:
                f.write("  无数据\n")
        except Exception as e:
            f.write(f"  检查失败: {e}\n")
        f.write("\n")

# 关闭数据库连接
del db

# 读取并打印输出
with open(output_file, 'r', encoding='utf-8') as f:
    logger.info("%s", f.read())

logger.info("\n数据检查完成，输出已保存到 %s", output_file)

