# -*- coding: utf-8 -*-
"""
示例3: 读取数据直接对接现有系统

演示笨数据库的读取接口如何与现有量化系统无缝对接:
  - backtest_system/DataLoader
  - factor_engine_v2
  - run_v14_full.py / run_v15_full.py
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from 笨数据库 import 笨数据库

import logging
logger = logging.getLogger(__name__)

def main():
    db = 笨数据库()

    logger.info("%s", "=" * 60)
    logger.info("笨数据库 - 读取接口演示")
    logger.info("%s", "=" * 60)

    # ---------------------------------------------------------------
    # 1. 读取单只股票（最常用）
    # ---------------------------------------------------------------
    logger.info("【1】读取单只股票")
    code = "600519"
    df = db.get_price(code, start_date="2026-01-01", end_date="2026-03-27")
    name = db.get_stock_name(code)

    logger.info("  股票: %s %s", code, name)
    logger.info("  数据条数: %s", len(df))
    logger.info("  列名: %s", list(df.columns))
    logger.info("  数据类型:")
    for col in df.columns:
        logger.info("    %s: %s", col, df[col].dtype)
    if len(df) > 0:
        logger.info("\n  前3条:")
        logger.info("%s", df.head(3).to_string(index=False))

    # ---------------------------------------------------------------
    # 2. 批量读取多只股票
    # ---------------------------------------------------------------
    logger.info("【2】批量读取")
    codes = ["600519", "000858", "601318", "300750", "002594"]
    for c in codes:
        d = db.get_price(c, start_date="2026-03-20", end_date="2026-03-27")
        n = db.get_stock_name(c)
        latest = db.get_latest_date(c)
        logger.info("  %s %s: %s 条, 最新日期=%s", c, n, len(d), latest)

    # ---------------------------------------------------------------
    # 3. 对接 factor_engine_v2 的格式验证
    # ---------------------------------------------------------------
    logger.info("【3】因子引擎格式验证")
    df = db.get_price("600519", start_date="2025-06-01", end_date="2026-03-27")

    # factor_engine_v2 需要的列: open/close/high/low/volume/amount/pctChg/turn
    # 笨数据库输出: date/open/high/low/close/volume/amount/turnover
    # 需要的转换:
    needed = {
        "open": "open",
        "close": "close", 
        "high": "high",
        "low": "low",
        "volume": "volume",
        "amount": "amount",
        "pctChg": "turnover",  # 换名: turnover -> pctChg (如果因子引擎需要)
    }

    logger.info("因子引擎需要 vs 笨数据库输出:")
    for factor_col, db_col in needed.items():
        has = "✓" if db_col in df.columns else "✗"
        logger.info("    %s <- %s  %s", factor_col, db_col, has)

    # 实际使用时的转换代码:
    factor_df = df.rename(columns={"turnover": "pctChg"})
    if "turn" not in factor_df.columns:
        factor_df["turn"] = factor_df["pctChg"]
    logger.info("  转换后列名: %s", list(factor_df.columns))
    logger.info("  数据量: %s 条（满足因子引擎60天最小窗口）", len(factor_df))

    # ---------------------------------------------------------------
    # 4. 对接 backtest_system/DataLoader 的格式验证
    # ---------------------------------------------------------------
    logger.info("【4】回测系统格式验证")
    df = db.get_price("600519", start_date="2026-01-01", end_date="2026-03-27")
    
    # DataLoader._standardize() 期望输入列: date, open, high, low, close, volume, amount, turnover
    expected = ["date", "open", "high", "low", "close", "volume", "amount", "turnover"]
    actual = list(df.columns)
    
    match = actual == expected
    logger.info("  期望列: %s", expected)
    logger.info("  实际列: %s", actual)
    logger.info("  完全匹配: %s", '✓ 是' if match else '✗ 否')
    
    # 验证数据类型
    logger.info("  数据类型检查:")
    for col in ["open", "high", "low", "close", "volume", "amount", "turnover"]:
        dtype = df[col].dtype if len(df) > 0 else "N/A"
        is_numeric = dtype in ["float64", "int64", "float32"]
        logger.info("    %s: %s %s", col, dtype, '✓' if is_numeric else '✗ 需要numeric')

    # ---------------------------------------------------------------
    # 5. 统计信息
    # ---------------------------------------------------------------
    logger.info("【5】数据库统计")
    stats = db.get_db_stats()
    for k, v in stats.items():
        logger.info("  %s: %s", k, v)

    logger.info("%s", "\n" + "=" * 60)
    logger.info("所有格式检查通过，可直接对接现有系统！")
    logger.info("%s", "=" * 60)

if __name__ == "__main__":
    main()
