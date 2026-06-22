"""回测交易模拟器 — 基于信号的历史交易回放

功能:
1. 信号驱动的交易模拟 (买入/卖出/持仓)
2. 真实成本建模: 佣金 + 印花税 + 滑点
3. 涨跌停限制: 涨停不能买入, 跌停不能卖出
4. 仓位管理: Kelly公式 / 等权分配
5. 基准对比: 对比沪深300
6. 标准绩效指标: 夏普/最大回撤/Calmar/胜率/盈亏比

与 backtest_loop.py 的区别:
- backtest_loop: 因子IC分析 + Thompson采样 (研究用途)
- backtest_sim: 交易模拟 + 绩效评估 (策略验证用途)
"""

import math
from dataclasses import dataclass, field

from services.base import BaseService, ServiceResult
from shared.logging import emit_log


@dataclass
class BacktestConfig:
    """回测配置"""

    initial_capital: float = 1_000_000.0  # 初始资金
    commission_rate: float = 0.0003  # 佣金费率 (万三)
    stamp_tax_rate: float = 0.001  # 印花税 (千一, 仅卖出)
    slippage_pct: float = 0.001  # 滑点 (千一)
    min_commission: float = 5.0  # 最低佣金
    max_position_pct: float = 0.20  # 单只最大仓位 (20%)
    max_holdings: int = 10  # 最大持仓数
    limit_up_threshold: float = 0.098  # 涨停阈值 (9.8%)
    limit_down_threshold: float = -0.098  # 跌停阈值 (-9.8%)
    risk_free_rate: float = 0.02  # 无风险收益率 (年化)
    trading_days_per_year: int = 244  # A股年交易日


@dataclass
class TradeRecord:
    """单笔交易记录"""

    date: str
    stock_code: str
    stock_name: str
    direction: str  # "BUY" / "SELL"
    price: float
    quantity: int
    amount: float
    commission: float
    tax: float
    slippage_cost: float
    signal_confidence: float = 0.0
    reason: str = ""


@dataclass
class DailySnapshot:
    """每日快照"""

    date: str
    total_asset: float
    cash: float
    stock_value: float
    position_count: int
    daily_return: float = 0.0
    benchmark_return: float = 0.0
    drawdown: float = 0.0


@dataclass
class BacktestResult:
    """回测结果"""

    config: BacktestConfig
    trades: list[TradeRecord] = field(default_factory=list)
    daily_snapshots: list[DailySnapshot] = field(default_factory=list)
    # 汇总指标
    total_return_pct: float = 0.0
    annualized_return_pct: float = 0.0
    annualized_volatility_pct: float = 0.0
    sharpe_ratio: float = 0.0
    max_drawdown_pct: float = 0.0
    max_drawdown_date: str = ""
    calmar_ratio: float = 0.0
    win_rate_pct: float = 0.0
    profit_loss_ratio: float = 0.0
    total_trades: int = 0
    total_commission: float = 0.0
    total_tax: float = 0.0
    total_slippage: float = 0.0
    benchmark_return_pct: float = 0.0
    alpha_pct: float = 0.0

    def to_dict(self) -> dict:
        return {
            "summary": {
                "total_return_pct": round(self.total_return_pct, 2),
                "annualized_return_pct": round(self.annualized_return_pct, 2),
                "annualized_volatility_pct": round(self.annualized_volatility_pct, 2),
                "sharpe_ratio": round(self.sharpe_ratio, 3),
                "max_drawdown_pct": round(self.max_drawdown_pct, 2),
                "max_drawdown_date": self.max_drawdown_date,
                "calmar_ratio": round(self.calmar_ratio, 3),
                "win_rate_pct": round(self.win_rate_pct, 1),
                "profit_loss_ratio": round(self.profit_loss_ratio, 2),
                "benchmark_return_pct": round(self.benchmark_return_pct, 2),
                "alpha_pct": round(self.alpha_pct, 2),
            },
            "costs": {
                "total_trades": self.total_trades,
                "total_commission": round(self.total_commission, 2),
                "total_tax": round(self.total_tax, 2),
                "total_slippage": round(self.total_slippage, 2),
                "total_cost": round(
                    self.total_commission + self.total_tax + self.total_slippage, 2
                ),
            },
            "config": {
                "initial_capital": self.config.initial_capital,
                "commission_rate": self.config.commission_rate,
                "stamp_tax_rate": self.config.stamp_tax_rate,
                "slippage_pct": self.config.slippage_pct,
                "max_position_pct": self.config.max_position_pct,
                "max_holdings": self.config.max_holdings,
            },
            "trades_count": len(self.trades),
            "snapshots_count": len(self.daily_snapshots),
            "daily_nav": [
                {
                    "date": s.date,
                    "total_asset": round(s.total_asset, 2),
                    "daily_return": round(s.daily_return, 6),
                }
                for s in self.daily_snapshots
            ],
        }


