#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
简单检查数据库
"""

import os

import logging
logger = logging.getLogger(__name__)

logger.info("%s", "当前目录:", os.getcwd())
db_path = "a_stock_quant.db"
logger.info("数据库文件存在: %s", os.path.exists(db_path))
if os.path.exists(db_path):
    logger.info("文件大小: %.1f MB", os.path.getsize(db_path) / 1024 / 1024)
else:
    logger.info("数据库文件不存在")
