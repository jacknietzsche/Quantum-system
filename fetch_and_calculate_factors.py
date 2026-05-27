#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
批量获取近5年股票数据并计算因子
支持增量更新：跳过已有数据的股票和已计算的因子

功能：
1. 获取所有A股列表
2. 对每只股票，获取近5年数据（如果数据库中已有，则跳过）
3. 计算因子并存储到数据库
"""

import sqlite3
import pandas as pd
import numpy as np
import time
import os
from datetime import datetime, timedelta
from typing import List, Dict, Optional

from core.logging_config import setup_logging, get_logger
setup_logging()
logger = get_logger(__name__)

# 因子表名
FACTORS_TABLE = "stock_factors"


def create_factors_table(conn: sqlite3.Connection):
    """创建因子存储表"""
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
    for idx_name, idx_sql in [
        (f"idx_{FACTORS_TABLE}_code", f"CREATE INDEX IF NOT EXISTS idx_{FACTORS_TABLE}_code ON {FACTORS_TABLE}(code)"),
        (f"idx_{FACTORS_TABLE}_date", f"CREATE INDEX IF NOT EXISTS idx_{FACTORS_TABLE}_date ON {FACTORS_TABLE}(trade_date)"),
        (f"idx_{FACTORS_TABLE}_code_date", f"CREATE INDEX IF NOT EXISTS idx_{FACTORS_TABLE}_code_date ON {FACTORS_TABLE}(code, trade_date)")
    ]:
        try:
            cursor.execute(idx_sql)
        except:
            pass
    
    conn.commit()
    logger.info(f"因子表 {FACTORS_TABLE} 已创建")


def get_all_stocks_from_db(conn: sqlite3.Connection) -> List[str]:
    """从数据库获取所有股票代码"""
    cursor = conn.cursor()
    cursor.execute("SELECT code FROM stocks ORDER BY code")
    return [row[0] for row in cursor.fetchall()]


def get_stocks_needing_data(conn: sqlite3.Connection, 
                            min_date: str = "2021-01-01") -> List[str]:
    """
    获取需要获取数据的股票列表
    跳过已有足够数据的股票
    """
    cursor = conn.cursor()
    
    # 获取每只股票的数据量
    cursor.execute("""
        SELECT code, COUNT(*) as cnt, MAX(trade_date) as max_date
        FROM daily_price
        GROUP BY code
        HAVING cnt < 1000 OR max_date < ?
    """, (min_date,))
    
    stocks_needing_data = [row[0] for row in cursor.fetchall()]
    
    # 如果所有股票都有足够数据，返回空列表
    if not stocks_needing_data:
        cursor.execute("SELECT COUNT(DISTINCT code) FROM daily_price")
        total = cursor.fetchone()[0]
        logger.info(f"所有 {total} 只股票已有足够数据")
        return []
    
    logger.info(f"需要获取数据的股票: {len(stocks_needing_data)} 只")
    return stocks_needing_data


def fetch_stock_data(code: str, start_date: str = "2021-01-01") -> Optional[pd.DataFrame]:
    """
    获取单只股票的数据（使用core/data.py）
    如果数据库中已有数据，跳过
    """
    try:
        # 使用core.data模块获取数据
        from data import StockDataFetcher
        
        fetcher = StockDataFetcher()
        df = fetcher.fetch_history(code, start_date=start_date, end_date=datetime.now().strftime("%Y-%m-%d"))
        
        if df is None or df.empty:
            logger.warning(f"股票 {code} 无数据")
            return None
        
        logger.info(f"获取股票 {code} 数据成功: {len(df)} 条记录")
        return df
        
    except Exception as e:
        logger.error(f"获取股票 {code} 数据失败: {e}")
        return None


def store_stock_data(conn: sqlite3.Connection, code: str, df: pd.DataFrame):
    """将股票数据存储到数据库"""
    cursor = conn.cursor()
    
    # 为每只股票创建按年份分表（如果不存在）
    # 或者存储到主表daily_price
    
    # 先删除该股票的旧数据（如果有）
    cursor.execute("DELETE FROM daily_price WHERE code = ?", (code,))
    
    # 插入新数据
    for _, row in df.iterrows():
        try:
            cursor.execute("""
                INSERT OR REPLACE INTO daily_price
                (code, trade_date, open, high, low, close, volume, amount, turnover, pct_chg)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                code,
                row.get('date', row.get('trade_date')),
                float(row.get('open', 0)),
                float(row.get('high', 0)),
                float(row.get('low', 0)),
                float(row.get('close', 0)),
                float(row.get('volume', 0)),
                float(row.get('amount', 0)),
                float(row.get('turnover', row.get('turn', 0))),
                float(row.get('pct_chg', row.get('pctChg', 0)))
            ))
        except Exception as e:
            logger.debug(f"插入数据失败: {e}")
            continue
    
    conn.commit()
    logger.info(f"存储股票 {code} 数据成功: {len(df)} 条记录")


