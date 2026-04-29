"""
BacktestEngine 回测引擎模块
==============================
封装 Backtrader 核心，提供简洁的回测接口。

功能:
    - 单策略 / 多股票回测
    - 参数优化
    - 自定义策略适配
    - 回测结果统一输出
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple

import backtrader as bt
import pandas as pd
import numpy as np

from .config import BacktestConfig
from .strategy_adapter import (
    BacktraderStrategyAdapter,
    StrategyObserver,
    OrderManager,
    EqualWeightStrategy,
)

logger = logging.getLogger(__name__)


class BenchmarkTracker(bt.Analyzer):
    """基准指数追踪器"""

    def __init__(self):
        self.values = []

    def next(self):
        # 使用第一个 data feed 的日期索引
        self.values.append({
            "date": self.datas[0].datetime.date(0),
            "value": self.strategy.broker.getvalue(),
        })


class BacktestEngine:
    """
    回测引擎 —— 封装 Backtrader 核心流程

    用法:
        engine = BacktestEngine(config)
        result = engine.run_backtest(
            existing_strategy=my_strategy,
            data_dict={"600519": df1, "000001": df2},
        )
    """

    def __init__(self, config: Optional[BacktestConfig] = None):
        """
        初始化回测引擎

        Args:
            config: 回测配置，默认使用 BacktestConfig()
        """
        self.config = config or BacktestConfig()
        self._cerebro: Optional[bt.Cerebro] = None
        self._result: Optional[dict] = None

        logger.info("BacktestEngine 初始化完成")

    # ================================================================
    # 核心接口
    # ================================================================

    def run_backtest(
        self,
        existing_strategy: Any = None,
        data_dict: Optional[Dict[str, pd.DataFrame]] = None,
        data_feeds: Optional[List] = None,
        benchmark: Optional[pd.DataFrame] = None,
        strategy_params: Optional[dict] = None,
        initial_cash: Optional[float] = None,
    ) -> dict:
        """
        执行回测

        Args:
            existing_strategy: 用户已有策略实例（需实现 get_buy_signals / get_sell_signals）
            data_dict: {股票代码: DataFrame} 行情数据
            data_feeds: 已转换的 Backtrader data feeds 列表（与 data_dict 二选一）
            benchmark: 基准指数数据（用于对比）
            strategy_params: 覆盖策略参数
            initial_cash: 初始资金（覆盖配置）

        Returns:
            回测结果字典，包含:
            - stats: 回测统计指标
            - trades: 交易记录
            - daily: 每日净值曲线
            - portfolio: 每日持仓快照
            - orders: 委托记录
        """
        # 创建 Cerebro
        cerebro = bt.Cerebro(**self.config.cerebro_kwargs)

        # 初始资金
        cash = initial_cash or self.config.portfolio.initial_cash
        cerebro.broker.setcash(cash)

        # 设置 A 股交易成本（手续费 + 印花税 + 滑点）
        _apply_china_commission(cerebro, self.config)

        # 加载数据
        if data_feeds:
            for feed in data_feeds:
                cerebro.adddata(feed)
        elif data_dict:
            for code, df in data_dict.items():
                feed = self._df_to_feed(df, name=code)
                cerebro.adddata(feed)

        # 加载基准
        if benchmark is not None:
            bench_feed = self._df_to_feed(benchmark, name="benchmark")
            cerebro.adddata(bench_feed)

        # 添加策略
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

        # 添加分析器
        cerebro.addanalyzer(StrategyObserver, _name="strategy_observer")
        cerebro.addanalyzer(OrderManager, _name="order_manager")
        cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name="sharpe",
                           riskfreerate=self.config.risk.risk_free_rate,
                           annualize=True)
        cerebro.addanalyzer(bt.analyzers.DrawDown, _name="drawdown")
        cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="trades")
        cerebro.addanalyzer(bt.analyzers.Returns, _name="returns")
        cerebro.addanalyzer(bt.analyzers.VWR, _name="vwr")
        cerebro.addanalyzer(bt.analyzers.SQN, _name="sqn")
        cerebro.addanalyzer(bt.analyzers.TimeReturn, _name="time_return")
        cerebro.addanalyzer(bt.analyzers.AnnualReturn, _name="annual_return")
        cerebro.addanalyzer(bt.analyzers.Calmar, _name="calmar")

        # 执行回测
        logger.info(f"开始回测: 初始资金 {cash:,.0f}")
        results = cerebro.run()
        strategy = results[0]

        # 收集结果
        self._result = self._collect_results(strategy, cash)

        # 保存 cerebro 引用（可用于绘图）
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
        cerebro = bt.Cerebro(**self.config.cerebro_kwargs)
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
        dates = [self._get_dates(data_dict).iloc[i] if i < len(self._get_dates(data_dict))
                 else pd.Timestamp.now() for i in range(len(daily_values))]

        return {
            "daily_value": pd.Series(daily_values, index=dates),
            "final_value": daily_values[-1] if daily_values else cash,
            "total_return": (daily_values[-1] / cash - 1) * 100 if daily_values else 0,
        }

    def optimize(
        self,
        param_ranges: dict,
        data_dict: Dict[str, pd.DataFrame],
        existing_strategy: Any = None,
        n_runs: int = 100,
    ) -> pd.DataFrame:
        """
        参数优化

        Args:
            param_ranges: 参数范围 {参数名: [start, end, step]}
            data_dict: 数据字典
            existing_strategy: 策略实例
            n_runs: 最大运行次数

        Returns:
            优化结果 DataFrame
        """
        cerebro = bt.Cerebro(maxcpus=1)  # 参数优化暂用单进程

        cash = self.config.portfolio.initial_cash
        cerebro.broker.setcash(cash)
        _apply_china_commission(cerebro, self.config)

        for code, df in data_dict.items():
            cerebro.adddata(self._df_to_feed(df, name=code))

        # 转换参数范围
        bt_params = {}
        for key, (start, end, step) in param_ranges.items():
            n_steps = int((end - start) / step) + 1
            bt_params[key] = np.linspace(start, end, min(n_steps, 20))

        cerebro.optstrategy(
            BacktraderStrategyAdapter,
            existing_strategy=[existing_strategy],
            data_dict=[data_dict],
            **bt_params,
        )
        cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name="sharpe",
                           riskfreerate=self.config.risk.risk_free_rate)

        results = cerebro.run(maxcpus=1)

        # 汇总结果
        rows = []
        for run in results:
            s = run[0]
            try:
                sharpe = s.analyzers.sharpe.get_analysis().get("sharperatio", 0) or 0
            except Exception:
                sharpe = 0
            rows.append({
                "sharpe": sharpe,
                "final_value": s.broker.getvalue(),
                **{k: getattr(s.p, k) for k in param_ranges},
            })

        df = pd.DataFrame(rows)
        df = df.sort_values("sharpe", ascending=False)
        logger.info(f"参数优化完成: {len(df)} 组参数, 最佳 Sharpe={df.iloc[0]['sharpe']:.4f}")
        return df

    # ================================================================
    # 结果收集
    # ================================================================

    def _collect_results(self, strategy: bt.Strategy, initial_cash: float) -> dict:
        """收集回测结果"""
        observer = strategy.analyzers.strategy_observer
        order_mgr = strategy.analyzers.order_manager

        # 基础统计
        final_value = strategy.broker.getvalue()
        total_return = (final_value / initial_cash - 1) * 100

        # Sharpe
        try:
            sharpe_analysis = strategy.analyzers.sharpe.get_analysis()
            sharpe = sharpe_analysis.get("sharperatio", 0) or 0
        except Exception:
            sharpe = 0

        # 最大回撤
        try:
            dd_analysis = strategy.analyzers.drawdown.get_analysis()
            max_dd = dd_analysis.get("max", {}).get("drawdown", 0) or 0
            max_dd_period = dd_analysis.get("max", {}).get("len", 0) or 0
        except Exception:
            max_dd = 0
            max_dd_period = 0

        # 交易分析
        n_trades = len(observer.trades)
        n_win = sum(1 for t in observer.trades if t.get("pnl", 0) > 0)
        n_loss = sum(1 for t in observer.trades if t.get("pnl", 0) < 0)
        win_rate = (n_win / max(n_trades, 1)) * 100
        total_won = sum(t.get("pnl", 0) for t in observer.trades if t.get("pnl", 0) > 0)
        total_lost = abs(sum(t.get("pnl", 0) for t in observer.trades if t.get("pnl", 0) < 0))
        profit_factor = total_won / max(total_lost, 1)

        # 年度收益
        try:
            annual = strategy.analyzers.annual_return.get_analysis()
            annual_returns = {str(k): round(v * 100, 2) for k, v in annual.items()}
        except Exception:
            annual_returns = {}

        # Calmar
        try:
            calmar = strategy.analyzers.calmar.get_analysis().get("calmar", 0) or 0
        except Exception:
            calmar = 0

        # SQN
        try:
            sqn = strategy.analyzers.sqn.get_analysis().get("sqn", 0) or 0
        except Exception:
            sqn = 0

        # 构造每日净值曲线
        daily_values = observer.daily_values
        # 使用第一根数据的日期序列
        n_values = len(daily_values)
        dates = self._safe_infer_dates(strategy, n_values)

        if len(dates) != n_values:
            # 补齐日期
            start = dates[0] if len(dates) > 0 else pd.Timestamp("2025-01-01")
            dates = pd.date_range(start=start, periods=n_values, freq="B")

        daily_series = pd.Series(daily_values[:len(dates)], index=dates[:len(daily_values)])

        # 每日收益率
        daily_returns = daily_series.pct_change().dropna()

        # trading_days 用实际数据长度
        trading_days = n_values

        # 年化收益
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

        # 处理 final_portfolio，添加 avg_cost 和 pnl_pct 字段
        final_portfolio = {}
        for code, pos in observer.positions.items():
            final_portfolio[code] = {
                "size": pos.get("size", 0),
                "price": round(pos.get("price", 0), 2),
                "value": round(pos.get("value", 0), 2),
                "avg_cost": round(pos.get("avg_cost", pos.get("price", 0)), 2),
                "pnl_pct": round(pos.get("pnl_pct", 0), 2),
            }

        return {
            "stats": stats,
            "trades": observer.trades,
            "trade_log": strategy.get_trade_log(),
            "orders": order_mgr.orders_log,
            "daily_value": daily_series,
            "daily_returns": daily_returns,
            "final_portfolio": final_portfolio,
        }

    # ================================================================
    # 工具方法
    # ================================================================

    def _df_to_feed(self, df: pd.DataFrame, name: str = "") -> bt.feeds.PandasData:
        """将 DataFrame 转换为 Backtrader PandasData"""
        if not isinstance(df.index, pd.DatetimeIndex):
            if "date" in df.columns:
                df = df.set_index("date")
                df.index = pd.to_datetime(df.index)
            else:
                df.index = pd.to_datetime(df.index)

        df = df.sort_index()

        for col in ["open", "high", "low", "close", "volume"]:
            if col not in df.columns:
                df[col] = 0.0

        return bt.feeds.PandasData(
            dataname=df,
            name=name,
            datetime=None,
            open="open",
            high="high",
            low="low",
            close="close",
            volume="volume",
            openinterest=None,
        )

    def _safe_infer_dates(self, strategy: bt.Strategy, n_values: int) -> pd.DatetimeIndex:
        """安全推断日期序列"""
        if strategy.datas:
            data = strategy.datas[0]
            dates = []
            try:
                for i in range(min(n_values, len(data))):
                    dates.append(data.datetime.date(i))
            except (IndexError, Exception):
                pass

            if len(dates) >= n_values:
                return pd.DatetimeIndex(dates)

            # 如果数据不足，用已知日期 + 补齐
            if dates:
                last = dates[-1]
                while len(dates) < n_values:
                    # 简单补齐工作日
                    from datetime import timedelta
                    next_d = last + timedelta(days=1)
                    while next_d.weekday() >= 5:
                        next_d += timedelta(days=1)
                    dates.append(next_d)
                    last = next_d

            return pd.DatetimeIndex(dates) if dates else pd.DatetimeIndex([])

        return pd.DatetimeIndex([])

    def _get_dates(self, data_dict: Dict[str, pd.DataFrame]) -> pd.DatetimeIndex:
        """获取所有数据中最长的日期序列"""
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
        """绘制回测结果图表"""
        if self._cerebro is None:
            logger.warning("尚未运行回测，无法绘图")
            return

        fig = self._cerebro.plot(
            style="candle",
            volume=True,
            barup="red",
            bardown="green",
            **kwargs,
        )

        if filename:
            import matplotlib.pyplot as plt
            plt.savefig(filename, dpi=150, bbox_inches="tight")
            logger.info(f"图表已保存: {filename}")

        return fig

    def get_result(self) -> Optional[dict]:
        """获取上次回测结果"""
        return self._result


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
        # 印花税（仅卖出）
        if size < 0:
            commission += abs(size) * price * self.p.stamp_duty_rate
        # 滑点成本
        commission += abs(size) * price * self.p.slippage_rate
        return commission

def _apply_china_commission(cerebro, config):
    """统一设置 A 股交易成本"""
    comm = ChinaStockCommission(
        commission=config.trade.commission_rate,
        stamp_duty_rate=config.trade.stamp_duty_rate,
        slippage_rate=config.trade.slippage_rate,
        min_commission=config.trade.commission_min,
    )
    cerebro.broker.addcommissioninfo(comm)
    return comm
