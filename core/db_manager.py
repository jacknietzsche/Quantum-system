"""
core.db_manager — 数据库管理模块
==================================
负责数据库的连接管理、表结构优化、索引管理等功能

设计原则:
  - 连接池管理，提高连接效率
  - 表结构优化，提高数据存储效率
  - 索引策略优化，提高查询效率
  - 批量操作支持，提高数据处理效率
"""

import sqlite3
import logging
import threading
from datetime import datetime
from typing import Dict, List, Optional, Any
from pathlib import Path
from contextlib import contextmanager

import pandas as pd
import numpy as np

from core.cache_manager import get_cache_manager

logger = logging.getLogger(__name__)

__all__ = [
    "DBManager",
    "get_db_manager",
    "close_db_manager",
]


class DBManager:
    """
    数据库管理器
    
    负责数据库的连接管理、表结构优化、索引管理等功能
    """
    
    def __init__(self, db_path: str = None):
        """
        初始化数据库管理器
        
        Args:
            db_path: 数据库路径，默认使用 local_db/a_stock_quant.db
        """
        if db_path is None:
            # 默认路径：项目根目录/local_db/a_stock_quant.db
            project_root = Path(__file__).resolve().parent.parent
            db_path = project_root / "local_db" / "a_stock_quant.db"
        
        self.db_path = str(db_path)
        self._check_connection()
        
        # 连接池
        self._connection_pool = []
        self._pool_size = 5
        self._lock = threading.RLock()
        
        # 缓存管理器
        self._cache_manager = get_cache_manager()
        
        # 初始化连接池
        self._init_pool()
        
        # 确保表结构和索引存在
        self._ensure_schema()
        
        logger.info(f"DBManager 初始化: {self.db_path}")
    
    def _check_connection(self):
        """检查数据库连接"""
        import os
        db_dir = os.path.dirname(self.db_path)
        if not os.path.exists(db_dir):
            os.makedirs(db_dir)
        
        # 尝试连接数据库
        try:
            conn = sqlite3.connect(self.db_path)
            conn.close()
        except Exception as e:
            raise Exception(f"数据库连接失败: {e}")
    
    def _init_pool(self):
        """初始化连接池"""
        with self._lock:
            for _ in range(self._pool_size):
                try:
                    conn = sqlite3.connect(self.db_path)
                    conn.row_factory = sqlite3.Row
                    self._connection_pool.append(conn)
                except Exception as e:
                    logger.error("初始化连接池失败: %s", e)
    
    @contextmanager
    def get_connection(self):
        """获取数据库连接"""
        conn = None
        try:
            with self._lock:
                if self._connection_pool:
                    conn = self._connection_pool.pop()
                else:
                    # 连接池为空，创建新连接
                    conn = sqlite3.connect(self.db_path)
                    conn.row_factory = sqlite3.Row
            yield conn
        finally:
            if conn:
                try:
                    with self._lock:
                        if len(self._connection_pool) < self._pool_size:
                            self._connection_pool.append(conn)
                        else:
                            conn.close()
                except Exception as e:
                    logger.error("返回连接到池失败: %s", e)
    
    def _ensure_schema(self):
        """确保表结构和索引存在"""
        with self.get_connection() as conn:
            c = conn.cursor()
            
            # 创建 stocks 表
            c.execute('''
                CREATE TABLE IF NOT EXISTS stocks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    code TEXT UNIQUE NOT NULL,
                    name TEXT NOT NULL,
                    exchange TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # 创建 daily_price 表
            c.execute('''
                CREATE TABLE IF NOT EXISTS daily_price (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    code TEXT NOT NULL,
                    trade_date DATE NOT NULL,
                    open REAL NOT NULL,
                    high REAL NOT NULL,
                    low REAL NOT NULL,
                    close REAL NOT NULL,
                    volume REAL NOT NULL,
                    amount REAL NOT NULL,
                    turnover REAL,
                    pct_chg REAL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(code, trade_date)
                )
            ''')
            
            # 创建索引
            c.execute('CREATE INDEX IF NOT EXISTS idx_daily_price_code ON daily_price(code)')
            c.execute('CREATE INDEX IF NOT EXISTS idx_daily_price_date ON daily_price(trade_date)')
            c.execute('CREATE INDEX IF NOT EXISTS idx_daily_price_code_date ON daily_price(code, trade_date)')
            c.execute('CREATE INDEX IF NOT EXISTS idx_stocks_code ON stocks(code)')
            
            conn.commit()
    
    def get_stock_list(self) -> pd.DataFrame:
        """
        获取股票列表
        
        Returns:
            DataFrame: columns: symbol, bs_code, name, market
        """
        # 尝试从缓存获取
        cache_key = "stock_list"
        cached_data = self._cache_manager.get("db", cache_key)
        if cached_data is not None:
            return cached_data
        
        with self.get_connection() as conn:
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
            
            # 缓存结果
            self._cache_manager.set("db", df, cache_key)
            
            return df
    
    def get_name_map(self) -> Dict[str, str]:
        """
        获取股票代码到名称的映射
        
        Returns:
            Dict: {code: name}
        """
        # 尝试从缓存获取
        cache_key = "name_map"
        cached_data = self._cache_manager.get("db", cache_key)
        if cached_data is not None:
            return cached_data
        
        with self.get_connection() as conn:
            df = pd.read_sql("SELECT code, name FROM stocks", conn)
            name_map = dict(zip(df['code'], df['name']))
            
            # 缓存结果
            self._cache_manager.set("db", name_map, cache_key)
            
            return name_map
    
    def get_daily(self, code: str, days: int = 120) -> pd.DataFrame:
        """
        获取单只股票日频数据
        
        Args:
            code: 6位股票代码，如 "600519"
            days: 获取天数
            
        Returns:
            DataFrame: index=date, columns: open, high, low, close, volume, amount, turnover, pct_change
        """
        # 尝试从缓存获取
        cache_key = f"daily_{code}_{days}"
        cached_data = self._cache_manager.get("db", cache_key)
        if cached_data is not None:
            return cached_data
        
        with self.get_connection() as conn:
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
            
            # 缓存结果
            self._cache_manager.set("db", df, cache_key)
            
            return df
    
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
        # 尝试从缓存获取
        cache_key = f"daily_range_{code}_{start_date}_{end_date}"
        cached_data = self._cache_manager.get("db", cache_key)
        if cached_data is not None:
            return cached_data
        
        with self.get_connection() as conn:
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
            
            # 缓存结果
            self._cache_manager.set("db", df, cache_key)
            
            return df
    
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
        cache_misses = []
        
        # 先尝试从缓存获取
        for code in codes:
            cache_key = f"daily_{code}_{days}"
            cached_data = self._cache_manager.get("db", cache_key)
            if cached_data is not None:
                result[code] = cached_data
            else:
                cache_misses.append(code)
        
        # 缓存未命中的从数据库获取
        if cache_misses:
            with self.get_connection() as conn:
                for code in cache_misses:
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
                    
                    if not df.empty:
                        # 转换日期
                        df['date'] = pd.to_datetime(df['date'])
                        df = df.set_index('date')
                        df = df.sort_index()  # 按日期升序
                        
                        # 确保数值类型
                        for col in ['open', 'high', 'low', 'close', 'volume', 'amount', 'turnover', 'pct_change']:
                            if col in df.columns:
                                df[col] = pd.to_numeric(df[col], errors='coerce')
                        
                        result[code] = df
                        
                        # 缓存结果
                        cache_key = f"daily_{code}_{days}"
                        self._cache_manager.set("db", df, cache_key)
        
        return result
    
    def get_stats(self) -> dict:
        """
        获取数据库统计信息
        
        Returns:
            dict: 数据库状态
        """
        with self.get_connection() as conn:
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
    
    def has_data(self, code: str) -> bool:
        """检查股票是否有数据"""
        with self.get_connection() as conn:
            c = conn.cursor()
            count = c.execute("SELECT COUNT(*) FROM daily_price WHERE code = ?", (code,)).fetchone()[0]
            return count > 0
    
    def get_stocks_with_min_data(self, min_days: int = 30) -> List[str]:
        """
        高效获取有足够数据的股票列表（单SQL查询）
        
        Args:
            min_days: 最少数据天数
            
        Returns:
            股票代码列表
        """
        with self.get_connection() as conn:
            # 使用 GROUP BY 直接筛选出有足够数据的股票
            df = pd.read_sql("""
                SELECT code 
                FROM daily_price 
                GROUP BY code 
                HAVING COUNT(*) >= ?
                ORDER BY code
            """, conn, params=(min_days,))
            return df['code'].tolist()
    
    def insert_stock(self, code: str, name: str, exchange: str) -> bool:
        """
        插入股票信息
        
        Args:
            code: 股票代码
            name: 股票名称
            exchange: 交易所
            
        Returns:
            是否成功
        """
        with self.get_connection() as conn:
            try:
                c = conn.cursor()
                c.execute(
                    "INSERT OR REPLACE INTO stocks (code, name, exchange, updated_at) VALUES (?, ?, ?, ?)",
                    (code, name, exchange, datetime.now())
                )
                conn.commit()
                return True
            except Exception as e:
                logger.error("插入股票失败: %s", e)
                conn.rollback()
                return False
    
    def insert_daily_price(self, code: str, trade_date: str, data: Dict[str, Any]) -> bool:
        """
        插入日频数据
        
        Args:
            code: 股票代码
            trade_date: 交易日期
            data: 数据字典
            
        Returns:
            是否成功
        """
        with self.get_connection() as conn:
            try:
                c = conn.cursor()
                c.execute(
                    """
                    INSERT OR REPLACE INTO daily_price 
                    (code, trade_date, open, high, low, close, volume, amount, turnover, pct_chg, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        code, trade_date, data.get('open', 0), data.get('high', 0),
                        data.get('low', 0), data.get('close', 0), data.get('volume', 0),
                        data.get('amount', 0), data.get('turnover', 0), data.get('pct_change', 0),
                        datetime.now()
                    )
                )
                conn.commit()
                return True
            except Exception as e:
                logger.error("插入日频数据失败: %s", e)
                conn.rollback()
                return False
    
    def batch_insert_daily_price(self, data_list: List[Dict[str, Any]]) -> int:
        """
        批量插入日频数据
        
        Args:
            data_list: 数据列表，每个元素包含 code, trade_date 和其他数据
            
        Returns:
            成功插入的数量
        """
        if not data_list:
            return 0
        
        with self.get_connection() as conn:
            try:
                c = conn.cursor()
                
                # 准备插入数据
                insert_data = []
                for data in data_list:
                    insert_data.append(
                        (
                            data.get('code'), data.get('trade_date'),
                            data.get('open', 0), data.get('high', 0),
                            data.get('low', 0), data.get('close', 0),
                            data.get('volume', 0), data.get('amount', 0),
                            data.get('turnover', 0), data.get('pct_change', 0),
                            datetime.now()
                        )
                    )
                
                # 执行批量插入
                c.executemany(
                    """
                    INSERT OR REPLACE INTO daily_price 
                    (code, trade_date, open, high, low, close, volume, amount, turnover, pct_chg, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    insert_data
                )
                
                conn.commit()
                return len(insert_data)
            except Exception as e:
                logger.error("批量插入日频数据失败: %s", e)
                conn.rollback()
                return 0
    
    def optimize_database(self) -> bool:
        """
        优化数据库
        
        Returns:
            是否成功
        """
        with self.get_connection() as conn:
            try:
                c = conn.cursor()
                c.execute("VACUUM")
                conn.commit()
                logger.info("数据库优化完成")
                return True
            except Exception as e:
                logger.error("数据库优化失败: %s", e)
                return False
    
    def close(self):
        """
        关闭数据库连接
        """
        with self._lock:
            for conn in self._connection_pool:
                try:
                    conn.close()
                except Exception as e:
                    logger.error("关闭连接失败: %s", e)
            self._connection_pool.clear()


# 全局数据库管理器实例
_db_manager = None
_db_manager_lock = threading.RLock()


def get_db_manager(db_path: str = None) -> DBManager:
    """
    获取数据库管理器实例
    
    Args:
        db_path: 数据库路径
        
    Returns:
        数据库管理器实例
    """
    global _db_manager
    with _db_manager_lock:
        if _db_manager is None:
            _db_manager = DBManager(db_path)
        return _db_manager


def close_db_manager():
    """
    关闭数据库管理器
    """
    global _db_manager
    with _db_manager_lock:
        if _db_manager:
            _db_manager.close()
            _db_manager = None
