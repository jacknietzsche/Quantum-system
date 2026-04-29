"""
core.record_manager — 记录管理模块
==================================
负责管理系统运行过程中产生的错误信息和量化分析成果，统一存储至指定文件夹。

设计原则:
  - 错误信息存储至 .learnings 文件夹
  - 分析成果存储至 .workbuddy 文件夹
  - 分类清晰，易于检索
  - 支持结构化存储
"""

import os
import json
import time
import threading
from datetime import datetime
from typing import Dict, Any, Optional, List
from pathlib import Path

import pandas as pd

logger = __import__('logging').getLogger(__name__)


class RecordManager:
    """
    记录管理器
    
    负责管理系统运行过程中产生的错误信息和量化分析成果
    """
    
    def __init__(self):
        # 确保文件夹存在
        self.learnings_dir = Path(r"c:\Users\21471\WorkBuddy\quant system\.learnings")
        self.workbuddy_dir = Path(r"c:\Users\21471\WorkBuddy\quant system\.workbuddy")
        
        self.learnings_dir.mkdir(parents=True, exist_ok=True)
        self.workbuddy_dir.mkdir(parents=True, exist_ok=True)
        
        # 锁
        self._lock = threading.RLock()
        
        logger.info("RecordManager 初始化完成")
    
    def record_error(self, error_type: str, message: str, details: Optional[Dict[str, Any]] = None) -> bool:
        """
        记录错误信息
        
        Args:
            error_type: 错误类型
            message: 错误消息
            details: 详细信息
            
        Returns:
            是否成功记录
        """
        try:
            # 构建错误记录
            error_record = {
                'timestamp': datetime.now().isoformat(),
                'error_type': error_type,
                'message': message,
                'details': details or {}
            }
            
            # 生成文件名
            timestamp = datetime.now().strftime("%Y%m%d")
            file_path = self.learnings_dir / f"ERRORS_{timestamp}.json"
            
            with self._lock:
                # 读取现有数据
                if file_path.exists():
                    with open(file_path, 'r', encoding='utf-8') as f:
                        try:
                            errors = json.load(f)
                        except json.JSONDecodeError:
                            errors = []
                else:
                    errors = []
                
                # 添加新错误
                errors.append(error_record)
                
                # 保存回文件
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(errors, f, ensure_ascii=False, indent=2)
            
            logger.debug("错误记录成功: %s", error_type)
            return True
        except Exception as e:
            logger.error("记录错误失败: %s", e)
            return False
    
    def record_result(self, result_type: str, data: Any, metadata: Optional[Dict[str, Any]] = None) -> bool:
        """
        记录分析成果
        
        Args:
            result_type: 成果类型
            data: 成果数据
            metadata: 元数据
            
        Returns:
            是否成功记录
        """
        try:
            # 构建成果记录
            result_record = {
                'timestamp': datetime.now().isoformat(),
                'result_type': result_type,
                'metadata': metadata or {}
            }
            
            # 生成文件名
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            base_name = f"{result_type}_{timestamp}"
            
            with self._lock:
                # 根据数据类型选择存储方式
                if isinstance(data, pd.DataFrame):
                    # 存储为 CSV 文件
                    file_path = self.workbuddy_dir / f"{base_name}.csv"
                    data.to_csv(file_path, index=True, encoding='utf-8-sig')
                    result_record['file_type'] = 'csv'
                    result_record['file_path'] = str(file_path.relative_to(self.workbuddy_dir))
                elif isinstance(data, dict):
                    # 存储为 JSON 文件
                    file_path = self.workbuddy_dir / f"{base_name}.json"
                    with open(file_path, 'w', encoding='utf-8') as f:
                        json.dump(data, f, ensure_ascii=False, indent=2)
                    result_record['file_type'] = 'json'
                    result_record['file_path'] = str(file_path.relative_to(self.workbuddy_dir))
                else:
                    # 存储为文本文件
                    file_path = self.workbuddy_dir / f"{base_name}.txt"
                    with open(file_path, 'w', encoding='utf-8') as f:
                        f.write(str(data))
                    result_record['file_type'] = 'txt'
                    result_record['file_path'] = str(file_path.relative_to(self.workbuddy_dir))
                
                # 更新成果索引
                index_path = self.workbuddy_dir / "RESULTS_INDEX.json"
                if index_path.exists():
                    with open(index_path, 'r', encoding='utf-8') as f:
                        try:
                            index = json.load(f)
                        except json.JSONDecodeError:
                            index = []
                else:
                    index = []
                
                index.append(result_record)
                
                # 只保留最近 1000 条记录
                if len(index) > 1000:
                    index = index[-1000:]
                
                with open(index_path, 'w', encoding='utf-8') as f:
                    json.dump(index, f, ensure_ascii=False, indent=2)
            
            logger.debug("成果记录成功: %s", result_type)
            return True
        except Exception as e:
            logger.error("记录成果失败: %s", e)
            return False
    
    def get_errors(self, error_type: Optional[str] = None, days: int = 7) -> List[Dict[str, Any]]:
        """
        获取错误记录
        
        Args:
            error_type: 错误类型，None 表示所有类型
            days: 最近几天的记录
            
        Returns:
            错误记录列表
        """
        errors = []
        cutoff_date = datetime.now() - pd.Timedelta(days=days)
        
        with self._lock:
            # 遍历错误文件
            for file_path in self.learnings_dir.glob("ERRORS_*.json"):
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        file_errors = json.load(f)
                    
                    # 过滤时间和类型
                    for error in file_errors:
                        error_time = datetime.fromisoformat(error['timestamp'])
                        if error_time >= cutoff_date:
                            if error_type is None or error['error_type'] == error_type:
                                errors.append(error)
                except Exception as e:
                    logger.error("读取错误文件失败 %s: %s", file_path, e)
        
        # 按时间排序
        errors.sort(key=lambda x: x['timestamp'], reverse=True)
        return errors
    
    def get_results(self, result_type: Optional[str] = None, days: int = 7) -> List[Dict[str, Any]]:
        """
        获取成果记录
        
        Args:
            result_type: 成果类型，None 表示所有类型
            days: 最近几天的记录
            
        Returns:
            成果记录列表
        """
        results = []
        cutoff_date = datetime.now() - pd.Timedelta(days=days)
        
        with self._lock:
            # 读取成果索引
            index_path = self.workbuddy_dir / "RESULTS_INDEX.json"
            if index_path.exists():
                try:
                    with open(index_path, 'r', encoding='utf-8') as f:
                        index = json.load(f)
                    
                    # 过滤时间和类型
                    for result in index:
                        result_time = datetime.fromisoformat(result['timestamp'])
                        if result_time >= cutoff_date:
                            if result_type is None or result['result_type'] == result_type:
                                results.append(result)
                except Exception as e:
                    logger.error("读取成果索引失败: %s", e)
        
        # 按时间排序
        results.sort(key=lambda x: x['timestamp'], reverse=True)
        return results
    
    def clear_errors(self, days: Optional[int] = None) -> bool:
        """
        清除错误记录
        
        Args:
            days: 保留最近几天的记录，None 表示全部清除
            
        Returns:
            是否成功清除
        """
        try:
            with self._lock:
                if days is None:
                    # 清除所有错误文件
                    for file_path in self.learnings_dir.glob("ERRORS_*.json"):
                        try:
                            file_path.unlink()
                        except Exception as e:
                            logger.error("删除错误文件失败 %s: %s", file_path, e)
                else:
                    # 清除指定天数之前的错误文件
                    cutoff_date = datetime.now() - pd.Timedelta(days=days)
                    for file_path in self.learnings_dir.glob("ERRORS_*.json"):
                        try:
                            # 从文件名提取日期
                            date_str = file_path.stem.replace("ERRORS_", "")
                            file_date = datetime.strptime(date_str, "%Y%m%d")
                            if file_date < cutoff_date:
                                file_path.unlink()
                        except Exception as e:
                            logger.error("处理错误文件失败 %s: %s", file_path, e)
            
            logger.debug("错误记录清除成功")
            return True
        except Exception as e:
            logger.error("清除错误记录失败: %s", e)
            return False
    
    def clear_results(self, days: Optional[int] = None) -> bool:
        """
        清除成果记录
        
        Args:
            days: 保留最近几天的记录，None 表示全部清除
            
        Returns:
            是否成功清除
        """
        try:
            with self._lock:
                if days is None:
                    # 清除所有成果文件和索引
                    for file_path in self.workbuddy_dir.glob("*.*"):
                        try:
                            if file_path.name != "RESULTS_INDEX.json":
                                file_path.unlink()
                        except Exception as e:
                            logger.error("删除成果文件失败 %s: %s", file_path, e)
                    
                    # 清空索引
                    index_path = self.workbuddy_dir / "RESULTS_INDEX.json"
                    if index_path.exists():
                        with open(index_path, 'w', encoding='utf-8') as f:
                            json.dump([], f)
                else:
                    # 清除指定天数之前的成果记录
                    cutoff_date = datetime.now() - pd.Timedelta(days=days)
                    
                    # 读取并更新索引
                    index_path = self.workbuddy_dir / "RESULTS_INDEX.json"
                    if index_path.exists():
                        try:
                            with open(index_path, 'r', encoding='utf-8') as f:
                                index = json.load(f)
                            
                            new_index = []
                            for result in index:
                                result_time = datetime.fromisoformat(result['timestamp'])
                                if result_time >= cutoff_date:
                                    new_index.append(result)
                                else:
                                    # 删除对应的成果文件
                                    file_path = self.workbuddy_dir / result['file_path']
                                    if file_path.exists():
                                        try:
                                            file_path.unlink()
                                        except Exception as e:
                                            logger.error("删除成果文件失败 %s: %s", file_path, e)
                            
                            # 保存更新后的索引
                            with open(index_path, 'w', encoding='utf-8') as f:
                                json.dump(new_index, f, ensure_ascii=False, indent=2)
                        except Exception as e:
                            logger.error("处理成果索引失败: %s", e)
            
            logger.debug("成果记录清除成功")
            return True
        except Exception as e:
            logger.error("清除成果记录失败: %s", e)
            return False


