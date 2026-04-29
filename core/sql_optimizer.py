"""
core.sql_optimizer — SQL优化工具模块
==================================
负责SQL查询优化和执行计划分析

设计原则:
  - 优化SQL查询语句
  - 分析执行计划
  - 提供查询性能建议
  - 批量操作优化
"""

import sqlite3
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any

import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


class SQLOptimizer:
    """
    SQL优化器
    
    负责SQL查询优化和执行计划分析
    """
    
    def __init__(self, db_path: str = None):
        """
        初始化SQL优化器
        
        Args:
            db_path: 数据库路径
        """
        if db_path is None:
            from pathlib import Path
            project_root = Path(__file__).resolve().parent.parent
            db_path = project_root / "local_db" / "a_stock_quant.db"
        
        self.db_path = str(db_path)
        logger.info(f"SQLOptimizer 初始化: {self.db_path}")
    
    def analyze_query(self, query: str, params: tuple = ()) -> Dict[str, Any]:
        """
        分析查询语句的执行计划
        
        Args:
            query: SQL查询语句
            params: 查询参数
            
        Returns:
            执行计划分析结果
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            
            try:
                # 执行EXPLAIN查询
                explain_query = f"EXPLAIN QUERY PLAN {query}"
                c.execute(explain_query, params)
                plan = [dict(row) for row in c.fetchall()]
                
                # 分析执行计划
                analysis = {
                    'plan': plan,
                    'has_index': any('SEARCH' in row.get('detail', '') for row in plan),
                    'has_scan': any('SCAN' in row.get('detail', '') for row in plan),
                    'suggestions': []
                }
                
                # 生成优化建议
                if analysis['has_scan']:
                    analysis['suggestions'].append('查询可能需要添加索引')
                
                return analysis
            except Exception as e:
                logger.error("分析查询失败: %s", e)
                return {'error': str(e)}
    
    def optimize_query(self, query: str, params: tuple = ()) -> str:
        """
        优化SQL查询语句
        
        Args:
            query: 原始SQL查询语句
            params: 查询参数
            
        Returns:
            优化后的SQL查询语句
        """
        # 移除多余空格
        optimized_query = ' '.join(query.split())
        
        # 优化LIMIT子句
        if 'LIMIT' not in optimized_query.upper() and 'ORDER BY' in optimized_query.upper():
            optimized_query += ' LIMIT 1000'
        
        # 优化WHERE子句
        if 'WHERE' in optimized_query.upper():
            # 确保使用索引列
            pass
        
        return optimized_query
    
    def get_index_suggestions(self, table_name: str) -> List[str]:
        """
        获取表的索引建议
        
        Args:
            table_name: 表名
            
        Returns:
            索引建议列表
        """
        suggestions = []
        
        # 分析表结构
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            
            # 获取表的列信息
            c.execute(f"PRAGMA table_info({table_name})")
            columns = [row[1] for row in c.fetchall()]
            
            # 获取表的索引信息
            c.execute(f"PRAGMA index_list({table_name})")
            indexes = [row[1] for row in c.fetchall()]
            
            # 分析常用查询模式
            common_columns = ['code', 'trade_date', 'date']
            
            for col in common_columns:
                if col in columns:
                    index_name = f"idx_{table_name}_{col}"
                    if index_name not in indexes:
                        suggestions.append(f"CREATE INDEX {index_name} ON {table_name}({col})")
            
            # 建议复合索引
            if 'code' in columns and 'trade_date' in columns:
                composite_index = f"idx_{table_name}_code_trade_date"
                if composite_index not in indexes:
                    suggestions.append(f"CREATE INDEX {composite_index} ON {table_name}(code, trade_date)")
        
        return suggestions
    
    def optimize_batch_insert(self, table_name: str, data_list: List[Dict[str, Any]]) -> tuple:
        """
        优化批量插入操作
        
        Args:
            table_name: 表名
            data_list: 数据列表
            
        Returns:
            (insert_sql, insert_data) 元组
        """
        if not data_list:
            return None, None
        
        # 获取字段名
        fields = list(data_list[0].keys())
        field_names = ', '.join(fields)
        placeholders = ', '.join(['?' for _ in fields])
        
        # 准备插入数据
        insert_data = []
        for data in data_list:
            row = [data.get(field) for field in fields]
            insert_data.append(tuple(row))
        
        # 构建插入语句
        insert_sql = f"INSERT OR REPLACE INTO {table_name} ({field_names}) VALUES ({placeholders})"
        
        return insert_sql, insert_data
    
    def get_table_stats(self, table_name: str) -> Dict[str, Any]:
        """
        获取表的统计信息
        
        Args:
            table_name: 表名
            
        Returns:
            表的统计信息
        """
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            
            # 获取表的行数
            c.execute(f"SELECT COUNT(*) FROM {table_name}")
            row_count = c.fetchone()[0]
            
            # 获取表的大小
            c.execute(f"PRAGMA table_info({table_name})")
            columns = c.fetchall()
            column_count = len(columns)
            
            # 获取索引信息
            c.execute(f"PRAGMA index_list({table_name})")
            indexes = c.fetchall()
            index_count = len(indexes)
            
            return {
                'table_name': table_name,
                'row_count': row_count,
                'column_count': column_count,
                'index_count': index_count,
                'indexes': [index[1] for index in indexes]
            }
    
    def optimize_database(self) -> Dict[str, Any]:
        """
        优化整个数据库
        
        Returns:
            优化结果
        """
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            
            try:
                # 执行VACUUM命令
                start_time = datetime.now()
                c.execute("VACUUM")
                conn.commit()
                end_time = datetime.now()
                vacuum_time = (end_time - start_time).total_seconds()
                
                # 获取数据库信息
                c.execute("PRAGMA page_count")
                page_count = c.fetchone()[0]
                
                c.execute("PRAGMA page_size")
                page_size = c.fetchone()[0]
                
                return {
                    'vacuum_time': vacuum_time,
                    'page_count': page_count,
                    'page_size': page_size,
                    'database_size': page_count * page_size
                }
            except Exception as e:
                logger.error("优化数据库失败: %s", e)
                return {'error': str(e)}
    
    def analyze_tables(self) -> Dict[str, Any]:
        """
        分析所有表的性能
        
        Returns:
            表性能分析结果
        """
        results = {}
        
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            
            # 获取所有表
            c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
            tables = [row[0] for row in c.fetchall()]
            
            for table in tables:
                results[table] = self.get_table_stats(table)
                results[table]['index_suggestions'] = self.get_index_suggestions(table)
        
        return results


# 全局SQL优化器实例
_sql_optimizer = None


def get_sql_optimizer(db_path: str = None) -> SQLOptimizer:
    """
    获取SQL优化器实例
    
    Args:
        db_path: 数据库路径
        
    Returns:
        SQL优化器实例
    """
    global _sql_optimizer
    if _sql_optimizer is None:
        _sql_optimizer = SQLOptimizer(db_path)
    return _sql_optimizer
