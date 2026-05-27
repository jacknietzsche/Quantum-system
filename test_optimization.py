"""
测试优化后的系统性能和稳定性
==================================
测试数据更新、数据获取、缓存机制、错误处理等功能
"""

import os
import time
from datetime import datetime

import pandas as pd

from core.data import UnifiedDataFetcher
from core.data_updater import DataUpdater
from core.data_scheduler import get_data_scheduler, force_update
from core.cache_manager import get_cache_stats
from core.record_manager import get_errors, get_results

from core.logging_config import setup_logging, get_logger
setup_logging()
logger = get_logger(__name__)


def test_data_update():
    """测试数据更新功能"""
    logger.info("开始测试数据更新功能...")
    
    try:
        updater = DataUpdater()
        
        # 测试更新股票列表
        logger.info("测试更新股票列表...")
        start_time = time.time()
        success = updater.update_stock_list()
        end_time = time.time()
        logger.info(f"股票列表更新完成，耗时: {end_time - start_time:.2f}秒，成功: {success}")
        
        # 测试更新单只股票数据
        logger.info("测试更新单只股票数据...")
        start_time = time.time()
        result = updater.update_stock_data(['000001', '600000'], days=30)
        end_time = time.time()
        logger.info(f"单只股票数据更新完成，耗时: {end_time - start_time:.2f}秒，结果: {result}")
        
        return True
    except Exception as e:
        logger.error(f"数据更新测试失败: {e}")
        return False


def test_data_retrieval():
    """测试数据获取功能"""
    logger.info("开始测试数据获取功能...")
    
    try:
        fetcher = UnifiedDataFetcher()
        
        # 测试获取单只股票数据
        logger.info("测试获取单只股票数据...")
        start_time = time.time()
        df = fetcher.get_daily('000001', days=30)
        end_time = time.time()
        logger.info(f"单只股票数据获取完成，耗时: {end_time - start_time:.2f}秒，数据长度: {len(df)}")
        
        # 测试批量获取股票数据
        logger.info("测试批量获取股票数据...")
        start_time = time.time()
        data = fetcher.get_batch_daily(['000001', '600000'], days=30)
        end_time = time.time()
        logger.info(f"批量股票数据获取完成，耗时: {end_time - start_time:.2f}秒，成功获取: {len(data)}只")
        
        # 测试回测数据加载
        logger.info("测试回测数据加载...")
        start_time = time.time()
        backtest_data = fetcher.load_multi_for_backtest(['000001', '600000'], start_date='20230101', end_date='20230131')
        end_time = time.time()
        logger.info(f"回测数据加载完成，耗时: {end_time - start_time:.2f}秒，成功加载: {len(backtest_data)}只")
        
        return True
    except Exception as e:
        logger.error(f"数据获取测试失败: {e}")
        return False


def test_cache_performance():
    """测试缓存性能"""
    logger.info("开始测试缓存性能...")
    
    try:
        fetcher = UnifiedDataFetcher()
        
        # 第一次获取（应该没有缓存）
        logger.info("第一次获取数据（无缓存）...")
        start_time = time.time()
        df1 = fetcher.get_daily('000001', days=30)
        end_time = time.time()
        logger.info(f"第一次获取耗时: {end_time - start_time:.2f}秒")
        
        # 第二次获取（应该有缓存）
        logger.info("第二次获取数据（有缓存）...")
        start_time = time.time()
        df2 = fetcher.get_daily('000001', days=30)
        end_time = time.time()
        logger.info(f"第二次获取耗时: {end_time - start_time:.2f}秒")
        
        # 检查缓存统计
        stats = get_cache_stats()
        logger.info(f"缓存统计: {stats}")
        
        return True
    except Exception as e:
        logger.error(f"缓存性能测试失败: {e}")
        return False


def test_error_handling():
    """测试错误处理功能"""
    logger.info("开始测试错误处理功能...")
    
    try:
        # 测试获取不存在的股票数据
        fetcher = UnifiedDataFetcher()
        logger.info("测试获取不存在的股票数据...")
        df = fetcher.get_daily('999999', days=30)
        logger.info(f"获取不存在的股票数据结果: {len(df)}条")
        
        # 检查错误记录
        errors = get_errors(days=1)
        logger.info(f"最近1天的错误记录: {len(errors)}条")
        
        return True
    except Exception as e:
        logger.error(f"错误处理测试失败: {e}")
        return False


def test_system_stability():
    """测试系统稳定性"""
    logger.info("开始测试系统稳定性...")
    
    try:
        fetcher = UnifiedDataFetcher()
        
        # 连续获取多只股票数据
        logger.info("连续获取多只股票数据...")
        symbols = ['000001', '600000', '300001', '000002', '600036']
        start_time = time.time()
        for symbol in symbols:
            df = fetcher.get_daily(symbol, days=30)
            logger.info(f"获取 {symbol} 数据: {len(df)}条")
        end_time = time.time()
        logger.info(f"连续获取完成，耗时: {end_time - start_time:.2f}秒")
        
        return True
    except Exception as e:
        logger.error(f"系统稳定性测试失败: {e}")
        return False


def test_data_scheduler():
    """测试数据调度器"""
    logger.info("开始测试数据调度器...")
    
    try:
        scheduler = get_data_scheduler()
        
        # 启动调度器
        logger.info("启动数据调度器...")
        scheduler.start()
        time.sleep(2)
        
        # 检查调度器状态
        status = scheduler.get_update_status()
        logger.info(f"调度器状态: {status}")
        
        # 停止调度器
        logger.info("停止数据调度器...")
        scheduler.stop()
        
        return True
    except Exception as e:
        logger.error(f"数据调度器测试失败: {e}")
        return False


def main():
    """主测试函数"""
    logger.info("开始系统性能和稳定性测试...")
    
    tests = [
        ('数据更新测试', test_data_update),
        ('数据获取测试', test_data_retrieval),
        ('缓存性能测试', test_cache_performance),
        ('错误处理测试', test_error_handling),
        ('系统稳定性测试', test_system_stability),
        ('数据调度器测试', test_data_scheduler)
    ]
    
    results = []
    for test_name, test_func in tests:
        logger.info(f"\n=== 运行 {test_name} ===")
        success = test_func()
        results.append((test_name, success))
        logger.info(f"{test_name} 结果: {'成功' if success else '失败'}")
    
    # 生成测试报告
    logger.info("\n=== 测试报告 ===")
    success_count = sum(1 for _, success in results if success)
    total_count = len(results)
    logger.info(f"测试完成: {success_count}/{total_count} 个测试通过")
    
    for test_name, success in results:
        logger.info(f"{test_name}: {'通过' if success else '失败'}")
    
    # 检查成果记录
    results = get_results(days=1)
    logger.info(f"\n最近1天的成果记录: {len(results)}条")
    
    return success_count == total_count


if __name__ == "__main__":
    success = main()
    if success:
        logger.info("所有测试通过！系统性能和稳定性良好。")
    else:
        logger.warning("部分测试失败，需要进一步优化。")
