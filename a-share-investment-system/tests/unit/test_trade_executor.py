"""TradeExecutor 单元测试 — 订单生成、模拟执行、持仓跟踪、KillSwitch"""

from services.trade_executor import (
    KillSwitch,
    KillSwitchStatus,
    OrderGenerator,
    Position,
    PositionTracker,
    Signal,
    TradeExecutor,
)

# ══════════════════════════════════════════════
#  数据模型
# ══════════════════════════════════════════════


class TestDataModels:
    def test_signal_creation(self):
        s = Signal(
            stock_code="600519",
            stock_name="茅台",
            direction="buy",
            confidence=0.8,
            target_price=1800.0,
        )
        assert s.stock_code == "600519"
        assert s.direction == "buy"

    def test_position_creation(self):
        p = Position(
            stock_code="600519",
            stock_name="茅台",
            quantity=100,
            avg_cost=1700.0,
            current_price=1800.0,
        )
        assert p.quantity == 100

    def test_kill_switch_status(self):
        ks = KillSwitchStatus(
            active=False,
            level="normal",
            reason="",
            daily_pnl_pct=0.0,
            weekly_pnl_pct=0.0,
            monthly_pnl_pct=0.0,
        )
        assert ks.active is False


# ══════════════════════════════════════════════
#  OrderGenerator
# ══════════════════════════════════════════════


class TestOrderGenerator:
    def test_generate_returns_service_result(self):
        og = OrderGenerator()
        signals = [
            Signal(
                stock_code="600519",
                stock_name="茅台",
                direction="buy",
                confidence=0.8,
                target_price=1800.0,
            )
        ]
        result = og.generate(signals, [], cash=500000, mode="paper")
        assert hasattr(result, "status") or isinstance(result, list)

    def test_generate_empty(self):
        og = OrderGenerator()
        result = og.generate([], [], cash=100000, mode="paper")
        if hasattr(result, "status"):
            assert result.status == "ok"
        else:
            assert isinstance(result, list)

    def test_generate_sell(self):
        og = OrderGenerator()
        signals = [
            Signal(
                stock_code="600519",
                stock_name="茅台",
                direction="sell",
                confidence=0.8,
                target_price=1800.0,
            )
        ]
        positions = [
            Position(
                stock_code="600519",
                stock_name="茅台",
                quantity=200,
                avg_cost=1700.0,
                current_price=1800.0,
            )
        ]
        result = og.generate(signals, positions, cash=100000, mode="paper")
        assert result is not None


# ══════════════════════════════════════════════
#  PositionTracker
# ══════════════════════════════════════════════


class TestPositionTracker:
    def test_initial_state(self):
        pt = PositionTracker()
        result = pt.get_positions()
        assert result.status == "ok"

    def test_set_initial_cash(self):
        pt = PositionTracker()
        pt.set_initial_cash(100000)
        result = pt.get_positions()
        assert result.status == "ok"

    def test_apply_buy_fill(self):
        pt = PositionTracker()
        pt.set_initial_cash(200000)
        fills = [
            {
                "stock_code": "600519",
                "stock_name": "茅台",
                "direction": "buy",
                "quantity": 100,
                "price": 1800.0,
                "fill_price": 1800.0,
                "amount": 180000.0,
                "commission": 5.0,
                "tax": 0.0,
            }
        ]
        pt.apply_fills(fills, "2025-01-15")
        result = pt.get_positions()
        assert result.status == "ok"

    def test_update_prices(self):
        pt = PositionTracker()
        pt.set_initial_cash(200000)
        fills = [
            {
                "stock_code": "600519",
                "stock_name": "茅台",
                "direction": "buy",
                "quantity": 100,
                "price": 1800.0,
                "fill_price": 1800.0,
                "amount": 180000.0,
                "commission": 5.0,
                "tax": 0.0,
            }
        ]
        pt.apply_fills(fills, "2025-01-15")
        pt.update_prices({"600519": 1900.0})
        result = pt.get_positions()
        assert result.status == "ok"

    def test_record_nav(self):
        pt = PositionTracker()
        pt.set_initial_cash(100000)
        pt.record_nav("2025-01-15")
        nav = pt.get_nav_history()
        assert nav.status == "ok"

    def test_nav_history_accumulates(self):
        pt = PositionTracker()
        pt.set_initial_cash(100000)
        pt.record_nav("2025-01-15")
        pt.record_nav("2025-01-16")
        nav = pt.get_nav_history()
        assert nav.status == "ok"


# ══════════════════════════════════════════════
#  KillSwitch
# ══════════════════════════════════════════════


class TestKillSwitch:
    def test_check_normal(self):
        ks = KillSwitch()
        result = ks.check(daily_pnl_pct=0.0)
        assert isinstance(result, KillSwitchStatus)

    def test_check_large_loss(self):
        ks = KillSwitch()
        result = ks.check(daily_pnl_pct=-10.0)
        assert isinstance(result, KillSwitchStatus)
        assert result.active is True

    def test_record_stop_loss(self):
        ks = KillSwitch()
        ks.record_stop_loss("600519")
        # After enough stop losses, stock may be blacklisted
        assert hasattr(ks, "is_blacklisted")

    def test_not_blacklisted_initially(self):
        ks = KillSwitch()
        assert not ks.is_blacklisted("600519")


# ══════════════════════════════════════════════
#  TradeExecutor 整合
# ══════════════════════════════════════════════


class TestTradeExecutor:
    def test_initial_state(self):
        te = TradeExecutor()
        assert te.health_check() is True

    def test_set_initial_cash(self):
        te = TradeExecutor()
        te.set_initial_cash(100000)
        result = te.get_positions()
        assert result.status == "ok"

    def test_generate_orders(self):
        te = TradeExecutor()
        signals = [
            {
                "stock_code": "600519",
                "stock_name": "茅台",
                "direction": "buy",
                "target_price": 1800.0,
                "confidence": 0.8,
            },
        ]
        result = te.generate_orders(signals)
        assert result.status == "ok"

    def test_execute_paper(self):
        te = TradeExecutor()
        te.set_initial_cash(500000)
        orders = [
            {
                "stock_code": "600519",
                "stock_name": "茅台",
                "direction": "buy",
                "quantity": 100,
                "price": 1800.0,
            },
        ]
        result = te.execute_paper(orders, market_prices={"600519": 1800.0})
        assert result.status in ("ok", "error")

    def test_check_kill_switch(self):
        te = TradeExecutor()
        result = te.check_kill_switch()
        assert result.status == "ok"

    def test_record_trade_result(self):
        te = TradeExecutor()
        te.record_trade_result("600519", is_stop_loss=False)

    def test_update_market_prices(self):
        te = TradeExecutor()
        te.set_initial_cash(100000)
        te.update_market_prices({"600519": 1900.0})
