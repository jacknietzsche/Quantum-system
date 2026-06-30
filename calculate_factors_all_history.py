#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
为已有充足数据的股票计算所有历史因子（优化版 - 多进程并行）

策略：
1. 只处理有充足数据（≥250条）的股票
2. 使用 FactorEngineV2 计算因子
3. 为每一个交易日计算因子（避免前视偏差）
4. 使用多进程并行加速
5. 支持增量更新（跳过已有因子数据的日期）
"""

import sqlite3
import pandas as pd
import numpy as np
import time
import os
from typing import List, Dict, Optional, Tuple
from multiprocessing import Pool, cpu_count
import argparse

from core.logging_config import setup_logging, get_logger
setup_logging()
logger = get_logger(__name__)

FACTORS_TABLE = "stock_factors"


def create_factors_table(conn: sqlite3.Connection):
    """创建因子表（如果不存在）"""
    cursor = conn.cursor()
    
    cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS {FACTORS_TABLE} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL,
            trade_date DATE NOT NULL,
            adjustment_coef REAL,
            momentum_score REAL,
            vol_price_score REAL,
            capital_flow_score REAL,
            liquidity_score REAL,
            volatility_risk_score REAL,
            sentiment_crowd_score REAL,
            microstructure_score REAL,
            reversal_risk_score REAL,
            disposition_effect_score REAL,
            behavioral_classic_score REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(code, trade_date)
        )
    """)
    
    # 创建索引
    for idx_sql in [
        f"CREATE INDEX IF NOT EXISTS idx_{FACTORS_TABLE}_code ON {FACTORS_TABLE}(code)",
        f"CREATE INDEX IF NOT EXISTS idx_{FACTORS_TABLE}_date ON {FACTORS_TABLE}(trade_date)",
        f"CREATE INDEX IF NOT EXISTS idx_{FACTORS_TABLE}_code_date ON {FACTORS_TABLE}(code, trade_date)"
    ]:
        try:
            cursor.execute(idx_sql)
        except:
            pass
    
    conn.commit()
    logger.info(f"因子表 {FACTORS_TABLE} 已创建")


def init_engine():
    """初始化因子引擎（每个进程独立初始化）"""
    from factor_engine_v2 import FactorEngineV2
    return FactorEngineV2()