# 全局记录管理器实例
_record_manager = None
_record_manager_lock = threading.Lock()


def get_record_manager() -> RecordManager:
    """
    获取记录管理器实例
    
    Returns:
        记录管理器实例
    """
    global _record_manager
    with _record_manager_lock:
        if _record_manager is None:
            _record_manager = RecordManager()
        return _record_manager


def record_error(error_type: str, message: str, details: Optional[Dict[str, Any]] = None) -> bool:
    """
    记录错误信息
    
    Args:
        error_type: 错误类型
        message: 错误消息
        details: 详细信息
        
    Returns:
        是否成功记录
    """
    record_manager = get_record_manager()
    return record_manager.record_error(error_type, message, details)


def record_result(result_type: str, data: Any, metadata: Optional[Dict[str, Any]] = None) -> bool:
    """
    记录分析成果
    
    Args:
        result_type: 成果类型
        data: 成果数据
        metadata: 元数据
        
    Returns:
        是否成功记录
    """
    record_manager = get_record_manager()
    return record_manager.record_result(result_type, data, metadata)


def get_errors(error_type: Optional[str] = None, days: int = 7) -> List[Dict[str, Any]]:
    """
    获取错误记录
    
    Args:
        error_type: 错误类型，None 表示所有类型
        days: 最近几天的记录
        
    Returns:
        错误记录列表
    """
    record_manager = get_record_manager()
    return record_manager.get_errors(error_type, days)


def get_results(result_type: Optional[str] = None, days: int = 7) -> List[Dict[str, Any]]:
    """
    获取成果记录
    
    Args:
        result_type: 成果类型，None 表示所有类型
        days: 最近几天的记录
        
    Returns:
        成果记录列表
    """
    record_manager = get_record_manager()
    return record_manager.get_results(result_type, days)
