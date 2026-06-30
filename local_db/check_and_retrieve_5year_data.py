#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检查并获取近5年历史市场数据

功能：
1. 检查本地数据库是否已有近5年的历史数据
2. 如果数据已存在，跳过检索过程
3. 如果数据不存在，执行数据库查询获取所需的5年数据集
"""
import os
import sys
from datetime import datetime, timedelta

# 添加当前目录到路径，确保能导入笨数据库模块
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from 笨数据库 import 笨数据库

import logging
logger = logging.getLogger(__name__)

def check_5year_data_exists(db):
    """
    检查数据库是否已有近5年的历史数据
    
    Args:
        db: 笨数据库实例
        
    Returns:
        bool: 如果已有5年数据返回True，否则返回False
    """
    # 获取数据库统计信息
    stats = db.get_db_stats()
    
    # 检查是否有数据
    if stats.get("行情记录数", 0) == 0:
        logger.info("数据库中无行情数据，需要初始化")
        return False
    
    # 检查最新日期
    latest_date = stats.get("最新日期")
    if latest_date == "无":
        logger.info("数据库中无行情数据，需要初始化")
        return False
    
    # 检查最早日期是否在5年前
    latest_dt = datetime.strptime(latest_date, "%Y-%m-%d")
    five_years_ago = latest_dt - timedelta(days=5*366)
    
    # 查询数据库中最早的日期
    conn = db._query_one("SELECT MIN(trade_date) FROM daily_price")
    if not conn:
        logger.info("无法查询数据库最早日期，需要初始化")
        return False
    
    earliest_date = conn
    earliest_dt = datetime.strptime(earliest_date, "%Y-%m-%d")
    
    # 检查最早日期是否早于5年前
    if earliest_dt <= five_years_ago:
        logger.info("数据库已有5年数据，最早日期: %s, 最新日期: %s", earliest_date, latest_date)
        return True
    else:
        logger.info("数据库数据不足5年，最早日期: %s, 需要更新", earliest_date)
        return False

def main():
    """
    主函数：检查并获取近5年历史数据
    """
    logger.info("%s", "=" * 60)
    logger.info("检查并获取近5年历史市场数据")
    logger.info("%s", "=" * 60)
    
    # 初始化数据库连接
    db = 笨数据库()
    
    try:
        # 检查是否已有5年数据
        if check_5year_data_exists(db):
            logger.info("✅ 数据检查完成：已有近5年历史数据，跳过数据检索")
            return
        
        logger.info("🔄 开始获取近5年历史数据...")
        
        # 初始化5年历史数据
        db.初始化历史数据(years=5)
        
        # 再次检查数据是否成功获取
        if check_5year_data_exists(db):
            logger.info("✅ 数据获取完成：成功获取近5年历史数据")
        else:
            logger.info("❌ 数据获取失败：无法获取足够的历史数据")
            
    except Exception as e:
        logger.info("\n❌ 执行过程中出错: %s", e)
    finally:
        # 清理资源
        del db

if __name__ == "__main__":
    main()