def calculate_stock_factors(args: Tuple[str, str, int]) -> Tuple[str, bool, int, str]:
    """
    为单只股票计算所有历史因子（用于多进程）
    
    Parameters
    ----------
    args : Tuple[code, db_path, min_records]
    
    Returns
    -------
    Tuple[code, success, factors_count, error_msg]
    """
    code, db_path, min_records = args
    
    try:
        # 每个进程独立连接数据库
        conn = sqlite3.connect(db_path)
        engine = init_engine()
        
        # 获取数据
        query = """
            SELECT 
                trade_date as date,
                open, high, low, close, volume, amount,
                turnover as turn,
                pct_chg as pctChg
            FROM daily_price
            WHERE code = ?
            ORDER BY trade_date
        """
        
        df = pd.read_sql_query(query, conn, params=(code,))
        
        if df.empty or len(df) < 60:
            conn.close()
            return (code, False, 0, "数据不足60条")
        
        # 确保数值列类型正确
        numeric_cols = ['open', 'high', 'low', 'close', 'volume', 'amount', 'turn', 'pctChg']
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
        
        # 计算 pct_change
        df['pct_change'] = df['pctChg'] / 100
        
        # 获取已有因子数据的日期
        cursor = conn.cursor()
        cursor.execute(f"""
            SELECT DISTINCT trade_date FROM {FACTORS_TABLE}
            WHERE code = ?
        """, (code,))
        existing_dates = set(row[0] for row in cursor.fetchall())
        
        # 为每一个交易日计算因子
        factors_to_insert = []
        
        for i in range(60, len(df)):
            current_date = df.iloc[i]['date']
            
            # 跳过已有因子数据的日期
            if current_date in existing_dates:
                continue
            
            # 使用截至当前日期的数据计算因子
            hist_data = df.iloc[:i+1].copy()
            
            # 计算因子
            result = engine.calculate(hist_data)
            
            # 获取因子值
            adjustment_coef = result.get('adjustment_coef', 1.0)
            category_scores = result.get('category_scores', {})
            
            factors_to_insert.append((
                code,
                current_date,
                adjustment_coef,
                category_scores.get('momentum', 0.5),
                category_scores.get('vol_price', 0.5),
                category_scores.get('capital_flow', 0.5),
                category_scores.get('liquidity', 0.5),
                category_scores.get('volatility_risk', 0.5),
                category_scores.get('sentiment_crowd', 0.5),
                category_scores.get('microstructure', 0.5),
                category_scores.get('reversal_risk', 0.5),
                category_scores.get('disposition_effect', 0.5),
                category_scores.get('behavioral_classic', 0.5)
            ))
        
        # 批量插入因子数据
        if factors_to_insert:
            cursor.executemany(f"""
                INSERT OR REPLACE INTO {FACTORS_TABLE}
                (code, trade_date, adjustment_coef,
                 momentum_score, vol_price_score, capital_flow_score, liquidity_score,
                 volatility_risk_score, sentiment_crowd_score, microstructure_score,
                 reversal_risk_score, disposition_effect_score, behavioral_classic_score)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, factors_to_insert)
            
            conn.commit()
        
        conn.close()
        
        return (code, True, len(factors_to_insert), "")
        
    except Exception as e:
        import traceback
        error_msg = f"{type(e).__name__}: {str(e)}"
        if 'conn' in locals():
            conn.close()
        return (code, False, 0, error_msg)


def batch_calculate_factors_mp(stocks: List[str],
                                db_path: str,
                                min_records: int = 250,
                                n_workers: int = 8):
    """使用多进程批量计算因子"""
    total = len(stocks)
    processed = 0
    success = 0
    failed = 0
    total_factors = 0
    
    logger.info(f"开始批量计算 {total} 只股票的所有历史因子...")
    logger.info(f"使用 {n_workers} 个进程并行计算")
    
    # 准备参数
    args_list = [(code, db_path, min_records) for code in stocks]
    
    # 使用多进程池
    with Pool(processes=n_workers) as pool:
        for result in pool.imap_unordered(calculate_stock_factors, args_list, chunksize=1):
            code, ok, factors_count, error_msg = result
            
            processed += 1
            if ok:
                success += 1
                total_factors += factors_count
            else:
                failed += 1
                if error_msg:
                    logger.warning(f"股票 {code} 计算失败: {error_msg}")
            
            # 每处理 10 只股票输出一次进度
            if processed % 10 == 0:
                logger.info(f"进度: {processed}/{total}, 成功: {success}, 失败: {failed}, 因子数: {total_factors:,}")
    
    logger.info(f"批量计算完成! 总计: {total}, 成功: {success}, 失败: {failed}, 总因子数: {total_factors:,}")
    
    return success, failed, total_factors


def get_stocks_needing_factors(conn: sqlite3.Connection, 
                              min_records: int = 250) -> List[str]:
    """获取需要计算因子的股票（有充足数据但尚未计算所有因子）"""
    cursor = conn.cursor()
    
    # 获取有充足数据的股票
    cursor.execute("""
        SELECT code, COUNT(*) as cnt
        FROM daily_price
        GROUP BY code
        HAVING cnt >= ?
    """, (min_records,))
    
    stocks_with_data = {row[0]: row[1] for row in cursor.fetchall()}
    
    # 获取已有因子数据的股票及其因子数量
    cursor.execute(f"""
        SELECT code, COUNT(*) as cnt
        FROM {FACTORS_TABLE}
        GROUP BY code
    """)
    stocks_with_factors = {row[0]: row[1] for row in cursor.fetchall()}
    
    # 需要计算因子的股票：有数据但没有因子，或因子数量不足
    stocks_needing_factors = []
    for code, data_count in stocks_with_data.items():
        factors_count = stocks_with_factors.get(code, 0)
        # 需要计算的因子数量 = 数据量 - 60（前60天无法计算） - 已有因子数
        needed_factors = max(0, data_count - 60 - factors_count)
        if needed_factors > 0:
            stocks_needing_factors.append(code)
    
    logger.info(f"有充足数据的股票: {len(stocks_with_data)} 只")
    logger.info(f"已计算部分/全部因子的股票: {len(stocks_with_factors)} 只")
    logger.info(f"需要计算因子的股票: {len(stocks_needing_factors)} 只")
    
    return stocks_needing_factors


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='为已有充足数据的股票计算所有历史因子（多进程优化版）')
    parser.add_argument('--db-path', type=str, default='local_db/a_stock_quant.db',
                        help='数据库路径')
    parser.add_argument('--min-records', type=int, default=250,
                        help='最小记录数（默认250条，约1年）')
    parser.add_argument('--limit', type=int, default=None,
                        help='限制处理股票数量（用于测试）')
    parser.add_argument('--workers', type=int, default=8,
                        help='并行进程数（默认8）')
    parser.add_argument('--code', type=str, default=None,
                        help='指定股票代码（用于测试）')
    
    args = parser.parse_args()
    
    # 检查数据库文件是否存在
    if not os.path.exists(args.db_path):
        logger.error(f"数据库文件不存在: {args.db_path}")
        return
    
    # 连接数据库
    conn = sqlite3.connect(args.db_path)
    logger.info(f"Connected to database: {args.db_path}")
    
    try:
        # 创建因子表
        create_factors_table(conn)
        
        # 获取需要计算因子的股票
        if args.code:
            # 指定单只股票
            logger.info(f"指定股票模式: {args.code}")
            stocks = [args.code]
        else:
            stocks = get_stocks_needing_factors(conn, min_records=args.min_records)
            
            if not stocks:
                logger.info("所有股票已计算所有历史因子，无需处理")
                return
            
            # 限制数量（用于测试）
            if args.limit:
                stocks = stocks[:args.limit]
                logger.info(f"限制处理前 {args.limit} 只股票（测试模式）")
        
        # 关闭主进程的数据库连接（子进程会创建自己的连接）
        conn.close()
        conn = None
        
        # 批量计算因子（多进程）
        start_time = time.time()
        success, failed, total_factors = batch_calculate_factors_mp(
            stocks, 
            args.db_path, 
            min_records=args.min_records,
            n_workers=args.workers
        )
        elapsed_time = time.time() - start_time
        
        # 输出统计信息
        logger.info(f"=" * 70)
        logger.info(f"计算完成!")
        logger.info(f"  处理股票数: {len(stocks)}")
        logger.info(f"  成功: {success}")
        logger.info(f"  失败: {failed}")
        logger.info(f"  总因子数: {total_factors:,}")
        logger.info(f"  耗时: {elapsed_time/60:.1f} 分钟")
        if success > 0:
            logger.info(f"  平均速度: {elapsed_time/success:.1f} 秒/只")
        logger.info(f"=" * 70)
        
    except Exception as e:
        logger.error(f"主程序出错: {e}")
        import traceback
        logger.error(traceback.format_exc())
    finally:
        if conn:
            conn.close()
            logger.info("数据库连接已关闭")


if __name__ == "__main__":
    main()
