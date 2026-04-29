"""
core.performance_tester — 性能测试工具模块
==================================
负责测试优化后的系统性能，包括查询响应时间、吞吐量、资源利用率等

设计原则:
  - 全面的性能测试指标
  - 可重复的测试方法
  - 详细的测试报告
  - 支持高并发测试
"""

import time
import threading
import psutil
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any
from concurrent.futures import ThreadPoolExecutor

import pandas as pd
import numpy as np

from core.db_manager import get_db_manager
from core.data_sharding import get_data_sharding_manager
from core.cache_manager import get_cache_stats

logger = logging.getLogger(__name__)


class PerformanceTester:
    """
    性能测试器
    
    负责测试优化后的系统性能
    """
    
    def __init__(self):
        """
        初始化性能测试器
        """
        self.db_manager = get_db_manager()
        self.sharding_manager = get_data_sharding_manager()
        self._lock = threading.RLock()
        logger.info("PerformanceTester 初始化完成")
    
    def test_query_response_time(self, code: str, days: int = 120, iterations: int = 10) -> Dict[str, Any]:
        """
        测试查询响应时间
        
        Args:
            code: 股票代码
            days: 获取天数
            iterations: 测试次数
            
        Returns:
            响应时间统计
        """
        times = []
        
        for i in range(iterations):
            start_time = time.time()
            df = self.db_manager.get_daily(code, days)
            end_time = time.time()
            times.append(end_time - start_time)
            logger.debug("查询 %s 第 {i+1} 次: {times[-1]:.4f}秒", code)
        
        times_array = np.array(times)
        
        return {
            'code': code,
            'days': days,
            'iterations': iterations,
            'min_time': float(times_array.min()),
            'max_time': float(times_array.max()),
            'avg_time': float(times_array.mean()),
            'std_time': float(times_array.std()),
            'total_time': float(times_array.sum())
        }
    
    def test_batch_query_performance(self, codes: List[str], days: int = 120, iterations: int = 5) -> Dict[str, Any]:
        """
        测试批量查询性能
        
        Args:
            codes: 股票代码列表
            days: 获取天数
            iterations: 测试次数
            
        Returns:
            批量查询性能统计
        """
        times = []
        results = []
        
        for i in range(iterations):
            start_time = time.time()
            data = self.db_manager.get_batch_daily(codes, days)
            end_time = time.time()
            times.append(end_time - start_time)
            results.append(len(data))
            logger.debug(f"批量查询第 {i+1} 次: {times[-1]:.4f}秒, 成功 {results[-1]}/{len(codes)}")
        
        times_array = np.array(times)
        results_array = np.array(results)
        
        return {
            'codes_count': len(codes),
            'days': days,
            'iterations': iterations,
            'min_time': float(times_array.min()),
            'max_time': float(times_array.max()),
            'avg_time': float(times_array.mean()),
            'std_time': float(times_array.std()),
            'total_time': float(times_array.sum()),
            'avg_success_count': float(results_array.mean())
        }
    
    def test_concurrent_performance(self, codes: List[str], concurrent_users: int = 10, iterations: int = 5) -> Dict[str, Any]:
        """
        测试并发性能
        
        Args:
            codes: 股票代码列表
            concurrent_users: 并发用户数
            iterations: 每个用户的测试次数
            
        Returns:
            并发性能统计
        """
        times = []
        errors = 0
        
        def worker(user_id):
            nonlocal errors
            # 每个线程创建自己的数据库管理器实例
            from core.db_manager import get_db_manager
            thread_db_manager = get_db_manager()
            
            for i in range(iterations):
                code = codes[i % len(codes)]
                start_time = time.time()
                try:
                    df = thread_db_manager.get_daily(code, 120)
                except Exception as e:
                    errors += 1
                    logger.error("用户 %s 第 {i+1} 次查询失败: %s", user_id, e)
                end_time = time.time()
                times.append(end_time - start_time)
                logger.debug("用户 %s 第 {i+1} 次查询: {times[-1]:.4f}秒", user_id)
        
        # 启动并发测试
        start_time = time.time()
        with ThreadPoolExecutor(max_workers=concurrent_users) as executor:
            executor.map(worker, range(concurrent_users))
        end_time = time.time()
        
        times_array = np.array(times)
        
        return {
            'concurrent_users': concurrent_users,
            'iterations_per_user': iterations,
            'total_queries': concurrent_users * iterations,
            'errors': errors,
            'success_rate': float((concurrent_users * iterations - errors) / (concurrent_users * iterations)),
            'min_time': float(times_array.min()),
            'max_time': float(times_array.max()),
            'avg_time': float(times_array.mean()),
            'std_time': float(times_array.std()),
            'total_time': float(end_time - start_time),
            'throughput': float((concurrent_users * iterations) / (end_time - start_time))
        }
    
    def test_resource_usage(self, codes: List[str], iterations: int = 10) -> Dict[str, Any]:
        """
        测试资源使用情况
        
        Args:
            codes: 股票代码列表
            iterations: 测试次数
            
        Returns:
            资源使用统计
        """
        cpu_usages = []
        memory_usages = []
        disk_usages = []
        
        process = psutil.Process()
        
        for i in range(iterations):
            # 记录测试前的资源使用
            cpu_before = process.cpu_percent(interval=0.1)
            memory_before = process.memory_info().rss / 1024 / 1024  # MB
            disk_before = psutil.disk_usage('.').used / 1024 / 1024  # MB
            
            # 执行查询
            code = codes[i % len(codes)]
            df = self.db_manager.get_daily(code, 120)
            
            # 记录测试后的资源使用
            cpu_after = process.cpu_percent(interval=0.1)
            memory_after = process.memory_info().rss / 1024 / 1024  # MB
            disk_after = psutil.disk_usage('.').used / 1024 / 1024  # MB
            
            cpu_usages.append(cpu_after - cpu_before)
            memory_usages.append(memory_after - memory_before)
            disk_usages.append(disk_after - disk_before)
            
            logger.debug(f"资源使用第 {i+1} 次: CPU {cpu_usages[-1]:.2f}%, 内存 {memory_usages[-1]:.2f}MB, 磁盘 {disk_usages[-1]:.2f}MB")
        
        cpu_array = np.array(cpu_usages)
        memory_array = np.array(memory_usages)
        disk_array = np.array(disk_usages)
        
        return {
            'iterations': iterations,
            'avg_cpu_usage': float(cpu_array.mean()),
            'max_cpu_usage': float(cpu_array.max()),
            'avg_memory_usage': float(memory_array.mean()),
            'max_memory_usage': float(memory_array.max()),
            'avg_disk_usage': float(disk_array.mean()),
            'max_disk_usage': float(disk_array.max())
        }
    
    def test_cache_performance(self, codes: List[str], iterations: int = 20) -> Dict[str, Any]:
        """
        测试缓存性能
        
        Args:
            codes: 股票代码列表
            iterations: 测试次数
            
        Returns:
            缓存性能统计
        """
        # 先清空缓存
        from core.cache_manager import clear_cache
        clear_cache("db")
        
        times = []
        cache_hits = []
        
        for i in range(iterations):
            code = codes[i % len(codes)]
            start_time = time.time()
            df = self.db_manager.get_daily(code, 120)
            end_time = time.time()
            times.append(end_time - start_time)
            
            # 获取缓存统计
            stats = get_cache_stats()
            cache_hits.append(stats.get('hits', 0))
            
            logger.debug(f"缓存测试第 {i+1} 次: {times[-1]:.4f}秒, 缓存命中 {cache_hits[-1]}")
        
        times_array = np.array(times)
        cache_hits_array = np.array(cache_hits)
        
        return {
            'iterations': iterations,
            'min_time': float(times_array.min()),
            'max_time': float(times_array.max()),
            'avg_time': float(times_array.mean()),
            'std_time': float(times_array.std()),
            'total_time': float(times_array.sum()),
            'final_cache_hits': int(cache_hits_array[-1]),
            'cache_hit_rate': float(cache_hits_array[-1] / iterations)
        }
    
    def run_comprehensive_test(self, codes: List[str]) -> Dict[str, Any]:
        """
        运行综合性能测试
        
        Args:
            codes: 股票代码列表
            
        Returns:
            综合性能测试结果
        """
        logger.info("开始综合性能测试...")
        
        results = {
            'timestamp': datetime.now().isoformat(),
            'stock_count': len(codes),
            'tests': {}
        }
        
        # 测试1: 单股票查询响应时间
        logger.info("测试1: 单股票查询响应时间")
        if codes:
            results['tests']['single_query'] = self.test_query_response_time(codes[0], 120, 10)
        
        # 测试2: 批量查询性能
        logger.info("测试2: 批量查询性能")
        batch_codes = codes[:10] if len(codes) >= 10 else codes
        results['tests']['batch_query'] = self.test_batch_query_performance(batch_codes, 120, 5)
        
        # 测试3: 并发性能
        logger.info("测试3: 并发性能")
        concurrent_codes = codes[:5] if len(codes) >= 5 else codes
        results['tests']['concurrent'] = self.test_concurrent_performance(concurrent_codes, 10, 5)
        
        # 测试4: 资源使用情况
        logger.info("测试4: 资源使用情况")
        resource_codes = codes[:5] if len(codes) >= 5 else codes
        results['tests']['resource_usage'] = self.test_resource_usage(resource_codes, 10)
        
        # 测试5: 缓存性能
        logger.info("测试5: 缓存性能")
        cache_codes = codes[:5] if len(codes) >= 5 else codes
        results['tests']['cache_performance'] = self.test_cache_performance(cache_codes, 20)
        
        # 生成测试报告
        self._generate_report(results)
        
        logger.info("综合性能测试完成")
        return results
    
    def _generate_report(self, results: Dict[str, Any]):
        """
        生成测试报告
        
        Args:
            results: 测试结果
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_path = f"performance_report_{timestamp}.json"
        
        import json
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        
        logger.info("性能测试报告已生成: %s", report_path)
        
        # 生成人类可读的报告
        human_report = self._generate_human_readable_report(results)
        human_report_path = f"performance_report_{timestamp}.txt"
        with open(human_report_path, 'w', encoding='utf-8') as f:
            f.write(human_report)
        
        logger.info("人类可读的性能测试报告已生成: %s", human_report_path)
    
    def _generate_human_readable_report(self, results: Dict[str, Any]) -> str:
        """
        生成人类可读的测试报告
        
        Args:
            results: 测试结果
            
        Returns:
            人类可读的报告
        """
        report = []
        report.append("=====================================")
        report.append("性能测试报告")
        report.append("=====================================")
        report.append(f"测试时间: {results['timestamp']}")
        report.append(f"测试股票数: {results['stock_count']}")
        report.append("")
        
        # 单股票查询
        if 'single_query' in results['tests']:
            test = results['tests']['single_query']
            report.append("1. 单股票查询响应时间")
            report.append(f"   股票代码: {test['code']}")
            report.append(f"   查询天数: {test['days']}")
            report.append(f"   测试次数: {test['iterations']}")
            report.append(f"   最小时间: {test['min_time']:.4f}秒")
            report.append(f"   最大时间: {test['max_time']:.4f}秒")
            report.append(f"   平均时间: {test['avg_time']:.4f}秒")
            report.append(f"   标准差: {test['std_time']:.4f}秒")
            report.append("")
        
        # 批量查询
        if 'batch_query' in results['tests']:
            test = results['tests']['batch_query']
            report.append("2. 批量查询性能")
            report.append(f"   股票数量: {test['codes_count']}")
            report.append(f"   查询天数: {test['days']}")
            report.append(f"   测试次数: {test['iterations']}")
            report.append(f"   最小时间: {test['min_time']:.4f}秒")
            report.append(f"   最大时间: {test['max_time']:.4f}秒")
            report.append(f"   平均时间: {test['avg_time']:.4f}秒")
            report.append(f"   平均成功数: {test['avg_success_count']:.1f}")
            report.append("")
        
        # 并发性能
        if 'concurrent' in results['tests']:
            test = results['tests']['concurrent']
            report.append("3. 并发性能")
            report.append(f"   并发用户数: {test['concurrent_users']}")
            report.append(f"   每用户测试次数: {test['iterations_per_user']}")
            report.append(f"   总查询次数: {test['total_queries']}")
            report.append(f"   错误次数: {test['errors']}")
            report.append(f"   成功率: {test['success_rate']:.2f}%")
            report.append(f"   平均响应时间: {test['avg_time']:.4f}秒")
            report.append(f"   总测试时间: {test['total_time']:.4f}秒")
            report.append(f"   吞吐量: {test['throughput']:.2f}次/秒")
            report.append("")
        
        # 资源使用
        if 'resource_usage' in results['tests']:
            test = results['tests']['resource_usage']
            report.append("4. 资源使用情况")
            report.append(f"   测试次数: {test['iterations']}")
            report.append(f"   平均CPU使用率: {test['avg_cpu_usage']:.2f}%")
            report.append(f"   最大CPU使用率: {test['max_cpu_usage']:.2f}%")
            report.append(f"   平均内存使用: {test['avg_memory_usage']:.2f}MB")
            report.append(f"   最大内存使用: {test['max_memory_usage']:.2f}MB")
            report.append("")
        
        # 缓存性能
        if 'cache_performance' in results['tests']:
            test = results['tests']['cache_performance']
            report.append("5. 缓存性能")
            report.append(f"   测试次数: {test['iterations']}")
            report.append(f"   平均响应时间: {test['avg_time']:.4f}秒")
            report.append(f"   最终缓存命中数: {test['final_cache_hits']}")
            report.append(f"   缓存命中率: {test['cache_hit_rate']:.2f}%")
            report.append("")
        
        report.append("=====================================")
        return '\n'.join(report)


# 全局性能测试器实例
_performance_tester = None


def get_performance_tester() -> PerformanceTester:
    """
    获取性能测试器实例
    
    Returns:
        性能测试器实例
    """
    global _performance_tester
    if _performance_tester is None:
        _performance_tester = PerformanceTester()
    return _performance_tester
