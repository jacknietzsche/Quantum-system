# -*- coding: utf-8 -*-
"""
后台运行：补充缺失股票数据 + 增量更新
使用笨数据库的断点续传功能，跳过已有数据的股票
"""
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler("sync_data.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)

from 笨数据库 import 笨数据库


def main():
    start = time.time()
    db = 笨数据库()

    # 1. 更新股票列表（force=True 确保最新）
    print("[步骤1] 更新股票列表...")
    db.更新股票列表(force=True)

    # 2. 初始化历史数据（断点续传，只下载缺失的）
    print("[步骤2] 下载缺失股票的历史数据（断点续传）...")
    db.初始化历史数据(years=5)

    # 3. 增量更新（补充最新交易日的数据）
    print("[步骤3] 增量更新所有股票到最新交易日...")
    db.每日增量更新()

    # 4. 显示最终状态
    elapsed = time.time() - start
    print("\n%s" % '='*50)
    print("  全部完成! 耗时 %.1f 分钟" % (elapsed/60))
    stats = db.get_db_stats()
    for k, v in stats.items():
        print("  %s: %s" % (k, v))

if __name__ == "__main__":
    main()
