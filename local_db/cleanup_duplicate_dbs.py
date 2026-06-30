#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
清理系统中的重复数据库，删除所有冗余的重复数据库实例，仅保留最新创建且数据最为完整的数据库
"""

import os
import shutil
from datetime import datetime

BACKUP_DIR = "backup"
CURRENT_DB = "a_stock_quant.db"
CLEANUP_BACKUP_DIR = "cleanup_backup"


def get_file_info(file_path):
    """
    获取文件信息
    """
    return {
        "name": os.path.basename(file_path),
        "path": file_path,
        "size": os.path.getsize(file_path),
        "mtime": os.path.getmtime(file_path),
        "mtime_str": datetime.fromtimestamp(os.path.getmtime(file_path)).strftime('%Y-%m-%d %H:%M:%S')
    }


def main():
    """
    主函数
    """
    print("=== 开始清理重复数据库 ===")
    
    # 确保清理备份目录存在
    os.makedirs(CLEANUP_BACKUP_DIR, exist_ok=True)
    
    # 获取当前数据库信息
    current_db_info = None
    if os.path.exists(CURRENT_DB):
        current_db_info = get_file_info(CURRENT_DB)
        print("当前数据库: %s" % current_db_info['name'])
        print("  创建时间: %s" % current_db_info['mtime_str'])
        print("  文件大小: %.2f MB" % (current_db_info['size'] / 1024 / 1024))
        print("当前数据库不存在")
        return
    
    # 获取备份目录中的数据库文件
    backup_files = []
    if os.path.exists(BACKUP_DIR):
        for file in os.listdir(BACKUP_DIR):
            if file.endswith(".db"):
                file_path = os.path.join(BACKUP_DIR, file)
                backup_files.append(get_file_info(file_path))
    
    # 按修改时间排序
    backup_files.sort(key=lambda x: x["mtime"], reverse=True)
    
    print("\n发现 %s 个备份数据库文件" % len(backup_files))
    
    # 备份并删除冗余的备份文件
    deleted_files = []
    for file_info in backup_files:
        print("\n处理备份: %s" % file_info['name'])
        print("  创建时间: %s" % file_info['mtime_str'])
        print("  文件大小: %.2f MB" % (file_info['size'] / 1024 / 1024))
        # 备份到清理备份目录
        backup_dest = os.path.join(CLEANUP_BACKUP_DIR, file_info['name'])
        print("  备份到: %s" % backup_dest)
        shutil.copy2(file_info['path'], backup_dest)
        
        # 删除原备份文件
        print("  删除原文件: %s" % file_info['path'])
        os.remove(file_info['path'])
        deleted_files.append(file_info)
    
    # 生成操作报告
    print("=== 清理操作报告 ===")
    print("保留的数据库:")
    print("  文件名: %s" % current_db_info['name'])
    print("  创建时间: %s" % current_db_info['mtime_str'])
    print("  文件大小: %.2f MB" % (current_db_info['size'] / 1024 / 1024))
    
    print("\n已删除的数据库 (%s 个):" % len(deleted_files))
    for file_info in deleted_files:
        print("  文件名: %s" % file_info['name'])
        print("  创建时间: %s" % file_info['mtime_str'])
        print("  文件大小: %.2f MB" % (file_info['size'] / 1024 / 1024))
    
    # 验证保留的数据库可正常访问
    print("=== 验证保留的数据库 ===")
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
