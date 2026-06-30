import sys
import os

# 添加项目根目录到路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.logging_config import setup_logging, get_logger

# 配置日志
setup_logging()
logger = get_logger(__name__)

from backtest_system.backtest_engine import BacktestEngine
from backtest_system.data_loader import DataLoader
from core.strategy import V16Scorer, StockFilter
from core.config import QuantConfig

# 测试数据加载
def test_data_loading():
    logger.info("测试数据加载...")
    data_loader = DataLoader()
    
    # 测试加载单只股票数据
    try:
        stock_data = data_loader.load_stock('600000', start_date='20240101', end_date='20240131')
        logger.info(f"加载 600000 数据成功，数据长度: {len(stock_data)}")
        logger.info(f"数据列: {list(stock_data.columns)}")
        logger.info(f"数据前5行:\n{stock_data.head()}")
        return stock_data
    except Exception as e:
        logger.error("加载数据失败: %s", e)
        return None

# 测试策略评分
def test_strategy_scoring(stock_data):
    logger.info("\n测试策略评分...")
    scorer = V16Scorer()
    
    # 测试评分功能
    try:
        if stock_data is not None and not stock_data.empty:
            score = scorer.score('600000', stock_data)
            logger.info("股票 600000 的评分: %s", score)
        else:
            logger.warning("股票数据为空")
    except Exception as e:
        logger.error("评分失败: %s", e)

# 测试股票过滤
def test_stock_filter():
    logger.info("\n测试股票过滤...")
    try:
        data_loader = DataLoader()
        stock_filter = StockFilter()
        
        # 加载多只股票数据
        stock_codes = ['600000', '600519', '000001']
        stock_data = {}
        
        for code in stock_codes:
            try:
                df = data_loader.load_stock(code, start_date='20240101', end_date='20240131')
                if not df.empty:
                    stock_data[code] = df
                    logger.info("加载 %s 数据成功，长度: {len(df)}", code)
                else:
                    logger.warning("%s 数据为空", code)
            except Exception as e:
                logger.error("加载 %s 数据失败: %s", code, e)
        
        logger.info(f"初始股票数量: {len(stock_data)}")
        
        # 测试过滤
        filtered_data = stock_filter.filter_by_data(stock_data)
        logger.info(f"过滤后股票数量: {len(filtered_data)}")
        
        return filtered_data
    except Exception as e:
        logger.error("过滤失败: %s", e)
        return None

if __name__ == "__main__":
    logger.info("开始测试回测系统...")
    stock_data = test_data_loading()
    test_strategy_scoring(stock_data)
    test_stock_filter()
    logger.info("测试完成")
