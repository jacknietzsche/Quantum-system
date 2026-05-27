#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试修改后的 calculate_and_store_factor 函数
"""

import sqlite3
import pandas as pd

from core.logging_config import setup_logging, get_logger
setup_logging()
logger = get_logger(__name__)

FACTORS_TABLE = "stock_factors"


def get_stock_data(conn: sqlite3.Connection, code: str) -> pd.DataFrame:
    """获取单只股票的价格数据"""
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
        return None
    
    # 确保数值列类型正确
    numeric_cols = ['open', 'high', 'low', 'close', 'volume', 'amount', 'turn', 'pctChg']
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
    
    # 计算 pct_change
    df['pct_change'] = df['pctChg'] / 100
    
    return df


def calculate_and_store_factor(conn: sqlite3.Connection, code: str, engine) -> bool:
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
        
        logger.info(f"股票 {code} 已有 {len(existing_dates)} 条因子数据")
        
        # 为每一个交易日计算因子（需要至少60天数据才能计算）
        factors_to_insert = []
        
        total_days = len(df)
        logger.info(f"股票 {code} 共有 {total_days} 个交易日数据，开始计算因子...")
        
        for i in range(60, total_days):
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
            logger.info(f"✅ 股票 {code} 计算了 {len(factors_to_insert)} 条因子数据")
        else:
            logger.info(f"⚠️  股票 {code} 所有日期的因子数据已存在，跳过")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ 股票 {code} 因子计算失败: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False


def main():
    """主函数 - 测试用"""
    # 连接数据库
    db_path = 'local_db/a_stock_quant.db'
    conn = sqlite3.connect(db_path)
    logger.info(f"Connected to database: {db_path}")
    
    try:
        # 初始化因子引擎
        from factor_engine_v2 import FactorEngineV2
        engine = FactorEngineV2()
        logger.info("✅ 因子引擎初始化成功")
        
        # 测试一只股票
        test_code = '000001'
        logger.info(f"开始测试股票 {test_code}...")
        
        success = calculate_and_store_factor(conn, test_code, engine)
        
        if success:
            # 查询计算结果
            cursor = conn.cursor()
            cursor.execute(f"""
                SELECT COUNT(*) FROM {FACTORS_TABLE}
                WHERE code = ?
            """, (test_code,))
            count = cursor.fetchone()[0]
            logger.info(f"✅ 测试完成！股票 {test_code} 共有 {count} 条因子数据")
            
            # 查看前几条数据
            cursor.execute(f"""
                SELECT code, trade_date, momentum_score, vol_price_score
                FROM {FACTORS_TABLE}
                WHERE code = ?
                ORDER BY trade_date
                LIMIT 5
            """, (test_code,))
            
            logger.info(f"前5条因子数据：")
            for row in cursor.fetchall():
                logger.info(f"  {row}")
        else:
            logger.error(f"❌ 测试失败！")
        
    except Exception as e:
        logger.error(f"主程序出错: {e}")
        import traceback
        logger.error(traceback.format_exc())
    finally:
        conn.close()
        logger.info("数据库连接已关闭")


if __name__ == "__main__":
    main()
