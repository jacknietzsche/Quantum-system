#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core.local_db_adapter - 本地 SQLite 数据库适配器
===================================================

从 v14 代码迁移而来。提供本地 SQLite 数据库的统一访问接口。

功能：
- 统一接口：与 RealDataFetcher 100% 兼容
- 透明切换：只需改一行代码
- 断点续传：支持增量更新
- 性能优化：批量读取、索引优化、WAL 模式

使用方式：
    from core.local_db_adapter import LocalDBAdapter

    db = LocalDBAdapter()
    df = db.get_price("600519", "2026-01-01", "2026-03-31")
"""
import os
import sqlite3
import logging
from pathlib import Path
from typing import Dict, List, Optional
import pandas as pd

logger = logging.getLogger('LocalDBAdapter')

# 默认数据库路径（基于 core/ 位置）
_DEFAULT_DB_PATH = str(Path(__file__).resolve().parent.parent / "local_db" / "a_stock_quant.db")


class LocalDBAdapter:
    """
    本地 SQLite 数据库适配器
    
    设计原则：
    1. 接口 100% 兼容 RealDataFetcher
    2. 单例模式，避免重复连接
    3. 懒加载：只在首次调用时初始化
    4. 批量读取优化：减少数据库 I/O
    """
    
    _instance = None
    
    def __new__(cls, db_path: str = None):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self, db_path: str = None):
        if hasattr(self, '_initialized') and self._initialized:
            return
        
        if db_path is None:
            db_path = _DEFAULT_DB_PATH
        
        self.db_path = os.path.abspath(db_path)
        self._conn = None
        self._name_cache: Dict[str, str] = {}
        
        if not os.path.exists(self.db_path):
            raise FileNotFoundError(f"数据库不存在: {self.db_path}")
        
        self._validate_schema()
        self._initialized = True
        stats = self.get_stats()
        logger.info(f"LocalDBAdapter 初始化: {stats['stock_count']}只股票, {stats['price_count']}万条行情")
    
    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path)
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA cache_size=-64000")
        return self._conn
    
    def _validate_schema(self):
        conn = self._get_conn()
        c = conn.cursor()
        c.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name IN ('stocks', 'daily_price')
        """)
        tables = {row[0] for row in c.fetchall()}
        if 'stocks' not in tables or 'daily_price' not in tables:
            raise ValueError(f"缺少必要的表，当前表: {tables}")
    
    def get_price(self, code: str, start_date: str = None, end_date: str = None, adjust: str = "none") -> pd.DataFrame:
        """读取股票行情数据 - 核心接口"""
        conn = self._get_conn()
        query = "SELECT trade_date, open, high, low, close, volume, amount, turnover FROM daily_price WHERE code = ?"
        params = [code]
        
        if start_date:
            query += " AND trade_date >= ?"
            params.append(start_date)
        if end_date:
            query += " AND trade_date <= ?"
            params.append(end_date)
        query += " ORDER BY trade_date ASC"
        
        try:
            df = pd.read_sql_query(query, conn, params=params)
        except Exception as e:
            logger.warning("读取 %s 失败: %s", code, e)
            return self._empty_df()
        
        if len(df) == 0:
            return self._empty_df()
        
        df = df.rename(columns={"trade_date": "date"})
        numeric_cols = ["open", "high", "low", "close", "volume", "amount", "turnover"]
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        return df
    
    def get_price_batch(self, codes: List[str], start_date: str = None, end_date: str = None) -> Dict[str, pd.DataFrame]:
        """批量读取多只股票数据"""
        if not codes:
            return {}
        
        conn = self._get_conn()
        placeholders = ",".join(["?"] * len(codes))
        query = f"""SELECT code, trade_date, open, high, low, close, volume, amount, turnover
            FROM daily_price WHERE code IN ({placeholders})"""
        params = list(codes)
        
        if start_date:
            query += " AND trade_date >= ?"
            params.append(start_date)
        if end_date:
            query += " AND trade_date <= ?"
            params.append(end_date)
        query += " ORDER BY code, trade_date ASC"
        
        df = pd.read_sql_query(query, conn, params=params)
        
        result = {}
        for code in codes:
            stock_df = df[df["code"] == code].copy()
            if len(stock_df) > 0:
                stock_df = stock_df.rename(columns={"trade_date": "date"})
                for col in ["open", "high", "low", "close", "volume", "amount", "turnover"]:
                    if col in stock_df.columns:
                        stock_df[col] = pd.to_numeric(stock_df[col], errors="coerce")
                result[code] = stock_df[["date", "open", "high", "low", "close", "volume", "amount", "turnover"]]
            else:
                result[code] = self._empty_df()
        return result
    
    def get_stock_name(self, code: str) -> str:
        if code in self._name_cache:
            return self._name_cache[code]
        conn = self._get_conn()
        c = conn.cursor()
        c.execute("SELECT name FROM stocks WHERE code = ?", (code,))
        row = c.fetchone()
        name = row[0] if row else ""
        self._name_cache[code] = name
        return name
    
    def get_all_codes(self) -> List[str]:
        conn = self._get_conn()
        c = conn.cursor()
        c.execute("SELECT code FROM stocks ORDER BY code")
        return [row[0] for row in c.fetchall()]
    
    def get_latest_date(self, code: str) -> Optional[str]:
        conn = self._get_conn()
        c = conn.cursor()
        c.execute("SELECT MAX(trade_date) FROM daily_price WHERE code = ?", (code,))
        row = c.fetchone()
        return row[0] if row and row[0] else None
    
    def get_stats(self) -> dict:
        conn = self._get_conn()
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
            "file_size_mb": os.path.getsize(self.db_path) / 1024 / 1024
        }
    
    def get_price_for_factor(self, code: str, start_date: str, end_date: str) -> pd.DataFrame:
        """获取用于因子计算的数据"""
        df = self.get_price(code, start_date, end_date)
        if len(df) == 0:
            return df
        df["pctChg"] = df["close"].pct_change() * 100
        df["pctChg"] = df["pctChg"].fillna(0)
        df["turn"] = df["turnover"] / 100
        return df
    
    def get_price_for_backtest(self, code: str, start_date: str, end_date: str) -> pd.DataFrame:
        """获取用于回测的数据"""
        df = self.get_price(code, start_date, end_date)
        if len(df) == 0:
            return df
        return df[["date", "open", "high", "low", "close", "volume"]]
    
    def _empty_df(self) -> pd.DataFrame:
        return pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume", "amount", "turnover"])
    
    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None


def get_adapter(db_path: str = None) -> LocalDBAdapter:
    return LocalDBAdapter(db_path)

if __name__ == "__main__":
    print("=" * 50)
    print("本地数据库适配器测试")
    print("=" * 50)
    
    db = LocalDBAdapter()
    
    print("\n--- 测试1: 读取 600519 ---")
    df = db.get_price("600519", "2026-03-01", "2026-03-31")
    print(f"贵州茅台: {len(df)} 条")
    if len(df) > 0:
        print(df.tail(3).to_string(index=False))
    
    print("\n--- 测试2: 批量读取 ---")
    for c in ["000858", "600519", "300750"]:
        d = db.get_price(c, "2026-03-20", "2026-03-31")
        print(f"{c} {db.get_stock_name(c)}: {len(d)} 条")
    
    print("\n--- 测试3: 统计 ---")
    stats = db.get_stats()
    print(f"股票数: {stats['stock_count']}, 行情: {stats['price_count']//10000}万条")
    print(f"日期范围: {stats['date_min']} ~ {stats['date_max']}")
    print(f"文件大小: {stats['file_size_mb']:.1f} MB")
    
    print("\n✅ 测试完成!")