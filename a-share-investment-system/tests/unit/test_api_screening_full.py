"""Tests for api.routes.screening."""

from fastapi import FastAPI
from fastapi.testclient import TestClient


def _make_client():
    from api.routes.screening import router

    app = FastAPI()
    app.include_router(router, prefix="/api/screening")
    return TestClient(app)


class TestScreeningRoutesFull:
    def test_styles(self):
        client = _make_client()
        response = client.get("/api/screening/styles")
        assert response.status_code == 200

    def test_status(self):
        client = _make_client()
        response = client.get("/api/screening/status")
        assert response.status_code == 200

    def test_history(self):
        client = _make_client()
        response = client.get("/api/screening/history")
        assert response.status_code == 200

    def test_results(self):
        client = _make_client()
        response = client.get("/api/screening/results")
        assert response.status_code in (200, 404)

    def test_abort(self):
        client = _make_client()
        response = client.post("/api/screening/abort")
        assert response.status_code in (200, 404, 405)

    def test_daily_summary(self):
        client = _make_client()
        response = client.get("/api/screening/daily-summary")
        assert response.status_code in (200, 404)
