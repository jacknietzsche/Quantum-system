"""
core.engine — 统一 Backtrader 回测引擎层
========================================
整合 backtest_system/backtest_engine.py + strategy_adapter.py + v14_adapter.py

提供:
  1. BacktestEngine — 封装 Backtrader 核心（Cerebro / Analyzers / A股成本模型）
  2. StrategyObserver — 交易观察器（记录每笔交易 + 每日净值）
  3. OrderManager — 委托管理器（跟踪订单状态）
  4. BacktraderStrategyAdapter — 策略适配器（桥接用户策略 → bt.Strategy）
  5. EqualWeightStrategy — 内置等权重基准策略
  6. V14StrategyAdapter — v14 量化选股策略回测适配器
  7. V15BacktestRunner — v15 一键回测运行器

设计原则:
  - 所有回测必须从此入口，禁止直接操作 Cerebro
  - 交易成本统一为 A 股模型（佣金+印花税+滑点）
  - 策略只需实现 get_buy_signals/get_sell_signals 即可对接
"""

import sys
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path

import backtrader as bt
import pandas as pd
import numpy as np

from core.config import (
    QuantConfig, TradeConfig, PortfolioConfig, RiskConfig,
    BacktestEngineConfig, DataSourceConfig,
)

logger = logging.getLogger(__name__)

# 项目根目录（v14 模块所在位置）
_PROJECT_ROOT = Path(__file__).resolve().parent.parent


# ================================================================
# A股交易成本模型
# ================================================================

class ChinaStockCommission(bt.CommInfoBase):
    """
    A 股交易成本模型

    买入: 手续费（佣金）+ 滑点
    卖出: 手续费（佣金）+ 滑点 + 印花税
    """

    params = (
        ("commission_rate", 0.0002),     # 佣金费率
        ("stamp_duty_rate", 0.001),      # 印花税率（仅卖出）
        ("slippage_rate", 0.001),        # 滑点率
        ("min_commission", 5.0),         # 最低佣金
        ("stocklike", True),
        ("commtype", bt.CommInfoBase.COMM_PERC),
        ("percabs", True),
    )

    def _getcommission(self, size, price, pseudoexec):
        """计算手续费"""
        value = abs(size) * price
        commission = max(value * self.p.commission_rate, self.p.min_commission)
        if size < 0:
            commission += abs(size) * price * self.p.stamp_duty_rate
        commission += abs(size) * price * self.p.slippage_rate
        return commission


def _apply_china_commission(cerebro, cfg: QuantConfig):
    """统一设置 A 股交易成本"""
    comm = ChinaStockCommission(
        commission=cfg.trade.commission_rate,
        stamp_duty_rate=cfg.trade.stamp_duty_rate,
        slippage_rate=cfg.trade.slippage_rate,
        min_commission=cfg.trade.commission_min,
    )
    cerebro.broker.addcommissioninfo(comm)
    return comm


# ================================================================
# StrategyObserver — 交易观察器
# ================================================================

class StrategyObserver(bt.Analyzer):
    """策略交易观察器 — 记录每笔交易和每日持仓快照"""

    def __init__(self):
        self.trades = []
        self.daily_values = []
        self.daily_cash = []
        self.positions = {}
        self._trade_counter = 0

    def notify_trade(self, trade):
        if trade.isclosed:
            self._trade_counter += 1
            code = trade.data._name if hasattr(trade.data, "_name") else str(trade.data)

            pnl = pnlcomm = commission = 0.0
            size = 0
            price = 0.0
            try: pnl = float(trade.pnl)
            except Exception: pass
            try: pnlcomm = float(trade.pnlcomm)
            except Exception: pass
            try: commission = float(trade.commission)
            except Exception: pass
            try: size = int(trade.size)
            except Exception: pass
            try: price = float(trade.price)
            except Exception: pass

            try: buy_date = bt.num2date(trade.dtopen).strftime("%Y-%m-%d")
            except Exception: buy_date = ""
            try: sell_date = bt.num2date(trade.dtclose).strftime("%Y-%m-%d")
            except Exception: sell_date = ""

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
        self.daily_values.append(self.strategy.broker.getvalue())
        self.daily_cash.append(self.strategy.broker.getcash())
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


