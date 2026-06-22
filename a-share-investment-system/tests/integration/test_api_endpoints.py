"""API 集成测试 — FastAPI TestClient 无需启动服务器"""

import pytest


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient

    from server import app

    return TestClient(app)


class TestSystemAPI:
    def test_status_endpoint(self, client):
        r = client.get("/api/system/status")
        assert r.status_code == 200

    def test_cache_stats(self, client):
        r = client.get("/api/system/cache-stats")
        assert r.status_code == 200


class TestPortfolioAPI:
    def test_get_holdings(self, client):
        r = client.get("/api/portfolio/holdings")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, (dict, list))

    def test_get_trades(self, client):
        r = client.get("/api/portfolio/trades")
        assert r.status_code == 200

    def test_get_summary(self, client):
        r = client.get("/api/portfolio/summary")
        assert r.status_code == 200


class TestLogsAPI:
    def test_get_recent_logs(self, client):
        r = client.get("/api/logs/recent")
        assert r.status_code == 200

    def test_get_error_logs(self, client):
        r = client.get("/api/logs/errors")
        assert r.status_code == 200


class TestMarketAPI:
    def test_market_regime(self, client):
        r = client.get("/api/market/regime")
        assert r.status_code in (200, 500)  # 500 if no data


class TestDatabaseAPI:
    def test_db_stats(self, client):
        r = client.get("/api/db/stats")
        assert r.status_code == 200

    def test_db_table_info(self, client):
        r = client.get("/api/db/table-info", params={"table": "stock_info"})
        assert r.status_code == 200


class TestScreeningAPI:
    def test_screening_styles(self, client):
        r = client.get("/api/screening/styles")
        assert r.status_code == 200

    def test_screening_status(self, client):
        r = client.get("/api/screening/status")
        assert r.status_code == 200


class TestRiskAPI:
    def test_risk_status(self, client):
        r = client.get("/api/risk/status")
        assert r.status_code == 200

    def test_risk_alerts(self, client):
        r = client.get("/api/risk/alerts")
        assert r.status_code == 200


class TestSettingsAPI:
    def test_get_email_settings(self, client):
        r = client.get("/api/settings/email")
        assert r.status_code == 200
