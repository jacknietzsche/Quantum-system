#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
批量计算股票因子并存储到数据库
支持增量计算：跳过已有因子数据的股票

功能：
1. 从daily_price表读取股票数据
2. 使用FactorEngineV2计算51个因子
3. 将因子存储到factors表
4. 支持增量更新（跳过已计算的股票）
"""

import sqlite3
import pandas as pd
import numpy as np
import time
from datetime import datetime, timedelta
import os
from typing import List, Dict, Optional

from core.logging_config import setup_logging, get_logger
setup_logging()
logger = get_logger(__name__)

# 因子表名
FACTORS_TABLE = "stock_factors"


def create_factors_table(conn: sqlite3.Connection):
    """创建因子存储表"""
    cursor = conn.cursor()
    
    # 创建因子表（如果不存在）
    cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS {FACTORS_TABLE} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL,
            trade_date DATE NOT NULL,
            -- 综合评分
            adjustment_coef REAL,
            -- 各大类评分
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
            -- 时间戳
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(code, trade_date)
        )
    """)
    
    # 创建索引
    cursor.execute(f"""
        CREATE INDEX IF NOT EXISTS idx_{FACTORS_TABLE}_code 
        ON {FACTORS_TABLE}(code)
    """)
    cursor.execute(f"""
        CREATE INDEX IF NOT EXISTS idx_{FACTORS_TABLE}_date 
        ON {FACTORS_TABLE}(trade_date)
    """)
    cursor.execute(f"""
        CREATE INDEX IF NOT EXISTS idx_{FACTORS_TABLE}_code_date 
        ON {FACTORS_TABLE}(code, trade_date)
    """)
    
    conn.commit()
    logger.info(f"因子表 {FACTORS_TABLE} 已创建（如果不存在）")


def get_stocks_needing_factors(conn: sqlite3.Connection, 
                                min_date: str = "2021-01-01",
                                batch_size: int = 100) -> List[str]:
    """
    获取需要计算因子的股票列表
    跳过已有因子数据的股票
    """
    cursor = conn.cursor()
    
    # 获取所有有价格数据的股票
    cursor.execute("""
        SELECT DISTINCT code 
        FROM daily_price 
        WHERE trade_date >= ?
        ORDER BY code
    """, (min_date,))
    
    all_stocks = [row[0] for row in cursor.fetchall()]
    logger.info(f"共有 {len(all_stocks)} 只股票有价格数据")
    
    # 获取已有因子数据的股票
    cursor.execute(f"""
        SELECT DISTINCT code 
        FROM {FACTORS_TABLE}
    """)
    
    stocks_with_factors = set(row[0] for row in cursor.fetchall())
    logger.info(f"已有 {len(stocks_with_factors)} 只股票计算了因子")
    
    # 需要计算的股票
    stocks_to_process = [code for code in all_stocks if code not in stocks_with_factors]
    logger.info(f"需要计算因子的股票: {len(stocks_to_process)} 只")
    
    return stocks_to_process


def get_stock_data(conn: sqlite3.Connection, 
                   code: str, 
                   min_date: str = "2021-01-01") -> Optional[pd.DataFrame]:
    """获取单只股票的价格数据"""
    query = """
        SELECT 
            code,
            trade_date as date,
            open,
            high,
            low,
            close,
            volume,
            amount,
            turnover as turn,
            pct_chg as pctChg
        FROM daily_price
        WHERE code = ? AND trade_date >= ?
        ORDER BY trade_date
    """
    
    df = pd.read_sql_query(query, conn, params=(code, min_date))
    
    if df.empty:
        return None
    
    # 重命名列以兼容FactorEngineV2
    df = df.rename(columns={
        'pct_chg': 'pctChg'
    })
    
    # 确保数值列是float类型
    numeric_cols = ['open', 'high', 'low', 'close', 'volume', 'amount', 'turn', 'pctChg']
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
    
    # 计算pct_change（如果缺失）
    if 'pctChg' in df.columns and df['pctChg'].notna().any():
        df['pct_change'] = df['pctChg'] / 100  # 转换为小数
    elif 'close' in df.columns:
        df['pct_change'] = df['close'].pct_change()
    
    return df


def calculate_factors_for_stock(df: pd.DataFrame, engine) -> Optional[Dict]:
    """为单只股票计算因子"""
    if len(df) < 60:  # 至少需要60个交易日的数据
        logger.warning(f"数据不足60条，跳过")
        return None
    
    try:
        result = engine.calculate(df)
        return result
    except Exception as e:
        logger.error(f"计算因子失败: {e}")
        return None


