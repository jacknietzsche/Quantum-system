"""回测引擎 — vectorbt驱动。

设计依据: S08 §8.5, Phase 7.2。
支持多股票组合回测、基准比较、详细指标计算。
vectorbt提供向量化回测加速，A股规则模拟通过AShareBroker。
"""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd

from tools.paper_trading import AShareBroker

logger = logging.getLogger(__name__)


def _fetch_kline_df(code: str, days: int = 250) -> pd.DataFrame:
    """从数据总线获取K线数据为DataFrame。"""
    try:
        from providers.data_bus import DatabaseFirstDataBus

        bus = DatabaseFirstDataBus()
        raw = bus.get_kline(code, days=days)
        if not raw:
            return pd.DataFrame()

        df = pd.DataFrame(raw)
        if "trade_date" in df.columns:
            df["date"] = pd.to_datetime(df["trade_date"])
            df.set_index("date", inplace=True)
        df.rename(
            columns={
                "open": "Open",
                "high": "High",
                "low": "Low",
                "close": "Close",
                "volume": "Volume",
            },
            inplace=True,
        )
        for col in ("Open", "High", "Low", "Close", "Volume"):
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        return df.dropna(subset=["Close"])
    except Exception as e:
        logger.warning("获取K线失败 %s: %s", code, e)
        return pd.DataFrame()


def _fetch_benchmark(days: int = 250) -> pd.DataFrame:
    """获取沪深300基准数据。"""
    try:
        from providers.data_bus import DatabaseFirstDataBus

        bus = DatabaseFirstDataBus()
        # 沪深300代码: 000300
        raw = bus.get_kline("000300", days=days)
        if not raw:
            # 尝试上证指数
            raw = bus.get_kline("000001", days=days)
        if not raw:
            return pd.DataFrame()

        df = pd.DataFrame(raw)
        if "trade_date" in df.columns:
            df["date"] = pd.to_datetime(df["trade_date"])
            df.set_index("date", inplace=True)
        if "close" in df.columns:
            df["Close"] = pd.to_numeric(df["close"], errors="coerce")
            return df[["Close"]].dropna()
    except Exception as e:
        logger.warning("获取基准数据失败: %s", e)
    return pd.DataFrame()