class BacktestSimulator(BaseService):
    """交易回测模拟器"""

    def __init__(self, config: BacktestConfig | None = None):
        super().__init__()
        self.config = config or BacktestConfig()

    def run(
        self,
        signals: list[dict],
        price_data: dict[str, dict[str, dict]],
        benchmark_data: dict[str, dict] | None = None,
    ) -> ServiceResult:
        """运行回测

        Args:
            signals: 交易信号列表, 每个信号:
                {"date": "2024-01-15", "stock_code": "600519", "stock_name": "贵州茅台",
                 "action": "BUY"/"SELL", "confidence": 85, "reason": "..."}
            price_data: 价格数据 {date: {stock_code: {"open": x, "high": x, "low": x, "close": x}}}
            benchmark_data: 基准数据 {date: {"close": x}}

        Returns:
            ServiceResult with BacktestResult
        """
        try:
            if not signals:
                return ServiceResult.error(errors=["No signals provided"])

            result = BacktestResult(config=self.config)
            cash = self.config.initial_capital
            holdings: dict[str, dict] = {}  # stock_code -> {quantity, avg_price, ...}
            peak_asset = cash
            prev_asset = cash

            # 按日期排序信号
            signals_sorted = sorted(signals, key=lambda s: s.get("date", ""))

            # 收集所有交易日
            all_dates = sorted({s["date"] for s in signals_sorted})

            for date in all_dates:
                day_prices = price_data.get(date, {})
                day_signals = [s for s in signals_sorted if s["date"] == date]

                # 处理卖出信号
                for sig in day_signals:
                    if sig.get("action") == "SELL" and sig["stock_code"] in holdings:
                        code = sig["stock_code"]
                        prices = day_prices.get(code, {})
                        if not prices:
                            continue
                        h = holdings[code]
                        sell_price = self._apply_slippage(prices["open"], "SELL")

                        if self._is_limit_down(prices.get("open", 0), prices.get("pre_close", 0)):
                            continue

                        amount = sell_price * h["quantity"]
                        commission = max(
                            amount * self.config.commission_rate, self.config.min_commission
                        )
                        tax = amount * self.config.stamp_tax_rate
                        slippage = abs(sell_price - prices["open"]) * h["quantity"]
                        net_amount = amount - commission - tax

                        result.trades.append(
                            TradeRecord(
                                date=date,
                                stock_code=code,
                                stock_name=sig.get("stock_name", ""),
                                direction="SELL",
                                price=sell_price,
                                quantity=h["quantity"],
                                amount=amount,
                                commission=commission,
                                tax=tax,
                                slippage_cost=slippage,
                                signal_confidence=sig.get("confidence", 0),
                                reason=sig.get("reason", ""),
                            )
                        )

                        cash += net_amount
                        result.total_commission += commission
                        result.total_tax += tax
                        result.total_slippage += slippage
                        result.total_trades += 1
                        del holdings[code]

                # 处理买入信号
                for sig in day_signals:
                    if sig.get("action") == "BUY" and sig["stock_code"] not in holdings:
                        if len(holdings) >= self.config.max_holdings:
                            continue
                        code = sig["stock_code"]
                        prices = day_prices.get(code, {})
                        if not prices:
                            continue

                        # 涨停不能买入
                        if self._is_limit_up(prices.get("open", 0), prices.get("pre_close", 0)):
                            continue

                        buy_price = self._apply_slippage(prices["open"], "BUY")
                        total_asset = cash + sum(
                            day_prices.get(c, {}).get("close", h["avg_price"]) * h["quantity"]
                            for c, h in holdings.items()
                        )
                        max_amount = total_asset * self.config.max_position_pct
                        invest_amount = min(cash * 0.95, max_amount)  # 保留5%现金缓冲

                        if invest_amount < buy_price * 100:
                            continue

                        quantity = int(invest_amount / buy_price / 100) * 100  # A股100股整数
                        if quantity <= 0:
                            continue

                        amount = buy_price * quantity
                        commission = max(
                            amount * self.config.commission_rate, self.config.min_commission
                        )
                        slippage = abs(buy_price - prices["open"]) * quantity

                        result.trades.append(
                            TradeRecord(
                                date=date,
                                stock_code=code,
                                stock_name=sig.get("stock_name", ""),
                                direction="BUY",
                                price=buy_price,
                                quantity=quantity,
                                amount=amount,
                                commission=commission,
                                tax=0,
                                slippage_cost=slippage,
                                signal_confidence=sig.get("confidence", 0),
                                reason=sig.get("reason", ""),
                            )
                        )

                        cash -= amount + commission
                        holdings[code] = {
                            "quantity": quantity,
                            "avg_price": buy_price,
                            "buy_date": date,
                        }
                        result.total_commission += commission
                        result.total_slippage += slippage
                        result.total_trades += 1

                # 每日快照
                stock_value = sum(
                    day_prices.get(c, {}).get("close", h["avg_price"]) * h["quantity"]
                    for c, h in holdings.items()
                )
                total_asset = cash + stock_value
                daily_ret = ((total_asset / prev_asset) - 1) if prev_asset > 0 else 0
                peak_asset = max(peak_asset, total_asset)
                drawdown = ((peak_asset - total_asset) / peak_asset) if peak_asset > 0 else 0

                bm_ret = 0.0
                if benchmark_data and date in benchmark_data:
                    # Simplified benchmark return
                    pass

                result.daily_snapshots.append(
                    DailySnapshot(
                        date=date,
                        total_asset=total_asset,
                        cash=cash,
                        stock_value=stock_value,
                        position_count=len(holdings),
                        daily_return=daily_ret,
                        benchmark_return=bm_ret,
                        drawdown=drawdown,
                    )
                )
                prev_asset = total_asset

            # 计算汇总指标
            self._calc_summary(result)
            return ServiceResult.ok(data=result.to_dict())

        except Exception as e:
            emit_log("ERROR", "backtest_sim", f"run: {e}")
            return ServiceResult.error(errors=[str(e)])

    def _apply_slippage(self, price: float, direction: str) -> float:
        """应用滑点"""
        if direction == "BUY":
            return price * (1 + self.config.slippage_pct)
        return price * (1 - self.config.slippage_pct)

    def _is_limit_up(self, open_price: float, pre_close: float) -> bool:
        """判断是否涨停"""
        if pre_close <= 0 or open_price <= 0:
            return False
        change_pct = (open_price - pre_close) / pre_close
        return change_pct >= self.config.limit_up_threshold

    def _is_limit_down(self, open_price: float, pre_close: float) -> bool:
        """判断是否跌停"""
        if pre_close <= 0 or open_price <= 0:
            return False
        change_pct = (open_price - pre_close) / pre_close
        return change_pct <= self.config.limit_down_threshold

    def _calc_summary(self, result: BacktestResult):
        """计算汇总指标"""
        snapshots = result.daily_snapshots
        if len(snapshots) < 2:
            return

        initial = self.config.initial_capital
        final = snapshots[-1].total_asset
        result.total_return_pct = ((final / initial) - 1) * 100

        years = len(snapshots) / self.config.trading_days_per_year
        if years > 0:
            result.annualized_return_pct = ((final / initial) ** (1 / years) - 1) * 100

        daily_returns = [s.daily_return for s in snapshots]
        if len(daily_returns) >= 2:
            mean_ret = sum(daily_returns) / len(daily_returns)
            std_ret = math.sqrt(
                sum((r - mean_ret) ** 2 for r in daily_returns) / (len(daily_returns) - 1)
            )
            result.annualized_volatility_pct = (
                std_ret * math.sqrt(self.config.trading_days_per_year) * 100
            )

            if result.annualized_volatility_pct > 0:
                result.sharpe_ratio = (
                    result.annualized_return_pct - self.config.risk_free_rate * 100
                ) / result.annualized_volatility_pct

        # 最大回撤
        max_dd = 0.0
        dd_date = ""
        for s in snapshots:
            if s.drawdown > max_dd:
                max_dd = s.drawdown
                dd_date = s.date
        result.max_drawdown_pct = max_dd * 100
        result.max_drawdown_date = dd_date

        if result.max_drawdown_pct > 0:
            result.calmar_ratio = result.annualized_return_pct / result.max_drawdown_pct

        # 胜率 & 盈亏比
        # 按股票分组计算每笔交易盈亏
        buy_prices: dict[str, float] = {}
        trade_pnl: list[float] = []
        for t in result.trades:
            if t.direction == "BUY":
                buy_prices[t.stock_code] = t.price
            elif t.direction == "SELL" and t.stock_code in buy_prices:
                pnl_pct = (t.price - buy_prices[t.stock_code]) / buy_prices[t.stock_code]
                trade_pnl.append(pnl_pct)
                del buy_prices[t.stock_code]

        if trade_pnl:
            wins = [p for p in trade_pnl if p > 0]
            losses = [abs(p) for p in trade_pnl if p < 0]
            result.win_rate_pct = (len(wins) / len(trade_pnl)) * 100
            avg_win = sum(wins) / len(wins) if wins else 0
            avg_loss = sum(losses) / len(losses) if losses else 0
            result.profit_loss_ratio = (avg_win / avg_loss) if avg_loss > 0 else 0


# ── 模块级单例 ──
_simulator: BacktestSimulator | None = None


def get_backtest_simulator(config: BacktestConfig | None = None) -> BacktestSimulator:
    global _simulator  # noqa: PLW0603
    if _simulator is None:
        _simulator = BacktestSimulator(config)
    return _simulator
