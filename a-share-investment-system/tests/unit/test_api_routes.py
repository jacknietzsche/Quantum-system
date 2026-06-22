"""Tests for API routes - logs, favorites."""

from fastapi import FastAPI
from fastapi.testclient import TestClient


class TestLogsRoutes:
    def test_recent_logs(self):
        from api.routes.logs import router

        app = FastAPI()
        app.include_router(router, prefix="/api/logs")
        client = TestClient(app)
        response = client.get("/api/logs/recent")
        assert response.status_code == 200

    def test_error_summary(self):
        from api.routes.logs import router

        app = FastAPI()
        app.include_router(router, prefix="/api/logs")
        client = TestClient(app)
        response = client.get("/api/logs/errors")
        assert response.status_code == 200

    def test_server_log(self):
        from api.routes.logs import router

        app = FastAPI()
        app.include_router(router, prefix="/api/logs")
        client = TestClient(app)
        response = client.get("/api/logs/server-log")
        assert response.status_code == 200
