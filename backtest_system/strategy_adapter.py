"""
StrategyAdapter 策略适配模块
==============================
核心功能：将已有的策略类无缝桥接到 Backtrader 框架。

适配策略接口规范:
    class MyExistingStrategy:
        def __init__(self, params: dict)
        def get_buy_signals(self, date, data) -> List[str]        # 返回买入代码列表
        def get_sell_signals(self, date, data, portfolio) -> List[str]  # 返回卖出代码列表

本适配器继承 bt.Strategy，在 next() 中调用上述接口，自动处理:
    - 仓位管理（等权重、单票上限、总仓位上限）
    - 交易成本（手续费、滑点、印花税）
    - 交易记录（用于后续报告分析）
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional, Any

import backtrader as bt
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


class StrategyObserver(bt.Analyzer):
    """
    策略交易观察器 —— 记录每笔交易和每日持仓快照
    """
    def __init__(self):
        self.trades = []       # 交易记录列表
        self.daily_values = [] # 每日净值
        self.daily_cash = []   # 每日现金
        self.positions = {}    # 当前持仓 {code: size}
        self._trade_counter = 0
        self._trade_data = {}  # 跟踪开仓信息 {data_ref: {size, price}}

    def notify_trade(self, trade):
        """交易完成通知"""
        if trade.isclosed:
            self._trade_counter += 1
            code = trade.data._name if hasattr(trade.data, "_name") else str(trade.data)

            # 提取交易信息（兼容不同版本）
            pnl = 0.0
            pnlcomm = 0.0
            commission = 0.0
            size = 0
            price = 0.0

            try:
                pnl = float(trade.pnl) if hasattr(trade, "pnl") else 0.0
            except (AttributeError, TypeError):
                pass
            try:
                pnlcomm = float(trade.pnlcomm) if hasattr(trade, "pnlcomm") else 0.0
            except (AttributeError, TypeError):
                pass
            try:
                commission = float(trade.commission) if hasattr(trade, "commission") else 0.0
            except (AttributeError, TypeError):
                pass
            try:
                size = int(trade.size) if hasattr(trade, "size") else 0
            except (AttributeError, TypeError):
                pass
            try:
                price = float(trade.price) if hasattr(trade, "price") else 0.0
            except (AttributeError, TypeError):
                pass

            # 获取日期
            try:
                buy_date = bt.num2date(trade.dtopen).strftime("%Y-%m-%d")
            except Exception as e:
                logger.debug("buy_date conversion failed: %s", e)
                buy_date = ""
            try:
                sell_date = bt.num2date(trade.dtclose).strftime("%Y-%m-%d")
            except Exception as e:
                logger.debug("sell_date conversion failed: %s", e)
                sell_date = ""

            # 计算收益率
            cost_basis = abs(price * size) if price > 0 and size != 0 else 1.0
            pnl_pct = (pnlcomm / cost_basis * 100) if cost_basis > 0 else 0.0

            self.trades.append({
                "id": self._trade_counter,
                "code": code,
                "buy_date": buy_date,
                "sell_date": sell_date,
                "buy_price": round(price, 3),
                "sell_price": round(price, 3),
                "size": size,
                "pnl": round(pnl, 2),
                "pnl_pct": round(pnl_pct, 2),
                "commission": round(commission, 2),
            })

    def next(self):
        """每日记录净值"""
        self.daily_values.append(self.strategy.broker.getvalue())
        self.daily_cash.append(self.strategy.broker.getcash())
        # 记录持仓
        pos = {}
        for data in self.strategy.datas:
            size = self.strategy.getposition(data).size
            if size != 0:
                name = data._name if hasattr(data, "_name") else str(data)
                pos[name] = {
                    "size": int(size),
                    "price": data.close[0],
                    "value": size * data.close[0],
                }
        self.positions = pos


class OrderManager(bt.Analyzer):
    """
    委托管理器 —— 跟踪每日发出的订单
    """
    def __init__(self):
        self.orders_log = []

    def notify_order(self, order):
        code = order.data._name if hasattr(order.data, "_name") else str(order.data)
        # order.executed.dt 是回测日期
        try:
            dt = order.executed.dt if order.executed.dt else datetime.now()
        except AttributeError:
            dt = datetime.now()
        date_str = dt.strftime("%Y-%m-%d") if hasattr(dt, "strftime") else str(dt)

        # Backtrader order status
        status_map = {
            bt.Order.Created: "Created",
            bt.Order.Submitted: "Submitted",
            bt.Order.Accepted: "Accepted",
            bt.Order.Partial: "Partial",
            bt.Order.Completed: "Completed",
            bt.Order.Canceled: "Canceled",
            bt.Order.Rejected: "Rejected",
            bt.Order.Margin: "Margin",
            bt.Order.Expired: "Expired",
        }
        status = status_map.get(order.status, str(order.status))

        exec_price = order.executed.price if order.executed else 0
        if exec_price == 0:
            exec_price = order.created.price if order.created else 0
        if exec_price == 0:
            try:
                exec_price = order.data.close[0]
            except (IndexError, AttributeError):
                exec_price = 0

        self.orders_log.append({
            "date": date_str,
            "code": code,
            "type": "buy" if order.isbuy() else "sell",
            "size": int(order.size),
            "price": round(float(exec_price), 3),
            "status": status,
            "commission": float(order.executed.comm) if order.executed and order.executed.comm else 0,
        })


class BacktraderStrategyAdapter(bt.Strategy):
    """
    策略适配器 —— 将用户已有策略桥接到 Backtrader

    用法:
        adapter = BacktraderStrategyAdapter(
            existing_strategy=my_strategy_instance,
            data_dict=data_dict,           # {code: DataFrame}
            params={
                "max_position_pct": 0.10,
                "max_total_position": 0.80,
            }
        )
        cerebro.addstrategy(BacktraderStrategyAdapter, ...)
    """

    params = (
        # 仓位管理
        ("existing_strategy", None),       # 已有策略实例
        ("data_dict", {}),                 # {code: DataFrame} 所有股票数据
        ("weight_mode", "equal"),          # equal / custom
        ("max_position_pct", 0.10),        # 单票仓位上限
        ("max_total_position", 0.80),      # 总仓位上限
        ("min_trade_amount", 100),         # 最小交易手数（股）
        # 交易参数
        ("commission_rate", 0.0002),       # 手续费率
        ("stamp_duty_rate", 0.001),        # 印花税率（卖出）
        ("slippage_rate", 0.001),          # 滑点率
    )

    def __init__(self):
        """初始化适配器"""
        self.strategy = self.p.existing_strategy
        self.data_dict = self.p.data_dict
        self.trade_log = []

        # 构建数据映射: code → data feed
        self.code_to_data = {}
        for data in self.datas:
            name = data._name if hasattr(data, "_name") else str(data)
            # 尝试多种名称格式匹配
            code = self._extract_code(name)
            self.code_to_data[code] = data

        # 交易计数器
        self._order_count = 0
        self._trade_dates = set()

        logger.info(f"策略适配器初始化完成，加载 {len(self.code_to_data)} 只股票")

    # ================================================================
    # 核心回测逻辑
    # ================================================================

    def next(self):
        """
        每个交易日调用 —— 核心适配逻辑

        1. 获取当前日期
        2. 构造策略需要的 data 格式
        3. 调用已有策略的买卖信号接口
        4. 执行买入/卖出操作
        """
        current_date = self.datas[0].datetime.date(0)
        date_str = current_date.strftime("%Y-%m-%d")

        # 构造当前持仓信息
        current_portfolio = self._get_current_portfolio()

        # 构造当前行情数据（供策略使用）
        market_data = self._build_market_data(current_date)

        # 调用已有策略获取买卖信号
        buy_signals = []
        sell_signals = []

        if self.strategy is not None:
            try:
                buy_signals = self.strategy.get_buy_signals(date_str, market_data)
                if buy_signals is None:
                    buy_signals = []
                buy_signals = [str(s).strip() for s in buy_signals]

                sell_signals = self.strategy.get_sell_signals(date_str, market_data, current_portfolio)
                if sell_signals is None:
                    sell_signals = []
                sell_signals = [str(s).strip() for s in sell_signals]
            except Exception as e:
                logger.error(f"调用策略信号失败 ({date_str}): {e}")

        # 执行卖出
        self._execute_sells(sell_signals, date_str)

        # 执行买入
        self._execute_buys(buy_signals, date_str)

        # 记录
        self._trade_dates.add(date_str)

    def stop(self):
        """回测结束"""
        logger.info(f"回测结束，共交易 {len(self._trade_dates)} 个交易日")

    # ================================================================
    # 交易执行
    # ================================================================

    def _execute_buys(self, signals: List[str], date_str: str):
        """执行买入操作"""
        if not signals:
            return

        total_value = self.broker.getvalue()
        current_stock_value = self._get_stock_value()
        available_for_buy = total_value * self.p.max_total_position - current_stock_value

        if available_for_buy <= 0:
            logger.debug(f"[{date_str}] 总仓位已达上限，跳过买入")
            return

        # 过滤已持仓的股票
        held_codes = set(self._get_held_codes())
        signals = [s for s in signals if s not in held_codes]

        if not signals:
            return

        # 等权重分配
        n_signals = len(signals)
        target_per_stock = min(
            total_value * self.p.max_position_pct,
            available_for_buy / n_signals if n_signals > 0 else 0,
        )

        for code in signals:
            data = self.code_to_data.get(code)
            if data is None:
                logger.debug(f"[{date_str}] 买入信号 {code} 无对应数据源，跳过")
                continue

            # 检查是否有有效价格
            if data.close[0] <= 0:
                continue

            # 计算买入数量（向下取整到 100 的倍数）
            buy_price = data.close[0] * (1 + self.p.slippage_rate)  # 含滑点
            size = int(target_per_stock / buy_price / self.p.min_trade_amount) * self.p.min_trade_amount

            if size <= 0:
                continue

            # 检查剩余可用资金
            cost = size * buy_price
            if cost > self.broker.getcash():
                logger.debug(f"[{date_str}] 资金不足，{code} 需要 {cost:.0f}，可用 {self.broker.getcash():.0f}")
                continue

            # 执行买入
            self._order_count += 1
            self.buy(data=data, size=size)
            self.trade_log.append({
                "date": date_str,
                "code": code,
                "action": "buy",
                "price": round(data.close[0], 3),
                "size": size,
                "value": round(size * data.close[0], 2),
            })
            logger.debug(f"[{date_str}] 买入 {code}: {size}股 @ {data.close[0]:.2f}")

    def _execute_sells(self, signals: List[str], date_str: str):
        """执行卖出操作"""
        if not signals:
            return

        held_codes = self._get_held_codes()

        for code in signals:
            if code not in held_codes:
                continue

            data = self.code_to_data.get(code)
            if data is None:
                continue

            position = self.getposition(data)
            if position.size == 0:
                continue

            # 卖出全部持仓
            self._order_count += 1
            self.sell(data=data, size=position.size)
            self.trade_log.append({
                "date": date_str,
                "code": code,
                "action": "sell",
                "price": round(data.close[0], 3),
                "size": int(position.size),
                "value": round(position.size * data.close[0], 2),
            })
            logger.debug(f"[{date_str}] 卖出 {code}: {position.size}股 @ {data.close[0]:.2f}")

    # ================================================================
    # 辅助方法
    # ================================================================

    def _get_current_portfolio(self) -> dict:
        """
        获取当前持仓信息，格式与用户策略期望一致

        Returns:
            {code: {"size": int, "price": float, "value": float, "pnl_pct": float}}
        """
        portfolio = {}
        for code, data in self.code_to_data.items():
            position = self.getposition(data)
            if position.size != 0:
                current_price = data.close[0]
                avg_cost = position.price if position.price > 0 else current_price
                pnl_pct = (current_price - avg_cost) / avg_cost * 100 if avg_cost > 0 else 0
                portfolio[code] = {
                    "size": int(position.size),
                    "price": round(current_price, 3),
                    "avg_cost": round(avg_cost, 3),
                    "value": round(position.size * current_price, 2),
                    "pnl_pct": round(pnl_pct, 2),
                }
        return portfolio

    def _build_market_data(self, current_date) -> dict:
        """
        构造市场行情数据，供用户策略使用

        Returns:
            {
                "date": "2025-01-15",
                "stocks": {
                    "600519": {"close": 1800.0, "open": 1790, "high": 1810, ...},
                    ...
                },
                "market": {"total_stocks": 50, ...}
            }
        """
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

    def _get_held_codes(self) -> List[str]:
        """获取当前持仓的股票代码列表"""
        codes = []
        for code, data in self.code_to_data.items():
            if self.getposition(data).size != 0:
                codes.append(code)
        return codes

    def _get_stock_value(self) -> float:
        """获取当前持仓股票总市值"""
        total = 0.0
        for data in self.datas:
            pos = self.getposition(data)
            if pos.size != 0:
                total += pos.size * data.close[0]
        return total

    @staticmethod
    def _extract_code(name: str) -> str:
        """
        从 data feed 名称中提取纯股票代码
        处理格式: "600519", "sh.600519", "600519_SH", "stock_600519" 等
        """
        import re
        # 提取纯数字代码
        match = re.search(r"(\d{6})", name)
        if match:
            return match.group(1)
        return name

    def get_trade_log(self) -> list:
        """获取完整交易记录"""
        return self.trade_log


class EqualWeightStrategy(bt.Strategy):
    """
    内置等权重策略 —— 用于测试和基准对比

    简单规则：
    - 每月第一个交易日调仓
    - 等权重买入所有股票
    - 不做择时
    """

    params = (
        ("rebalance_days", 20),       # 调仓间隔（交易日）
        ("max_position_pct", 0.10),   # 单票仓位上限
        ("max_total_position", 0.80), # 总仓位上限
    )

    def __init__(self):
        self.day_count = 0

    def next(self):
        self.day_count += 1

        if self.day_count % self.p.rebalance_days != 1:
            return

        total_value = self.broker.getvalue()
        n_data = len(self.datas)
        if n_data == 0:
            return

        target_pct = min(self.p.max_position_pct, self.p.max_total_position / n_data)
        target_value = total_value * target_pct

        # 先卖出
        for data in self.datas:
            pos = self.getposition(data)
            if pos.size > 0:
                self.sell(data=data, size=pos.size)

        # 再买入
        for data in self.datas:
            if data.close[0] <= 0:
                continue
            size = int(target_value / data.close[0] / 100) * 100
            if size > 0 and size * data.close[0] <= self.broker.getcash():
                self.buy(data=data, size=size)
