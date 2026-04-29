#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
backtest_v16_optimized.py — V16 优化版策略回测

使用 V16Scorer 进行回测，验证优化后的策略性能

优化重点:
- 提升风险调整后收益
- 降低最大回撤
- 增强策略稳定性
- 调仓周期控制在7个自然日以内

回测结果将与之前的版本进行对比
"""

import os
import sys
import logging
import argparse
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import numpy as np
import quantstats as qs

# 项目根目录
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.config import QuantConfig, SelectionConfig
from core.strategy import V16Scorer, StockFilter
from core.data import UnifiedDataFetcher

# 日志配置
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(os.path.join(PROJECT_ROOT, 'logs', 'backtest_v16.log'), encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)


def load_stock_data(data_provider, symbols, start_date, end_date):
    """
    加载股票数据
    """
    stock_data = {}
    for symbol in symbols:
        try:
            df = data_provider.get_daily(symbol, days=365)
            if df is not None and len(df) > 0:
                stock_data[symbol] = df
        except Exception as e:
            logger.warning("加载 %s 数据失败: %s", symbol, e)
    return stock_data


def run_backtest(
    start_date, 
    end_date, 
    top_n=10, 
    rebalance_days=5,
    initial_cash=1000000
):
    """
    运行回测
    """
    logger.info("开始 V16 优化版策略回测: %s 到 %s", start_date, end_date)
    logger.info("参数: top_n=%s, rebalance_days=%s, initial_cash=%s", top_n, rebalance_days, initial_cash)
    
    # 配置
    config = QuantConfig()
    config.selection.top_n = top_n
    config.selection.rebalance_days = rebalance_days
    
    # 数据提供者
    data_provider = UnifiedDataFetcher()
    
    # 股票过滤器
    stock_filter = StockFilter(config.selection)
    
    # V16 评分器
    scorer = V16Scorer(config)
    
    # 加载股票列表
    stock_list_df = data_provider.get_stock_list()
    symbols = stock_list_df['symbol'].tolist()
    logger.info(f"可用股票数量: {len(symbols)}")
    
    # 加载数据
    stock_data = load_stock_data(data_provider, symbols, start_date, end_date)
    logger.info(f"成功加载 {len(stock_data)} 只股票数据")
    
    # 过滤股票
    stock_data = stock_filter.filter_by_data(stock_data)
    stock_data = stock_filter.filter_by_liquidity(stock_data)
    stock_data = stock_filter.filter_by_suspended_days(stock_data)
    logger.info(f"过滤后股票数量: {len(stock_data)}")
    
    if not stock_data:
        logger.error("没有可用的股票数据，回测失败")
        return None
    
    # 生成回测日期列表
    all_dates = sorted(list(set(
        date for df in stock_data.values() for date in df.index
    )))
    backtest_dates = [d for d in all_dates if d >= start_date and d <= end_date]
    
    if not backtest_dates:
        logger.error("没有可用的回测日期")
        return None
    
    logger.info(f"回测日期范围: {backtest_dates[0]} 到 {backtest_dates[-1]}")
    logger.info(f"回测日期数量: {len(backtest_dates)}")
    
    # 回测结果
    portfolio = {
        'date': [],
        'cash': [],
        'holdings': [],
        'total_assets': [],
        'daily_return': []
    }
    
    # 初始化
    cash = initial_cash
    holdings = {}
    last_rebalance_date = None
    
    for i, current_date in enumerate(backtest_dates):
        logger.info("处理日期: %s", current_date)
        
        # 计算每日收益
        if i > 0:
            prev_date = backtest_dates[i-1]
            daily_return = 0
            for symbol, shares in holdings.items():
                if symbol in stock_data:
                    df = stock_data[symbol]
                    if prev_date in df.index and current_date in df.index:
                        prev_price = df.loc[prev_date, 'close']
                        curr_price = df.loc[current_date, 'close']
                        daily_return += shares * (curr_price - prev_price)
            
            cash += daily_return
            portfolio['daily_return'].append(daily_return / (cash - daily_return) if (cash - daily_return) > 0 else 0)
        else:
            portfolio['daily_return'].append(0)
        
        # 调仓
        if last_rebalance_date is None or (current_date - last_rebalance_date).days >= rebalance_days:
            logger.info("执行调仓: %s", current_date)
            
            # 准备评分数据
            scoring_data = {}
            for symbol, df in stock_data.items():
                if current_date in df.index:
                    # 获取当前日期之前的数据
                    symbol_data = df[df.index <= current_date]
                    if len(symbol_data) >= 20:
                        scoring_data[symbol] = symbol_data
            
            logger.info(f"参与评分的股票数量: {len(scoring_data)}")
            
            if scoring_data:
                # 批量评分
                scores = scorer.score_batch(scoring_data, batch_print=100)
                
                if scores:
                    # 选择Top N
                    top_stocks = scores[:top_n]
                    selected_symbols = [s['symbol'] for s in top_stocks]
                    
                    logger.info("选中的股票: %s", selected_symbols)
                    
                    # 计算每只股票的权重（等权）
                    weight_per_stock = 1.0 / top_n
                    total_investment = cash * 0.95  # 保留5%现金
                    
                    # 卖出不在选中列表中的股票
                    for symbol in list(holdings.keys()):
                        if symbol not in selected_symbols:
                            if symbol in stock_data and current_date in stock_data[symbol].index:
                                price = stock_data[symbol].loc[current_date, 'close']
                                cash += holdings[symbol] * price
                            del holdings[symbol]
                    
                    # 买入新选中的股票
                    for symbol in selected_symbols:
                        if symbol in stock_data and current_date in stock_data[symbol].index:
                            price = stock_data[symbol].loc[current_date, 'close']
                            investment = total_investment * weight_per_stock
                            shares = int(investment / price)
                            holdings[symbol] = shares
                            cash -= shares * price
                    
                    last_rebalance_date = current_date
        
        # 计算总资产
        total_assets = cash
        for symbol, shares in holdings.items():
            if symbol in stock_data and current_date in stock_data[symbol].index:
                price = stock_data[symbol].loc[current_date, 'close']
                total_assets += shares * price
        
        # 记录结果
        portfolio['date'].append(current_date)
        portfolio['cash'].append(cash)
        portfolio['holdings'].append(dict(holdings))
        portfolio['total_assets'].append(total_assets)
    
    # 生成回测结果DataFrame
    portfolio_df = pd.DataFrame(portfolio)
    portfolio_df.set_index('date', inplace=True)
    
    # 计算收益率
    portfolio_df['returns'] = portfolio_df['total_assets'].pct_change().fillna(0)
    
    logger.info(f"回测完成，总交易日: {len(portfolio_df)}")
    logger.info(f"最终总资产: {portfolio_df['total_assets'].iloc[-1]:.2f}")
    logger.info(f"总收益率: {(portfolio_df['total_assets'].iloc[-1] / initial_cash - 1) * 100:.2f}%")
    
    return portfolio_df


def generate_report(portfolio_df, output_dir):
    """
    生成回测报告
    """
    if portfolio_df is None or len(portfolio_df) == 0:
        logger.error("没有回测数据，无法生成报告")
        return
    
    # 确保输出目录存在
    os.makedirs(output_dir, exist_ok=True)
    
    # 生成quantstats报告
    returns = portfolio_df['returns']
    
    # 报告文件名
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    report_file = os.path.join(output_dir, f'quantstats_v16_optimized_{timestamp}.html')
    
    # 生成HTML报告
    qs.reports.html(returns, output=report_file, title='V16 优化版策略回测报告')
    logger.info("回测报告已生成: %s", report_file)
    
    # 计算关键指标
    metrics = {
        '总收益率': (portfolio_df['total_assets'].iloc[-1] / portfolio_df['total_assets'].iloc[0] - 1) * 100,
        '年化收益率': qs.stats.annual_return(returns) * 100,
        '最大回撤': qs.stats.max_drawdown(returns) * 100,
        '夏普比率': qs.stats.sharpe(returns),
        '索提诺比率': qs.stats.sortino(returns),
        '卡玛比率': qs.stats.calmar(returns),
        '胜率': qs.stats.win_rate(returns),
        '平均收益': qs.stats.avg_return(returns) * 100,
        '平均亏损': qs.stats.avg_loss(returns) * 100,
        '收益波动率': qs.stats.volatility(returns) * 100,
    }
    
    # 打印指标
    logger.info("关键绩效指标:")
    for key, value in metrics.items():
        logger.info("%s: {value:.2f}", key)
    
    # 保存指标到文件
    metrics_file = os.path.join(output_dir, f'metrics_v16_optimized_{timestamp}.txt')
    with open(metrics_file, 'w', encoding='utf-8') as f:
        f.write('V16 优化版策略回测指标\n')
        f.write('=' * 50 + '\n')
        for key, value in metrics.items():
            f.write(f"{key}: {value:.2f}\n")
    
    logger.info("指标文件已生成: %s", metrics_file)
    
    return report_file, metrics


def main():
    """
    主函数
    """
    parser = argparse.ArgumentParser(description='V16 优化版策略回测')
    parser.add_argument('--start-date', type=str, default='2024-01-01', help='回测开始日期 (YYYY-MM-DD)')
    parser.add_argument('--end-date', type=str, default='2024-12-31', help='回测结束日期 (YYYY-MM-DD)')
    parser.add_argument('--top-n', type=int, default=10, help='每轮选择的股票数量')
    parser.add_argument('--rebalance-days', type=int, default=5, help='调仓间隔（交易日）')
    parser.add_argument('--initial-cash', type=float, default=1000000, help='初始资金')
    parser.add_argument('--output-dir', type=str, default=os.path.join(PROJECT_ROOT, 'reports', 'backtest_reports'), help='报告输出目录')
    
    args = parser.parse_args()
    
    # 转换日期
    start_date = pd.to_datetime(args.start_date)
    end_date = pd.to_datetime(args.end_date)
    
    # 运行回测
    portfolio_df = run_backtest(
        start_date=start_date,
        end_date=end_date,
        top_n=args.top_n,
        rebalance_days=args.rebalance_days,
        initial_cash=args.initial_cash
    )
    
    # 生成报告
    if portfolio_df is not None:
        generate_report(portfolio_df, args.output_dir)


if __name__ == '__main__':
    main()
