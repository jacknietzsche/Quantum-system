"""
core.optimized_data_processor — 优化的数据处理模块
==================================
负责高效的数据加载、预处理和转换，减少不必要的操作，提高回测系统性能

设计原则:
  - 缓存机制，避免重复加载
  - 向量化处理，提高计算效率
  - 并行处理，加速数据加载
  - 内存优化，减少内存使用
  - 数据预处理，减少回测过程中的计算量
"""

import os
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Optional, Any

import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)

__all__ = [
    "OptimizedDataProcessor",
    "get_optimized_data_processor",
]


class OptimizedDataProcessor:
    """
    优化的数据处理器
    
    负责高效的数据加载、预处理和转换
    """
    
    def __init__(self, cache_dir: str = None):
        """
        初始化数据处理器
        
        Args:
            cache_dir: 缓存目录
        """
        self._cache_dir = cache_dir or os.path.join(os.path.dirname(__file__), '../data_cache')
        os.makedirs(self._cache_dir, exist_ok=True)
        
        self._data_cache: Dict[str, pd.DataFrame] = {}
        self._processed_data: Dict[str, pd.DataFrame] = {}
        self._lock = threading.RLock()
        
        logger.info(f"OptimizedDataProcessor 初始化完成，缓存目录: {self._cache_dir}")
    
    def process_data_dict(self, data_dict: Dict[str, pd.DataFrame]) -> Dict[str, pd.DataFrame]:
        """
        批量处理数据字典
        
        Args:
            data_dict: {股票代码: DataFrame} 行情数据
            
        Returns:
            处理后的数据字典
        """
        logger.info(f"开始处理 {len(data_dict)} 只股票数据...")
        
        # 使用线程池并行处理数据
        processed_dict = {}
        with ThreadPoolExecutor(max_workers=min(8, len(data_dict))) as executor:
            futures = {executor.submit(self._process_single_stock, code, df): code 
                      for code, df in data_dict.items()}
            
            for future in futures:
                code = futures[future]
                try:
                    processed_df = future.result()
                    processed_dict[code] = processed_df
                except Exception as e:
                    logger.error("处理 %s 数据失败: %s", code, e)
                    # 使用原始数据作为 fallback
                    processed_dict[code] = data_dict[code]
        
        logger.info("数据处理完成")
        return processed_dict
    
    def _process_single_stock(self, code: str, df: pd.DataFrame) -> pd.DataFrame:
        """
        处理单只股票的数据
        
        Args:
            code: 股票代码
            df: 原始数据
            
        Returns:
            处理后的数据
        """
        # 检查缓存
        cache_key = f"{code}_processed"
        if cache_key in self._processed_data:
            return self._processed_data[cache_key]
        
        # 确保日期索引
        if not isinstance(df.index, pd.DatetimeIndex):
            if "date" in df.columns:
                df = df.set_index("date")
                df.index = pd.to_datetime(df.index)
            else:
                df.index = pd.to_datetime(df.index)
        
        # 排序
        df = df.sort_index()
        
        # 确保必要列存在
        required_columns = ["open", "high", "low", "close", "volume"]
        for col in required_columns:
            if col not in df.columns:
                df[col] = 0.0
        
        # 向量化计算技术指标
        df = self._calculate_indicators(df)
        
        # 缓存处理结果
        with self._lock:
            self._processed_data[cache_key] = df
        
        return df
    
    def _calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        向量化计算技术指标
        
        Args:
            df: 原始数据
            
        Returns:
            带有技术指标的数据
        """
        # 计算简单移动平均线
        if len(df) > 5:
            df['ma5'] = df['close'].rolling(window=5).mean()
        if len(df) > 10:
            df['ma10'] = df['close'].rolling(window=10).mean()
        if len(df) > 20:
            df['ma20'] = df['close'].rolling(window=20).mean()
        
        # 计算收益率
        df['return'] = df['close'].pct_change()
        
        # 计算成交量变化
        df['volume_change'] = df['volume'].pct_change()
        
        # 计算波动率
        if len(df) > 5:
            df['volatility'] = df['return'].rolling(window=5).std()
        
        return df
    
    def load_data_batch(self, codes: List[str], data_fetcher) -> Dict[str, pd.DataFrame]:
        """
        批量加载数据
        
        Args:
            codes: 股票代码列表
            data_fetcher: 数据获取器
            
        Returns:
            数据字典
        """
        logger.info(f"开始批量加载 {len(codes)} 只股票数据...")
        
        data_dict = {}
        with ThreadPoolExecutor(max_workers=min(8, len(codes))) as executor:
            futures = {executor.submit(self._load_single_stock, code, data_fetcher): code 
                      for code in codes}
            
            for future in futures:
                code = futures[future]
                try:
                    df = future.result()
                    if not df.empty:
                        data_dict[code] = df
                except Exception as e:
                    logger.error("加载 %s 数据失败: %s", code, e)
        
        logger.info(f"批量加载完成，成功加载 {len(data_dict)} 只股票数据")
        return data_dict
    
    def _load_single_stock(self, code: str, data_fetcher) -> pd.DataFrame:
        """
        加载单只股票的数据
        
        Args:
            code: 股票代码
            data_fetcher: 数据获取器
            
        Returns:
            数据
        """
        # 检查缓存
        cache_key = f"{code}_raw"
        if cache_key in self._data_cache:
            return self._data_cache[cache_key]
        
        # 加载数据
        df = data_fetcher.get_daily(code, days=100)
        
        # 缓存数据
        if not df.empty:
            with self._lock:
                self._data_cache[cache_key] = df
        
        return df
    
    def optimize_data_for_backtest(self, data_dict: Dict[str, pd.DataFrame]) -> Dict[str, pd.DataFrame]:
        """
        优化数据用于回测
        
        Args:
            data_dict: 数据字典
            
        Returns:
            优化后的数据字典
        """
        logger.info("开始优化数据用于回测...")
        
        # 处理数据
        processed_dict = self.process_data_dict(data_dict)
        
        # 进一步优化数据结构
        optimized_dict = {}
        for code, df in processed_dict.items():
            # 只保留必要的列
            required_columns = ["open", "high", "low", "close", "volume"]
            df = df[required_columns]
            
            # 确保数据类型正确
            df = df.astype({
                "open": np.float64,
                "high": np.float64,
                "low": np.float64,
                "close": np.float64,
                "volume": np.float64
            })
            
            optimized_dict[code] = df
        
        logger.info("数据优化完成")
        return optimized_dict
    
    def clear_cache(self):
        """
        清除缓存
        """
        with self._lock:
            self._data_cache.clear()
            self._processed_data.clear()
        logger.info("缓存已清除")
    
    def get_cache_size(self) -> Dict[str, int]:
        """
        获取缓存大小
        
        Returns:
            缓存大小信息
        """
        with self._lock:
            return {
                "raw_data_cache": len(self._data_cache),
                "processed_data_cache": len(self._processed_data)
            }


# 全局数据处理器实例
_optimized_data_processor = None


def get_optimized_data_processor() -> OptimizedDataProcessor:
    """
    获取优化的数据处理器实例
    
    Returns:
        数据处理器实例
    """
    global _optimized_data_processor
    if _optimized_data_processor is None:
        _optimized_data_processor = OptimizedDataProcessor()
    return _optimized_data_processor
