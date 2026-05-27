"""
core.performance_analyzer — 性能分析工具模块
==================================
负责分析回测系统的性能瓶颈，识别CPU密集型操作、内存使用瓶颈及I/O效率问题

设计原则:
  - 全面的性能分析指标
  - 详细的瓶颈识别
  - 可视化的分析结果
  - 量化的性能数据
"""

import time
import psutil
import logging
import cProfile
import pstats
from datetime import datetime
from typing import Dict, List, Optional, Any
from io import StringIO

import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)

__all__ = [
    "PerformanceAnalyzer",
    "get_performance_analyzer",
    "analyze_performance",
]


class PerformanceAnalyzer:
    """
    性能分析器
    
    负责分析回测系统的性能瓶颈
    """
    
    def __init__(self):
        """
        初始化性能分析器
        """
        self._profiler = cProfile.Profile()
        self._start_time = 0
        self._end_time = 0
        self._process = psutil.Process()
        self._memory_before = 0
        self._memory_after = 0
        self._cpu_before = 0
        self._cpu_after = 0
        logger.info("PerformanceAnalyzer 初始化完成")
    
    def start(self):
        """
        开始性能分析
        """
        self._start_time = time.time()
        self._memory_before = self._process.memory_info().rss / 1024 / 1024  # MB
        self._cpu_before = self._process.cpu_percent(interval=0.1)
        self._profiler.enable()
        logger.info("性能分析开始")
    
    def stop(self):
        """
        停止性能分析
        """
        self._profiler.disable()
        self._end_time = time.time()
        self._memory_after = self._process.memory_info().rss / 1024 / 1024  # MB
        self._cpu_after = self._process.cpu_percent(interval=0.1)
        logger.info("性能分析停止")
    
    def get_stats(self) -> Dict[str, Any]:
        """
        获取性能统计信息
        
        Returns:
            性能统计信息
        """
        # 计算执行时间
        execution_time = self._end_time - self._start_time
        
        # 计算内存使用变化
        memory_used = self._memory_after - self._memory_before
        
        # 计算CPU使用变化
        cpu_used = self._cpu_after - self._cpu_before
        
        # 获取函数调用统计
        s = StringIO()
        ps = pstats.Stats(self._profiler, stream=s)
        ps.sort_stats('cumulative')
        ps.print_stats()
        stats_output = s.getvalue()
        
        # 分析热点函数
        hot_functions = self._analyze_hot_functions(stats_output)
        
        return {
            'execution_time': execution_time,
            'memory_used': memory_used,
            'cpu_used': cpu_used,
            'hot_functions': hot_functions,
            'stats_output': stats_output
        }
    
    def _analyze_hot_functions(self, stats_output: str) -> List[Dict[str, Any]]:
        """
        分析热点函数
        
        Args:
            stats_output: 性能统计输出
            
        Returns:
            热点函数列表
        """
        hot_functions = []
        lines = stats_output.split('\n')
        
        # 跳过前面的行，找到函数统计部分
        start_parsing = False
        for line in lines:
            if line.strip().startswith('ncalls'):
                start_parsing = True
                continue
            
            if start_parsing and line.strip():
                parts = line.strip().split()
                if len(parts) >= 6:
                    hot_functions.append({
                        'ncalls': parts[0],
                        'tottime': float(parts[1]),
                        'percall': float(parts[2]),
                        'cumtime': float(parts[3]),
                        'percall_cum': float(parts[4]),
                        'filename': parts[5],
                        'lineno': parts[6] if len(parts) > 6 else '',
                        'function': ' '.join(parts[7:]) if len(parts) > 7 else ''
                    })
        
        # 按累计时间排序，取前10个热点函数
        hot_functions.sort(key=lambda x: x['cumtime'], reverse=True)
        return hot_functions[:10]
    
    def generate_report(self, stats: Dict[str, Any], report_name: str = None) -> str:
        """
        生成性能分析报告
        
        Args:
            stats: 性能统计信息
            report_name: 报告名称
            
        Returns:
            报告文件路径
        """
        if report_name is None:
            report_name = f"performance_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        # 生成文本报告
        report_path = f"{report_name}.txt"
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write("=====================================\n")
            f.write("性能分析报告\n")
            f.write("=====================================\n")
            f.write(f"分析时间: {datetime.now().isoformat()}\n")
            f.write(f"执行时间: {stats['execution_time']:.2f}秒\n")
            f.write(f"内存使用变化: {stats['memory_used']:.2f}MB\n")
            f.write(f"CPU使用变化: {stats['cpu_used']:.2f}%\n")
            f.write("\n热点函数:\n")
            f.write("-" * 80 + "\n")
            f.write("{:<10} {:<10} {:<10} {:<10} {:<10} {:<20} {:<10} {:<20}\n".format(
                'ncalls', 'tottime', 'percall', 'cumtime', 'percall_cum', 'filename', 'lineno', 'function'
            ))
            f.write("-" * 80 + "\n")
            for func in stats['hot_functions']:
                f.write("{:<10} {:<10.4f} {:<10.4f} {:<10.4f} {:<10.4f} {:<20} {:<10} {:<20}\n".format(
                    func['ncalls'], func['tottime'], func['percall'],
                    func['cumtime'], func['percall_cum'], func['filename'],
                    func['lineno'], func['function']
                ))
            f.write("-" * 80 + "\n")
            f.write("\n详细统计:\n")
            f.write(stats['stats_output'])
        
        logger.info("性能分析报告已生成: %s", report_path)
        return report_path
    
    def analyze_function(self, func, *args, **kwargs) -> Dict[str, Any]:
        """
        分析单个函数的性能
        
        Args:
            func: 要分析的函数
            *args: 函数参数
            **kwargs: 函数关键字参数
            
        Returns:
            性能统计信息
        """
        self.start()
        try:
            result = func(*args, **kwargs)
        finally:
            self.stop()
        
        stats = self.get_stats()
        return stats


# 全局性能分析器实例
_performance_analyzer = None


def get_performance_analyzer() -> PerformanceAnalyzer:
    """
    获取性能分析器实例
    
    Returns:
        性能分析器实例
    """
    global _performance_analyzer
    if _performance_analyzer is None:
        _performance_analyzer = PerformanceAnalyzer()
    return _performance_analyzer


def analyze_performance(func, *args, **kwargs) -> Dict[str, Any]:
    """
    分析函数性能
    
    Args:
        func: 要分析的函数
        *args: 函数参数
        **kwargs: 函数关键字参数
        
    Returns:
        性能统计信息
    """
    analyzer = get_performance_analyzer()
    return analyzer.analyze_function(func, *args, **kwargs)
