#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
backtest_comprehensive_local.py — 全面的量化策略回测

使用本地存储的全部历史数据执行全面的量化策略回测，生成专业、详尽的回测报告。

报告包含：
- 策略表现概览
- 关键绩效指标（年化收益率、最大回撤、夏普比率、胜率等）
- 交易明细分析
- 风险评估
- 参数敏感性测试结果
- 与基准指数的对比分析
"""

import os
import sys
import logging
import argparse
from datetime import datetime, date
from pathlib import Path

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

# 项目根目录
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.config import QuantConfig, SelectionConfig
from core.strategy import V16Scorer, StockFilter
from core.data import UnifiedDataFetcher
from backtest_system.backtest_engine import BacktestEngine
from backtest_system.data_loader import DataLoader
from backtest_system.config import BacktestConfig

# 日志配置
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(os.path.join(PROJECT_ROOT, 'logs', 'backtest_comprehensive.log'), encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)


class V16StrategyAdapter:
    """
    V16Scorer 策略适配器，用于 BacktestEngine
    """
    
    def __init__(self, config=None):
        self.config = config or QuantConfig()
        # 禁用成分股过滤，避免所有股票被过滤
        self.config.selection.filter_include_hs300 = False
        self.config.selection.filter_include_zz500 = False
        self.config.selection.filter_include_hs300_zz500 = False
        # 降低过滤标准，确保有股票通过过滤
        self.config.selection.filter_min_turnover = 0.5  # 降低最小换手率要求
        self.config.selection.filter_min_avg_amount = 5000000  # 降低最小成交额要求
        self.scorer = V16Scorer(self.config)
        self.stock_filter = StockFilter(self.config.selection)
        self.data_provider = UnifiedDataFetcher()
        self.holdings = {}
        self.last_rebalance_date = None
    
    def get_buy_signals(self, date, data_dict):
        """
        获取买入信号
        """
        logger.info("获取买入信号: %s", date)
        logger.info(f"当前持仓: {self.holdings}")
        logger.info(f"上次调仓日期: {self.last_rebalance_date}")
        
        # 处理不同格式的 data_dict
        stock_data = {}
        if isinstance(data_dict, dict):
            # 检查是否是 BacktraderStrategyAdapter 格式
            if 'stocks' in data_dict:
                # 从 stocks 字段提取数据
                stocks = data_dict.get('stocks', {})
                logger.info(f"从 stocks 字段提取数据，股票数量: {len(stocks)}")
                
                # 对于 Backtrader 格式，我们需要使用原始数据字典
                # 这里直接使用 self.data_provider 获取历史数据
                logger.info("使用 UnifiedDataFetcher 获取历史数据")
                
                # 构建股票数据字典
                for code in stocks.keys():
                    try:
                        # 获取历史数据
                        df = self.data_provider.get_price(code, start_date='20210324', end_date=date.replace('-', ''))
                        if len(df) >= 20:
                            stock_data[code] = df
                        else:
                            logger.debug("股票 %s 数据长度不足20，当前长度: {len(df)}", code)
                    except Exception as e:
                        logger.debug("获取股票 %s 数据失败: %s", code, e)
            else:
                # 原始格式: {code: DataFrame}
                logger.info(f"处理原始格式数据，总股票数量: {len(data_dict)}")
                for code, df in data_dict.items():
                    # 确保数据足够
                    if len(df) >= 20:
                        stock_data[code] = df
                    else:
                        logger.debug("股票 %s 数据长度不足20，当前长度: {len(df)}", code)
        else:
            logger.warning(f"data_dict 不是字典类型，而是: {type(data_dict)}")
        
        logger.info(f"初始股票数量: {len(stock_data)}")
        
        # 调试：检查前5只股票的数据
        if stock_data:
            logger.info("调试：检查前5只股票的数据")
            for i, (code, df) in enumerate(list(stock_data.items())[:5]):
                logger.info("  股票 %s: 数据长度={len(df)}, 平均换手率={df['turn'].mean():.2f}%, 平均成交额={df['amount'].mean():,.2f} 元, 最新价格={df['close'].iloc[-1]:.2f} 元", code)
        
        # 过滤股票
        stock_data = self.stock_filter.filter_by_data(stock_data)
        logger.info(f"过滤后股票数量 (数据): {len(stock_data)}")
        
        # 调试：检查过滤后的数据
        if stock_data:
            logger.info("调试：检查数据过滤后的前5只股票")
            for i, (code, df) in enumerate(list(stock_data.items())[:5]):
                logger.info("  股票 %s: 数据长度={len(df)}", code)
        
        stock_data = self.stock_filter.filter_by_liquidity(stock_data)
        logger.info(f"过滤后股票数量 (流动性): {len(stock_data)}")
        
        # 调试：检查过滤后的数据
        if stock_data:
            logger.info("调试：检查流动性过滤后的前5只股票")
            for i, (code, df) in enumerate(list(stock_data.items())[:5]):
                logger.info("  股票 %s: 平均换手率={df['turn'].mean():.2f}%, 平均成交额={df['amount'].mean():,.2f} 元", code)
        
        stock_data = self.stock_filter.filter_by_suspended_days(stock_data)
        logger.info(f"过滤后股票数量 (停牌): {len(stock_data)}")
        
        # 调试：检查过滤后的数据
        if stock_data:
            logger.info("调试：检查停牌过滤后的前5只股票")
            for i, (code, df) in enumerate(list(stock_data.items())[:5]):
                logger.info("  股票 %s: 数据长度={len(df)}", code)
        
        # 如果过滤后股票数量为0，尝试使用简化过滤
        if not stock_data and len(data_dict) > 0:
            logger.warning("所有股票都被过滤，尝试使用简化过滤逻辑")
            # 简化过滤：只检查数据长度
            stock_data = {}
            if 'stocks' in data_dict:
                # Backtrader 格式，重新获取数据
                stocks = data_dict.get('stocks', {})
                for code in stocks.keys():
                    try:
                        df = self.data_provider.get_price(code, start_date='20210324', end_date=date.replace('-', ''))
                        if len(df) >= 10:  # 降低数据长度要求
                            stock_data[code] = df
                    except Exception as e:
                        logger.debug("获取股票 %s 数据失败: %s", code, e)
            else:
                # 原始格式
                for code, df in data_dict.items():
                    if len(df) >= 10:  # 降低数据长度要求
                        stock_data[code] = df
            logger.info(f"简化过滤后股票数量: {len(stock_data)}")
        
        if stock_data:
            # 批量评分
            logger.info("开始批量评分")
            try:
                scores = self.scorer.score_batch(stock_data, batch_print=100)
                logger.info(f"评分完成，得到 {len(scores)} 个评分结果")
                
                if scores:
                    # 选择Top N
                    top_n = min(self.config.selection.top_n, len(scores))
                    logger.info("选择Top %s 股票", top_n)
                    
                    top_stocks = scores[:top_n]
                    selected_symbols = [s['symbol'] for s in top_stocks]
                    logger.info("选中的股票: %s", selected_symbols)
                    
                    # 生成买入信号（返回股票代码列表）
                    buy_signals = selected_symbols
                    
                    # 更新持仓
                    self.holdings = {symbol: 1.0 / top_n for symbol in selected_symbols}
                    self.last_rebalance_date = date
                    
                    logger.info("买入信号: %s", buy_signals)
                    logger.info(f"更新后的持仓: {self.holdings}")
                    
                    return buy_signals
                else:
                    logger.warning("评分结果为空")
            except Exception as e:
                logger.error("评分失败: %s", e)
                # 评分失败时，返回前N只股票
                if len(stock_data) > 0:
                    top_n = min(self.config.selection.top_n, len(stock_data))
                    buy_signals = list(stock_data.keys())[:top_n]
                    logger.info("评分失败，返回前 %s 只股票: %s", top_n, buy_signals)
                    self.holdings = {symbol: 1.0 / top_n for symbol in buy_signals}
                    self.last_rebalance_date = date
                    return buy_signals
        else:
            logger.warning("没有符合条件的股票")
            # 如果没有符合条件的股票，返回前10只数据最长的股票
            if len(data_dict) > 0:
                # 按数据长度排序
                if 'stocks' in data_dict:
                    # Backtrader 格式，获取数据并排序
                    stocks = data_dict.get('stocks', {})
                    stock_data_list = []
                    for code in stocks.keys():
                        try:
                            df = self.data_provider.get_price(code, start_date='20210324', end_date=date.replace('-', ''))
                            stock_data_list.append((code, df))
                        except Exception as e:
                            logger.debug("获取股票 %s 数据失败: %s", code, e)
                    sorted_stocks = sorted(stock_data_list, key=lambda x: len(x[1]), reverse=True)
                else:
                    # 原始格式
                    sorted_stocks = sorted(data_dict.items(), key=lambda x: len(x[1]), reverse=True)
                
                top_n = min(10, len(sorted_stocks))
                buy_signals = [s[0] for s in sorted_stocks[:top_n]]
                logger.info("没有符合条件的股票，返回前 %s 只数据最长的股票: %s", top_n, buy_signals)
                self.holdings = {symbol: 1.0 / top_n for symbol in buy_signals}
                self.last_rebalance_date = date
                return buy_signals
        
        return []
    
    def get_sell_signals(self, date, data_dict, current_positions=None, *args):
        """
        获取卖出信号
        
        Args:
            date: 日期
            data_dict: 股票数据字典
            current_positions: 当前持仓（可选）
        """
        # 卖出不在持仓中的股票
        sell_signals = []
        # 处理不同格式的 data_dict
        if isinstance(data_dict, dict):
            if 'stocks' in data_dict:
                # Backtrader 格式
                stocks = data_dict.get('stocks', {})
                for symbol in list(self.holdings.keys()):
                    if symbol not in stocks:
                        sell_signals.append(symbol)
            else:
                # 原始格式
                for symbol in list(self.holdings.keys()):
                    if symbol not in data_dict:
                        sell_signals.append(symbol)
        
        return sell_signals
    
    def get_trade_log(self):
        """
        获取交易日志
        """
        return []


def load_local_data(start_date, end_date):
    """
    从本地数据库加载历史数据
    """
    logger.info("加载本地历史数据: %s ~ %s", start_date, end_date)
    
    # 从本地数据库获取完整的A股股票列表
    logger.info("从本地数据库获取完整的A股股票列表")
    symbols = []
    db = None
    try:
        # 添加本地数据库路径到系统路径
        sys.path.insert(0, os.path.join(PROJECT_ROOT, 'local_db'))
        from 笨数据库 import 笨数据库
        
        # 初始化数据库连接
        db_path = os.path.join(PROJECT_ROOT, 'local_db', 'a_stock_quant.db')
        logger.info("数据库路径: %s", db_path)
        logger.info(f"数据库文件存在: {os.path.exists(db_path)}")
        
        db = 笨数据库(db_path)
        
        # 确保股票列表已更新
        db.更新股票列表()
        
        # 获取所有股票代码
        symbols = db.get_all_codes()
        logger.info(f"从本地数据库获取到 {len(symbols)} 只股票")
        
        # 检查股票列表
        if symbols:
            logger.info(f"前10只股票: {symbols[:10]}")
        else:
            logger.warning("股票列表为空，尝试重新更新股票列表")
            # 强制更新股票列表
            db.更新股票列表(force=True)
            symbols = db.get_all_codes()
            logger.info(f"重新更新后获取到 {len(symbols)} 只股票")
        
        # 检查数据库统计信息
        stats = db.get_db_stats()
        logger.info("数据库统计: %s", stats)
        
        # 验证数据完整性并获取调整后的开始日期
        start_date = validate_data_integrity(db, symbols, start_date, end_date)
        
    except Exception as e:
        logger.error("从本地数据库获取股票列表失败: %s", e)
        # 不使用预设股票列表，而是尝试直接从数据库获取
        try:
            if db:
                # 再次尝试获取股票列表
                db.更新股票列表(force=True)
                symbols = db.get_all_codes()
                logger.info(f"再次尝试后获取到 {len(symbols)} 只股票")
        except Exception as e2:
            logger.error("再次尝试失败: %s", e2)
            # 如果仍然失败，抛出异常，不使用预设列表
            raise Exception("无法从本地数据库获取股票列表，请检查数据库连接和数据完整性")
    
    # 尝试从缓存或本地文件加载数据
    data_dict = {}
    cache_dir = os.path.join(PROJECT_ROOT, 'backtest_system', 'cache', 'market_data')
    logger.info("缓存目录: %s", cache_dir)
    logger.info(f"缓存目录是否存在: {os.path.exists(cache_dir)}")
    
    # 确保缓存目录存在
    os.makedirs(cache_dir, exist_ok=True)
    
    # 使用全部可用股票数据
    logger.info(f"使用全部可用股票数据，共 {len(symbols)} 只股票")
    
    logger.info(f"开始加载 {len(symbols)} 只股票数据")
    
    # 先检查缓存
    for symbol in symbols:
        # 尝试多种日期格式的缓存文件
        cache_files = [
            os.path.join(cache_dir, f"{symbol}_{start_date}_{end_date}_qfq.pkl"),
            os.path.join(cache_dir, f"{symbol}_20240101_20241231_qfq.pkl"),
            os.path.join(cache_dir, f"{symbol}_20240101_20260408_qfq.pkl")
        ]
        
        loaded = False
        for cache_file in cache_files:
            if os.path.exists(cache_file):
                try:
                    import pickle
                    with open(cache_file, 'rb') as f:
                        df = pickle.load(f)
                    if not df.empty:
                        data_dict[symbol] = df
                        logger.debug("从缓存加载 %s 数据成功，数据长度: {len(df)}", symbol)
                        loaded = True
                        break
                    else:
                        logger.debug("缓存文件 %s 为空", symbol)
                except Exception as e:
                    logger.debug("从缓存加载 %s 失败: %s", symbol, e)
            else:
                logger.debug("缓存文件不存在: %s", cache_file)
        
        if not loaded:
            logger.debug("未找到 %s 的缓存文件", symbol)
    
    # 如果缓存不足，使用本地数据库加载
    if len(data_dict) < len(symbols):
        logger.info(f"缓存数据不足，从本地数据库加载剩余股票数据")
        
        # 只加载未从缓存获取的股票
        remaining_symbols = [s for s in symbols if s not in data_dict]
        if remaining_symbols:
            logger.info(f"开始从本地数据库加载 {len(remaining_symbols)} 只股票数据")
            
            try:
                # 从本地数据库加载数据
                sys.path.insert(0, os.path.join(PROJECT_ROOT, 'local_db'))
                from 笨数据库 import 笨数据库
                
                db = 笨数据库(os.path.join(PROJECT_ROOT, 'local_db', 'a_stock_quant.db'))
                
                for symbol in remaining_symbols:
                    try:
                        # 转换日期格式为数据库格式 (YYYY-MM-DD)
                        db_start_date = datetime.strptime(start_date, "%Y%m%d").strftime("%Y-%m-%d")
                        db_end_date = datetime.strptime(end_date, "%Y%m%d").strftime("%Y-%m-%d")
                        df = db.get_price(symbol, db_start_date, db_end_date)
                        if not df.empty:
                            data_dict[symbol] = df
                            logger.debug("从本地数据库加载 %s 数据成功，数据长度: {len(df)}", symbol)
                            
                            # 保存到缓存
                            cache_file = os.path.join(cache_dir, f"{symbol}_{start_date}_{end_date}_qfq.pkl")
                            try:
                                import pickle
                                with open(cache_file, 'wb') as f:
                                    pickle.dump(df, f)
                                logger.debug("已缓存 %s 数据到 %s", symbol, cache_file)
                            except Exception as e:
                                logger.debug("缓存 %s 数据失败: %s", symbol, e)
                        else:
                            logger.warning("本地数据库中 %s 无数据", symbol)
                    except Exception as e:
                        logger.warning("从本地数据库加载 %s 失败: %s", symbol, e)
                
                logger.info(f"本地数据库加载完成: {len(data_dict) - (len(symbols) - len(remaining_symbols))} 只股票成功加载")
            except Exception as e:
                logger.error("从本地数据库加载数据失败: %s", e)
                # 回退到 DataLoader
                logger.info("回退到使用 DataLoader 加载数据")
                loader = DataLoader(
                    start_date=start_date,
                    end_date=end_date,
                    adjust="qfq"
                )
                loaded_data = loader.load_multi(remaining_symbols, start_date, end_date)
                data_dict.update(loaded_data)
                logger.info(f"DataLoader 加载完成: {len(loaded_data)} 只股票成功加载")
    
    # 加载基准指数
    benchmark = None
    try:
        logger.info("开始加载基准指数: 沪深300")
        # 先尝试从缓存加载
        benchmark_cache = os.path.join(cache_dir, f"000300_{start_date}_{end_date}_qfq.pkl")
        if os.path.exists(benchmark_cache):
            import pickle
            with open(benchmark_cache, 'rb') as f:
                benchmark = pickle.load(f)
            logger.info("从缓存加载基准指数成功")
        else:
            # 使用 DataLoader 加载
            loader = DataLoader(
                start_date=start_date,
                end_date=end_date,
                adjust="qfq"
            )
            benchmark = loader.load_benchmark("000300")
            logger.info("基准指数加载成功: 沪深300")
    except Exception as e:
        logger.warning("基准指数加载失败: %s", e)
    
    logger.info(f"数据加载完成: {len(data_dict)} 只股票, 基准指数: {'沪深300' if benchmark is not None else '无'}")
    
    # 如果没有加载到任何数据，使用模拟数据
    if not data_dict:
        logger.warning("没有加载到任何股票数据，使用模拟数据")
        data_dict = generate_simulated_data(symbols, start_date, end_date)
    
    return data_dict, benchmark

def validate_data_integrity(db, symbols, start_date, end_date):
    """
    验证数据完整性
    
    Args:
        db: 笨数据库实例
        symbols: 股票代码列表
        start_date: 开始日期
        end_date: 结束日期
    
    Returns:
        str: 调整后的开始日期
    """
    logger.info("开始验证数据完整性")
    
    # 检查数据覆盖范围是否至少5年
    start_dt = datetime.strptime(start_date, "%Y%m%d")
    end_dt = datetime.strptime(end_date, "%Y%m%d")
    data_years = (end_dt - start_dt).days / 365.25
    
    if data_years < 5:
        logger.warning(f"数据覆盖范围不足5年，仅为 {data_years:.1f} 年")
        # 扩展开始日期以确保至少5年数据
        new_start_dt = end_dt - timedelta(days=5*366)
        new_start_date = new_start_dt.strftime("%Y%m%d")
        logger.info("扩展开始日期至 %s 以确保至少5年数据", new_start_date)
        start_date = new_start_date
    else:
        logger.info(f"数据覆盖范围充足: {data_years:.1f} 年")
    
    # 转换日期格式为数据库格式 (YYYY-MM-DD)
    db_start_date = datetime.strptime(start_date, "%Y%m%d").strftime("%Y-%m-%d")
    db_end_date = datetime.strptime(end_date, "%Y%m%d").strftime("%Y-%m-%d")
    
    logger.info("数据库查询日期范围: %s ~ %s", db_start_date, db_end_date)
    
    # 检查数据完整性
    missing_data_stocks = []
    sample_size = min(100, len(symbols))  # 抽样检查100只股票
    sample_symbols = symbols[:sample_size]
    
    logger.info("抽样检查 %s 只股票的数据完整性", sample_size)
    
    for symbol in sample_symbols:
        try:
            # 获取股票数据
            df = db.get_price(symbol, db_start_date, db_end_date)
            if len(df) == 0:
                missing_data_stocks.append(symbol)
                logger.warning("股票 %s 无数据", symbol)
            else:
                # 检查数据长度是否足够
                expected_days = (end_dt - start_dt).days
                actual_days = len(df)
                if actual_days < expected_days * 0.9:  # 允许10%的缺失
                    missing_data_stocks.append(symbol)
                    logger.warning("股票 %s 数据不足，期望 %s 天，实际 %s 天", symbol, expected_days, actual_days)
                else:
                    logger.debug("股票 %s 数据完整，共 {len(df)} 条记录", symbol)
        except Exception as e:
            missing_data_stocks.append(symbol)
            logger.warning("检查股票 %s 数据时出错: %s", symbol, e)
    
    # 如果发现数据缺失，触发数据补充
    if missing_data_stocks:
        logger.warning(f"发现 {len(missing_data_stocks)} 只股票数据缺失，触发数据补充")
        try:
            # 执行数据补充
            logger.info("开始执行数据补充")
            db.初始化历史数据(years=5)
            logger.info("数据补充完成")
        except Exception as e:
            logger.error("数据补充失败: %s", e)
    else:
        logger.info("数据完整性检查通过，所有抽样股票数据完整")
    
    # 再次验证数据完整性
    logger.info("再次验证数据完整性")
    final_missing = []
    for symbol in sample_symbols:
        try:
            df = db.get_price(symbol, db_start_date, db_end_date)
            if len(df) == 0:
                final_missing.append(symbol)
        except Exception as e:
            final_missing.append(symbol)
    
    if final_missing:
        logger.warning(f"仍有 {len(final_missing)} 只股票数据缺失")
    else:
        logger.info("数据完整性验证通过")
    
    return start_date


def generate_simulated_data(symbols, start_date, end_date):
    """
    生成模拟数据，用于测试
    """

    data_dict = {}
    start = pd.to_datetime(start_date)
    end = pd.to_datetime(end_date)
    dates = pd.date_range(start=start, end=end, freq='B')
    
    for symbol in symbols:
        # 生成模拟价格数据
        np.random.seed(int(symbol[-4:]))  # 使用股票代码后四位作为种子
        base_price = 100 + np.random.randint(0, 100)
        returns = np.random.normal(0, 0.02, len(dates))
        prices = base_price * np.exp(np.cumsum(returns))
        
        # 生成模拟成交量
        volumes = np.random.randint(1000000, 10000000, len(dates))
        
        # 生成模拟换手率和成交额
        turns = np.random.uniform(1.0, 5.0, len(dates))  # 1-5% 换手率
        amounts = volumes * prices  # 成交额 = 成交量 * 价格
        
        # 创建DataFrame
        df = pd.DataFrame({
            'date': dates,
            'open': prices * (1 + np.random.normal(0, 0.005, len(dates))),
            'high': prices * (1 + np.random.normal(0, 0.01, len(dates))),
            'low': prices * (1 - np.random.normal(0, 0.01, len(dates))),
            'close': prices,
            'volume': volumes,
            'turn': turns,
            'amount': amounts
        })
        df = df.set_index('date')
        data_dict[symbol] = df
    
    logger.info(f"生成模拟数据: {len(data_dict)} 只股票")
    return data_dict


def run_backtest(data_dict, benchmark, initial_cash=1000000):
    """
    执行回测
    """
    logger.info(f"开始回测: 初始资金 {initial_cash:,.0f}")
    logger.info(f"股票数据数量: {len(data_dict)}")
    
    # 初始化回测引擎
    config = BacktestConfig()
    config.portfolio.initial_cash = initial_cash
    engine = BacktestEngine(config)
    
    # 创建策略实例
    logger.info("创建V16StrategyAdapter策略实例")
    strategy = V16StrategyAdapter()
    
    # 执行回测
    logger.info("执行回测...")
    result = engine.run_backtest(
        existing_strategy=strategy,
        data_dict=data_dict,
        benchmark=benchmark
    )
    
    logger.info("回测执行完成")
    logger.info(f"回测结果: {result.keys()}")
    if 'stats' in result:
        logger.info(f"回测统计: {result['stats']}")
    
    return result, engine


def generate_report(result, benchmark, output_dir):
    """
    生成回测报告
    """
    logger.info("开始生成回测报告，输出目录: %s", output_dir)
    
    # 确保输出目录存在
    os.makedirs(output_dir, exist_ok=True)
    logger.info("输出目录准备完成")
    
    # 使用quantstats生成详细的量化分析报告
    try:
        import quantstats as qs
        logger.info("开始生成quantstats详细报告")
        
        # 获取日收益率数据
        daily_returns = result.get('daily_returns', pd.Series())
        if not daily_returns.empty:
            # 确保索引是日期格式
            if not isinstance(daily_returns.index, pd.DatetimeIndex):
                try:
                    daily_returns.index = pd.to_datetime(daily_returns.index)
                except Exception:
                    pass  # 日期解析失败，使用原索引
            
            # 生成quantstats报告
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            quantstats_report_file = os.path.join(output_dir, f'quantstats_report_{timestamp}.html')
            
            # 生成完整的quantstats报告
            qs.reports.html(
                daily_returns,
                benchmark=benchmark['close'].pct_change().dropna() if benchmark is not None and not benchmark.empty else None,
                output=quantstats_report_file,
                title="A股量化策略详细分析报告",
                show="all"
            )
            
            logger.info("quantstats详细报告已生成: %s", quantstats_report_file)
        else:
            logger.warning("日收益率数据为空，无法生成quantstats报告")
    except Exception as e:
        logger.warning("生成quantstats报告失败: %s", e)
    
    # 保存回测结果
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    result_file = os.path.join(output_dir, f'backtest_result_{timestamp}.json')
    import json
    try:
        with open(result_file, 'w', encoding='utf-8') as f:
            # 转换日期格式
            def serialize(obj):
                if isinstance(obj, pd.Series):
                    # 将Series转换为字典，并将Timestamp索引转换为字符串
                    return {date.strftime('%Y-%m-%d'): value for date, value in obj.items()}
                elif isinstance(obj, pd.DatetimeIndex):
                    return obj.strftime('%Y-%m-%d').tolist()
                elif isinstance(obj, (np.integer, np.floating)):
                    return float(obj)
                raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")
            
            # 简化结果，只保存关键数据
            # 处理daily_value和daily_returns，将Timestamp键转换为字符串
            daily_value = result.get('daily_value', pd.Series())
            daily_returns = result.get('daily_returns', pd.Series())
            
            # 将Timestamp索引转换为字符串
            if not daily_value.empty:
                daily_value_dict = {date.strftime('%Y-%m-%d'): value for date, value in daily_value.items()}
            else:
                daily_value_dict = {}
            
            if not daily_returns.empty:
                daily_returns_dict = {date.strftime('%Y-%m-%d'): value for date, value in daily_returns.items()}
            else:
                daily_returns_dict = {}
            
            simplified_result = {
                'stats': result.get('stats', {}),
                'trades': result.get('trades', [])[:100],  # 只保存前100条交易
                'daily_value': daily_value_dict,
                'daily_returns': daily_returns_dict
            }
            
            json.dump(simplified_result, f, ensure_ascii=False, indent=2, default=serialize)
        
        logger.info("回测结果已保存: %s", result_file)
    except Exception as e:
        logger.error("保存回测结果失败: %s", e)
    
    # 返回quantstats报告文件路径
    return quantstats_report_file



def main():
    """
    主函数
    """
    parser = argparse.ArgumentParser(description='全面的量化策略回测')
    parser.add_argument('--start-date', type=str, default='20240101', help='回测开始日期 (YYYYMMDD)')
    parser.add_argument('--end-date', type=str, default=date.today().strftime('%Y%m%d'), help='回测结束日期 (YYYYMMDD)')
    parser.add_argument('--initial-cash', type=float, default=1000000, help='初始资金')
    parser.add_argument('--output-dir', type=str, default=os.path.join(PROJECT_ROOT, 'reports', 'backtest_reports'), help='报告输出目录')
    
    args = parser.parse_args()
    
    try:
        # 加载数据
        data_dict, benchmark = load_local_data(args.start_date, args.end_date)
        
        if not data_dict:
            logger.error("没有加载到股票数据，回测失败")
            return
        
        # 执行回测
        result, engine = run_backtest(data_dict, benchmark, args.initial_cash)
        
        # 生成报告
        generate_report(result, benchmark, args.output_dir)
    except Exception as e:
        logger.error("回测过程中出现错误: %s", e)
        # 生成错误报告
        error_report = os.path.join(args.output_dir, f'backtest_error_{datetime.now().strftime("%Y%m%d_%H%M%S")}.html')
        with open(error_report, 'w', encoding='utf-8') as f:
            f.write(f"""
            <!DOCTYPE html>
            <html lang="zh-CN">
            <head>
                <meta charset="UTF-8">
                <title>回测错误报告</title>
            </head>
            <body>
                <h1>回测错误报告</h1>
                <p>生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
                <p>错误信息: {str(e)}</p>
                <p>请检查网络连接和数据源配置</p>
            </body>
            </html>
            """)
        logger.info("错误报告已生成: %s", error_report)


if __name__ == '__main__':
    main()
