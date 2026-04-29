"""
检查数据库状态
==================================
检查数据库是否可以正常连接和查询
"""

import os
import sys
import logging
import sqlite3

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

from core.db_manager import get_db_manager


def main():
    """主函数"""
    logger.info("开始检查数据库状态...")
    
    try:
        # 获取数据库管理器
        db_manager = get_db_manager()
        logger.info("数据库管理器初始化成功")
        
        # 获取数据库统计信息
        stats = db_manager.get_stats()
        logger.info(f"数据库统计信息: {stats}")
        
        # 获取股票列表
        stock_list = db_manager.get_stock_list()
        logger.info(f"股票列表数量: {len(stock_list)}")
        
        # 测试获取单只股票数据
        if not stock_list.empty:
            code = stock_list.iloc[0]['symbol']
            df = db_manager.get_daily(code, 10)
            logger.info(f"获取 {code} 数据成功，共 {len(df)} 条")
        
        logger.info("数据库状态正常！")
        return True
    except Exception as e:
        logger.error(f"数据库检查失败: {e}")
        return False


if __name__ == "__main__":
    main()