def store_factors(conn: sqlite3.Connection,
                  code: str,
                  df: pd.DataFrame,
                  factor_result: Dict):
    """将因子数据存储到数据库（每个交易日一行）"""
    cursor = conn.cursor()
    
    # 获取综合评分和各大类评分
    adjustment_coef = factor_result.get('adjustment_coef', 1.0)
    category_scores = factor_result.get('category_scores', {})
    all_factors = factor_result.get('all_factors', {})
    
    if df.empty:
        return
    
    # 为每一天的数据存储因子（使用滚动窗口计算）
    logger.debug(f"为股票 {code} 计算滚动因子...")
    
    # 使用滚动窗口计算每一天的因子
    for i in range(60, len(df)):  # 至少需要60天数据
        try:
            # 取截至当前日期的数据窗口
            window_df = df.iloc[:i+1].copy()
            
            # 计算因子
            result = engine.calculate(window_df) if 'engine' in dir() else None
            if result is None:
                continue
            
            trade_date = df.iloc[i]['date'] if 'date' in df.columns else df.index[i]
            adj_coef = result.get('adjustment_coef', 1.0)
            cat_scores = result.get('category_scores', {})
            
            # 插入或替换因子数据
            cursor.execute(f"""
                INSERT OR REPLACE INTO {FACTORS_TABLE}
                (code, trade_date, adjustment_coef,
                 momentum_score, vol_price_score, capital_flow_score, liquidity_score,
                 volatility_risk_score, sentiment_crowd_score, microstructure_score,
                 reversal_risk_score, disposition_effect_score, behavioral_classic_score)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                code,
                trade_date,
                adj_coef,
                cat_scores.get('momentum', 0.5),
                cat_scores.get('vol_price', 0.5),
                cat_scores.get('capital_flow', 0.5),
                cat_scores.get('liquidity', 0.5),
                cat_scores.get('volatility_risk', 0.5),
                cat_scores.get('sentiment_crowd', 0.5),
                cat_scores.get('microstructure', 0.5),
                cat_scores.get('reversal_risk', 0.5),
                cat_scores.get('disposition_effect', 0.5),
                cat_scores.get('behavioral_classic', 0.5)
            ))
            
        except Exception as e:
            logger.debug(f"计算日期 {trade_date} 的因子失败: {e}")
            continue
    
    conn.commit()
    logger.info(f"存储股票 {code} 的因子数据成功")


def process_stocks_batch(conn: sqlite3.Connection,
                         stocks: List[str],
                         engine,
                         batch_size: int = 10):
    """批量处理股票"""
    total = len(stocks)
    processed = 0
    success = 0
    failed = 0
    
    logger.info(f"开始处理 {total} 只股票...")
    
    for i, code in enumerate(stocks):
        try:
            # 获取股票数据
            df = get_stock_data(conn, code)
            if df is None or df.empty:
                logger.warning(f"股票 {code} 无数据，跳过")
                failed += 1
                continue
            
            # 计算因子
            factor_result = calculate_factors_for_stock(df, engine)
            if factor_result is None:
                logger.warning(f"股票 {code} 因子计算失败，跳过")
                failed += 1
                continue
            
            # 存储因子
            store_factors(conn, code, df, factor_result)
            
            success += 1
            processed += 1
            
            # 每处理10只股票输出一次进度
            if (i + 1) % 10 == 0:
                logger.info(f"进度: {i+1}/{total}, 成功: {success}, 失败: {failed}")
            
            # 避免请求过快
            time.sleep(0.01)
            
        except Exception as e:
            logger.error(f"处理股票 {code} 时出错: {e}")
            failed += 1
    
    logger.info(f"处理完成! 总计: {total}, 成功: {success}, 失败: {failed}")


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='批量计算股票因子并存储到数据库')
    parser.add_argument('--db-path', type=str, default='local_db/a_stock_quant.db',
                        help='数据库路径')
    parser.add_argument('--min-date', type=str, default='2021-01-01',
                        help='最小日期 (格式: YYYY-MM-DD)')
    parser.add_argument('--batch-size', type=int, default=10,
                        help='批处理大小')
    parser.add_argument('--limit', type=int, default=None,
                        help='限制处理股票数量（用于测试）')
    
    args = parser.parse_args()
    
    # 检查数据库文件是否存在
    if not os.path.exists(args.db_path):
        logger.error(f"数据库文件不存在: {args.db_path}")
        return
    
    # 连接数据库
    conn = sqlite3.connect(args.db_path)
    logger.info(f" connected to database: {args.db_path}")
    
    try:
        # 创建因子表
        create_factors_table(conn)
        
        # 初始化因子引擎
        from factor_engine_v2 import FactorEngineV2
        engine = FactorEngineV2()
        logger.info("因子引擎初始化成功")
        
        # 获取需要处理的股票
        stocks = get_stocks_needing_factors(conn, min_date=args.min_date)
        
        if args.limit:
            stocks = stocks[:args.limit]
            logger.info(f"限制处理前 {args.limit} 只股票（测试模式）")
        
        if not stocks:
            logger.info("所有股票已计算因子，无需处理")
            return
        
        # 批量处理
        process_stocks_batch(conn, stocks, engine, batch_size=args.batch_size)
        
        # 输出统计信息
        cursor = conn.cursor()
        cursor.execute(f"SELECT COUNT(DISTINCT code) FROM {FACTORS_TABLE}")
        total_with_factors = cursor.fetchone()[0]
        logger.info(f"因子表中共有 {total_with_factors} 只股票的因子数据")
        
    except Exception as e:
        logger.error(f"主程序出错: {e}")
        import traceback
        traceback.print_exc()
    finally:
        conn.close()
        logger.info("数据库连接已关闭")


if __name__ == "__main__":
    main()