def calculate_and_store_factors(conn: sqlite3.Connection, 
                                code: str, 
                                engine):
    """计算并存储股票的因子"""
    # 获取股票数据
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
        WHERE code = ?
        ORDER BY trade_date
    """
    
    df = pd.read_sql_query(query, conn, params=(code,))
    
    if df.empty or len(df) < 60:
        logger.warning(f"股票 {code} 数据不足60条，跳过")
        return False
    
    # 计算因子（使用滚动窗口）
    logger.info(f"为股票 {code} 计算因子（{len(df)} 条记录）...")
    
    # 使用FactorEngineV2计算因子
    # 注意：这里需要为每一天计算因子（使用截至该日的数据）
    # 这是一个耗时的操作
    
    # 简化版：只计算最新一天的因子
    try:
        # 准备DataFrame
        df['pct_change'] = df['pctChg'] / 100
        df['turn'] = df['turnover']
        
        # 计算因子
        result = engine.calculate(df)
        
        # 存储因子（只存储最新一天）
        cursor = conn.cursor()
        last_date = df['date'].iloc[-1]
        adj_coef = result.get('adjustment_coef', 1.0)
        cat_scores = result.get('category_scores', {})
        
        cursor.execute(f"""
            INSERT OR REPLACE INTO {FACTORS_TABLE}
            (code, trade_date, adjustment_coef,
             momentum_score, vol_price_score, capital_flow_score, liquidity_score,
             volatility_risk_score, sentiment_crowd_score, microstructure_score,
             reversal_risk_score, disposition_effect_score, behavioral_classic_score)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            code,
            last_date,
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
        
        conn.commit()
        logger.info(f"计算并存储股票 {code} 的因子成功")
        return True
        
    except Exception as e:
        logger.error(f"计算股票 {code} 的因子失败: {e}")
        return False


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='获取近5年股票数据并计算因子')
    parser.add_argument('--db-path', type=str, default='local_db/a_stock_quant.db',
                        help='数据库路径')
    parser.add_argument('--min-date', type=str, default='2021-01-01',
                        help='最小日期 (格式: YYYY-MM-DD)')
    parser.add_argument('--limit', type=int, default=None,
                        help='限制处理股票数量（用于测试）')
    parser.add_argument('--skip-fetch', action='store_true',
                        help='跳过数据获取，只计算因子')
    
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
        
        if not args.skip_fetch:
            # 获取需要数据的股票
            stocks = get_stocks_needing_data(conn, min_date=args.min_date)
            
            if stocks:
                if args.limit:
                    stocks = stocks[:args.limit]
                    logger.info(f"限制处理前 {args.limit} 只股票（测试模式）")
                
                logger.info(f"开始获取 {len(stocks)} 只股票的数据...")
                
                for i, code in enumerate(stocks):
                    df = fetch_stock_data(code, start_date=args.min_date)
                    if df is not None and not df.empty:
                        store_stock_data(conn, code, df)
                    
                    if (i + 1) % 10 == 0:
                        logger.info(f"数据获取进度: {i+1}/{len(stocks)}")
                    
                    time.sleep(0.1)  # 避免请求过快
        
        # 计算因子
        logger.info("开始计算因子...")
        
        # 获取所有有数据的股票
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT code FROM daily_price ORDER BY code")
        all_stocks = [row[0] for row in cursor.fetchall()]
        
        # 获取已有因子的股票
        cursor.execute(f"SELECT DISTINCT code FROM {FACTORS_TABLE}")
        stocks_with_factors = set(row[0] for row in cursor.fetchall())
        
        # 需要计算因子的股票
        stocks_to_calculate = [code for code in all_stocks if code not in stocks_with_factors]
        
        if args.limit:
            stocks_to_calculate = stocks_to_calculate[:args.limit]
        
        logger.info(f"需要计算因子的股票: {len(stocks_to_calculate)} 只")
        
        success = 0
        failed = 0
        
        for i, code in enumerate(stocks_to_calculate):
            if calculate_and_store_factors(conn, code, engine):
                success += 1
            else:
                failed += 1
            
            if (i + 1) % 10 == 0:
                logger.info(f"因子计算进度: {i+1}/{len(stocks_to_calculate)}, 成功: {success}, 失败: {failed}")
        
        logger.info(f"因子计算完成! 成功: {success}, 失败: {failed}")
        
    except Exception as e:
        logger.error(f"主程序出错: {e}")
        import traceback
        traceback.print_exc()
    finally:
        conn.close()
        logger.info("数据库连接已关闭")


if __name__ == "__main__":
    main()
