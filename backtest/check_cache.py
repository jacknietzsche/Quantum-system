import pickle
import os

import logging
logger = logging.getLogger(__name__)

# 缓存目录
cache_dir = r"c:\Users\21471\WorkBuddy\quant system\backtest_system\cache\market_data"

# 检查缓存文件
cache_files = [f for f in os.listdir(cache_dir) if f.endswith('.pkl')]
logger.info("找到 %s 个缓存文件", len(cache_files))

# 检查第一个缓存文件
if cache_files:
    first_file = os.path.join(cache_dir, cache_files[0])
    logger.info("检查缓存文件: %s", first_file)
    
    try:
        with open(first_file, 'rb') as f:
            df = pickle.load(f)
        
        logger.info("数据长度: %s", len(df))
        logger.info("列名: %s", list(df.columns))
        logger.info("是否包含 'pctChg' 列: %s", 'pctChg' in df.columns)
        logger.info("是否包含 'turn' 列: %s", 'turn' in df.columns)
        
        # 打印前几行数据
        logger.info("前几行数据:")
        logger.info("%s", df.head())
    except Exception as e:
        logger.info("读取缓存文件失败: %s", e)
