"""Unit tests for services.risk."""

from unittest.mock import MagicMock


class TestRiskService:
    def _make_service(self, holdings=None):
        from services.risk import RiskService

        mock_session = MagicMock()
        mock_db = MagicMock()
        mock_session.return_value = mock_db
        if holdings is None:
            mock_db.query.return_value.filter_by.return_value.all.return_value = []
        else:
            mock_db.query.return_value.filter_by.return_value.all.return_value = holdings
        svc = RiskService(db_session_factory=mock_session)
        return svc, mock_db

    def test_audit_no_holdings(self):
        svc, _ = self._make_service([])
        result = svc.audit()
        assert result["status"] == "ok"
        assert result["overall_pass"] is True
        assert result["stock_risks"] == []

    def test_audit_with_holdings(self):
        h1 = MagicMock()
        h1.stock_code = "600519"
        h1.stock_name = "Moutai"
        h1.cost_value = 180000
        h1.profit_loss_pct = 5.0
        h2 = MagicMock()
        h2.stock_code = "000858"
        h2.stock_name = "Wuliangye"
        h2.cost_value = 75000
        h2.profit_loss_pct = -3.0
        svc, _ = self._make_service([h1, h2])
        result = svc.audit()
        assert result["status"] == "ok"
        assert result["overall_pass"] is True
        assert len(result["stock_risks"]) == 2

    def test_position_plan_no_holdings(self):
        svc, _ = self._make_service([])
        result = svc.position_plan()
        assert result["status"] == "ok"
        assert result["holding_count"] == 0

    def test_position_plan_with_holdings(self):
        h1 = MagicMock()
        h1.stock_code = "600519"
        h1.stock_name = "Moutai"
        h1.cost_value = 180000
        h1.profit_loss_pct = 5.0
        svc, _ = self._make_service([h1])
        result = svc.position_plan()
        assert result["status"] == "ok"
        assert result["holding_count"] == 1
        assert len(result["stock_distribution"]) == 1

    def test_get_review_stats(self):
        svc, _ = self._make_service([])
        result = svc.get_review_stats()
        assert result["status"] == "ok"
