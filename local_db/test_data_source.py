# -*- coding: utf-8 -*-
"""测试7层数据源"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from 笨数据库 import 笨数据库, DATA_SOURCES

import logging
logger = logging.getLogger(__name__)
logger.info("数据源列表:")
for i, src in enumerate(DATA_SOURCES, 1):
    logger.info("  %s. %s", i, src)
logger.info("%s", )

db = 笨数据库()
code = '600519'
start_date = '2026-03-01'
end_date = '2026-04-05'

logger.info("测试获取 %s 数据 (%s ~ %s)...", code, start_date, end_date)
try:
    db._更新单只股票数据(code, start_date, end_date)
    df = db.get_price(code, '2026-03-01', '2026-04-05')
    logger.info("%s 获取成功: %s 条记录", code, len(df))
    if len(df) > 0:
        logger.info("日期范围: %s ~ %s", df.date.iloc[0], df.date.iloc[-1])
        logger.info("最新收盘价: %s", df.close.iloc[-1])
except Exception as e:
    logger.info("错误: %s", e)