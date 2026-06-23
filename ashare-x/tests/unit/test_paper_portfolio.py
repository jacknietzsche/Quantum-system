"""PaperPortfolio 交易仿真度单元测试。"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from services.paper_portfolio import PaperPortfolio


@pytest.fixture()
def portfolio(tmp_path, monkeypatch):
    """构造使用临时数据库的 PaperPortfolio，并 mock 数据总线。"""
    from providers import data_bus as db_mod

    fake_bus = MagicMock()
    fake_bus.get_stock_info.return_value = {"latest_price": 110.0, "prev_close": 100.0}
    fake_bus.get_kline.return_value = [
        {"trade_date": "2026-06-19", "open": 99, "high": 101, "low": 98, "close": 100},
        {"trade_date": "2026-06-20", "open": 105, "high": 110, "low": 104, "close": 110},
    ]
    monkeypatch.setattr(db_mod, "DatabaseFirstDataBus", lambda *args, **kwargs: fake_bus)

    db_path = tmp_path / "portfolio.db"
    pp = PaperPortfolio(db_path=str(db_path), config=None)
    pp.slippage = 0.0  # 默认关闭滑点，便于精确断言
    return pp


class TestBuy:
    def test_buy_success(self, portfolio):
        result = portfolio.buy("600519", "茅台", 100.0, 100, "测试买入")
        assert result["ok"] is True
        assert result["shares"] == 100
        assert result["price"] == 100.0

    def test_buy_rejects_non_lot(self, portfolio):
        result = portfolio.buy("600519", "茅台", 100.0, 50)
        assert result["ok"] is False
        assert "100股" in result["error"]

    def test_buy_rejects_insufficient_funds(self, portfolio):
        result = portfolio.buy("600519", "茅台", 105.0, 1000)
        assert result["ok"] is False
        assert "资金不足" in result["error"]

    def test_buy_rejects_limit_up(self, portfolio):
        # 主板涨停价为 100 * 1.1 = 110
        result = portfolio.buy("600519", "茅台", 110.0, 100)
        assert result["ok"] is False
        assert "涨停限制" in result["error"]

    def test_buy_applies_slippage(self, portfolio):
        portfolio.slippage = 0.01
        result = portfolio.buy("600519", "茅台", 100.0, 100)
        assert result["ok"] is True
        assert result["price"] == 101.0


class TestAdd:
    def test_add_to_existing(self, portfolio):
        portfolio.buy("600519", "茅台", 100.0, 100)
        result = portfolio.add("600519", "茅台", 105.0, 100, "加仓")
        assert result["ok"] is True
        assert result["total_shares"] == 200
        assert result["new_avg_cost"] == 102.5

    def test_add_falls_back_to_buy(self, portfolio):
        result = portfolio.add("600519", "茅台", 100.0, 100)
        assert result["ok"] is True
        assert result["action"] == "BUY"

    def test_add_rejects_limit_up(self, portfolio):
        portfolio.buy("600519", "茅台", 100.0, 100)
        result = portfolio.add("600519", "茅台", 110.0, 100)
        assert result["ok"] is False
        assert "涨停限制" in result["error"]


class TestReduceAndClear:
    def test_reduce_success(self, portfolio):
        portfolio.buy("600519", "茅台", 100.0, 200)
        # 买入当日全部 T+1 冻结，无法卖出
        result = portfolio.reduce("600519", 110.0, 100)
        assert result["ok"] is False
        assert "T+1" in result["error"]

    def test_reduce_after_unblock(self, portfolio):
        portfolio.buy("600519", "茅台", 100.0, 200)
        portfolio.update_prices()
        result = portfolio.reduce("600519", 110.0, 100)
        assert result["ok"] is True
        assert result["remaining_shares"] == 100

    def test_reduce_rejects_limit_down(self, portfolio):
        portfolio.buy("600519", "茅台", 100.0, 200)
        portfolio.update_prices()
        # 跌停价为 100 * 0.9 = 90
        result = portfolio.reduce("600519", 90.0, 100)
        assert result["ok"] is False
        assert "跌停限制" in result["error"]

    def test_clear_success(self, portfolio):
        portfolio.buy("600519", "茅台", 100.0, 100)
        portfolio.update_prices()
        result = portfolio.clear("600519", 110.0, "清仓")
        assert result["ok"] is True
        assert result["action"] == "REDUCE"
        assert result["remaining_shares"] == 0


class TestLimitHelpers:
    def test_detect_price_limit_main_board(self, portfolio):
        assert portfolio._detect_price_limit_pct("600519") == 0.10
        assert portfolio._detect_price_limit_pct("000001") == 0.10

    def test_detect_price_limit_star_chinext(self, portfolio):
        assert portfolio._detect_price_limit_pct("688981") == 0.20
        assert portfolio._detect_price_limit_pct("300750") == 0.20
        assert portfolio._detect_price_limit_pct("839680") == 0.20

    def test_get_limit_prices(self, portfolio):
        up, down = portfolio._get_limit_prices("600519")
        assert up == 110.0
        assert down == 90.0

    def test_get_limit_prices_no_data(self, portfolio, monkeypatch):
        monkeypatch.setattr(portfolio, "_fetch_prev_close", lambda code: None)
        up, down = portfolio._get_limit_prices("600519")
        assert up is None
        assert down is None


class TestAccountAndHoldings:
    def test_get_holdings(self, portfolio):
        portfolio.buy("600519", "茅台", 100.0, 100)
        holdings = portfolio.get_holdings()
        assert len(holdings) == 1
        assert holdings[0]["shares"] == 100

    def test_get_account(self, portfolio):
        portfolio.buy("600519", "茅台", 100.0, 100)
        account = portfolio.get_account()
        assert account["holding_count"] == 1
        assert account["cash"] < account["initial_capital"]

    def test_get_trade_history(self, portfolio):
        portfolio.buy("600519", "茅台", 100.0, 100)
        history = portfolio.get_trade_history()
        assert len(history) == 1
        assert history[0]["action"] == "BUY"


class TestDailyPlanExecution:
    def test_execute_paper_trade_routes_to_portfolio(self, tmp_path, monkeypatch):
        from services.daily_plan import DailyPlanGenerator
        from services.position_engine import PositionDecision

        fake_portfolio = MagicMock()
        fake_portfolio.buy.return_value = {"ok": True, "action": "BUY"}

        monkeypatch.setattr(DailyPlanGenerator, "__init__", lambda self, config=None: None)
        gen = DailyPlanGenerator()
        gen.portfolio = fake_portfolio

        decision = PositionDecision(
            action="INITIAL_BUY", stock_code="600519", stock_name="茅台",
            target_shares=100, current_price=100.0, target_price=100.0,
            reasoning="买入",
        )
        result = gen._execute_paper_trade(decision)
        assert result["ok"] is True
        fake_portfolio.buy.assert_called_once_with(
            "600519", "茅台", 100.0, 100, "买入"
        )

    def test_execute_paper_trade_returns_error(self, tmp_path, monkeypatch):
        from services.daily_plan import DailyPlanGenerator
        from services.position_engine import PositionDecision

        fake_portfolio = MagicMock()
        fake_portfolio.clear.return_value = {"ok": False, "error": "跌停限制"}

        monkeypatch.setattr(DailyPlanGenerator, "__init__", lambda self, config=None: None)
        gen = DailyPlanGenerator()
        gen.portfolio = fake_portfolio

        decision = PositionDecision(
            action="CLEAR", stock_code="600519", stock_name="茅台",
            current_price=90.0, target_price=90.0, reasoning="清仓",
        )
        result = gen._execute_paper_trade(decision)
        assert result["ok"] is False
        assert "跌停限制" in result["error"]