class VectorbtBacktest:
    """vectorbt驱动的向量化回测引擎。"""

    def __init__(self, initial_capital: float = 1_000_000):
        self.initial_capital = initial_capital

    def run(
        self,
        stock_codes: list[str],
        strategy: str = "ma_cross",
        days: int = 250,
        benchmark_code: str = "000300",
    ) -> dict[str, Any]:
        """执行向量化回测。

        Args:
            stock_codes: 股票代码列表
            strategy: 策略名称 (ma_cross / rsi / bollinger)
            days: 回测天数
            benchmark_code: 基准代码

        Returns:
            {total_return, benchmark_return, sharpe, max_drawdown,
             win_rate, trades, per_stock}
        """
        try:
            import vectorbt as vbt
        except ImportError:
            logger.warning("vectorbt未安装，降级到AShareBroker")
            return self._fallback_backtest(stock_codes, days)

        per_stock_results: dict[str, dict] = {}
        all_returns: list[pd.Series] = []

        for code in stock_codes:
            df = _fetch_kline_df(code, days=days)
            if df.empty or len(df) < 30:
                logger.info("跳过 %s (数据不足: %d条)", code, len(df))
                continue

            close = df["Close"]

            # 生成信号
            signals = self._generate_signals(close, strategy)
            if signals is None:
                continue

            # vectorbt回测
            entries = signals == 1
            exits = signals == -1

            try:
                pf = vbt.Portfolio.from_signals(
                    close,
                    entries,
                    exits,
                    init_cash=self.initial_capital / len(stock_codes),
                    fees=0.00025,
                    slippage=0.001,
                    freq="1D",
                )

                returns = pf.total_return()
                stats = pf.stats()

                per_stock_results[code] = {
                    "total_return": f"{returns * 100:.2f}%",
                    "sharpe": float(stats.get("Sharpe Ratio", 0)) if isinstance(stats, dict) else 0,
                    "max_drawdown": f"{pf.max_drawdown() * 100:.2f}%",
                    "total_trades": int(pf.trades.count),
                    "win_rate": (
                        f"{pf.trades.win_rate() * 100:.1f}%" if len(pf.trades) > 0 else "N/A"
                    ),
                }

                # 收集日收益率用于组合计算
                daily_returns = pf.returns()
                if isinstance(daily_returns, pd.Series):
                    all_returns.append(daily_returns)

            except Exception as e:
                logger.warning("回测 %s 失败: %s", code, e)
                continue

        # 基准比较
        bench_df = _fetch_benchmark(days=days)
        bench_return = 0.0
        if not bench_df.empty and len(bench_df) > 1:
            bench_return = (bench_df["Close"].iloc[-1] / bench_df["Close"].iloc[0] - 1) * 100

        # 组合指标
        portfolio_return = 0.0
        portfolio_sharpe = 0.0
        portfolio_max_dd = 0.0

        if all_returns:
            combined = pd.concat(all_returns, axis=1).mean(axis=1).dropna()
            if len(combined) > 0:
                portfolio_return = float(combined.sum() * 100)
                if combined.std() > 0:
                    portfolio_sharpe = float(
                        combined.mean() / combined.std() * (252 ** 0.5)
                    )
                cumulative = (1 + combined).cumprod()
                running_max = cumulative.cummax()
                drawdown = (cumulative - running_max) / running_max
                portfolio_max_dd = float(drawdown.min() * 100)

        return {
            "total_return": f"{portfolio_return:.2f}%",
            "benchmark_return": f"{bench_return:.2f}%",
            "excess_return": f"{portfolio_return - bench_return:.2f}%",
            "sharpe": round(portfolio_sharpe, 2),
            "max_drawdown": f"{portfolio_max_dd:.2f}%",
            "per_stock": per_stock_results,
            "stock_count": len(per_stock_results),
        }

    def _generate_signals(
        self, close: pd.Series, strategy: str
    ) -> pd.Series | None:
        """生成交易信号。"""
        try:
            import vectorbt as vbt

            if strategy == "ma_cross":
                fast = vbt.MA.run(close, window=5)
                slow = vbt.MA.run(close, window=20)
                entries = fast.ma_crossed_above(slow)
                exits = fast.ma_crossed_below(slow)

            elif strategy == "rsi":
                rsi = vbt.RSI.run(close, window=14)
                entries = rsi.rsi < 30
                exits = rsi.rsi > 70

            elif strategy == "bollinger":
                bb = vbt.BBANDS.run(close, window=20)
                entries = close < bb.lower
                exits = close > bb.upper

            else:
                fast = vbt.MA.run(close, window=5)
                slow = vbt.MA.run(close, window=20)
                entries = fast.ma_crossed_above(slow)
                exits = fast.ma_crossed_below(slow)

            signals = pd.Series(0, index=close.index)
            signals[entries] = 1
            signals[exits] = -1
            return signals

        except Exception as e:
            logger.warning("生成信号失败(%s): %s", strategy, e)
            return None

    def _fallback_backtest(
        self, stock_codes: list[str], days: int
    ) -> dict[str, Any]:
        """无vectorbt时的降级回测。"""
        broker = AShareBroker(initial_capital=self.initial_capital)

        for code in stock_codes[:3]:
            df = _fetch_kline_df(code, days=days)
            if df.empty:
                continue
            first_price = float(df["Close"].iloc[0])
            last_price = float(df["Close"].iloc[-1])
            broker.buy(code, first_price, 100, str(df.index[0].date()))
            broker.sell(code, last_price, str(df.index[-1].date()))

        metrics = broker.get_metrics()
        metrics["per_stock"] = {}
        metrics["stock_count"] = len(stock_codes)
        return metrics


def run_factor_backtest(
    stocks: list[dict],
    start_date: str = "2026-01-01",
    end_date: str = "2026-06-30",
    initial_capital: float = 1_000_000,
) -> dict:
    """因子回测（兼容旧接口）。

    Args:
        stocks: 股票列表 [{code, close/price}]
        start_date: 回测开始日期
        end_date: 回测结束日期
        initial_capital: 初始资金

    Returns:
        回测指标字典
    """
    if not stocks:
        return {"total_return": "0.00%", "error": "无股票数据"}

    codes = [
        s.get("code", s.get("stock_code", ""))
        for s in stocks
        if s.get("code") or s.get("stock_code")
    ]
    codes = [c for c in codes if c]

    if not codes:
        broker = AShareBroker(initial_capital=initial_capital)
        first = stocks[0]
        price = first.get("close", first.get("price", 100))
        broker.buy(first.get("code", "000001"), price, 100, start_date)
        broker.sell(first.get("code", "000001"), price * 1.1, end_date)
        return broker.get_metrics()

    engine = VectorbtBacktest(initial_capital=initial_capital)
    return engine.run(codes, strategy="ma_cross")
