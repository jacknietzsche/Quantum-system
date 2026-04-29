# -*- coding: utf-8 -*-
"""
示例2: 每日增量更新
每天收盘后运行一次，自动下载当天的新数据
可配合 Windows 任务计划程序 / cron 定时自动执行
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from 笨数据库 import 笨数据库

import logging
logger = logging.getLogger(__name__)

def main():
    db = 笨数据库()

    # 更新前先刷一下股票列表（新增/退市）
    db.更新股票列表(force=True)

    # 增量更新
    db.每日增量更新()

    # 显示结果
    logger.info("%s", )
    stats = db.get_db_stats()
    logger.info("更新后数据库状态:")
    for k, v in stats.items():
        logger.info("  %s: %s", k, v)

if __name__ == "__main__":
    main()
