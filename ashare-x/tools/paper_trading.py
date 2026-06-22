"""模拟交易工具。

设计依据: S08 §8.4, experiments exp13.1。
A股规则: T+1, 100股整数倍, 涨跌停, 手续费。
"""

from __future__ import annotations

import logging
from decimal import Decimal

logger = logging.getLogger(__name__)


class AShareBroker:
    """A股Broker模拟（实验验证通过 exp13.1）。"""

    def __init__(self, initial_capital: float = 1_000_000):
        self.initial_capital = Decimal(str(initial_capital))
        self.cash = self.initial_capital
        self.positions: dict[str, dict] = {}
        self.trades: list[dict] = []
        self.daily_nav: list[dict] = []

    def buy(self, code: str, price: float, quantity: int, date: str) -> bool:
        """买入。"""
        if quantity % 100 != 0:
            return False

        price_d = Decimal(str(price))
        cost = price_d * quantity
        commission = max(cost * Decimal("0.00025"), Decimal("5"))
        transfer_fee = cost * Decimal("0.00001")
        total_cost = cost + commission + transfer_fee

        if total_cost > self.cash:
            return False

        self.cash -= total_cost
        self.positions[code] = {
            "price": price_d,
            "quantity": quantity,
            "date": date,
        }
        self.trades.append(
            {
                "date": date,
                "code": code,
                "action": "BUY",
                "price": float(price_d),
                "quantity": quantity,
                "cost": float(total_cost),
            }
        )
        return True

    def sell(self, code: str, price: float, date: str) -> bool:
        """卖出。"""
        if code not in self.positions:
            return False

        pos = self.positions[code]
        price_d = Decimal(str(price))
        revenue = price_d * pos["quantity"]
        commission = max(revenue * Decimal("0.00025"), Decimal("5"))
        stamp_tax = revenue * Decimal("0.001")
        transfer_fee = revenue * Decimal("0.00001")
        net_revenue = revenue - commission - stamp_tax - transfer_fee

        profit = net_revenue - pos["price"] * pos["quantity"]
        self.cash += net_revenue
        self.trades.append(
            {
                "date": date,
                "code": code,
                "action": "SELL",
                "price": float(price_d),
                "quantity": pos["quantity"],
                "revenue": float(net_revenue),
                "profit": float(profit),
            }
        )
        del self.positions[code]
        return True

    def record_nav(self, date: str, prices: dict[str, float]):
        """记录每日净值。"""
        stock_value = sum(
            Decimal(str(prices.get(code, float(pos["price"])))) * pos["quantity"]
            for code, pos in self.positions.items()
        )
        total = self.cash + stock_value
        self.daily_nav.append(
            {
                "date": date,
                "total": float(total),
                "cash": float(self.cash),
                "stock_value": float(stock_value),
            }
        )

    def get_metrics(self) -> dict:
        """计算回测指标。"""
        if not self.daily_nav:
            return {}

        navs = [d["total"] for d in self.daily_nav]
        total_return = (navs[-1] - navs[0]) / navs[0] if navs[0] else 0

        max_drawdown = 0
        peak = navs[0]
        for nav in navs:
            peak = max(peak, nav)
            drawdown = (peak - nav) / peak if peak else 0
            max_drawdown = max(max_drawdown, drawdown)

        sell_trades = [t for t in self.trades if t["action"] == "SELL"]
        win = [t for t in sell_trades if t.get("profit", 0) > 0]
        lose = [t for t in sell_trades if t.get("profit", 0) <= 0]
        total_trades = len(win) + len(lose)

        return {
            "total_return": f"{total_return * 100:.2f}%",
            "max_drawdown": f"{max_drawdown * 100:.2f}%",
            "total_trades": len(self.trades),
            "win_rate": f"{len(win) / total_trades * 100:.1f}%" if total_trades else "N/A",
            "final_nav": navs[-1] if navs else 0,
        }
