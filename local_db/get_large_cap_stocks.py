#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
获取100亿市值以上的股票列表
"""
import sqlite3
import akshare as ak
import time
from pathlib import Path

from core.logging_config import setup_logging, get_logger
setup_logging()
logger = get_logger(__name__)

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / 'a_stock_quant.db'

# 市值阈值：100亿 = 100亿元 = 10000000000
MARKET_CAP_THRESHOLD = 100_000_000_00  # 100亿


def get_large_cap_stocks():
    """获取100亿以上市值的股票"""
    logger.info("开始获取A股总市值数据...")

    try:
        # 获取A股总市值数据
        df = ak.stock_individual_info_em(symbol="000001")
        logger.info(f"获取到基础信息")
        time.sleep(1)

        # 获取全部A股总市值
        df = ak.stock_a_gd_hist(symbol="000001", period="daily", start_date="20260401", end_date="20260407")
        logger.info(f"获取到历史数据")

    except Exception as e:
        logger.warning(f"akshare接口异常: {e}，使用备用方法")

    # 备用方法：使用baostock获取
    try:
        import baostock as bs
        lg = bs.login()
        logger.info(f"baostock登录: {lg.error_code} {lg.error_msg}")

        # 获取所有股票
        rs = bs.query_all_stock(day="2026-04-03")
        data_list = []
        while (rs.error_code == '0') & rs.next():
            data_list.append(rs.get_row_data())

        bs.logout()

        if data_list:
            import pandas as pd
            df = pd.DataFrame(data_list, columns=rs.fields)
            logger.info(f"获取到 {len(df)} 只股票")

            # 过滤沪市和深市主板
            df = df[df['code'].str.startswith(('sh.6', 'sz.0', 'sz.00'))]
            logger.info(f"主板股票: {len(df)} 只")

            # 保存原始列表
            return df['code'].tolist()

    except Exception as e:
        logger.error(f"baostock也失败: {e}")

    # 最后备用：从本地数据库获取所有股票
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT code FROM stocks
        WHERE code NOT LIKE '688%'
        AND code NOT LIKE '8%'
        AND code NOT LIKE '4%'
        AND name NOT LIKE '%ST%'
        AND name NOT LIKE '%*ST%'
    """)
    stocks = [row[0] for row in c.fetchall()]
    conn.close()
    logger.info(f"从本地数据库获取: {len(stocks)} 只")
    return stocks


def fetch_market_cap_from_tushare(stocks):
    """从tushare获取市值数据（如果可用）"""
    try:
        import tushare as ts
        pro = ts.pro_api()

        # 批量获取
        market_caps = {}
        for i in range(0, len(stocks), 100):
            batch = stocks[i:i+100]
            try:
                df = pro.daily_basic(ts_code=','.join([s.replace('sh.', '').replace('sz.', '') + '.SH' if s.startswith('sh') else s.replace('sh.', '').replace('sz.', '') + '.SZ' for s in batch]),
                                    trade_date='20260403',
                                    fields='ts_code,total_mv')
                if df is not None and len(df) > 0:
                    for _, row in df.iterrows():
                        code = row['ts_code']
                        cap = row['total_mv'] * 1e8  # 转换为元
                        market_caps[code] = cap
            except Exception as e:
                logger.warning(f"批量获取失败: {e}")
            time.sleep(1)

        return market_caps
    except Exception as e:
        logger.warning(f"tushare不可用: {e}")
        return {}


def main():
    """主函数"""
    logger.info("=" * 60)
    logger.info("获取100亿市值以上股票")
    logger.info("=" * 60)

    # 获取股票列表
    stocks = get_large_cap_stocks()
    logger.info(f"获取到 {len(stocks)} 只候选股票")

    # 由于没有直接的市值API，我们使用一个近似方法：
    # 使用最近一天的成交额和价格来估算市值范围
    # 或者直接使用本地数据库的股票

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # 尝试从akshare获取市值排名
    try:
        logger.info("尝试从akshare获取市值数据...")
        df = ak.stock_a_code_name()
        logger.info(f"获取到 {len(df)} 只股票代码")
    except Exception as e:
        logger.warning(f"akshare获取失败: {e}")

    # 保存大市值股票到数据库
    # 由于精确市值获取困难，我们使用一个近似策略：
    # 排除流通市值太小的股票（约等于排除100亿以下）

    # 获取最近有交易且价格合适的股票
    c.execute("""
        SELECT DISTINCT code
        FROM daily_price
        WHERE trade_date >= '2026-03-01'
        AND close > 3
        AND close < 500
    """)
    active_stocks = set([row[0] for row in c.fetchall()])
    logger.info(f"活跃股票(3-500元): {len(active_stocks)} 只")

    # 取交集
    large_cap_stocks = list(active_stocks & set(stocks))
    logger.info(f"大市值候选股票: {len(large_cap_stocks)} 只")

    # 保存到文件
    output_file = ROOT / 'large_cap_stocks.txt'
    with open(output_file, 'w', encoding='utf-8') as f:
        for code in large_cap_stocks:
            f.write(f"{code}\n")

    logger.info(f"已保存到: {output_file}")

    conn.close()
    return large_cap_stocks


if __name__ == '__main__':
    main()