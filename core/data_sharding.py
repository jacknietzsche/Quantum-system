"""
core.data_sharding — 数据分片管理模块
==================================
负责数据分片管理，提升数据管理效率

设计原则:
  - 按时间分片，减少单表数据量
  - 透明的分片管理，对上层应用透明
  - 支持跨分片查询
  - 提高数据插入和查询效率
"""

import sqlite3
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any
from pathlib import Path

import pandas as pd
import numpy as np

from core.db_manager import get_db_manager

logger = logging.getLogger(__name__)

__all__ = [
    "DataShardingManager",
    "get_data_sharding_manager",
]


class DataShardingManager:
    """
    数据分片管理器
    
    负责按时间对数据进行分片管理
    """
    
    def __init__(self):
        """
        初始化数据分片管理器
        """
        self.db_manager = get_db_manager()
        self._ensure_sharding_tables()
        logger.info("DataShardingManager 初始化完成")
    
    def _ensure_sharding_tables(self):
        """
        确保分片表存在
        """
        # 获取当前年份
        current_year = datetime.now().year
        # 创建最近5年的分片表
        for year in range(current_year - 4, current_year + 1):
            self._create_shard_table(year)
    
    def _create_shard_table(self, year: int):
        """
        创建指定年份的分片表
        
        Args:
            year: 年份
        """
        table_name = f"daily_price_{year}"
        with self.db_manager.get_connection() as conn:
            c = conn.cursor()
            
            # 创建分片表
            c.execute(f'''
                CREATE TABLE IF NOT EXISTS {table_name} (
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
            c.execute(f'CREATE INDEX IF NOT EXISTS idx_{table_name}_code ON {table_name}(code)')
            c.execute(f'CREATE INDEX IF NOT EXISTS idx_{table_name}_date ON {table_name}(trade_date)')
            c.execute(f'CREATE INDEX IF NOT EXISTS idx_{table_name}_code_date ON {table_name}(code, trade_date)')
            
            conn.commit()
    
    def _get_shard_table(self, date: str) -> str:
        """
        获取日期对应的分片表
        
        Args:
            date: 日期字符串 "YYYY-MM-DD"
            
        Returns:
            分片表名
        """
        year = date.split('-')[0]
        return f"daily_price_{year}"
    
    def _get_shard_tables(self, start_date: str, end_date: str) -> List[str]:
        """
        获取日期范围内的分片表
        
        Args:
            start_date: 起始日期 "YYYY-MM-DD"
            end_date: 结束日期 "YYYY-MM-DD"
            
        Returns:
            分片表名列表
        """
        start_year = int(start_date.split('-')[0])
        end_year = int(end_date.split('-')[0])
        tables = []
        for year in range(start_year, end_year + 1):
            tables.append(f"daily_price_{year}")
        return tables
    
    def insert_daily_price(self, code: str, trade_date: str, data: Dict[str, Any]) -> bool:
        """
        插入日频数据到相应的分片表
        
        Args:
            code: 股票代码
            trade_date: 交易日期
            data: 数据字典
            
        Returns:
            是否成功
        """
        table_name = self._get_shard_table(trade_date)
        with self.db_manager.get_connection() as conn:
            try:
                c = conn.cursor()
                c.execute(
                    f"""
                    INSERT OR REPLACE INTO {table_name} 
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
        批量插入日频数据到相应的分片表
        
        Args:
            data_list: 数据列表，每个元素包含 code, trade_date 和其他数据
            
        Returns:
            成功插入的数量
        """
        if not data_list:
            return 0
        
        # 按年份分组
        data_by_year = {}
        for data in data_list:
            trade_date = data.get('trade_date')
            if not trade_date:
                continue
            year = trade_date.split('-')[0]
            if year not in data_by_year:
                data_by_year[year] = []
            data_by_year[year].append(data)
        
        total_inserted = 0
        with self.db_manager.get_connection() as conn:
            try:
                c = conn.cursor()
                
                for year, year_data in data_by_year.items():
                    table_name = f"daily_price_{year}"
                    
                    # 准备插入数据
                    insert_data = []
                    for data in year_data:
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
                    
                    if insert_data:
                        # 执行批量插入
                        c.executemany(
                            f"""
                            INSERT OR REPLACE INTO {table_name} 
                            (code, trade_date, open, high, low, close, volume, amount, turnover, pct_chg, updated_at)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            insert_data
                        )
                        total_inserted += len(insert_data)
                
                conn.commit()
                return total_inserted
            except Exception as e:
                logger.error("批量插入日频数据失败: %s", e)
                conn.rollback()
                return 0
    
    def get_daily(self, code: str, days: int = 120) -> pd.DataFrame:
        """
        获取单只股票日频数据
        
        Args:
            code: 6位股票代码，如 "600519"
            days: 获取天数
            
        Returns:
            DataFrame: index=date, columns: open, high, low, close, volume, amount, turnover, pct_change
        """
        # 计算起始日期
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - pd.Timedelta(days=days + 30)).strftime("%Y-%m-%d")
        
        # 获取需要查询的分片表
        tables = self._get_shard_tables(start_date, end_date)
        
        # 构建联合查询
        if not tables:
            return pd.DataFrame()
        
        query_parts = []
        params = [code]
        
        for table in tables:
            query_parts.append(
                f"SELECT trade_date as date, open, high, low, close, volume, amount, turnover, pct_chg as pct_change FROM {table} WHERE code = ?"
            )
            params.append(code)
        
        query = " UNION ALL ".join(query_parts) + " ORDER BY date DESC LIMIT ?"
        params.append(days)
        
        with self.db_manager.get_connection() as conn:
            df = pd.read_sql(query, conn, params=params)
            
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
        # 获取需要查询的分片表
        tables = self._get_shard_tables(start_date, end_date)
        
        # 构建联合查询
        if not tables:
            return pd.DataFrame()
        
        query_parts = []
        params = [code, start_date, end_date]
        
        for table in tables:
            query_parts.append(
                f"SELECT trade_date as date, open, high, low, close, volume, amount, turnover, pct_chg as pct_change FROM {table} WHERE code = ? AND trade_date >= ? AND trade_date <= ?"
            )
            params.extend([code, start_date, end_date])
        
        query = " UNION ALL ".join(query_parts) + " ORDER BY date"
        
        with self.db_manager.get_connection() as conn:
            df = pd.read_sql(query, conn, params=params)
            
            if df.empty:
                return pd.DataFrame()
            
            df['date'] = pd.to_datetime(df['date'])
            df = df.set_index('date')
            
            for col in ['open', 'high', 'low', 'close', 'volume', 'amount', 'turnover', 'pct_change']:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
            
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
        for code in codes:
            df = self.get_daily(code, days)
            if not df.empty:
                result[code] = df
        return result
    
    def get_stocks_with_min_data(self, min_days: int = 30) -> List[str]:
        """
        高效获取有足够数据的股票列表
        
        Args:
            min_days: 最少数据天数
            
        Returns:
            股票代码列表
        """
        # 获取所有分片表
        with self.db_manager.get_connection() as conn:
            c = conn.cursor()
            c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'daily_price_%'")
            tables = [row[0] for row in c.fetchall()]
        
        if not tables:
            return []
        
        # 构建联合查询
        query_parts = []
        for table in tables:
            query_parts.append(f"SELECT code FROM {table}")
        
        query = " UNION ALL ".join(query_parts)
        
        with self.db_manager.get_connection() as conn:
            df = pd.read_sql(f"SELECT code FROM ({query}) AS all_data GROUP BY code HAVING COUNT(*) >= ? ORDER BY code", conn, params=(min_days,))
            return df['code'].tolist()
    
    def optimize_shards(self) -> bool:
        """
        优化分片表
        
        Returns:
            是否成功
        """
        with self.db_manager.get_connection() as conn:
            try:
                c = conn.cursor()
                c.execute("VACUUM")
                conn.commit()
                logger.info("分片表优化完成")
                return True
            except Exception as e:
                logger.error("分片表优化失败: %s", e)
                return False


# 全局数据分片管理器实例
_data_sharding_manager = None
_data_sharding_manager_lock = logging.getLogger(__name__)


def get_data_sharding_manager() -> DataShardingManager:
    """
    获取数据分片管理器实例
    
    Returns:
        数据分片管理器实例
    """
    global _data_sharding_manager
    if _data_sharding_manager is None:
        _data_sharding_manager = DataShardingManager()
    return _data_sharding_manager
