"""Tests for services/portfolio.py - expanded coverage."""

from __future__ import annotations

from unittest.mock import MagicMock


class TestPortfolioExpanded:
    def _make(self):
        from services.portfolio import PortfolioService

        mock_db = MagicMock()
        svc = PortfolioService(lambda: mock_db)
        return svc, mock_db

    def test_get_holdings_empty(self):
        svc, db = self._make()
        q = MagicMock()
        q.filter_by.return_value = q
        q.all.return_value = []
        db.query.return_value = q
        result = svc.get_holdings()
        assert result["status"] == "ok"
        assert result["positions"] == []

    def test_get_holdings_with_data(self):
        svc, db = self._make()
        h = MagicMock()
        h.stock_code = "600519"
        h.stock_name = "M"
        h.buy_date = "2025-01-01"
        h.buy_price = 1800
        h.quantity = 100
        h.current_price = 1900
        h.cost_value = 180000
        h.current_value = 190000
        h.profit_loss = 10000
        h.profit_loss_pct = 5.56
        q = MagicMock()
        q.filter_by.return_value = q
        q.all.return_value = [h]
        db.query.return_value = q
        result = svc.get_holdings()
        assert result["status"] == "ok"

    def test_get_holdings_map(self):
        svc, db = self._make()
        q = MagicMock()
        q.filter_by.return_value = q
        q.all.return_value = []
        db.query.return_value = q
        result = svc.get_holdings_map()
        assert isinstance(result, dict)

    def test_reset_portfolio(self):
        svc, db = self._make()
        q = MagicMock()
        q.delete.return_value = None
        db.query.return_value = q
        result = svc.reset_portfolio()
        assert isinstance(result, dict)

    def test_sell_position_no_holding(self):
        svc, db = self._make()
        q = MagicMock()
        q.filter_by.return_value = q
        q.first.return_value = None
        db.query.return_value = q
        result = svc.sell_position("600519", 50, 1900)
        assert isinstance(result, dict)
