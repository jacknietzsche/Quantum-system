# -*- coding: utf-8 -*-
"""
示例1: 初始化5年历史数据
首次运行使用，下载全市场A股过去5年的日线行情
中途可随时 Ctrl+C 打断，再次运行会从断点继续
"""
import sys
import os

# 确保能导入笨数据库（无论从哪里运行）
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from 笨数据库 import 笨数据库

import logging
logger = logging.getLogger(__name__)

def main():
    db = 笨数据库()

    # 查看当前状态
    stats = db.get_db_stats()
    logger.info("当前数据库状态:")
    for k, v in stats.items():
        logger.info("  %s: %s", k, v)
    logger.info("%s", )

    # 开始初始化（默认5年，可传参数改为其他年数）
    years = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    logger.info("即将下载过去 %s 年的历史数据...", years)
    logger.info("提示: 中途 Ctrl+C 可安全打断，再次运行自动断点续传")
    logger.info("%s", )

    db.初始化历史数据(years=years)

    # 完成后显示统计
    logger.info("%s", )
    stats = db.get_db_stats()
    logger.info("完成后数据库状态:")
    for k, v in stats.items():
        logger.info("  %s: %s", k, v)

if __name__ == "__main__":
    main()
