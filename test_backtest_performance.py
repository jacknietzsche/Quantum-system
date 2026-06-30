"""
测试回测系统性能
==================================
分析回测系统的性能瓶颈
"""

import os
import sys
from datetime import datetime

from core.logging_config import setup_logging, get_logger
setup_logging()
logger = get_logger(__name__)

from core.data import UnifiedDataFetcher
from backtest_system.backtest_engine import BacktestEngine
from core.performance_analyzer import analyze_performance


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
        # 简单策略：每天买入前3只股票
        stocks = list(data['stocks'].keys())[:3]
        return stocks
    
    def get_sell_signals(self, date, data, portfolio):
        """
        获取卖出信号
        """
        # 简单策略：卖出所有持仓
        return list(portfolio.keys())


def run_backtest():
    """
    运行回测
    """
    # 获取数据
    fetcher = UnifiedDataFetcher()
    
    # 获取测试数据
    codes = ['000001', '000002', '000004', '000006', '000007']
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
    
    # 创建回测引擎
    engine = BacktestEngine()
    
    # 运行回测
    result = engine.run_backtest(
        existing_strategy=strategy,
        data_dict=data_dict
    )
    
    logger.info(f"回测完成，最终资金: {result['stats']['final_value']:.2f}")
    return result


def main():
    """
    主函数
    """
    logger.info("开始分析回测系统性能...")
    
    try:
        # 分析回测性能
        from core.performance_analyzer import get_performance_analyzer
        analyzer = get_performance_analyzer()
        
        analyzer.start()
        result = run_backtest()
        analyzer.stop()
        
        stats = analyzer.get_stats()
        
        # 生成性能报告
        report_path = analyzer.generate_report(stats, "backtest_performance_report")
        logger.info(f"性能分析报告已生成: {report_path}")
        
        # 打印性能统计信息
        logger.info("\n性能统计信息:")
        logger.info(f"执行时间: {stats['execution_time']:.2f}秒")
        logger.info(f"内存使用变化: {stats['memory_used']:.2f}MB")
        logger.info(f"CPU使用变化: {stats['cpu_used']:.2f}%")
        
        logger.info("\n热点函数:")
        for i, func in enumerate(stats['hot_functions'], 1):
            logger.info(f"{i}. {func['filename']}:{func['lineno']} {func['function']} - 累计时间: {func['cumtime']:.4f}秒")
        
        logger.info("回测系统性能分析完成！")
    except Exception as e:
        logger.error(f"性能分析失败: {e}")
        import traceback
        logger.error(traceback.format_exc())


if __name__ == "__main__":
    main()
