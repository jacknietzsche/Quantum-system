#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
分析备份目录中的数据库文件，检查它们的创建时间和数据完整性
"""

import os
import sqlite3
import pandas as pd
from datetime import datetime


BACKUP_DIR = "backup"
CURRENT_DB = "a_stock_quant.db"


def get_db_stats(db_path):
    """
    获取数据库统计信息
    """
    try:
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        
        # 检查stocks表
        c.execute("SELECT COUNT(*) FROM stocks")
        stock_count = c.fetchone()[0]
        
        # 检查daily_price表
        c.execute("SELECT COUNT(*) FROM daily_price")
        price_count = c.fetchone()[0]
        
        # 检查日期范围
        c.execute("SELECT MIN(trade_date), MAX(trade_date) FROM daily_price")
        date_range = c.fetchone()
        
        # 检查有数据的股票数
        c.execute("SELECT COUNT(DISTINCT code) FROM daily_price")
        stock_with_data = c.fetchone()[0]
        
        conn.close()
        
        return {
            "stock_count": stock_count,
            "price_count": price_count,
            "date_range": date_range,
            "stock_with_data": stock_with_data,
            "file_size": os.path.getsize(db_path)
        }
    except Exception as e:
        print("检查数据库 %s 时出错: %s", db_path, e)
        return None


def analyze_backups():
    """
    分析备份目录中的数据库文件
    """
    backup_files = []
    
    # 遍历备份目录
    for file in os.listdir(BACKUP_DIR):
        if file.endswith(".db"):
            file_path = os.path.join(BACKUP_DIR, file)
            file_size = os.path.getsize(file_path)
            creation_time = os.path.getmtime(file_path)
            creation_date = datetime.fromtimestamp(creation_time)
            
            # 获取数据库统计信息
            stats = get_db_stats(file_path)
            
            backup_files.append({
                "file": file,
                "path": file_path,
                "size": file_size,
                "creation_time": creation_time,
                "creation_date": creation_date,
                "stats": stats
            })
    
    # 按创建时间排序
    backup_files.sort(key=lambda x: x["creation_time"], reverse=True)
    
    return backup_files


def analyze_current_db():
    """
    分析当前数据库
    """
    if os.path.exists(CURRENT_DB):
        file_size = os.path.getsize(CURRENT_DB)
        creation_time = os.path.getmtime(CURRENT_DB)
        creation_date = datetime.fromtimestamp(creation_time)
        stats = get_db_stats(CURRENT_DB)
        
        return {
            "file": CURRENT_DB,
            "path": CURRENT_DB,
            "size": file_size,
            "creation_time": creation_time,
            "creation_date": creation_date,
            "stats": stats
        }
    else:
        return None


def main():
    """
    主函数
    """
    print("=== 分析备份数据库 ===")
    backup_files = analyze_backups()
    
    print("发现 %s 个备份数据库文件", len(backup_files))
    print("")
    
    for i, file_info in enumerate(backup_files):
        print("备份 %s: %s", i+1, file_info['file'])
        print("  创建时间: %s", file_info['creation_date'].strftime('%Y-%m-%d %H:%M:%S'))
        print("  文件大小: %.2f MB", file_info["size"] / 1024 / 1024)
        if file_info["stats"]:
            print("  股票数量: %s", file_info['stats']['stock_count'])
            print("  行情记录: %s", file_info['stats']['price_count'])
            print("  有数据的股票: %s", file_info['stats']['stock_with_data'])
            if file_info['stats']['date_range']:
                print("  日期范围: %s ~ %s", file_info['stats']['date_range'][0], file_info['stats']['date_range'][1])
        print("")
    
    print("=== 分析当前数据库 ===")
    current_db = analyze_current_db()
    if current_db:
        print("当前数据库: %s", current_db['file'])
        print("  创建时间: %s", current_db['creation_date'].strftime('%Y-%m-%d %H:%M:%S'))
        print("  文件大小: %.2f MB", current_db['size'] / 1024 / 1024)
        if current_db['stats']:
            print("  股票数量: %s", current_db['stats']['stock_count'])
            print("  行情记录: %s", current_db['stats']['price_count'])
            print("  有数据的股票: %s", current_db['stats']['stock_with_data'])
            if current_db['stats']['date_range']:
                print("  日期范围: %s ~ %s", current_db['stats']['date_range'][0], current_db['stats']['date_range'][1])
    else:
        print("当前数据库不存在")
    
    # 确定需要保留的数据库
    print("=== 需要保留的数据库 ===")
    if current_db:
        print("保留当前数据库: %s", current_db['file'])
        print("  原因: 最新创建且数据最完整")
    
    # 确定需要删除的备份
    print("=== 需要删除的备份 ===")
    for file_info in backup_files:
        print("删除: %s", file_info['file'])
        print("  创建时间: %s", file_info['creation_date'].strftime('%Y-%m-%d %H:%M:%S'))
print("  文件大小: %.2f MB", file_info['size'] / 1024 / 1024)

if __name__ == "__main__":
    main()
