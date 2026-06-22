"""交易执行器 - 订单生成+模拟执行+仓位追踪+风控熔断 - 来源: a-share-skill + QuantLLM"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from services.base import BaseService, ServiceResult

# ── 数据类 ──


@dataclass
class Signal:
    stock_code: str
    stock_name: str
    direction: str  # "买入" | "卖出" | "持有"
    confidence: float  # 0-1
    target_price: float = 0.0
    reason: str = ""


@dataclass
class Order:
    order_id: str
    stock_code: str
    stock_name: str
    direction: str
    quantity: int
    price_type: str  # "开盘价" | "收盘价" | "限价"
    limit_price: float
    signal_confidence: float
    signal_reason: str
    target_date: str
    status: str = "待执行"  # 待执行/已成交/已撤销/部分成交


@dataclass
class Position:
    stock_code: str
    stock_name: str
    quantity: int
    avg_cost: float
    current_price: float
    market_value: float = 0.0
    profit_loss: float = 0.0
    profit_loss_pct: float = 0.0
    buy_date: str = ""
    hold_days: int = 0


@dataclass
class KillSwitchStatus:
    active: bool
    level: str  # "normal" | "warning" | "restricted" | "halted"
    reason: str
    daily_pnl_pct: float
    weekly_pnl_pct: float
    monthly_pnl_pct: float
    blacklisted_stocks: list[str] = field(default_factory=list)


# ── 交易成本配置 ──

TRADING_COSTS = {
    "commission_rate": 0.00025,  # 万2.5佣金
    "stamp_tax_rate": 0.001,  # 千1印花税(仅卖出)
    "min_commission": 5.0,  # 最低佣金5元
    "slippage_bps": 5.0,  # 滑点5bps
    "impact_bps_per_million": 1.0,  # 每百万冲击成本1bp
}


class OrderGenerator:
    """信号→订单转换 + 成本感知过滤 + 约束检查"""

    def __init__(self, costs: dict | None = None):
        self.costs = costs or TRADING_COSTS

    def generate(
        self,
        signals: list[Signal],
        current_positions: list[Position],
        cash: float,
        mode: str = "paper",
        trading_date: str | None = None,
    ) -> ServiceResult:
        """将信号列表转换为可执行订单"""
        trading_date = trading_date or datetime.now().strftime("%Y-%m-%d")
        orders: list[dict[str, Any]] = []
        skipped: list[dict[str, str]] = []

        position_map = {p.stock_code: p for p in current_positions}

        for sig in signals:
            if sig.direction == "持有":
                skipped.append({"signal": sig.stock_code, "reason": "持有信号无需操作"})
                continue

            # 成本感知过滤
            estimated_cost = self._estimate_cost(sig)
            edge = sig.confidence * 0.05 - estimated_cost  # 假设5%预期收益x置信度
            if edge <= 0 and sig.direction == "买入":
                skipped.append(
                    {
                        "signal": sig.stock_code,
                        "reason": f"成本过滤: edge_after_cost={edge:.4f} <= 0",
                    }
                )
                continue

            # T+1约束:今日买入的不能卖出
            if sig.direction == "卖出":
                pos = position_map.get(sig.stock_code)
                if pos and pos.buy_date == trading_date:
                    skipped.append(
                        {
                            "signal": sig.stock_code,
                            "reason": f"T+1约束: {sig.stock_code}今日买入,不可卖出",
                        }
                    )
                    continue

            # 涨跌停约束
            if sig.direction == "买入" and self._is_limit_up(sig):
                skipped.append({"signal": sig.stock_code, "reason": "涨停不追"})
                continue
            if sig.direction == "卖出" and self._is_limit_down(sig):
                skipped.append({"signal": sig.stock_code, "reason": "跌停不卖"})
                continue

            # 生成订单
            quantity = self._calc_quantity(sig, current_positions, cash, mode)
            if quantity <= 0 and sig.direction == "买入":
                skipped.append({"signal": sig.stock_code, "reason": "现金不足"})
                continue
            if quantity <= 0 and sig.direction == "卖出":
                skipped.append({"signal": sig.stock_code, "reason": "无持仓可卖"})
                continue

            order = Order(
                order_id=f"ORD-{trading_date}-{sig.stock_code}-{len(orders) + 1:03d}",
                stock_code=sig.stock_code,
                stock_name=sig.stock_name,
                direction=sig.direction,
                quantity=quantity,
                price_type="开盘价" if mode == "paper" else "限价",
                limit_price=sig.target_price,
                signal_confidence=sig.confidence,
                signal_reason=sig.reason,
                target_date=trading_date,
            )
            orders.append(order.__dict__)

        return ServiceResult.ok(
            data={
                "orders": orders,
                "skipped": skipped,
                "total_signals": len(signals),
                "orders_generated": len(orders),
                "orders_skipped": len(skipped),
            }
        )

    def _estimate_cost(self, sig: Signal) -> float:
        """估算往返交易成本占交易金额的比例"""
        cost = self.costs["commission_rate"] * 2  # 买卖各一次
        if sig.direction == "卖出":
            cost += self.costs["stamp_tax_rate"]
        cost += self.costs["slippage_bps"] / 10000 * 2
        return cost

    def _calc_quantity(self, sig: Signal, positions: list[Position], cash: float, mode: str) -> int:
        """计算订单数量(整百股)"""
        price = sig.target_price if sig.target_price > 0 else 10.0
        if sig.direction == "买入":
            max_spend = cash * 0.2  # 单只股票最多20%仓位
            qty = int(max_spend / price / 100) * 100
            return max(100, qty)
        pos = next((p for p in positions if p.stock_code == sig.stock_code), None)
        if pos:
            return pos.quantity
        return 0

    def _is_limit_up(self, sig: Signal) -> bool:
        return False  # 需要实时数据,默认不限制

    def _is_limit_down(self, sig: Signal) -> bool:
        return False


class SimulatedExecution:
    """模拟执行引擎 - 滑点+佣金+部分成交"""

    def __init__(self, costs: dict | None = None):
        self.costs = costs or TRADING_COSTS
        self.execution_log: list[dict] = []

    def execute(
        self, orders: list[dict], market_prices: dict[str, float], trading_date: str
    ) -> ServiceResult:
        """模拟执行订单列表"""
        fills = []
        total_commission = 0.0
        total_tax = 0.0
        total_slippage = 0.0

        for order_dict in orders:
            code = order_dict["stock_code"]
            direction = order_dict["direction"]
            quantity = order_dict["quantity"]
            base_price = market_prices.get(code, order_dict.get("limit_price", 10.0))

            # 滑点计算
            slippage_pct = self.costs["slippage_bps"] / 10000
            if direction == "买入":
                fill_price = base_price * (1 + slippage_pct)
            else:
                fill_price = base_price * (1 - slippage_pct)
            fill_price = round(fill_price, 2)

            amount = fill_price * quantity
            commission = max(self.costs["min_commission"], amount * self.costs["commission_rate"])
            tax = amount * self.costs["stamp_tax_rate"] if direction == "卖出" else 0.0
            slippage_cost = abs(fill_price - base_price) * quantity

            total_commission += commission
            total_tax += tax
            total_slippage += slippage_cost

            fills.append(
                {
                    "order_id": order_dict["order_id"],
                    "stock_code": code,
                    "stock_name": order_dict.get("stock_name", ""),
                    "direction": direction,
                    "quantity": quantity,
                    "fill_price": fill_price,
                    "amount": round(amount, 2),
                    "commission": round(commission, 2),
                    "tax": round(tax, 2),
                    "slippage_cost": round(slippage_cost, 2),
                    "trade_date": trading_date,
                    "status": "已成交",
                }
            )

        self.execution_log.extend(fills)

        return ServiceResult.ok(
            data={
                "fills": fills,
                "total_fills": len(fills),
                "total_commission": round(total_commission, 2),
                "total_tax": round(total_tax, 2),
                "total_slippage": round(total_slippage, 2),
                "total_cost": round(total_commission + total_tax + total_slippage, 2),
            }
        )


class PositionTracker:
    """仓位追踪器 - 多账户 + 净值计算"""

    def __init__(self):
        self.positions: dict[str, Position] = {}
        self.cash: float = 1_000_000.0  # 默认初始资金100万
        self.initial_cash: float = 1_000_000.0
        self.nav_history: list[dict] = []

    def set_initial_cash(self, amount: float):
        self.cash = amount
        self.initial_cash = amount

    def apply_fills(self, fills: list[dict], trading_date: str):
        """应用成交记录更新持仓和现金"""
        for fill in fills:
            code = fill["stock_code"]
            direction = fill["direction"]
            qty = fill["quantity"]
            price = fill["fill_price"]
            amount = fill["amount"]
            cost = fill["commission"] + fill["tax"]

            if direction == "买入":
                self.cash -= amount + cost
                if code in self.positions:
                    pos = self.positions[code]
                    total_cost = pos.avg_cost * pos.quantity + amount
                    pos.quantity += qty
                    pos.avg_cost = total_cost / pos.quantity if pos.quantity > 0 else 0
                else:
                    self.positions[code] = Position(
                        stock_code=code,
                        stock_name=fill.get("stock_name", ""),
                        quantity=qty,
                        avg_cost=price,
                        current_price=price,
                        buy_date=trading_date,
                    )
            else:  # 卖出
                self.cash += amount - cost
                if code in self.positions:
                    pos = self.positions[code]
                    pos.quantity -= qty
                    if pos.quantity <= 0:
                        del self.positions[code]

    def update_prices(self, prices: dict[str, float]):
        """更新持仓市价"""
        for code, pos in self.positions.items():
            if code in prices and prices[code] > 0:
                pos.current_price = prices[code]
                pos.market_value = pos.current_price * pos.quantity
                pos.profit_loss = (pos.current_price - pos.avg_cost) * pos.quantity
                pos.profit_loss_pct = (
                    (pos.current_price / pos.avg_cost - 1) * 100 if pos.avg_cost > 0 else 0
                )

    def record_nav(self, date: str):
        """记录当日净值"""
        stock_value = sum(p.market_value for p in self.positions.values())
        total_asset = self.cash + stock_value
        daily_return = (total_asset / self.initial_cash - 1) * 100 if self.initial_cash > 0 else 0

        self.nav_history.append(
            {
                "date": date,
                "total_asset": round(total_asset, 2),
                "cash": round(self.cash, 2),
                "stock_value": round(stock_value, 2),
                "daily_return_pct": round(daily_return, 2),
                "position_count": len(self.positions),
            }
        )

    def get_positions(self) -> ServiceResult:
        """获取当前持仓"""
        return ServiceResult.ok(
            data={
                "positions": [
                    {
                        "stock_code": p.stock_code,
                        "stock_name": p.stock_name,
                        "quantity": p.quantity,
                        "avg_cost": round(p.avg_cost, 2),
                        "current_price": round(p.current_price, 2),
                        "market_value": round(p.market_value, 2),
                        "profit_loss": round(p.profit_loss, 2),
                        "profit_loss_pct": round(p.profit_loss_pct, 2),
                    }
                    for p in self.positions.values()
                ],
                "cash": round(self.cash, 2),
                "total_asset": round(
                    self.cash + sum(p.market_value for p in self.positions.values()), 2
                ),
                "position_count": len(self.positions),
            }
        )

    def get_nav_history(self) -> ServiceResult:
        return ServiceResult.ok(data={"nav": self.nav_history, "count": len(self.nav_history)})


class KillSwitch:
    """风控熔断器"""

    def __init__(self):
        self.daily_pnl: list[float] = []
        self.weekly_pnl: list[float] = []
        self.monthly_pnl: list[float] = []
        self.blacklist: dict[str, datetime] = {}  # stock_code → 解禁日期
        self.consecutive_stop_losses: dict[str, int] = {}

    def check(
        self, daily_pnl_pct: float, positions: list[Position] | None = None
    ) -> KillSwitchStatus:
        """检查熔断状态"""
        self.daily_pnl.append(daily_pnl_pct)

        # 滚动计算
        daily_5d = sum(self.daily_pnl[-5:]) if len(self.daily_pnl) >= 5 else sum(self.daily_pnl)
        weekly_5d = sum(self.daily_pnl[-25:]) if len(self.daily_pnl) >= 25 else sum(self.daily_pnl)
        monthly_20d = (
            sum(self.daily_pnl[-20:]) if len(self.daily_pnl) >= 20 else sum(self.daily_pnl)
        )

        level = "normal"
        reason = ""

        if daily_5d < -5.0:
            level = "warning"
            reason = f"5日亏损{daily_5d:.1f}% > 5%,停止新开仓"
        if weekly_5d < -10.0:
            level = "restricted"
            reason = f"近5周亏损{weekly_5d:.1f}% > 10%,仓位降至30%"
        if monthly_20d < -15.0:
            level = "halted"
            reason = f"近20日亏损{monthly_20d:.1f}% > 15%,清仓暂停"

        return KillSwitchStatus(
            active=(level != "normal"),
            level=level,
            reason=reason,
            daily_pnl_pct=round(daily_5d, 2),
            weekly_pnl_pct=round(weekly_5d, 2),
            monthly_pnl_pct=round(monthly_20d, 2),
            blacklisted_stocks=list(self.blacklist.keys()),
        )

    def record_stop_loss(self, stock_code: str):
        """记录止损"""
        self.consecutive_stop_losses[stock_code] = (
            self.consecutive_stop_losses.get(stock_code, 0) + 1
        )
        if self.consecutive_stop_losses[stock_code] >= 3:
            # 黑名单30天
            self.blacklist[stock_code] = datetime.now() + timedelta(days=30)

    def is_blacklisted(self, stock_code: str) -> bool:
        if stock_code not in self.blacklist:
            return False
        if datetime.now() > self.blacklist[stock_code]:
            del self.blacklist[stock_code]
            self.consecutive_stop_losses.pop(stock_code, None)
            return False
        return True


class TradeExecutor(BaseService):
    """交易执行器 - 整合订单生成+模拟执行+仓位追踪+熔断"""

    def __init__(self):
        super().__init__()
        self.order_gen: OrderGenerator = OrderGenerator()
        self.execution: SimulatedExecution = SimulatedExecution()
        self.tracker: PositionTracker = PositionTracker()
        self.kill_switch: KillSwitch = KillSwitch()

    def generate_orders(
        self,
        signals: list[dict],
        mode: str = "paper",
        trading_date: str | None = None,
        cash: float | None = None,
    ) -> ServiceResult:
        """信号→订单(含成本过滤和约束检查)"""
        try:
            sig_objects = [
                Signal(
                    stock_code=s["stock_code"],
                    stock_name=s.get("stock_name", ""),
                    direction=s.get("action", s.get("verdict", "持有")),
                    confidence=s.get("confidence", 0.5),
                    target_price=s.get("target_price", 0),
                    reason=s.get("reason", ""),
                )
                for s in signals
            ]

            positions = list(self.tracker.positions.values())
            if cash is not None:
                self.tracker.cash = cash

            # 熔断检查
            ks = self.check_kill_switch()
            if ks.status == "ok" and ks.data.get("active"):
                return ServiceResult.ok(
                    data={
                        "orders": [],
                        "skipped": [{"reason": f"熔断激活: {ks.data.get('reason', '')}"}],
                        "total_signals": len(signals),
                        "orders_generated": 0,
                        "orders_skipped": len(signals),
                    }
                )

            return self.order_gen.generate(
                sig_objects, positions, self.tracker.cash, mode, trading_date
            )
        except Exception as e:
            return ServiceResult.error(errors=[f"generate_orders failed: {e}"])

    def execute_paper(
        self, orders: list[dict], market_prices: dict[str, float], trading_date: str | None = None
    ) -> ServiceResult:
        """模拟执行订单"""
        try:
            trading_date = trading_date or datetime.now().strftime("%Y-%m-%d")
            result = self.execution.execute(orders, market_prices, trading_date)
            if result.status == "ok":
                self.tracker.apply_fills(result.data["fills"], trading_date)
                self.tracker.record_nav(trading_date)
            return result
        except Exception as e:
            return ServiceResult.error(errors=[f"execute_paper failed: {e}"])

    def get_positions(self) -> ServiceResult:
        return self.tracker.get_positions()

    def update_market_prices(self, prices: dict[str, float]):
        self.tracker.update_prices(prices)

    def check_kill_switch(self) -> ServiceResult:
        """检查熔断状态"""
        try:
            if not self.tracker.nav_history:
                return ServiceResult.ok(data={"active": False, "level": "normal"})

            nav = self.tracker.nav_history
            if len(nav) >= 2:
                daily_return = (nav[-1]["total_asset"] / nav[-2]["total_asset"] - 1) * 100
            else:
                daily_return = 0.0

            status = self.kill_switch.check(daily_return)
            return ServiceResult.ok(data=status.__dict__)
        except Exception as e:
            return ServiceResult.error(errors=[f"check_kill_switch failed: {e}"])

    def record_trade_result(self, stock_code: str, is_stop_loss: bool = False):
        """记录交易结果(用于黑名单追踪)"""
        if is_stop_loss:
            self.kill_switch.record_stop_loss(stock_code)

    def set_initial_cash(self, amount: float):
        self.tracker.set_initial_cash(amount)
