"""
测试优化后的系统性能
==================================
测试数据存储架构优化后的性能
"""

import os
import sys
from datetime import datetime

from core.logging_config import setup_logging, get_logger
setup_logging()
logger = get_logger(__name__)

from core.performance_tester import get_performance_tester
from core.db_manager import get_db_manager


def main():
    """主测试函数"""
    logger.info("开始测试优化后的系统性能...")
    
    # 获取数据库管理器
    db_manager = get_db_manager()
    
    # 获取股票列表
    logger.info("获取股票列表...")
    stock_list = db_manager.get_stock_list()
    codes = stock_list['symbol'].tolist()
    
    if not codes:
        logger.error("没有股票数据，请先更新数据")
        return
    
    logger.info(f"获取到 {len(codes)} 只股票")
    
    # 取前20只股票进行测试
    test_codes = codes[:20]
    logger.info(f"使用前 {len(test_codes)} 只股票进行测试: {test_codes[:5]}...")
    
    # 获取性能测试器
    tester = get_performance_tester()
    
    # 运行综合性能测试
    results = tester.run_comprehensive_test(test_codes)
    
    # 打印测试结果
    logger.info("\n测试结果摘要:")
    logger.info(f"测试时间: {results['timestamp']}")
    logger.info(f"测试股票数: {results['stock_count']}")
    
    if 'single_query' in results['tests']:
        test = results['tests']['single_query']
        logger.info(f"单股票查询平均响应时间: {test['avg_time']:.4f}秒")
    
    if 'batch_query' in results['tests']:
        test = results['tests']['batch_query']
        logger.info(f"批量查询平均响应时间: {test['avg_time']:.4f}秒")
    
    if 'concurrent' in results['tests']:
        test = results['tests']['concurrent']
        logger.info(f"并发测试吞吐量: {test['throughput']:.2f}次/秒")
        logger.info(f"并发测试成功率: {test['success_rate']:.2f}%")
    
    if 'cache_performance' in results['tests']:
        test = results['tests']['cache_performance']
        logger.info(f"缓存命中率: {test['cache_hit_rate']:.2f}%")
    
    logger.info("性能测试完成！")


if __name__ == "__main__":
    main()
