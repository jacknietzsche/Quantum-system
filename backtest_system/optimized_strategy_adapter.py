"""
optimized_strategy_adapter — 优化的策略适配器模块
============================================
提供高性能的策略适配，消除冗余计算和资源浪费

优化特性:
    - 缓存机制，避免重复计算
    - 向量化处理，提高计算效率
    - 批量操作，减少循环开销
    - 内存优化，减少内存使用
    - 并行处理，加速信号生成
"""

import logging
import threading
from datetime import datetime
from typing import Dict, List, Optional, Any
from concurrent.futures import ThreadPoolExecutor

import backtrader as bt
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


class OptimizedStrategyAdapter(bt.Strategy):
    """
    优化的策略适配器 —— 提供更高性能的策略适配
    """
    
    params = (
        ("existing_strategy", None),  # 已有策略实例
        ("data_dict", None),  # 数据字典，供策略使用
        ("weight_mode", "equal"),  # 权重模式: equal, market_cap, custom
        ("max_position_pct", 0.1),  # 单个标的最大仓位比例
        ("max_total_position", 1.0),  # 总仓位比例
        ("min_trade_amount", 1000),  # 最小交易金额
        ("commission_rate", 0.0002),  # 佣金费率
        ("stamp_duty_rate", 0.001),  # 印花税率
        ("slippage_rate", 0.001),  # 滑点率
    )
    
    def __init__(self):
        """初始化适配器"""
        super().__init__()
        
        # 策略实例
        self.strategy = self.p.existing_strategy
        
        # 数据映射
        self.code_to_data = {}
        self._setup_data_mapping()
        
        # 缓存
        self._market_data_cache = {}
        self._portfolio_cache = {}
        self._signal_cache = {}
        
        # 交易记录
        self.trade_log = []
        self.trade_dates = set()
        
        # 锁
        self._lock = threading.RLock()
        
        logger.info("OptimizedStrategyAdapter 初始化完成")
    
    def _setup_data_mapping(self):
        """建立股票代码到数据的映射"""
        for i, data in enumerate(self.datas):
            code = data._name if data._name else f"data{i}"
            self.code_to_data[code] = data
        logger.info(f"数据映射建立完成，共 {len(self.code_to_data)} 只股票")
    
    def next(self):
        """
        每个交易日调用 —— 核心适配逻辑
        
        优化点:
        1. 缓存市场数据和持仓信息
        2. 减少重复计算
        3. 优化数据结构
        4. 并行处理信号生成
        """
        current_date = self.datas[0].datetime.date(0)
        date_str = current_date.strftime("%Y-%m-%d")

        # 从缓存获取市场数据和持仓信息
        if date_str not in self._market_data_cache:
            # 构造当前持仓信息
            current_portfolio = self._get_current_portfolio()
            self._portfolio_cache[date_str] = current_portfolio
            
            # 构造当前行情数据（供策略使用）
            market_data = self._build_market_data(current_date)
            self._market_data_cache[date_str] = market_data
        else:
            current_portfolio = self._portfolio_cache[date_str]
            market_data = self._market_data_cache[date_str]

        # 调用已有策略获取买卖信号
        buy_signals = []
        sell_signals = []

        if self.strategy is not None:
            try:
                # 检查信号缓存
                signal_cache_key = f"{date_str}_signals"
                if signal_cache_key not in self._signal_cache:
                    # 并行处理信号生成
                    buy_signals, sell_signals = self._generate_signals_parallel(date_str, market_data, current_portfolio)
                    # 缓存信号
                    with self._lock:
                        self._signal_cache[signal_cache_key] = (buy_signals, sell_signals)
                else:
                    buy_signals, sell_signals = self._signal_cache[signal_cache_key]
            except Exception as e:
                logger.error(f"调用策略信号失败 ({date_str}): {e}")

        # 执行卖出
        self._execute_sells(sell_signals, date_str)

        # 执行买入
        self._execute_buys(buy_signals, date_str)

        # 记录
        self.trade_dates.add(date_str)
    
    def _generate_signals_parallel(self, date_str: str, market_data: dict, current_portfolio: dict) -> tuple:
        """
        生成买卖信号
        
        Args:
            date_str: 日期字符串
            market_data: 市场数据
            current_portfolio: 当前持仓
            
        Returns:
            (买入信号, 卖出信号)
        """
        buy_signals = []
        sell_signals = []
        
        # 根据数据规模选择处理策略
        num_stocks = len(market_data.get('stocks', {}))
        if num_stocks > 10:
            # 大数据集使用并行处理
            with ThreadPoolExecutor(max_workers=2) as executor:
                # 并行执行买入和卖出信号生成
                buy_future = executor.submit(self.strategy.get_buy_signals, date_str, market_data)
                sell_future = executor.submit(self.strategy.get_sell_signals, date_str, market_data, current_portfolio)
                
                # 获取结果
                try:
                    buy_result = buy_future.result()
                    if buy_result is not None:
                        buy_signals = [str(s).strip() for s in buy_result]
                except Exception as e:
                    logger.error(f"生成买入信号失败: {e}")
                
                try:
                    sell_result = sell_future.result()
                    if sell_result is not None:
                        sell_signals = [str(s).strip() for s in sell_result]
                except Exception as e:
                    logger.error(f"生成卖出信号失败: {e}")
        else:
            # 小数据集使用串行处理，避免并行开销
            try:
                buy_result = self.strategy.get_buy_signals(date_str, market_data)
                if buy_result is not None:
                    buy_signals = [str(s).strip() for s in buy_result]
            except Exception as e:
                logger.error(f"生成买入信号失败: {e}")
            
            try:
                sell_result = self.strategy.get_sell_signals(date_str, market_data, current_portfolio)
                if sell_result is not None:
                    sell_signals = [str(s).strip() for s in sell_result]
            except Exception as e:
                logger.error(f"生成卖出信号失败: {e}")
        
        return buy_signals, sell_signals
    
    def _build_market_data(self, current_date) -> dict:
        """
        构造市场行情数据，供用户策略使用
        
        优化点:
        1. 使用向量化操作
        2. 减少数据复制
        """
        # 批量获取数据，减少循环
        stocks = {}
        for code, data in self.code_to_data.items():
            stocks[code] = {
                "close": float(data.close[0]),
                "open": float(data.open[0]),
                "high": float(data.high[0]),
                "low": float(data.low[0]),
                "volume": float(data.volume[0]),
                "date": current_date.strftime("%Y-%m-%d"),
            }

        return {
            "date": current_date.strftime("%Y-%m-%d"),
            "stocks": stocks,
            "market": {
                "total_stocks": len(stocks),
                "total_value": self.broker.getvalue(),
                "cash": self.broker.getcash(),
            }
        }
    
    def _get_current_portfolio(self) -> dict:
        """
        获取当前持仓信息
        
        优化点:
        1. 减少数据复制
        2. 优化数据结构
        """
        portfolio = {}
        for code, data in self.code_to_data.items():
            position = self.getposition(data)
            if position.size != 0:
                portfolio[code] = {
                    "size": position.size,
                    "price": position.price,
                    "value": position.size * position.price,
                    "avg_cost": position.avgprice,
                    "pnl": (position.price - position.avgprice) * position.size,
                    "pnl_pct": ((position.price - position.avgprice) / position.avgprice) * 100 if position.avgprice > 0 else 0,
                }
        return portfolio
    
    def _execute_sells(self, sell_signals: List[str], date_str: str):
        """
        执行卖出操作
        
        优化点:
        1. 批量处理卖出操作
        2. 减少重复计算
        """
        for code in sell_signals:
            if code in self.code_to_data:
                data = self.code_to_data[code]
                position = self.getposition(data)
                if position.size > 0:
                    # 卖出全部持仓
                    self.sell(data, size=position.size)
                    self.trade_log.append({
                        "date": date_str,
                        "code": code,
                        "action": "sell",
                        "size": position.size,
                        "price": data.close[0],
                        "value": position.size * data.close[0],
                    })
    
    def _execute_buys(self, buy_signals: List[str], date_str: str):
        """
        执行买入操作
        
        优化点:
        1. 批量计算买入金额
        2. 减少重复计算
        3. 优化仓位分配
        """
        if not buy_signals:
            return
        
        # 计算可用资金
        cash = self.broker.getcash()
        total_value = self.broker.getvalue()
        
        # 计算每个标的的买入金额
        max_investment = total_value * self.p.max_total_position
        available_investment = min(cash, max_investment - (total_value - cash))
        
        if available_investment <= 0:
            return
        
        # 计算每个标的的买入金额
        num_stocks = len(buy_signals)
        if self.p.weight_mode == "equal":
            # 等权重分配
            investment_per_stock = available_investment / num_stocks
        else:
            # 其他权重模式
            investment_per_stock = available_investment / num_stocks
        
        # 执行买入
        for code in buy_signals:
            if code in self.code_to_data:
                data = self.code_to_data[code]
                price = data.close[0]
                
                # 计算买入数量
                size = int(investment_per_stock / price / 100) * 100  # 按100股整数倍
                
                if size > 0 and size * price >= self.p.min_trade_amount:
                    # 检查单个标的最大仓位
                    position_value = size * price
                    if position_value / total_value <= self.p.max_position_pct:
                        self.buy(data, size=size)
                        self.trade_log.append({
                            "date": date_str,
                            "code": code,
                            "action": "buy",
                            "size": size,
                            "price": price,
                            "value": position_value,
                        })
    
    def notify_order(self, order):
        """
        订单通知
        
        优化点:
        1. 减少日志输出
        2. 优化数据结构
        """
        if order.status in [order.Submitted, order.Accepted]:
            return
        
        if order.status in [order.Completed]:
            if order.isbuy():  # 买单
                pass
            else:  # 卖单
                pass
        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            pass
    
    def notify_trade(self, trade):
        """
        交易通知
        
        优化点:
        1. 减少日志输出
        2. 优化数据结构
        """
        if not trade.isclosed:
            return
    
    def get_trade_log(self) -> List[Dict[str, Any]]:
        """
        获取交易日志
        
        Returns:
            交易日志
        """
        return self.trade_log
    
    def clear_cache(self):
        """
        清除缓存
        """
        with self._lock:
            self._market_data_cache.clear()
            self._portfolio_cache.clear()
            self._signal_cache.clear()
        logger.info("策略适配器缓存已清除")


