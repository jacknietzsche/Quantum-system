"""
core.performance_benchmark — 性能基准测试模块
==================================
负责建立性能基准测试体系，量化优化前后的关键指标

设计原则:
  - 全面的性能指标
  - 可重复的测试方法
  - 详细的测试报告
  - 量化的性能对比
"""

import os
import time
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any

import pandas as pd
import numpy as np

from core.data import UnifiedDataFetcher
from backtest_system.backtest_engine import BacktestEngine
from backtest_system.optimized_backtest_system import get_optimized_backtest_system

logger = logging.getLogger(__name__)


class PerformanceBenchmark:
    """
    性能基准测试
    
    负责测试和比较优化前后的回测系统性能
    """
    
    def __init__(self):
        """
        初始化性能基准测试
        """
        self._results = []
        self._benchmark_results = []
        logger.info("PerformanceBenchmark 初始化完成")
    
    def run_benchmark(
        self,
        codes: List[str],
        existing_strategy: Any = None,
        n_runs: int = 3,
        initial_cash: float = 1000000.0,
    ) -> Dict[str, Any]:
        """
        运行性能基准测试
        
        Args:
            codes: 股票代码列表
            existing_strategy: 策略实例
            n_runs: 运行次数
            initial_cash: 初始资金
            
        Returns:
            基准测试结果
        """
        logger.info("开始性能基准测试，代码数量: {len(codes)}, 运行次数: %s", n_runs)
        
        # 加载数据
        fetcher = UnifiedDataFetcher()
        data_dict = {}
        for code in codes:
            df = fetcher.get_daily(code, days=100)
            if not df.empty:
                data_dict[code] = df
        
        if not data_dict:
            logger.error("没有获取到测试数据")
            return {}
        
        logger.info(f"获取到 {len(data_dict)} 只股票的测试数据")
        
        # 测试原始回测系统
        original_results = []
        for i in range(n_runs):
            logger.info("运行原始回测系统，第 {i+1}/%s 次", n_runs)
            start_time = time.time()
            
            engine = BacktestEngine()
            result = engine.run_backtest(
                existing_strategy=existing_strategy,
                data_dict=data_dict,
                initial_cash=initial_cash,
            )
            
            end_time = time.time()
            execution_time = end_time - start_time
            
            original_results.append({
                "run": i+1,
                "execution_time": execution_time,
                "final_value": result.get('stats', {}).get('final_value', 0),
                "total_return": result.get('stats', {}).get('total_return', 0),
                "sharpe_ratio": result.get('stats', {}).get('sharpe_ratio', 0),
            })
        
        # 测试优化回测系统
        optimized_results = []
        for i in range(n_runs):
            logger.info("运行优化回测系统，第 {i+1}/%s 次", n_runs)
            start_time = time.time()
            
            system = get_optimized_backtest_system()
            result = system.run_backtest(
                existing_strategy=existing_strategy,
                data_dict=data_dict,
                initial_cash=initial_cash,
            )
            
            end_time = time.time()
            execution_time = end_time - start_time
            
            optimized_results.append({
                "run": i+1,
                "execution_time": execution_time,
                "final_value": result.get('stats', {}).get('final_value', 0),
                "total_return": result.get('stats', {}).get('total_return', 0),
                "sharpe_ratio": result.get('stats', {}).get('sharpe_ratio', 0),
            })
        
        # 计算统计数据
        original_stats = self._calculate_stats(original_results)
        optimized_stats = self._calculate_stats(optimized_results)
        
        # 计算性能提升
        performance_improvement = self._calculate_improvement(original_stats, optimized_stats)
        
        # 生成测试报告
        report = {
            "test_date": datetime.now().isoformat(),
            "codes": codes,
            "n_runs": n_runs,
            "initial_cash": initial_cash,
            "original_stats": original_stats,
            "optimized_stats": optimized_stats,
            "performance_improvement": performance_improvement,
            "original_results": original_results,
            "optimized_results": optimized_results,
        }
        
        # 保存结果
        self._results.append(report)
        
        # 生成报告文件
        self._generate_report(report)
        
        logger.info("性能基准测试完成")
        return report
    
    def _calculate_stats(self, results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        计算统计数据
        
        Args:
            results: 测试结果列表
            
        Returns:
            统计数据
        """
        execution_times = [r['execution_time'] for r in results]
        final_values = [r['final_value'] for r in results]
        total_returns = [r['total_return'] for r in results]
        sharpe_ratios = [r['sharpe_ratio'] for r in results]
        
        return {
            "mean_execution_time": np.mean(execution_times),
            "std_execution_time": np.std(execution_times),
            "min_execution_time": np.min(execution_times),
            "max_execution_time": np.max(execution_times),
            "mean_final_value": np.mean(final_values),
            "mean_total_return": np.mean(total_returns),
            "mean_sharpe_ratio": np.mean(sharpe_ratios),
        }
    
    def _calculate_improvement(self, original_stats: Dict[str, Any], optimized_stats: Dict[str, Any]) -> Dict[str, Any]:
        """
        计算性能提升
        
        Args:
            original_stats: 原始系统统计数据
            optimized_stats: 优化系统统计数据
            
        Returns:
            性能提升数据
        """
        return {
            "execution_time_improvement": ((original_stats['mean_execution_time'] - optimized_stats['mean_execution_time']) / original_stats['mean_execution_time']) * 100,
            "final_value_diff": optimized_stats['mean_final_value'] - original_stats['mean_final_value'],
            "total_return_diff": optimized_stats['mean_total_return'] - original_stats['mean_total_return'],
            "sharpe_ratio_diff": optimized_stats['mean_sharpe_ratio'] - original_stats['mean_sharpe_ratio'],
        }
    
    def _generate_report(self, report: Dict[str, Any]):
        """
        生成测试报告
        
        Args:
            report: 测试报告数据
        """
        report_name = f"performance_benchmark_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        report_path = f"{report_name}.txt"
        
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write("=====================================\n")
            f.write("性能基准测试报告\n")
            f.write("=====================================\n")
            f.write(f"测试时间: {report['test_date']}\n")
            f.write(f"测试股票数量: {len(report['codes'])}\n")
            f.write(f"运行次数: {report['n_runs']}\n")
            f.write(f"初始资金: {report['initial_cash']:.2f}\n")
            f.write("\n原始回测系统统计:\n")
            f.write("-" * 80 + "\n")
            f.write(f"平均执行时间: {report['original_stats']['mean_execution_time']:.2f}秒\n")
            f.write(f"执行时间标准差: {report['original_stats']['std_execution_time']:.2f}秒\n")
            f.write(f"最小执行时间: {report['original_stats']['min_execution_time']:.2f}秒\n")
            f.write(f"最大执行时间: {report['original_stats']['max_execution_time']:.2f}秒\n")
            f.write(f"平均最终资金: {report['original_stats']['mean_final_value']:.2f}\n")
            f.write(f"平均总收益率: {report['original_stats']['mean_total_return']:.2f}%\n")
            f.write(f"平均夏普比率: {report['original_stats']['mean_sharpe_ratio']:.4f}\n")
            f.write("\n优化回测系统统计:\n")
            f.write("-" * 80 + "\n")
            f.write(f"平均执行时间: {report['optimized_stats']['mean_execution_time']:.2f}秒\n")
            f.write(f"执行时间标准差: {report['optimized_stats']['std_execution_time']:.2f}秒\n")
            f.write(f"最小执行时间: {report['optimized_stats']['min_execution_time']:.2f}秒\n")
            f.write(f"最大执行时间: {report['optimized_stats']['max_execution_time']:.2f}秒\n")
            f.write(f"平均最终资金: {report['optimized_stats']['mean_final_value']:.2f}\n")
            f.write(f"平均总收益率: {report['optimized_stats']['mean_total_return']:.2f}%\n")
            f.write(f"平均夏普比率: {report['optimized_stats']['mean_sharpe_ratio']:.4f}\n")
            f.write("\n性能提升:\n")
            f.write("-" * 80 + "\n")
            f.write(f"执行时间提升: {report['performance_improvement']['execution_time_improvement']:.2f}%\n")
            f.write(f"最终资金差异: {report['performance_improvement']['final_value_diff']:.2f}\n")
            f.write(f"总收益率差异: {report['performance_improvement']['total_return_diff']:.2f}%\n")
            f.write(f"夏普比率差异: {report['performance_improvement']['sharpe_ratio_diff']:.4f}\n")
            f.write("\n详细测试结果:\n")
            f.write("-" * 80 + "\n")
            f.write("原始回测系统:\n")
            for i, result in enumerate(report['original_results']):
                f.write(f"Run {i+1}: 执行时间={result['execution_time']:.2f}秒, 最终资金={result['final_value']:.2f}, 总收益率={result['total_return']:.2f}%, 夏普比率={result['sharpe_ratio']:.4f}\n")
            f.write("\n优化回测系统:\n")
            for i, result in enumerate(report['optimized_results']):
                f.write(f"Run {i+1}: 执行时间={result['execution_time']:.2f}秒, 最终资金={result['final_value']:.2f}, 总收益率={result['total_return']:.2f}%, 夏普比率={result['sharpe_ratio']:.4f}\n")
        
        logger.info("性能基准测试报告已生成: %s", report_path)
    
    def get_results(self) -> List[Dict[str, Any]]:
        """
        获取测试结果
        
        Returns:
            测试结果列表
        """
        return self._results


# 全局性能基准测试实例
_performance_benchmark = None


def get_performance_benchmark() -> PerformanceBenchmark:
    """
    获取性能基准测试实例
    
    Returns:
        性能基准测试实例
    """
    global _performance_benchmark
    if _performance_benchmark is None:
        _performance_benchmark = PerformanceBenchmark()
    return _performance_benchmark


def run_performance_benchmark(
    codes: List[str],
    existing_strategy: Any = None,
    n_runs: int = 3,
    initial_cash: float = 1000000.0,
) -> Dict[str, Any]:
    """
    运行性能基准测试
    
    Args:
        codes: 股票代码列表
        existing_strategy: 策略实例
        n_runs: 运行次数
        initial_cash: 初始资金
        
    Returns:
        基准测试结果
    """
    benchmark = get_performance_benchmark()
    return benchmark.run_benchmark(
        codes=codes,
        existing_strategy=existing_strategy,
        n_runs=n_runs,
        initial_cash=initial_cash,
    )
