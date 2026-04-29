"""
测试回测系统优化性能
==================================
比较优化前后的回测系统性能，量化优化效果
"""

import os
import sys
import logging
import time
from datetime import datetime

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

from core.data import UnifiedDataFetcher
from backtest_system.backtest_engine import BacktestEngine
from backtest_system.optimized_backtest_engine import OptimizedBacktestEngine
from core.performance_analyzer import get_performance_analyzer


class TestStrategy:
    """
    测试策略类
    """
    
    def __init__(self, params=None):
        self.params = params or {}
    
    def get_buy_signals(self, date, data):
        """
        获取买入信号
        """
        # 简单策略：每天买入前5只股票
        stocks = list(data['stocks'].keys())[:5]
        return stocks
    
    def get_sell_signals(self, date, data, portfolio):
        """
        获取卖出信号
        """
        # 简单策略：卖出所有持仓
        return list(portfolio.keys())


def run_original_backtest(data_dict, strategy):
    """
    运行原始回测
    """
    logger.info("开始运行原始回测...")
    engine = BacktestEngine()
    result = engine.run_backtest(
        existing_strategy=strategy,
        data_dict=data_dict
    )
    logger.info(f"原始回测完成，最终资金: {result['stats']['final_value']:.2f}")
    return result


def run_optimized_backtest(data_dict, strategy):
    """
    运行优化回测
    """
    logger.info("开始运行优化回测...")
    engine = OptimizedBacktestEngine()
    result = engine.run_backtest(
        existing_strategy=strategy,
        data_dict=data_dict
    )
    logger.info(f"优化回测完成，最终资金: {result['stats']['final_value']:.2f}")
    return result


def main():
    """
    主函数
    """
    logger.info("开始测试回测系统优化性能...")
    
    try:
        # 获取数据
        fetcher = UnifiedDataFetcher()
        
        # 获取测试数据
        codes = ['000001', '000002', '000004', '000006', '000007', '000008', '000009', '000010', '000011', '000012']
        data_dict = {}
        for code in codes:
            df = fetcher.get_daily(code, days=100)
            if not df.empty:
                data_dict[code] = df
        
        if not data_dict:
            logger.error("没有获取到测试数据")
            return
        
        logger.info(f"获取到 {len(data_dict)} 只股票的测试数据")
        
        # 创建策略
        strategy = TestStrategy()
        
        # 初始化性能分析器
        analyzer = get_performance_analyzer()
        
        # 测试原始回测
        analyzer.start()
        start_time = time.time()
        original_result = run_original_backtest(data_dict, strategy)
        original_time = time.time() - start_time
        analyzer.stop()
        original_stats = analyzer.get_stats()
        original_report = analyzer.generate_report(original_stats, "original_backtest_performance")
        
        # 测试优化回测
        analyzer.start()
        start_time = time.time()
        optimized_result = run_optimized_backtest(data_dict, strategy)
        optimized_time = time.time() - start_time
        analyzer.stop()
        optimized_stats = analyzer.get_stats()
        optimized_report = analyzer.generate_report(optimized_stats, "optimized_backtest_performance")
        
        # 计算性能提升
        time_improvement = ((original_time - optimized_time) / original_time) * 100
        memory_improvement = ((original_stats['memory_used'] - optimized_stats['memory_used']) / original_stats['memory_used']) * 100 if original_stats['memory_used'] > 0 else 0
        
        # 打印性能对比
        logger.info("\n==================================")
        logger.info("回测系统性能对比")
        logger.info("==================================")
        logger.info(f"原始回测时间: {original_time:.2f}秒")
        logger.info(f"优化回测时间: {optimized_time:.2f}秒")
        logger.info(f"时间提升: {time_improvement:.2f}%")
        logger.info(f"原始回测内存使用: {original_stats['memory_used']:.2f}MB")
        logger.info(f"优化回测内存使用: {optimized_stats['memory_used']:.2f}MB")
        logger.info(f"内存提升: {memory_improvement:.2f}%")
        logger.info(f"原始回测性能报告: {original_report}")
        logger.info(f"优化回测性能报告: {optimized_report}")
        
        # 验证结果一致性
        original_final_value = original_result['stats']['final_value']
        optimized_final_value = optimized_result['stats']['final_value']
        value_diff = abs(original_final_value - optimized_final_value)
        value_diff_pct = (value_diff / original_final_value) * 100
        
        logger.info("\n==================================")
        logger.info("结果一致性验证")
        logger.info("==================================")
        logger.info(f"原始回测最终资金: {original_final_value:.2f}")
        logger.info(f"优化回测最终资金: {optimized_final_value:.2f}")
        logger.info(f"资金差异: {value_diff:.2f} ({value_diff_pct:.2f}%)")
        
        if value_diff_pct < 0.1:
            logger.info("结果一致性良好")
        else:
            logger.warning("结果存在较大差异，需要检查优化实现")
        
        logger.info("\n回测系统优化性能测试完成！")
        
    except Exception as e:
        logger.error(f"性能测试失败: {e}")
        import traceback
        logger.error(traceback.format_exc())


if __name__ == "__main__":
    main()
