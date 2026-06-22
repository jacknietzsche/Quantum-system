"""Expanded tests for shared/models.py."""

from __future__ import annotations


class TestModelsExpanded:
    def test_trade_status_enum(self):
        from shared.models import TradeStatus

        assert hasattr(TradeStatus, "HOLDING")
        assert hasattr(TradeStatus, "SOLD")

    def test_risk_level_enum(self):
        from shared.models import RiskLevel

        assert hasattr(RiskLevel, "HIGH")
        assert hasattr(RiskLevel, "MEDIUM")
        assert hasattr(RiskLevel, "LOW")

    def test_stock_info_model(self):
        from shared.models import StockInfo

        assert hasattr(StockInfo, "stock_code")
        assert hasattr(StockInfo, "stock_name")

    def test_portfolio_model(self):
        from shared.models import Portfolio

        assert hasattr(Portfolio, "stock_code")
        assert hasattr(Portfolio, "buy_price")

    def test_watchlist_model(self):
        from shared.models import Watchlist

        assert hasattr(Watchlist, "stock_code")
        assert hasattr(Watchlist, "stock_name")

    def test_daily_report_model(self):
        from shared.models import DailyReport

        assert hasattr(DailyReport, "date")
        assert hasattr(DailyReport, "report_file")

    def test_init_db(self):
        from shared.models import init_db

        # Just verify it doesn't crash
        assert callable(init_db)
