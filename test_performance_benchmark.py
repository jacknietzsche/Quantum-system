"""
测试性能基准
==================================
运行性能基准测试，量化优化前后的关键指标
"""

import os
import sys

from core.logging_config import setup_logging, get_logger
setup_logging()
logger = get_logger(__name__)

from core.performance_benchmark import run_performance_benchmark


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


def main():
    """
    主函数
    """
    logger.info("开始性能基准测试...")
    
    try:
        # 测试股票代码
        codes = ['000001', '000002', '000004', '000006', '000007', '000008', '000009', '000010', '000011', '000012']
        
        # 创建测试策略
        strategy = TestStrategy()
        
        # 运行性能基准测试
        report = run_performance_benchmark(
            codes=codes,
            existing_strategy=strategy,
            n_runs=3,
            initial_cash=1000000.0,
        )
        
        # 打印关键结果
        logger.info("\n==================================")
        logger.info("性能基准测试结果")
        logger.info("==================================")
        logger.info(f"测试股票数量: {len(codes)}")
        logger.info(f"运行次数: {report['n_runs']}")
        logger.info(f"初始资金: {report['initial_cash']:.2f}")
        logger.info("\n原始回测系统:")
        logger.info(f"平均执行时间: {report['original_stats']['mean_execution_time']:.2f}秒")
        logger.info(f"平均最终资金: {report['original_stats']['mean_final_value']:.2f}")
        logger.info(f"平均总收益率: {report['original_stats']['mean_total_return']:.2f}%")
        logger.info(f"平均夏普比率: {report['original_stats']['mean_sharpe_ratio']:.4f}")
        logger.info("\n优化回测系统:")
        logger.info(f"平均执行时间: {report['optimized_stats']['mean_execution_time']:.2f}秒")
        logger.info(f"平均最终资金: {report['optimized_stats']['mean_final_value']:.2f}")
        logger.info(f"平均总收益率: {report['optimized_stats']['mean_total_return']:.2f}%")
        logger.info(f"平均夏普比率: {report['optimized_stats']['mean_sharpe_ratio']:.4f}")
        logger.info("\n性能提升:")
        logger.info(f"执行时间提升: {report['performance_improvement']['execution_time_improvement']:.2f}%")
        logger.info(f"最终资金差异: {report['performance_improvement']['final_value_diff']:.2f}")
        logger.info(f"总收益率差异: {report['performance_improvement']['total_return_diff']:.2f}%")
        logger.info(f"夏普比率差异: {report['performance_improvement']['sharpe_ratio_diff']:.4f}")
        
        logger.info("\n性能基准测试完成！")
        
    except Exception as e:
        logger.error(f"性能基准测试失败: {e}")
        import traceback
        logger.error(traceback.format_exc())


if __name__ == "__main__":
    main()