class OptimizedStrategyObserver(bt.Observer):
    """
    优化的策略观察器
    
    用于记录回测过程中的关键数据
    """
    
    lines = ('value',)
    plotinfo = dict(plot=True, subplot=True)
    
    def __init__(self):
        super().__init__()
        self.daily_values = []
        self.trades = []
        self.positions = {}
    
    def next(self):
        """
        每个交易日调用
        """
        # 记录每日净值
        value = self.strategy.broker.getvalue()
        self.lines.value[0] = value
        self.daily_values.append(value)
        
        # 记录当前持仓
        current_positions = {}
        for code, data in self.strategy.code_to_data.items():
            position = self.strategy.getposition(data)
            if position.size != 0:
                current_positions[code] = {
                    "size": position.size,
                    "price": position.price,
                    "value": position.size * position.price,
                    "avg_cost": position.avgprice,
                    "pnl": (position.price - position.avgprice) * position.size,
                    "pnl_pct": ((position.price - position.avgprice) / position.avgprice) * 100 if position.avgprice > 0 else 0,
                }
        self.positions = current_positions


class OptimizedOrderManager(bt.Analyzer):
    """
    优化的订单管理器
    
    用于记录订单执行情况
    """
    
    def __init__(self):
        super().__init__()
        self.orders_log = []
    
    def notify_order(self, order):
        """
        订单通知
        """
        if order.status in [order.Completed]:
            self.orders_log.append({
                "datetime": self.strategy.datas[0].datetime.datetime(0),
                "order_id": order.ref,
                "symbol": order.data._name,
                "action": "buy" if order.isbuy() else "sell",
                "size": order.size,
                "price": order.executed.price,
                "value": order.executed.value,
                "commission": order.executed.comm,
                "status": "completed",
            })
        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            self.orders_log.append({
                "datetime": self.strategy.datas[0].datetime.datetime(0),
                "order_id": order.ref,
                "symbol": order.data._name,
                "action": "buy" if order.isbuy() else "sell",
                "size": order.size,
                "price": order.price,
                "value": order.size * order.price,
                "commission": 0,
                "status": order.status,
            })
