"""
optimized_backtest_system — 整合的优化回测系统
============================================
提供高性能的回测系统，整合所有优化组件

优化特性:
    - 向量化计算，减少 Python 循环
    - 并行处理，提高数据处理速度
    - 缓存机制，避免重复计算
    - 数据预处理，减少回测过程中的计算量
    - 内存优化，减少内存使用
    - 代码结构优化，消除冗余计算和资源浪费
"""

import logging
from typing import Dict, List, Optional, Any

import backtrader as bt
import pandas as pd
import numpy as np

from .config import BacktestConfig
from .optimized_backtest_engine import OptimizedBacktestEngine
from .optimized_strategy_adapter import (
    OptimizedStrategyAdapter,
    OptimizedStrategyObserver,
    OptimizedOrderManager,
)
from core.optimized_data_processor import get_optimized_data_processor

logger = logging.getLogger(__name__)


class OptimizedBacktestSystem:
    """
    优化回测系统 —— 整合所有优化组件

    用法:
        system = OptimizedBacktestSystem()
        result = system.run_backtest(
            existing_strategy=my_strategy,
            codes=['000001', '000002', '000004'],
        )
    """

    def __init__(self, config: Optional[BacktestConfig] = None):
        """
        初始化回测系统

        Args:
            config: 回测配置，默认使用 BacktestConfig()
        """
        self.config = config or BacktestConfig()
        self._backtest_engine = OptimizedBacktestEngine(config)
        self._data_processor = get_optimized_data_processor()
        
        logger.info("OptimizedBacktestSystem 初始化完成")

    def run_backtest(
        self,
        existing_strategy: Any = None,
        codes: Optional[List[str]] = None,
        data_dict: Optional[Dict[str, pd.DataFrame]] = None,
        benchmark: Optional[pd.DataFrame] = None,
        strategy_params: Optional[dict] = None,
        initial_cash: Optional[float] = None,
    ) -> dict:
        """
        执行回测

        Args:
            existing_strategy: 用户已有策略实例（需实现 get_buy_signals / get_sell_signals）
            codes: 股票代码列表
            data_dict: {股票代码: DataFrame} 行情数据（与 codes 二选一）
            benchmark: 基准指数数据（用于对比）
            strategy_params: 覆盖策略参数
            initial_cash: 初始资金（覆盖配置）

        Returns:
            回测结果字典，包含:
            - stats: 回测统计指标
            - trades: 交易记录
            - daily: 每日净值曲线
            - portfolio: 每日持仓快照
            - orders: 委托记录
        """
        # 加载数据
        if codes and not data_dict:
            from core.data import UnifiedDataFetcher
            fetcher = UnifiedDataFetcher()
            data_dict = self._data_processor.load_data_batch(codes, fetcher)
        
        if not data_dict:
            logger.error("没有数据可用于回测")
            return {}
        
        # 优化数据
        optimized_data = self._data_processor.optimize_data_for_backtest(data_dict)
        
        # 运行回测
        result = self._backtest_engine.run_backtest(
            existing_strategy=existing_strategy,
            data_dict=optimized_data,
            benchmark=benchmark,
            strategy_params=strategy_params,
            initial_cash=initial_cash,
        )
        
        # 清除缓存
        self.clear_cache()
        
        return result
    
    def run_benchmark(
        self,
        codes: List[str],
        initial_cash: Optional[float] = None,
    ) -> dict:
        """
        运行等权重基准策略
        
        Args:
            codes: 股票代码列表
            initial_cash: 初始资金
            
        Returns:
            基准回测结果
        """
        # 加载数据
        from core.data import UnifiedDataFetcher
        fetcher = UnifiedDataFetcher()
        data_dict = self._data_processor.load_data_batch(codes, fetcher)
        
        if not data_dict:
            logger.error("没有数据可用于基准回测")
            return {}
        
        # 优化数据
        optimized_data = self._data_processor.optimize_data_for_backtest(data_dict)
        
        # 运行基准回测
        result = self._backtest_engine.run_benchmark(
            data_dict=optimized_data,
            initial_cash=initial_cash,
        )
        
        # 清除缓存
        self.clear_cache()
        
        return result
    
    def optimize(
        self,
        param_ranges: dict,
        codes: List[str],
        existing_strategy: Any = None,
        n_runs: int = 100,
    ) -> pd.DataFrame:
        """
        参数优化

        Args:
            param_ranges: 参数范围 {参数名: [start, end, step]}
            codes: 股票代码列表
            existing_strategy: 策略实例
            n_runs: 最大运行次数

        Returns:
            优化结果 DataFrame
        """
        # 加载数据
        from core.data import UnifiedDataFetcher
        fetcher = UnifiedDataFetcher()
        data_dict = self._data_processor.load_data_batch(codes, fetcher)
        
        if not data_dict:
            logger.error("没有数据可用于参数优化")
            return pd.DataFrame()
        
        # 优化数据
        optimized_data = self._data_processor.optimize_data_for_backtest(data_dict)
        
        # 运行参数优化
        result = self._backtest_engine.optimize(
            param_ranges=param_ranges,
            data_dict=optimized_data,
            existing_strategy=existing_strategy,
            n_runs=n_runs,
        )
        
        # 清除缓存
        self.clear_cache()
        
        return result
    
    def clear_cache(self):
        """
        清除缓存
        """
        self._data_processor.clear_cache()
        logger.info("回测系统缓存已清除")
    
    def get_cache_size(self) -> Dict[str, int]:
        """
        获取缓存大小
        
        Returns:
            缓存大小信息
        """
        return self._data_processor.get_cache_size()


# 全局回测系统实例
_optimized_backtest_system = None


def get_optimized_backtest_system() -> OptimizedBacktestSystem:
    """
    获取优化回测系统实例
    
    Returns:
        回测系统实例
    """
    global _optimized_backtest_system
    if _optimized_backtest_system is None:
        _optimized_backtest_system = OptimizedBacktestSystem()
    return _optimized_backtest_system