# ================================================================
# OrderManager — 委托管理器
# ================================================================

class OrderManager(bt.Analyzer):
    """委托管理器 — 跟踪每日发出的订单"""

    def __init__(self):
        self.orders_log = []

    def notify_order(self, order):
        code = order.data._name if hasattr(order.data, "_name") else str(order.data)
        try:
            dt = order.executed.dt if order.executed.dt else datetime.now()
        except AttributeError:
            dt = datetime.now()
        date_str = dt.strftime("%Y-%m-%d") if hasattr(dt, "strftime") else str(dt)

        status_map = {
            bt.Order.Created: "Created", bt.Order.Submitted: "Submitted",
            bt.Order.Accepted: "Accepted", bt.Order.Partial: "Partial",
            bt.Order.Completed: "Completed", bt.Order.Canceled: "Canceled",
            bt.Order.Rejected: "Rejected", bt.Order.Margin: "Margin",
            bt.Order.Expired: "Expired",
        }

        exec_price = 0
        if order.executed:
            exec_price = order.executed.price
        if exec_price == 0 and order.created:
            exec_price = order.created.price
        if exec_price == 0:
            try: exec_price = order.data.close[0]
            except Exception: pass

        self.orders_log.append({
            "date": date_str,
            "code": code,
            "type": "buy" if order.isbuy() else "sell",
            "size": int(order.size),
            "price": round(float(exec_price), 3),
            "status": status_map.get(order.status, str(order.status)),
            "commission": float(order.executed.comm) if order.executed and order.executed.comm else 0,
        })


# ================================================================
# BacktraderStrategyAdapter — 策略适配器
# ================================================================

