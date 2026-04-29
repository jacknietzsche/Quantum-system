"""
简单性能测试脚本
==================================
测试性能分析工具是否正常工作
"""

import time
import logging

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

from core.performance_analyzer import get_performance_analyzer


def test_function():
    """
    测试函数
    """
    logger.info("开始测试函数")
    
    # 模拟一些计算密集型操作
    result = 0
    for i in range(1000000):
        result += i
    
    # 模拟一些I/O操作
    time.sleep(0.5)
    
    logger.info(f"测试函数完成，结果: {result}")
    return result


def main():
    """
    主函数
    """
    logger.info("开始简单性能测试...")
    
    try:
        analyzer = get_performance_analyzer()
        
        analyzer.start()
        result = test_function()
        analyzer.stop()
        
        stats = analyzer.get_stats()
        
        # 生成性能报告
        report_path = analyzer.generate_report(stats, "simple_performance_report")
        logger.info(f"性能分析报告已生成: {report_path}")
        
        # 打印性能统计信息
        logger.info("\n性能统计信息:")
        logger.info(f"执行时间: {stats['execution_time']:.2f}秒")
        logger.info(f"内存使用变化: {stats['memory_used']:.2f}MB")
        logger.info(f"CPU使用变化: {stats['cpu_used']:.2f}%")
        
        logger.info("\n热点函数:")
        for i, func in enumerate(stats['hot_functions'], 1):
            logger.info(f"{i}. {func['filename']}:{func['lineno']} {func['function']} - 累计时间: {func['cumtime']:.4f}秒")
        
        logger.info("简单性能测试完成！")
    except Exception as e:
        logger.error(f"性能分析失败: {e}")
        import traceback
        logger.error(traceback.format_exc())


if __name__ == "__main__":
    main()
