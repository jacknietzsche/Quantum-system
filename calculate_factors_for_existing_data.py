#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
为已有充足数据的股票计算因子

策略：
1. 只处理有充足数据（≥250条）的股票
2. 使用FactorEngineV2计算因子
3. 存储因子到数据库
4. 支持增量更新（跳过已有因子数据的股票）
"""

import sqlite3
import pandas as pd
import numpy as np
import time
import os
from typing import List, Dict, Optional

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


def get_stocks_with_sufficient_data(conn: sqlite3.Connection, 
                                   min_records: int = 250) -> List[str]:
    """获取有充足数据的股票列表"""
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT code, COUNT(*) as cnt
        FROM daily_price
        GROUP BY code
        HAVING cnt >= ?
        ORDER BY cnt DESC
    """, (min_records,))
    
    stocks = [row[0] for row in cursor.fetchall()]
    logger.info(f"有至少{min_records}条记录的股票: {len(stocks)} 只")
    
    return stocks


def get_stocks_needing_factors(conn: sqlite3.Connection, 
                              min_records: int = 250) -> List[str]:
    """获取需要计算因子的股票（有充足数据但尚未计算因子）"""
    cursor = conn.cursor()
    
    # 获取有充足数据的股票
    cursor.execute("""
        SELECT code
        FROM (
            SELECT code, COUNT(*) as cnt
            FROM daily_price
            GROUP BY code
            HAVING cnt >= ?
        )
    """, (min_records,))
    
    stocks_with_data = set(row[0] for row in cursor.fetchall())
    
    # 获取已有因子数据的股票
    cursor.execute(f"SELECT DISTINCT code FROM {FACTORS_TABLE}")
    stocks_with_factors = set(row[0] for row in cursor.fetchall())
    
    # 需要计算因子的股票
    stocks_needing_factors = list(stocks_with_data - stocks_with_factors)
    
    logger.info(f"有充足数据的股票: {len(stocks_with_data)} 只")
    logger.info(f"已计算因子的股票: {len(stocks_with_factors)} 只")
    logger.info(f"需要计算因子的股票: {len(stocks_needing_factors)} 只")
    
    return stocks_needing_factors


def get_stock_data(conn: sqlite3.Connection, 
                   code: str) -> Optional[pd.DataFrame]:
    """获取单只股票的价格数据"""
    query = """
        SELECT 
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
        WHERE code = ?
        ORDER BY trade_date
    """
    
    df = pd.read_sql_query(query, conn, params=(code,))
    
    if df.empty or len(df) < 60:
        return None
    
    # 确保数值列类型正确
    numeric_cols = ['open', 'high', 'low', 'close', 'volume', 'amount', 'turn', 'pctChg']
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
    
    # 计算pct_change（如果缺失）
    if 'pctChg' in df.columns:
        df['pct_change'] = df['pctChg'] / 100
    elif 'close' in df.columns:
        df['pct_change'] = df['close'].pct_change()
    
    return df


def calculate_and_store_factor(conn: sqlite3.Connection,
                              code: str,
                              engine) -> bool:
    """计算并存储单只股票的所有历史因子"""
    df = get_stock_data(conn, code)
    
    if df is None or len(df) < 60:
        logger.warning(f"股票 {code} 数据不足60条，跳过")
        return False
    
    try:
        # 获取该股票已有因子数据的日期
        cursor = conn.cursor()
        cursor.execute(f"""
            SELECT DISTINCT trade_date FROM {FACTORS_TABLE}
            WHERE code = ?
        """, (code,))
        existing_dates = set(row[0] for row in cursor.fetchall())
        
        # 为每一个交易日计算因子（需要至少60天数据才能计算）
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
            logger.debug(f"股票 {code} 计算了 {len(factors_to_insert)} 条因子数据")
        
        return True
        
    except Exception as e:
        logger.error(f"股票 {code} 因子计算失败: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False


def batch_calculate_factors(conn: sqlite3.Connection,
                           stocks: List[str],
                           engine,
                           batch_size: int = 10):
    """批量计算因子"""
    total = len(stocks)
    processed = 0
    success = 0
    failed = 0
    
    logger.info(f"开始批量计算 {total} 只股票的因子...")
    
    for i, code in enumerate(stocks):
        if calculate_and_store_factor(conn, code, engine):
            success += 1
        else:
            failed += 1
        
        processed += 1
        
        # 每处理10只股票输出一次进度
        if (i + 1) % 10 == 0:
            logger.info(f"进度: {i+1}/{total}, 成功: {success}, 失败: {failed}")
        
        # 避免请求过快
        time.sleep(0.01)
    
    logger.info(f"批量计算完成! 总计: {total}, 成功: {success}, 失败: {failed}")


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='为已有充足数据的股票计算因子')
    parser.add_argument('--db-path', type=str, default='local_db/a_stock_quant.db',
                        help='数据库路径')
    parser.add_argument('--min-records', type=int, default=250,
                        help='最小记录数（默认250条，约1年）')
    parser.add_argument('--limit', type=int, default=None,
                        help='限制处理股票数量（用于测试）')
    parser.add_argument('--batch-size', type=int, default=10,
                        help='批处理大小')
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
        
        # 初始化因子引擎
        from factor_engine_v2 import FactorEngineV2
        engine = FactorEngineV2()
        logger.info("因子引擎初始化成功")
        
        # 获取需要计算因子的股票
        if args.code:
            # 指定单只股票
            logger.info(f"指定股票模式: {args.code}")
            stocks = [args.code]
        else:
            # 获取需要计算因子的股票列表
            stocks = get_stocks_needing_factors(conn, min_records=args.min_records)
            
            if not stocks:
                logger.info("所有股票已计算因子，无需处理")
                return
            
            # 限制数量（用于测试）
            if args.limit:
                stocks = stocks[:args.limit]
                logger.info(f"限制处理前 {args.limit} 只股票（测试模式）")
        
        # 批量计算因子
        batch_calculate_factors(conn, stocks, engine, batch_size=args.batch_size)
        
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
