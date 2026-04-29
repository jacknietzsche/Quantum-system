#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试数据库连接和股票列表获取
"""

import os
import sys
from pathlib import Path

# 项目根目录
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

# 测试数据库连接
print("测试数据库连接...")
try:
    # 添加本地数据库路径到系统路径
    sys.path.insert(0, os.path.join(PROJECT_ROOT, 'local_db'))
    from 笨数据库 import 笨数据库
    
    # 初始化数据库连接
    db_path = os.path.join(PROJECT_ROOT, 'local_db', 'a_stock_quant.db')
    print(f"数据库路径: {db_path}")
    print(f"数据库文件存在: {os.path.exists(db_path)}")
    
    db = 笨数据库(db_path)
    print("数据库连接成功")
    
    # 确保股票列表已更新
    print("更新股票列表...")
    db.更新股票列表()
    
    # 获取所有股票代码
    symbols = db.get_all_codes()
    print(f"获取到 {len(symbols)} 只股票")
    if symbols:
        print(f"前10只股票: {symbols[:10]}")
    
    # 检查数据库统计信息
    stats = db.get_db_stats()
    print("数据库统计:")
    for k, v in stats.items():
        print(f"  {k}: {v}")
    
    print("测试成功!")
except Exception as e:
    print(f"测试失败: {e}")
    import traceback
    traceback.print_exc()
