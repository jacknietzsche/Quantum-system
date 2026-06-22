"""Tests for API routes - portfolio, risk."""

from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient


class TestPortfolioRoutes:
    def test_portfolio_summary(self):
        from api.routes.portfolio import router

        app = FastAPI()
        app.include_router(router, prefix="/api/portfolio")
        client = TestClient(app)
        with patch("api.routes.portfolio._get_service") as msvc:
            mock_svc = MagicMock()
            mock_svc.get_portfolio_summary.return_value = {"status": "ok", "total_asset": 0}
            msvc.return_value = mock_svc
            response = client.get("/api/portfolio/summary")
            assert response.status_code == 200

    def test_portfolio_holdings(self):
        from api.routes.portfolio import router

        app = FastAPI()
        app.include_router(router, prefix="/api/portfolio")
        client = TestClient(app)
        with patch("api.routes.portfolio._get_service") as msvc:
            mock_svc = MagicMock()
            mock_svc.get_holdings.return_value = {"status": "ok", "positions": []}
            msvc.return_value = mock_svc
            response = client.get("/api/portfolio/holdings")
            assert response.status_code == 200

    def test_portfolio_all_summaries(self):
        from api.routes.portfolio import router

        app = FastAPI()
        app.include_router(router, prefix="/api/portfolio")
        client = TestClient(app)
        with patch("api.routes.portfolio._get_service") as msvc:
            mock_svc = MagicMock()
            mock_svc.get_all_portfolios_summary.return_value = {"portfolios": {}}
            msvc.return_value = mock_svc
            response = client.get("/api/portfolio/all-summaries")
            assert response.status_code == 200


class TestRiskRoutes:
    def test_risk_status(self):
        from api.routes.risk import router

        app = FastAPI()
        app.include_router(router, prefix="/api/risk")
        client = TestClient(app)
        with (
            patch("services.risk_engine.RiskEngine") as mre,
            patch("services.trade_executor.TradeExecutor") as mte,
        ):
            mock_re = MagicMock()
            mock_re.full_audit.return_value.data = {"pass": True}
            mre.return_value = mock_re
            mock_te = MagicMock()
            mock_te.get_positions.return_value.data = {"positions": []}
            mock_te.check_kill_switch.return_value.data = {"active": False}
            mte.return_value = mock_te
            response = client.get("/api/risk/status")
            assert response.status_code == 200

    def test_risk_alerts(self):
        from api.routes.risk import router

        app = FastAPI()
        app.include_router(router, prefix="/api/risk")
        client = TestClient(app)
        response = client.get("/api/risk/alerts")
        assert response.status_code == 200

    def test_risk_portfolio_var(self):
        from api.routes.risk import router

        app = FastAPI()
        app.include_router(router, prefix="/api/risk")
        client = TestClient(app)
        response = client.get("/api/risk/portfolio-var")
        assert response.status_code == 200

    def test_risk_stress_test(self):
        from api.routes.risk import router

        app = FastAPI()
        app.include_router(router, prefix="/api/risk")
        client = TestClient(app)
        response = client.get("/api/risk/stress-test")
        assert response.status_code == 200