class BacktraderStrategyAdapter(bt.Strategy):
    """
    策略适配器 — 将用户已有策略桥接到 Backtrader

    用户策略接口:
        class MyStrategy:
            def get_buy_signals(self, date, data) -> List[str]
            def get_sell_signals(self, date, data, portfolio) -> List[str]
    """

    params = (
        ("existing_strategy", None),
        ("data_dict", {}),
        ("weight_mode", "equal"),
        ("max_position_pct", 0.10),
        ("max_total_position", 0.80),
        ("min_trade_amount", 100),
        ("commission_rate", 0.0002),
        ("stamp_duty_rate", 0.001),
        ("slippage_rate", 0.001),
    )

    def __init__(self):
        self.strategy = self.p.existing_strategy
        self.data_dict = self.p.data_dict
        self.trade_log = []

        self.code_to_data = {}
        for data in self.datas:
            name = data._name if hasattr(data, "_name") else str(data)
            code = self._extract_code(name)
            self.code_to_data[code] = data

        self._order_count = 0
        self._trade_dates = set()

        logger.info(f"策略适配器初始化完成，加载 {len(self.code_to_data)} 只股票")

    def next(self):
        current_date = self.datas[0].datetime.date(0)
        date_str = current_date.strftime("%Y-%m-%d")

        current_portfolio = self._get_current_portfolio()
        market_data = self._build_market_data(current_date)

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
                logger.error("调用策略信号失败 (%s): %s", date_str, e)

        self._execute_sells(sell_signals, date_str)
        self._execute_buys(buy_signals, date_str)
        self._trade_dates.add(date_str)

    def stop(self):
        logger.info(f"回测结束，共交易 {len(self._trade_dates)} 个交易日")

    # ── 交易执行 ──

    def _execute_buys(self, signals: List[str], date_str: str):
        if not signals:
            return
        total_value = self.broker.getvalue()
        current_stock_value = self._get_stock_value()
        available_for_buy = total_value * self.p.max_total_position - current_stock_value
        if available_for_buy <= 0:
            return

        held_codes = set(self._get_held_codes())
        signals = [s for s in signals if s not in held_codes]
        if not signals:
            return

        n_signals = len(signals)
        target_per_stock = min(
            total_value * self.p.max_position_pct,
            available_for_buy / n_signals if n_signals > 0 else 0,
        )

        for code in signals:
            data = self.code_to_data.get(code)
            if data is None or data.close[0] <= 0:
                continue

            buy_price = data.close[0] * (1 + self.p.slippage_rate)
            size = int(target_per_stock / buy_price / self.p.min_trade_amount) * self.p.min_trade_amount
            if size <= 0:
                continue
            cost = size * buy_price
            if cost > self.broker.getcash():
                continue

            self._order_count += 1
            self.buy(data=data, size=size)
            self.trade_log.append({
                "date": date_str, "code": code, "action": "buy",
                "price": round(data.close[0], 3), "size": size,
                "value": round(size * data.close[0], 2),
            })

    def _execute_sells(self, signals: List[str], date_str: str):
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
            self._order_count += 1
            self.sell(data=data, size=position.size)
            self.trade_log.append({
                "date": date_str, "code": code, "action": "sell",
                "price": round(data.close[0], 3), "size": int(position.size),
                "value": round(position.size * data.close[0], 2),
            })

    # ── 辅助方法 ──

    def _get_current_portfolio(self) -> dict:
        portfolio = {}
        for code, data in self.code_to_data.items():
            position = self.getposition(data)
            if position.size != 0:
                current_price = data.close[0]
                avg_cost = position.price if position.price > 0 else current_price
                pnl_pct = (current_price - avg_cost) / avg_cost * 100 if avg_cost > 0 else 0
                portfolio[code] = {
                    "size": int(position.size), "price": round(current_price, 3),
                    "avg_cost": round(avg_cost, 3),
                    "value": round(position.size * current_price, 2),
                    "pnl_pct": round(pnl_pct, 2),
                }
        return portfolio

    def _build_market_data(self, current_date) -> dict:
        stocks = {}
        for code, data in self.code_to_data.items():
            stocks[code] = {
                "close": float(data.close[0]), "open": float(data.open[0]),
                "high": float(data.high[0]), "low": float(data.low[0]),
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
        return [code for code, data in self.code_to_data.items()
                if self.getposition(data).size != 0]

    def _get_stock_value(self) -> float:
        return sum(pos.size * data.close[0]
                   for data in self.datas
                   if (pos := self.getposition(data)).size != 0)

    @staticmethod
    def _extract_code(name: str) -> str:
        import re
        match = re.search(r"(\d{6})", name)
        return match.group(1) if match else name

    def get_trade_log(self) -> list:
        return self.trade_log


# ================================================================
# EqualWeightStrategy — 内置等权重基准策略
# ================================================================

class EqualWeightStrategy(bt.Strategy):
    """内置等权重策略 — 每月调仓，等权买入"""

    params = (
        ("rebalance_days", 20),
        ("max_position_pct", 0.10),
        ("max_total_position", 0.80),
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

        for data in self.datas:
            pos = self.getposition(data)
            if pos.size > 0:
                self.sell(data=data, size=pos.size)

        for data in self.datas:
            if data.close[0] <= 0:
                continue
            size = int(target_value / data.close[0] / 100) * 100
            if size > 0 and size * data.close[0] <= self.broker.getcash():
                self.buy(data=data, size=size)


# ================================================================
# V14StrategyAdapter — v14 量化选股策略回测适配器
# ================================================================

class V14StrategyAdapter:
    """
    v14 量化策略适配器（用于回测）

    将 v14 因子评分系统封装为标准策略接口:
    - get_buy_signals() → Top N 高评分股票
    - get_sell_signals() → 评分降幅卖出

    ===== V15 改进：支持多种调仓模式 =====
    - monthly: 每月调仓 (20天)
    - quarterly: 季度调仓 (60天)
    - threshold: 阈值触发式调仓（评分变动超过阈值）
    """

    def __init__(
        self,
        data_fetcher=None,
        rebalance_days: int = 20,
        top_n: int = 5,
        score_threshold: float = 0.0,
        min_hold_days: int = 5,
        sell_score_drop: float = 0.05,
        mode: str = "rolling",
        request_days: int = 300,
        silent: bool = True,
        # V15 新增参数
        rebalance_mode: str = "quarterly",     # 调仓模式: monthly / quarterly / threshold
        rebalance_threshold: float = 0.30,     # 阈值触发式调仓的评分变动阈值
        rebalance_layers: int = 3,             # 分层调仓的批次数
    ):
        self.rebalance_days = rebalance_days
        self.top_n = top_n
        self.score_threshold = score_threshold
        self.min_hold_days = min_hold_days
        self.sell_score_drop = sell_score_drop
        self.mode = mode
        self.request_days = request_days
        self.data_fetcher = data_fetcher

        # V15 新增：调仓模式
        self.rebalance_mode = rebalance_mode
        self.rebalance_threshold = rebalance_threshold
        self.rebalance_layers = rebalance_layers

        # 根据模式设置默认调仓天数
        if rebalance_mode == "daily":
            self.rebalance_days = 1
        elif rebalance_mode == "biweekly":
            self.rebalance_days = 2  # 每2-3个交易日调仓
        elif rebalance_mode == "weekly":
            self.rebalance_days = 5
        elif rebalance_mode == "monthly":
            self.rebalance_days = 20
        elif rebalance_mode == "quarterly":
            self.rebalance_days = 60

        if silent:
            for mod in ["quant_stock_v12", "enhanced_factors", "market_data",
                        "httpx", "openai", "urllib3"]:
                logging.getLogger(mod).setLevel(logging.WARNING)

        self._v14_components = None
        self._prev_scores = {}
        self._buy_history = {}
        self._json_snapshot = None
        self._initialized = False

        root_str = str(_PROJECT_ROOT)
        if root_str not in sys.path:
            sys.path.insert(0, root_str)

    @classmethod
    def from_json_report(cls, json_path: str, **kwargs):
        """从已有的 v14 JSON 报告创建适配器（快照模式）"""
        import json
        adapter = cls(mode="json_snapshot", **kwargs)
        with open(json_path, "r", encoding="utf-8") as f:
            adapter._json_snapshot = json.load(f)
        logger.info("从 JSON 报告加载: %s", json_path)
        return adapter

    def get_buy_signals(self, date: str, data: dict) -> List[str]:
        if self.mode == "json_snapshot":
            return self._get_signals_from_snapshot(date, data)
        return self._get_signals_from_scoring(date, data)

    # ===== V15 改进：阈值触发式调仓检查 =====
    def should_rebalance(self, date: str, day_count: int, current_portfolio: dict, data: dict) -> bool:
        """
        判断是否需要触发调仓

        Args:
            date: 当前日期
            day_count: 距离上次调仓的交易天数
            current_portfolio: 当前持仓
            data: 股票数据

        Returns:
            True 表示需要调仓
        """
        # 时间周期触发
        if day_count > 0 and day_count % self.rebalance_days == 1:
            return True

        # 阈值触发式调仓
        if self.rebalance_mode == "threshold" and current_portfolio:
            return self._check_threshold_trigger(data, current_portfolio)

        return False

    def _check_threshold_trigger(self, data: dict, current_portfolio: dict) -> bool:
        """检查是否触发阈值调仓"""
        try:
            if not self._initialized:
                self._init_v14_components()

            stocks_data = data.get("stocks", {})
            if not stocks_data:
                return False

            # 获取当前持仓的评分变化
            max_change = 0.0
            for code in current_portfolio.keys():
                new_score = self._prev_scores.get(code, 0)
                old_score = self._prev_scores.get(f"_{code}_prev", new_score)
                if old_score > 0:
                    change = abs(old_score - new_score) / old_score
                    max_change = max(max_change, change)

            return max_change >= self.rebalance_threshold
        except Exception:
            return False

    def get_sell_signals(self, date: str, data: dict, current_portfolio: dict) -> List[str]:
        sell_list = []
        for code, pos in current_portfolio.items():
            buy_date = self._buy_history.get(code)
            if buy_date:
                hold_days = (datetime.strptime(date, "%Y-%m-%d") - buy_date).days
                if hold_days < self.min_hold_days:
                    continue

            new_score = self._prev_scores.get(code, 0)
            old_score = self._prev_scores.get(f"_{code}_prev", new_score)

            if new_score < self.score_threshold:
                sell_list.append(code)
            elif old_score > 0 and (old_score - new_score) > self.sell_score_drop:
                sell_list.append(code)
        return sell_list

    def _get_signals_from_scoring(self, date: str, data: dict) -> List[str]:
        try:
            if not self._initialized:
                self._init_v14_components()

            stocks_data = data.get("stocks", {})
            if not stocks_data:
                return []

            v14_data = self._build_v14_data(stocks_data, date)
            if not v14_data:
                return []

            scored = self._run_v14_scoring(v14_data)
            top_stocks = sorted(scored, key=lambda x: x["total_score"], reverse=True)[:self.top_n]

            buy_codes = []
            for s in top_stocks:
                if s["total_score"] >= self.score_threshold:
                    buy_codes.append(s["symbol"])
                    self._prev_scores[s["symbol"]] = s["total_score"]
                    self._buy_history[s["symbol"]] = datetime.strptime(date, "%Y-%m-%d")

            return buy_codes
        except Exception as e:
            logger.error("v14 评分失败 (%s): %s", date, e)
            return []

    def _get_signals_from_snapshot(self, date: str, data: dict) -> List[str]:
        if self._json_snapshot is None:
            return []

        top_stocks = self._json_snapshot.get("top_stocks", [])
        codes = [s["symbol"] for s in top_stocks[:self.top_n]
                 if s.get("total_score", 0) >= self.score_threshold]

        snapshot_date = self._json_snapshot.get("date", "")
        if date == snapshot_date:
            for code in codes:
                self._buy_history[code] = datetime.strptime(date, "%Y-%m-%d")
            return codes
        return []

    def _init_v14_components(self):
        if self._initialized:
            return
        try:
            from a_stock_selector_v12_optimized import HuanfangStockSelectorV12
            from enhanced_factor_calculator import EnhancedFactorCalculator
            from anti_top_factors import AntiTopFilter
            from factor_engine_v2 import FactorEngineV2

            self._v14_components = {
                "selector": HuanfangStockSelectorV12(),
                "enhanced_calc": EnhancedFactorCalculator(),
                "anti_top": AntiTopFilter(),
                "factor_engine": FactorEngineV2(),
            }
            self._initialized = True
        except ImportError as e:
            logger.error("v14 模块导入失败: %s", e)
            raise

    def _build_v14_data(self, stocks_data: dict, date: str):
        if self.data_fetcher is None:
            return None
        v14_data = {}
        for code in stocks_data:
            try:
                df = self.data_fetcher.get_daily(code, days=self.request_days)
                if df is not None and len(df) >= 60:
                    v14_data[code] = df
            except Exception:
                pass
        return v14_data if v14_data else None

    def _run_v14_scoring(self, v14_data):
        if not self._v14_components:
            return []

        selector = self._v14_components["selector"]
        enhanced_calc = self._v14_components["enhanced_calc"]
        anti_top = self._v14_components["anti_top"]
        factor_engine = self._v14_components["factor_engine"]

        results = []
        for sym, sdf in v14_data.items():
            try:
                factors = selector.calculate_all_factors(sdf)
                if not factors:
                    continue
                base_score = selector.calculate_comprehensive_score(factors)

                enhanced_factors = enhanced_calc.calculate_stock_factors(sdf)
                enhanced_score = enhanced_calc.get_adjusted_score(
                    enhanced_factors, {}
                ) if enhanced_factors else base_score * 0.8

                final_score = base_score * 0.70 + enhanced_score * 0.30

                anti_top_result = anti_top.evaluate(sdf)
                penalty = anti_top.get_score_penalty(anti_top_result)
                final_score *= penalty

                factor_v2_result = factor_engine.calculate(sdf)
                final_score *= factor_v2_result["adjustment_coef"]

                final_score = float(np.clip(final_score, 0, 1))
                results.append({
                    "symbol": sym, "total_score": final_score,
                    "base_score": base_score, "enhanced_score": enhanced_score,
                    "factor_v2_coef": factor_v2_result["adjustment_coef"],
                    "anti_top_penalty": penalty,
                })
            except Exception:
                pass
        return results


# ================================================================
# BacktestEngine — 统一回测引擎
# ================================================================

class BacktestEngine:
    """
    回测引擎 — 封装 Backtrader 核心流程

    用法:
        engine = BacktestEngine(config)
        result = engine.run_backtest(
            existing_strategy=my_strategy,
            data_dict={"600519": df1, "000001": df2},
        )
    """

    def __init__(self, config: Optional[QuantConfig] = None):
        self.config = config or QuantConfig()
        self._cerebro: Optional[bt.Cerebro] = None
        self._result: Optional[dict] = None
        logger.info("BacktestEngine 初始化完成")

    def run_backtest(
        self,
        existing_strategy: Any = None,
        data_dict: Optional[Dict[str, pd.DataFrame]] = None,
        data_feeds: Optional[List] = None,
        benchmark: Optional[pd.DataFrame] = None,
        strategy_params: Optional[dict] = None,
        initial_cash: Optional[float] = None,
    ) -> dict:
        """执行回测"""
        cerebro = bt.Cerebro(
            preload=self.config.backtest_engine.preload,
            runonce=self.config.backtest_engine.runonce,
        )

        cash = initial_cash or self.config.portfolio.initial_cash
        cerebro.broker.setcash(cash)
        _apply_china_commission(cerebro, self.config)

        # 加载数据
        if data_feeds:
            for feed in data_feeds:
                cerebro.adddata(feed)
        elif data_dict:
            for code, df in data_dict.items():
                cerebro.adddata(self._df_to_feed(df, name=code))

        if benchmark is not None:
            cerebro.adddata(self._df_to_feed(benchmark, name="benchmark"))

        # 策略参数
        params = strategy_params or {}
        default_params = {
            "existing_strategy": existing_strategy,
            "data_dict": data_dict or {},
            "weight_mode": self.config.portfolio.weight_mode,
            "max_position_pct": self.config.portfolio.max_position_pct,
            "max_total_position": self.config.portfolio.max_total_position,
            "min_trade_amount": self.config.portfolio.min_trade_amount,
            "commission_rate": self.config.trade.commission_rate,
            "stamp_duty_rate": self.config.trade.stamp_duty_rate,
            "slippage_rate": self.config.trade.slippage_rate,
        }
        default_params.update(params)
        cerebro.addstrategy(BacktraderStrategyAdapter, **default_params)

        # 分析器
        cerebro.addanalyzer(StrategyObserver, _name="strategy_observer")
        cerebro.addanalyzer(OrderManager, _name="order_manager")
        cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name="sharpe",
                           riskfreerate=self.config.risk.risk_free_rate, annualize=True)
        cerebro.addanalyzer(bt.analyzers.DrawDown, _name="drawdown")
        cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="trades")
        cerebro.addanalyzer(bt.analyzers.Returns, _name="returns")
        cerebro.addanalyzer(bt.analyzers.VWR, _name="vwr")
        cerebro.addanalyzer(bt.analyzers.SQN, _name="sqn")
        cerebro.addanalyzer(bt.analyzers.TimeReturn, _name="time_return")
        cerebro.addanalyzer(bt.analyzers.AnnualReturn, _name="annual_return")
        cerebro.addanalyzer(bt.analyzers.Calmar, _name="calmar")

        logger.info(f"开始回测: 初始资金 {cash:,.0f}")
        results = cerebro.run()
        strategy = results[0]

        self._result = self._collect_results(strategy, cash)
        self._cerebro = cerebro
        logger.info(f"回测完成: 最终资金 {self._result['stats']['final_value']:,.2f}")
        return self._result

    def run_benchmark(
        self,
        data_dict: Dict[str, pd.DataFrame],
        initial_cash: Optional[float] = None,
    ) -> dict:
        """运行等权重基准策略"""
        cash = initial_cash or self.config.portfolio.initial_cash
        cerebro = bt.Cerebro(preload=True, runonce=True)
        cerebro.broker.setcash(cash)
        _apply_china_commission(cerebro, self.config)

        for code, df in data_dict.items():
            cerebro.adddata(self._df_to_feed(df, name=code))

        cerebro.addstrategy(
            EqualWeightStrategy,
            max_position_pct=self.config.portfolio.max_position_pct,
            max_total_position=self.config.portfolio.max_total_position,
        )

        cerebro.addanalyzer(StrategyObserver, _name="strategy_observer")
        cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name="sharpe",
                           riskfreerate=self.config.risk.risk_free_rate)
        cerebro.addanalyzer(bt.analyzers.DrawDown, _name="drawdown")
        cerebro.addanalyzer(bt.analyzers.TimeReturn, _name="time_return")

        results = cerebro.run()
        strategy = results[0]
        observer = strategy.analyzers.strategy_observer
        daily_values = observer.daily_values
        dates = self._get_dates(data_dict)

        return {
            "daily_value": pd.Series(daily_values[:len(dates)], index=dates[:len(daily_values)]),
            "final_value": daily_values[-1] if daily_values else cash,
            "total_return": (daily_values[-1] / cash - 1) * 100 if daily_values else 0,
        }

    # ── 结果收集 ──

    def _collect_results(self, strategy: bt.Strategy, initial_cash: float) -> dict:
        observer = strategy.analyzers.strategy_observer
        order_mgr = strategy.analyzers.order_manager

        final_value = strategy.broker.getvalue()
        total_return = (final_value / initial_cash - 1) * 100

        try:
            sharpe = strategy.analyzers.sharpe.get_analysis().get("sharperatio", 0) or 0
        except Exception: sharpe = 0

        try:
            dd = strategy.analyzers.drawdown.get_analysis()
            max_dd = dd.get("max", {}).get("drawdown", 0) or 0
            max_dd_period = dd.get("max", {}).get("len", 0) or 0
        except Exception:
            max_dd = max_dd_period = 0

        n_trades = len(observer.trades)
        n_win = sum(1 for t in observer.trades if t.get("pnl", 0) > 0)
        n_loss = sum(1 for t in observer.trades if t.get("pnl", 0) < 0)
        win_rate = (n_win / max(n_trades, 1)) * 100
        total_won = sum(t.get("pnl", 0) for t in observer.trades if t.get("pnl", 0) > 0)
        total_lost = abs(sum(t.get("pnl", 0) for t in observer.trades if t.get("pnl", 0) < 0))
        profit_factor = total_won / max(total_lost, 1)

        try:
            annual = strategy.analyzers.annual_return.get_analysis()
            annual_returns = {str(k): round(v * 100, 2) for k, v in annual.items()}
        except Exception: annual_returns = {}

        try: calmar = strategy.analyzers.calmar.get_analysis().get("calmar", 0) or 0
        except Exception: calmar = 0

        try: sqn = strategy.analyzers.sqn.get_analysis().get("sqn", 0) or 0
        except Exception: sqn = 0

        daily_values = observer.daily_values
        n_values = len(daily_values)
        dates = self._safe_infer_dates(strategy, n_values)

        if len(dates) != n_values:
            start = dates[0] if len(dates) > 0 else pd.Timestamp("2025-01-01")
            dates = pd.date_range(start=start, periods=n_values, freq="B")

        daily_series = pd.Series(daily_values[:len(dates)], index=dates[:len(daily_values)])
        daily_returns = daily_series.pct_change().dropna()
        trading_days = n_values
        n_years = trading_days / 252
        annual_return = ((final_value / initial_cash) ** (1 / max(n_years, 0.01)) - 1) * 100 if final_value > 0 else 0

        stats = {
            "initial_cash": initial_cash,
            "final_value": round(final_value, 2),
            "total_return": round(total_return, 2),
            "annual_return": round(annual_return, 2),
            "sharpe_ratio": round(sharpe, 4),
            "max_drawdown": round(max_dd, 2),
            "max_drawdown_days": max_dd_period,
            "calmar_ratio": round(calmar, 4),
            "sqn": round(sqn, 4),
            "total_trades": n_trades,
            "win_rate": round(win_rate, 2),
            "profit_factor": round(profit_factor, 2),
            "win_trades": n_win,
            "loss_trades": n_loss,
            "annual_returns": annual_returns,
            "trading_days": trading_days,
        }

        return {
            "stats": stats,
            "trades": observer.trades,
            "trade_log": strategy.get_trade_log(),
            "orders": order_mgr.orders_log,
            "daily_value": daily_series,
            "daily_returns": daily_returns,
            "final_portfolio": observer.positions,
        }

    # ── 工具方法 ──

    def _df_to_feed(self, df: pd.DataFrame, name: str = "") -> bt.feeds.PandasData:
        if not isinstance(df.index, pd.DatetimeIndex):
            if "date" in df.columns:
                df = df.set_index("date")
            df.index = pd.to_datetime(df.index)
        df = df.sort_index()
        for col in ["open", "high", "low", "close", "volume"]:
            if col not in df.columns:
                df[col] = 0.0
        return bt.feeds.PandasData(
            dataname=df, name=name, datetime=None,
            open="open", high="high", low="low", close="close",
            volume="volume", openinterest=None,
        )

    def _safe_infer_dates(self, strategy: bt.Strategy, n_values: int) -> pd.DatetimeIndex:
        if strategy.datas:
            data = strategy.datas[0]
            dates = []
            try:
                for i in range(min(n_values, len(data))):
                    dates.append(data.datetime.date(i))
            except Exception: pass

            if len(dates) >= n_values:
                return pd.DatetimeIndex(dates)
            if dates:
                last = dates[-1]
                while len(dates) < n_values:
                    next_d = last + timedelta(days=1)
                    while next_d.weekday() >= 5:
                        next_d += timedelta(days=1)
                    dates.append(next_d)
                    last = next_d
            return pd.DatetimeIndex(dates) if dates else pd.DatetimeIndex([])
        return pd.DatetimeIndex([])

    def _get_dates(self, data_dict):
        all_dates = []
        for df in data_dict.values():
            if isinstance(df.index, pd.DatetimeIndex):
                all_dates.append(df.index)
            elif "date" in df.columns:
                all_dates.append(pd.to_datetime(df["date"]))
        if all_dates:
            return pd.DatetimeIndex(all_dates).unique().sort_values()
        return pd.DatetimeIndex([])

    def plot(self, filename: Optional[str] = None, **kwargs):
        if self._cerebro is None:
            logger.warning("尚未运行回测，无法绘图")
            return
        fig = self._cerebro.plot(style="candle", volume=True,
                                  barup="red", bardown="green", **kwargs)
        if filename:
            import matplotlib.pyplot as plt
            plt.savefig(filename, dpi=150, bbox_inches="tight")
        return fig

    def get_result(self) -> Optional[dict]:
        return self._result
