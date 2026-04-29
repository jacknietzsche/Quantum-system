"""
测试大数据集性能
==================================
测试优化回测系统在大数据集上的性能表现
"""

import os
import sys
import logging
import time

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

from core.data import UnifiedDataFetcher
from backtest_system.backtest_engine import BacktestEngine
from backtest_system.optimized_backtest_system import get_optimized_backtest_system


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
        # 简单策略：每天买入前10只股票
        stocks = list(data['stocks'].keys())[:10]
        return stocks
    
    def get_sell_signals(self, date, data, portfolio):
        """
        获取卖出信号
        """
        # 简单策略：卖出所有持仓
        return list(portfolio.keys())


def run_original_backtest(data_dict, strategy, initial_cash=1000000.0):
    """
    运行原始回测
    """
    logger.info("开始运行原始回测系统...")
    start_time = time.time()
    
    engine = BacktestEngine()
    result = engine.run_backtest(
        existing_strategy=strategy,
        data_dict=data_dict,
        initial_cash=initial_cash,
    )
    
    end_time = time.time()
    execution_time = end_time - start_time
    
    logger.info(f"原始回测完成，执行时间: {execution_time:.2f}秒, 最终资金: {result.get('stats', {}).get('final_value', 0):.2f}")
    return execution_time, result


def run_optimized_backtest(data_dict, strategy, initial_cash=1000000.0):
    """
    运行优化回测
    """
    logger.info("开始运行优化回测系统...")
    start_time = time.time()
    
    system = get_optimized_backtest_system()
    result = system.run_backtest(
        existing_strategy=strategy,
        data_dict=data_dict,
        initial_cash=initial_cash,
    )
    
    end_time = time.time()
    execution_time = end_time - start_time
    
    logger.info(f"优化回测完成，执行时间: {execution_time:.2f}秒, 最终资金: {result.get('stats', {}).get('final_value', 0):.2f}")
    return execution_time, result


def main():
    """
    主函数
    """
    logger.info("开始测试大数据集性能...")
    
    try:
        # 测试股票代码（更多股票）
        codes = [
            '000001', '000002', '000004', '000006', '000007', '000008', '000009', '000010', '000011', '000012',
            '000014', '000016', '000017', '000018', '000019', '000020', '000021', '000022', '000023', '000025',
            '000026', '000027', '000028', '000029', '000030', '000031', '000032', '000033', '000034', '000035'
        ]
        
        # 加载数据
        logger.info(f"开始加载 {len(codes)} 只股票数据...")
        fetcher = UnifiedDataFetcher()
        data_dict = {}
        for code in codes:
            df = fetcher.get_daily(code, days=100)
            if not df.empty:
                data_dict[code] = df
        
        if not data_dict:
            logger.error("没有获取到测试数据")
            return
        
        logger.info(f"成功加载 {len(data_dict)} 只股票数据")
        
        # 创建测试策略
        strategy = TestStrategy()
        
        # 运行原始回测
        original_time, original_result = run_original_backtest(data_dict, strategy)
        
        # 运行优化回测
        optimized_time, optimized_result = run_optimized_backtest(data_dict, strategy)
        
        # 计算性能提升
        performance_improvement = ((original_time - optimized_time) / original_time) * 100
        
        # 打印结果
        logger.info("\n==================================")
        logger.info("大数据集性能测试结果")
        logger.info("==================================")
        logger.info(f"测试股票数量: {len(data_dict)}")
        logger.info(f"原始回测系统执行时间: {original_time:.2f}秒")
        logger.info(f"优化回测系统执行时间: {optimized_time:.2f}秒")
        logger.info(f"性能提升: {performance_improvement:.2f}%")
        logger.info(f"原始回测系统最终资金: {original_result.get('stats', {}).get('final_value', 0):.2f}")
        logger.info(f"优化回测系统最终资金: {optimized_result.get('stats', {}).get('final_value', 0):.2f}")
        logger.info(f"原始回测系统总收益率: {original_result.get('stats', {}).get('total_return', 0):.2f}%")
        logger.info(f"优化回测系统总收益率: {optimized_result.get('stats', {}).get('total_return', 0):.2f}%")
        
        logger.info("\n大数据集性能测试完成！")
        
    except Exception as e:
        logger.error(f"性能测试失败: {e}")
        import traceback
        logger.error(traceback.format_exc())


if __name__ == "__main__":
    main()
