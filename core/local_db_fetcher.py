# -*- coding: utf-8 -*-
"""
本地SQLite数据库获取器
======================
使用本地数据库 (local_db/a_stock_quant.db) 获取数据
优先使用本地数据，缺失时回退到网络获取
"""
import sqlite3
import logging
from datetime import datetime
from typing import Dict, List, Optional
from pathlib import Path

import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


class LocalDBFetcher:
    """
    本地SQLite数据库获取器
    
    使用方法:
        from core.local_db_fetcher import LocalDBFetcher
        fetcher = LocalDBFetcher()
        df = fetcher.get_daily("600519", days=120)
    """
    
    def __init__(self, db_path: str = None):
        """
        初始化本地数据库获取器
        
        Args:
            db_path: 数据库路径，默认使用 local_db/a_stock_quant.db
        """
        if db_path is None:
            # 默认路径：项目根目录/local_db/a_stock_quant.db
            project_root = Path(__file__).resolve().parent.parent
            db_path = project_root / "local_db" / "a_stock_quant.db"
        
        self.db_path = str(db_path)
        self._check_connection()
        logger.info(f"LocalDBFetcher 初始化: {self.db_path}")
    
    def _check_connection(self):
        """检查数据库连接"""
        import os
        if not os.path.exists(self.db_path):
            raise FileNotFoundError(f"数据库文件不存在: {self.db_path}")
    
    def _connect(self):
        """获取数据库连接"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def get_stock_list(self) -> pd.DataFrame:
        """
        获取股票列表
        
        Returns:
            DataFrame: columns: symbol, bs_code, name, market
        """
        conn = self._connect()
        try:
            df = pd.read_sql("""
                SELECT 
                    code as symbol,
                    code as bs_code,
                    name,
                    exchange as market
                FROM stocks 
                ORDER BY code
            """, conn)
            
            # 转换市场代码
            df['market'] = df['market'].str.upper()
            return df
        finally:
            conn.close()
    
    def get_name_map(self) -> Dict[str, str]:
        """
        获取股票代码到名称的映射
        
        Returns:
            Dict: {code: name}
        """
        conn = self._connect()
        try:
            df = pd.read_sql("SELECT code, name FROM stocks", conn)
            return dict(zip(df['code'], df['name']))
        finally:
            conn.close()
    
    def get_daily(self, code: str, days: int = 120) -> pd.DataFrame:
        """
        获取单只股票日频数据
        
        Args:
            code: 6位股票代码，如 "600519"
            days: 获取天数
            
        Returns:
            DataFrame: index=date, columns: open, high, low, close, volume, amount, turnover, pct_change
        """
        conn = self._connect()
        try:
            # 计算起始日期
            end_date = datetime.now().strftime("%Y-%m-%d")
            
            # 从数据库获取数据
            df = pd.read_sql("""
                SELECT 
                    trade_date as date,
                    open, high, low, close,
                    volume, amount, turnover,
                    pct_chg as pct_change
                FROM daily_price
                WHERE code = ?
                ORDER BY trade_date DESC
                LIMIT ?
            """, conn, params=(code, days))
            
            if df.empty:
                return pd.DataFrame()
            
            # 转换日期
            df['date'] = pd.to_datetime(df['date'])
            df = df.set_index('date')
            df = df.sort_index()  # 按日期升序
            
            # 确保数值类型
            for col in ['open', 'high', 'low', 'close', 'volume', 'amount', 'turnover', 'pct_change']:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
            
            return df
        finally:
            conn.close()
    
    def get_daily_range(self, code: str, start_date: str, end_date: str) -> pd.DataFrame:
        """
        获取指定日期范围的日频数据
        
        Args:
            code: 6位股票代码
            start_date: 起始日期 "YYYY-MM-DD"
            end_date: 结束日期 "YYYY-MM-DD"
            
        Returns:
            DataFrame: index=date
        """
        conn = self._connect()
        try:
            df = pd.read_sql("""
                SELECT 
                    trade_date as date,
                    open, high, low, close,
                    volume, amount, turnover,
                    pct_chg as pct_change
                FROM daily_price
                WHERE code = ? AND trade_date >= ? AND trade_date <= ?
                ORDER BY trade_date
            """, conn, params=(code, start_date, end_date))
            
            if df.empty:
                return pd.DataFrame()
            
            df['date'] = pd.to_datetime(df['date'])
            df = df.set_index('date')
            
            for col in ['open', 'high', 'low', 'close', 'volume', 'amount', 'turnover', 'pct_change']:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
            
            return df
        finally:
            conn.close()
    
    def get_batch_daily(self, codes: List[str], days: int = 120) -> Dict[str, pd.DataFrame]:
        """
        批量获取多只股票日频数据
        
        Args:
            codes: 股票代码列表
            days: 获取天数
            
        Returns:
            Dict: {code: DataFrame}
        """
        result = {}
        for code in codes:
            df = self.get_daily(code, days)
            if not df.empty:
                result[code] = df
        return result
    
    def get_stats(self) -> dict:
        """
        获取数据库统计信息
        
        Returns:
            dict: 数据库状态
        """
        conn = self._connect()
        try:
            c = conn.cursor()
            
            stock_count = c.execute("SELECT COUNT(*) FROM stocks").fetchone()[0]
            price_count = c.execute("SELECT COUNT(*) FROM daily_price").fetchone()[0]
            stock_with_data = c.execute("SELECT COUNT(DISTINCT code) FROM daily_price").fetchone()[0]
            date_min = c.execute("SELECT MIN(trade_date) FROM daily_price").fetchone()[0]
            date_max = c.execute("SELECT MAX(trade_date) FROM daily_price").fetchone()[0]
            
            return {
                "stock_count": stock_count,
                "price_count": price_count,
                "stock_with_data": stock_with_data,
                "date_min": date_min,
                "date_max": date_max,
            }
        finally:
            conn.close()
    
    def has_data(self, code: str) -> bool:
        """检查股票是否有数据"""
        conn = self._connect()
        try:
            c = conn.cursor()
            count = c.execute("SELECT COUNT(*) FROM daily_price WHERE code = ?", (code,)).fetchone()[0]
            return count > 0
        finally:
            conn.close()

    def get_stocks_with_min_data(self, min_days: int = 30) -> List[str]:
        """
        高效获取有足够数据的股票列表（单SQL查询）
        
        Args:
            min_days: 最少数据天数
            
        Returns:
            股票代码列表
        """
        conn = self._connect()
        try:
            # 使用 GROUP BY 直接筛选出有足够数据的股票
            df = pd.read_sql("""
                SELECT code 
                FROM daily_price 
                GROUP BY code 
                HAVING COUNT(*) >= ?
                ORDER BY code
            """, conn, params=(min_days,))
            return df['code'].tolist()
        finally:
            conn.close()


# 便捷函数
def get_local_fetcher() -> LocalDBFetcher:
    """获取本地数据库获取器实例"""
    return LocalDBFetcher()


if __name__ == "__main__":
    # 测试
    fetcher = LocalDBFetcher()
    stats = fetcher.get_stats()
    print("数据库统计:", stats)
    
    # 测试获取数据
    df = fetcher.get_daily("600519", days=10)
    print(f"\n600519 最近10天数据 ({len(df)}条):")
    print(df.tail())