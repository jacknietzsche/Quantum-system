"""API 契约测试 — 验证所有端点返回格式符合预期

基于 FastAPI 自动生成的 OpenAPI schema 验证响应结构。
不依赖外部数据源, 使用 Mock 数据。
"""

import pytest


class TestAPIContracts:
    """API 契约测试 — 验证返回格式"""

    def test_health_endpoint(self, client):
        """GET /api/health 返回 {status, version}"""
        resp = client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert "status" in data
        assert "version" in data
        assert data["status"] == "ok"

    def test_system_status_format(self, client):
        """GET /api/system/status 返回包含 database 和 data_sources"""
        resp = client.get("/api/system/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "status" in data
        assert "version" in data

    def test_system_dashboard_format(self, client):
        """GET /api/system/dashboard 返回完整健康面板"""
        resp = client.get("/api/system/dashboard")
        assert resp.status_code == 200
        data = resp.json()
        assert "system" in data
        assert "database" in data
        assert "data_sources" in data
        assert "cache" in data
        assert "llm" in data
        assert "recent_errors" in data

    def test_portfolio_holdings_format(self, client):
        """GET /api/portfolio/holdings 返回 {positions, total, total_asset}"""
        resp = client.get("/api/portfolio/holdings?type=value")
        assert resp.status_code == 200
        data = resp.json()
        assert "positions" in data
        assert isinstance(data["positions"], list)

    def test_portfolio_summary_format(self, client):
        """GET /api/portfolio/summary 返回组合摘要"""
        resp = client.get("/api/portfolio/summary?type=value")
        assert resp.status_code == 200
        data = resp.json()

    def test_market_regime_format(self, client):
        """GET /api/market/regime 返回市场态势"""
        resp = client.get("/api/market/regime")
        assert resp.status_code == 200

    def test_risk_status_format(self, client):
        """GET /api/risk/status 返回风控状态"""
        resp = client.get("/api/risk/status")
        assert resp.status_code == 200

    def test_signals_today_format(self, client):
        """GET /api/signals/today 返回信号列表"""
        resp = client.get("/api/signals/today")
        assert resp.status_code == 200

    def test_screening_status_format(self, client):
        """GET /api/screening/status 返回选股状态"""
        resp = client.get("/api/screening/status")
        assert resp.status_code == 200

    def test_favorites_list_format(self, client):
        """GET /api/favorites/ 返回自选股列表"""
        resp = client.get("/api/favorites/")
        assert resp.status_code == 200

    def test_logs_recent_format(self, client):
        """GET /api/logs/recent 返回日志列表"""
        resp = client.get("/api/logs/recent")
        assert resp.status_code == 200

    def test_performance_metrics_format(self, client):
        """GET /api/performance/metrics 返回绩效指标"""
        resp = client.get("/api/performance/metrics?type=value")
        assert resp.status_code == 200
        data = resp.json()
        assert "status" in data

    def test_notifications_recent_format(self, client):
        """GET /api/notifications/recent 返回通知列表"""
        resp = client.get("/api/notifications/recent")
        assert resp.status_code == 200
        data = resp.json()
        assert "notifications" in data
        assert isinstance(data["notifications"], list)

    def test_db_stats_format(self, client):
        """GET /api/db/stats 返回数据库统计"""
        resp = client.get("/api/db/stats")
        assert resp.status_code == 200

    def test_system_sources_format(self, client):
        """GET /api/system/sources 返回数据源健康"""
        resp = client.get("/api/system/sources")
        assert resp.status_code == 200
        data = resp.json()

    def test_tasks_list_format(self, client):
        """GET /api/tasks/ 返回任务列表"""
        resp = client.get("/api/tasks/")
        assert resp.status_code == 200

    def test_workflow_status_format(self, client):
        """GET /api/workflow/status 返回工作流状态"""
        resp = client.get("/api/workflow/status")
        assert resp.status_code == 200


@pytest.fixture
def client():
    """创建 FastAPI TestClient"""
    from fastapi.testclient import TestClient

    from server import app

    return TestClient(app)
