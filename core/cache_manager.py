"""
core.cache_manager — 缓存管理模块
==================================
负责管理数据缓存，包括内存缓存和磁盘缓存，提供高效的缓存机制和合理的缓存失效策略。

设计原则:
  - 内存缓存优先，减少磁盘 I/O
  - 合理的缓存失效策略
  - 支持缓存更新机制
  - 线程安全
"""

import os
import time
import pickle
import hashlib
import threading
from datetime import datetime, timedelta
from typing import Optional, Any, Dict, List
from pathlib import Path

import pandas as pd

from core.config import DataSourceConfig

logger = __import__('logging').getLogger(__name__)

__all__ = [
    "CacheManager",
    "get_cache_manager",
    "clear_cache",
    "get_cache_stats",
]


class CacheManager:
    """
    缓存管理器
    
    管理数据缓存，包括内存缓存和磁盘缓存
    """
    
    def __init__(self, config: Optional[DataSourceConfig] = None):
        self.cfg = config or DataSourceConfig()
        
        # 确保缓存目录存在
        Path(self.cfg.cache_dir).mkdir(parents=True, exist_ok=True)
        
        # 内存缓存
        self._memory_cache: Dict[str, Dict[str, Any]] = {}
        self._memory_cache_lock = threading.RLock()
        
        # 缓存统计
        self._hits = 0
        self._misses = 0
        self._evictions = 0
        
        logger.info("CacheManager 初始化完成")
    
    def _get_cache_key(self, prefix: str, *args) -> str:
        """生成缓存键"""
        key_parts = [prefix] + [str(arg) for arg in args]
        key_str = "_".join(key_parts)
        return hashlib.md5(key_str.encode()).hexdigest()
    
    def _get_disk_cache_path(self, key: str) -> str:
        """获取磁盘缓存路径"""
        return os.path.join(self.cfg.cache_dir, f"{key}.pkl")
    
    def get(self, prefix: str, *args) -> Optional[Any]:
        """
        获取缓存数据
        
        Args:
            prefix: 缓存前缀
            *args: 缓存键参数
            
        Returns:
            缓存数据，如果不存在或已过期则返回 None
        """
        key = self._get_cache_key(prefix, *args)
        
        # 先检查内存缓存
        with self._memory_cache_lock:
            if key in self._memory_cache:
                cache_entry = self._memory_cache[key]
                if not self._is_expired(cache_entry['timestamp']):
                    self._hits += 1
                    logger.debug("内存缓存命中: %s", prefix)
                    return cache_entry['data']
                else:
                    # 内存缓存已过期
                    del self._memory_cache[key]
                    self._evictions += 1
        
        # 检查磁盘缓存
        disk_path = self._get_disk_cache_path(key)
        try:
            stat = os.stat(disk_path)
            if not self._is_expired(stat.st_mtime):
                with open(disk_path, 'rb') as f:
                    data = pickle.load(f)
                
                # 加载到内存缓存
                with self._memory_cache_lock:
                    self._memory_cache[key] = {
                        'data': data,
                        'timestamp': time.time()
                    }
                
                self._hits += 1
                logger.debug("磁盘缓存命中: %s", prefix)
                return data
        except (FileNotFoundError, Exception):
            pass
        
        self._misses += 1
        logger.debug("缓存未命中: %s", prefix)
        return None
    
    def set(self, prefix: str, data: Any, *args) -> bool:
        """
        设置缓存数据
        
        Args:
            prefix: 缓存前缀
            data: 要缓存的数据
            *args: 缓存键参数
            
        Returns:
            是否成功设置缓存
        """
        key = self._get_cache_key(prefix, *args)
        
        # 检查数据类型
        allowed_types = (dict, pd.DataFrame, pd.Series, list, tuple, set, str, int, float, bool, type(None))
        if not isinstance(data, allowed_types):
            logger.warning(f"不支持的缓存数据类型: {type(data)}")
            return False
        
        # 检查数据大小
        try:
            data_size = len(pickle.dumps(data))
            if data_size > 10 * 1024 * 1024:  # 10MB
                logger.warning(f"缓存数据过大: {data_size / 1024 / 1024:.2f}MB")
                return False
        except Exception as e:
            logger.warning("无法计算数据大小: %s", e)
            return False
        
        # 存储到内存缓存
        with self._memory_cache_lock:
            # 检查内存缓存大小
            if len(self._memory_cache) > 1000:  # 限制内存缓存数量
                # 移除最旧的缓存
                oldest_key = min(self._memory_cache, key=lambda k: self._memory_cache[k]['timestamp'])
                del self._memory_cache[oldest_key]
                self._evictions += 1
            
            self._memory_cache[key] = {
                'data': data,
                'timestamp': time.time()
            }
        
        # 存储到磁盘缓存
        disk_path = self._get_disk_cache_path(key)
        try:
            with open(disk_path, 'wb') as f:
                pickle.dump(data, f)
            return True
        except Exception as e:
            logger.error("写入磁盘缓存失败: %s", e)
            return False
    
    def delete(self, prefix: str, *args) -> bool:
        """
        删除缓存
        
        Args:
            prefix: 缓存前缀
            *args: 缓存键参数
            
        Returns:
            是否成功删除缓存
        """
        key = self._get_cache_key(prefix, *args)
        
        # 从内存缓存删除
        with self._memory_cache_lock:
            if key in self._memory_cache:
                del self._memory_cache[key]
                self._evictions += 1
        
        # 从磁盘缓存删除
        disk_path = self._get_disk_cache_path(key)
        try:
            os.remove(disk_path)
            return True
        except FileNotFoundError:
            return True
        except Exception as e:
            logger.error("删除磁盘缓存失败: %s", e)
            return False
    
    def clear(self, prefix: Optional[str] = None) -> bool:
        """
        清除缓存
        
        Args:
            prefix: 缓存前缀，如果为 None 则清除所有缓存
            
        Returns:
            是否成功清除缓存
        """
        try:
            # 清除内存缓存
            with self._memory_cache_lock:
                if prefix:
                    keys_to_delete = [k for k in self._memory_cache if k.startswith(prefix)]
                    for key in keys_to_delete:
                        del self._memory_cache[key]
                        self._evictions += 1
                else:
                    self._memory_cache.clear()
                    self._evictions += len(self._memory_cache)
            
            # 清除磁盘缓存
            if prefix:
                pattern = f"{prefix}*.pkl"
                import glob
                for file_path in glob.glob(os.path.join(self.cfg.cache_dir, pattern)):
                    try:
                        os.remove(file_path)
                    except Exception as e:
                        logger.error("删除磁盘缓存文件失败: %s", e)
            else:
                import shutil
                shutil.rmtree(self.cfg.cache_dir)
                Path(self.cfg.cache_dir).mkdir(parents=True, exist_ok=True)
            
            return True
        except Exception as e:
            logger.error("清除缓存失败: %s", e)
            return False
    
    def get_stats(self) -> Dict[str, int]:
        """
        获取缓存统计信息
        
        Returns:
            缓存统计信息
        """
        with self._memory_cache_lock:
            memory_size = len(self._memory_cache)
        
        # 计算磁盘缓存大小
        disk_size = 0
        try:
            for file in os.listdir(self.cfg.cache_dir):
                if file.endswith('.pkl'):
                    file_path = os.path.join(self.cfg.cache_dir, file)
                    disk_size += os.path.getsize(file_path)
        except Exception as e:
            logger.debug("disk cache size calculation failed: %s", e)

        return {
            'hits': self._hits,
            'misses': self._misses,
            'evictions': self._evictions,
            'memory_size': memory_size,
            'disk_size': disk_size
        }
    
    def _is_expired(self, timestamp: float) -> bool:
        """
        检查缓存是否过期
        
        Args:
            timestamp: 缓存时间戳
            
        Returns:
            是否过期
        """
        age = time.time() - timestamp
        return age > self.cfg.cache_hours * 3600
    
    def update_cache(self, prefix: str, data: Any, *args) -> bool:
        """
        更新缓存
        
        Args:
            prefix: 缓存前缀
            data: 新的缓存数据
            *args: 缓存键参数
            
        Returns:
            是否成功更新缓存
        """
        # 先删除旧缓存
        self.delete(prefix, *args)
        # 再设置新缓存
        return self.set(prefix, data, *args)


# 全局缓存管理器实例
_cache_manager = None
_cache_manager_lock = threading.Lock()


def get_cache_manager(config: Optional[DataSourceConfig] = None) -> CacheManager:
    """
    获取缓存管理器实例
    
    Args:
        config: 数据源配置
        
    Returns:
        缓存管理器实例
    """
    global _cache_manager
    with _cache_manager_lock:
        if _cache_manager is None:
            _cache_manager = CacheManager(config)
        return _cache_manager


def clear_cache(prefix: Optional[str] = None) -> bool:
    """
    清除缓存
    
    Args:
        prefix: 缓存前缀，如果为 None 则清除所有缓存
        
    Returns:
        是否成功清除缓存
    """
    cache_manager = get_cache_manager()
    return cache_manager.clear(prefix)


def get_cache_stats() -> Dict[str, int]:
    """
    获取缓存统计信息
    
    Returns:
        缓存统计信息
    """
    cache_manager = get_cache_manager()
    return cache_manager.get_stats()
