"""
core.data_scheduler — 数据更新调度器
==================================
负责管理数据更新的频率和触发条件，确保数据及时同步至数据库。

设计原则:
  - 合理的更新频率策略
  - 灵活的触发条件
  - 可靠的错误处理
  - 高效的更新机制
"""

import os
import time
import threading
import schedule
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Callable
from pathlib import Path

from core.data_updater import DataUpdater
from core.record_manager import record_error, record_result
from core.config import DataSourceConfig

logger = __import__('logging').getLogger(__name__)


class DataScheduler:
    """
    数据更新调度器
    
    负责管理数据更新的频率和触发条件
    """
    
    def __init__(self, config: Optional[DataSourceConfig] = None):
        self.cfg = config or DataSourceConfig()
        self.updater = DataUpdater(self.cfg)
        self._lock = threading.RLock()
        self._running = False
        self._update_thread = None
        
        # 更新状态
        self._update_status = {
            'last_stock_list_update': None,
            'last_stock_data_update': None,
            'last_update_result': None
        }
        
        logger.info("DataScheduler 初始化完成")
    
    def start(self):
        """
        启动调度器
        """
        with self._lock:
            if self._running:
                logger.warning("调度器已经在运行")
                return
            
            self._running = True
            
            # 设置定时任务
            self._setup_schedules()
            
            # 启动调度线程
            self._update_thread = threading.Thread(target=self._run_schedule, daemon=True)
            self._update_thread.start()
            
            logger.info("调度器已启动")
    
    def stop(self):
        """
        停止调度器
        """
        with self._lock:
            if not self._running:
                logger.warning("调度器已经停止")
                return
            
            self._running = False
            if self._update_thread:
                self._update_thread.join(timeout=5)
            
            logger.info("调度器已停止")
    
    def _setup_schedules(self):
        """
        设置定时任务
        """
        # 每天收盘后更新股票数据（16:00）
        schedule.every().day.at("16:00").do(self.update_all_stocks)
        
        # 每周一更新股票列表（9:00）
        schedule.every().monday.at("09:00").do(self.update_stock_list)
        
        # 每小时检查一次数据更新状态
        schedule.every().hour.do(self.check_update_status)
    
    def _run_schedule(self):
        """
        运行调度任务
        """
        while self._running:
            try:
                schedule.run_pending()
                time.sleep(60)  # 每分钟检查一次
            except Exception as e:
                error_msg = f"调度器运行失败: {e}"
                logger.error(error_msg)
                record_error("scheduler", error_msg, {"error": str(e)})
                time.sleep(60)
    
    def update_stock_list(self) -> bool:
        """
        更新股票列表
        
        Returns:
            是否成功更新
        """
        logger.info("开始更新股票列表...")
        
        try:
            success = self.updater.update_stock_list()
            self._update_status['last_stock_list_update'] = datetime.now().isoformat()
            self._update_status['last_update_result'] = success
            
            if success:
                logger.info("股票列表更新成功")
                record_result("stock_list_update", {
                    "status": "success",
                    "timestamp": datetime.now().isoformat()
                })
            else:
                error_msg = "股票列表更新失败"
                logger.warning(error_msg)
                record_error("update", error_msg)
            
            return success
        except Exception as e:
            error_msg = f"股票列表更新异常: {e}"
            logger.error(error_msg)
            record_error("update", error_msg, {"error": str(e)})
            self._update_status['last_update_result'] = False
            return False
    
    def update_all_stocks(self, days: int = 180) -> Dict[str, bool]:
        """
        更新所有股票数据
        
        Args:
            days: 更新天数
            
        Returns:
            更新结果
        """
        logger.info("开始更新所有股票数据（%s天）...", days)
        
        try:
            result = self.updater.update_all_stocks(days)
            self._update_status['last_stock_data_update'] = datetime.now().isoformat()
            
            # 统计结果
            success_count = sum(1 for v in result.values() if v)
            total_count = len(result)
            
            logger.info("股票数据更新完成: %s/%s 只成功", success_count, total_count)
            
            record_result("stock_data_update", {
                "status": "success",
                "success_count": success_count,
                "total_count": total_count,
                "timestamp": datetime.now().isoformat()
            })
            
            return result
        except Exception as e:
            error_msg = f"股票数据更新异常: {e}"
            logger.error(error_msg)
            record_error("update", error_msg, {"error": str(e)})
            return {}
    
    def update_stocks(self, symbols: List[str], days: int = 180) -> Dict[str, bool]:
        """
        更新指定股票数据
        
        Args:
            symbols: 股票代码列表
            days: 更新天数
            
        Returns:
            更新结果
        """
        logger.info(f"开始更新指定股票数据（{len(symbols)}只）...")
        
        try:
            result = self.updater.update_stock_data(symbols, days)
            
            # 统计结果
            success_count = sum(1 for v in result.values() if v)
            total_count = len(result)
            
            logger.info("指定股票数据更新完成: %s/%s 只成功", success_count, total_count)
            
            record_result("stock_data_update", {
                "status": "success",
                "success_count": success_count,
                "total_count": total_count,
                "symbols": symbols,
                "timestamp": datetime.now().isoformat()
            })
            
            return result
        except Exception as e:
            error_msg = f"指定股票数据更新异常: {e}"
            logger.error(error_msg)
            record_error("update", error_msg, {"error": str(e), "symbols": symbols})
            return {}
    
    def check_update_status(self):
        """
        检查更新状态
        """
        logger.debug("检查数据更新状态...")
        
        # 检查股票列表是否需要更新
        last_list_update = self._update_status.get('last_stock_list_update')
        if last_list_update:
            last_update_time = datetime.fromisoformat(last_list_update)
            days_since_update = (datetime.now() - last_update_time).days
            if days_since_update > 7:
                logger.warning("股票列表超过7天未更新，建议更新")
        
        # 检查股票数据是否需要更新
        last_data_update = self._update_status.get('last_stock_data_update')
        if last_data_update:
            last_update_time = datetime.fromisoformat(last_data_update)
            days_since_update = (datetime.now() - last_update_time).days
            if days_since_update > 1:
                logger.warning("股票数据超过1天未更新，建议更新")
    
    def get_update_status(self) -> Dict[str, Optional[str]]:
        """
        获取更新状态
        
        Returns:
            更新状态
        """
        return self._update_status
    
    def force_update(self, update_list: bool = True, update_data: bool = True, days: int = 180):
        """
        强制更新数据
        
        Args:
            update_list: 是否更新股票列表
            update_data: 是否更新股票数据
            days: 更新天数
        """
        logger.info("执行强制更新...")
        
        if update_list:
            self.update_stock_list()
        
        if update_data:
            self.update_all_stocks(days)
        
        logger.info("强制更新完成")


