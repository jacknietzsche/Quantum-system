#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
简单清理脚本，删除备份目录中的所有数据库文件
"""

import os
import shutil
from datetime import datetime

BACKUP_DIR = "backup"
CURRENT_DB = "a_stock_quant.db"


def main():
    print("=== 开始清理备份数据库 ===")
    
    # 检查当前数据库是否存在
    if not os.path.exists(CURRENT_DB):
        print("错误: 当前数据库不存在")
        return
    
    # 获取当前数据库信息
    current_size = os.path.getsize(CURRENT_DB)
    current_mtime = os.path.getmtime(CURRENT_DB)
    current_mtime_str = datetime.fromtimestamp(current_mtime).strftime('%Y-%m-%d %H:%M:%S')
    
    print("当前数据库: %s" % CURRENT_DB)
    print("  大小: %.2f MB" % (current_size / 1024 / 1024))
    
    # 检查备份目录
    if not os.path.exists(BACKUP_DIR):
        print("备份目录不存在，无需清理")
        return
    
    # 获取备份文件列表
    backup_files = []
    for file in os.listdir(BACKUP_DIR):
        if file.endswith(".db"):
            file_path = os.path.join(BACKUP_DIR, file)
            backup_files.append(file_path)
    
    if not backup_files:
        print("备份目录中没有数据库文件，无需清理")
        return
    
print("发现 %s 个备份数据库文件" % len(backup_files)
    
    # 删除备份文件
    for file_path in backup_files:
        file_name = os.path.basename(file_path)
        file_size = os.path.getsize(file_path)
        file_mtime = os.path.getmtime(file_path)
        file_mtime_str = datetime.fromtimestamp(file_mtime).strftime('%Y-%m-%d %H:%M:%S')
        
print("删除备份: %s" % file_name)
print("  大小: %.2f MB" % file_size / 1024 / 1024)
        
        try:
            os.remove(file_path)
            print("  删除成功")
        except Exception as e:
print("  删除失败: %s" % e)
    
    # 验证当前数据库可访问
    print("=== 验证当前数据库 ===")
    try:
        import sqlite3

        conn = sqlite3.connect(CURRENT_DB)
        c = conn.cursor()
        
        # 检查stocks表
        c.execute("SELECT COUNT(*) FROM stocks")
        stock_count = c.fetchone()[0]
print("  股票数量: %s" % stock_count)
        
        # 检查daily_price表
        c.execute("SELECT COUNT(*) FROM daily_price")
        price_count = c.fetchone()[0]
print("  行情记录: %s" % price_count)
        
        # 检查日期范围
        c.execute("SELECT MIN(trade_date), MAX(trade_date) FROM daily_price")
        date_range = c.fetchone()
        if date_range:
print("  日期范围: %s ~ %s" % date_range[0], date_range[1])
        
        conn.close()
        print("数据库访问正常")
    except Exception as e:
print("  数据库访问出错: %s" % e)
    
    print("=== 清理完成 ===")


if __name__ == "__main__":
    main()