# 全局数据调度器实例
_data_scheduler = None
_data_scheduler_lock = threading.RLock()


def get_data_scheduler(config: Optional[DataSourceConfig] = None) -> DataScheduler:
    """
    获取数据调度器实例
    
    Args:
        config: 数据源配置
        
    Returns:
        数据调度器实例
    """
    global _data_scheduler
    with _data_scheduler_lock:
        if _data_scheduler is None:
            _data_scheduler = DataScheduler(config)
        return _data_scheduler


def start_scheduler():
    """
    启动数据调度器
    """
    scheduler = get_data_scheduler()
    scheduler.start()


def stop_scheduler():
    """
    停止数据调度器
    """
    scheduler = get_data_scheduler()
    scheduler.stop()


def force_update(update_list: bool = True, update_data: bool = True, days: int = 180):
    """
    强制更新数据
    
    Args:
        update_list: 是否更新股票列表
        update_data: 是否更新股票数据
        days: 更新天数
    """
    scheduler = get_data_scheduler()
    scheduler.force_update(update_list, update_data, days)


def update_stocks(symbols: List[str], days: int = 180) -> Dict[str, bool]:
    """
    更新指定股票数据
    
    Args:
        symbols: 股票代码列表
        days: 更新天数
        
    Returns:
        更新结果
    """
    scheduler = get_data_scheduler()
    return scheduler.update_stocks(symbols, days)
