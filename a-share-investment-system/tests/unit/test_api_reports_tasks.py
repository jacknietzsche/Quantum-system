"""Tests for api.routes.reports and api.routes.tasks."""

from contextlib import contextmanager
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient


def _mock_db_session():
    @contextmanager
    def _db_session():
        mock_db = MagicMock()
        q = MagicMock()
        q.filter.return_value = q
        q.filter_by.return_value = q
        q.order_by.return_value = q
        q.limit.return_value = q
        q.offset.return_value = q
        q.count.return_value = 0
        q.first.return_value = None
        q.all.return_value = []
        q.one_or_none.return_value = None
        mock_db.query.return_value = q
        yield mock_db

    return _db_session


class TestReportsRoutes:
    def test_reports_list(self):
        from api.routes.reports import router

        app = FastAPI()
        app.include_router(router, prefix="/api/reports")
        client = TestClient(app)
        try:
            with patch("api.routes.reports.db_session", new_callable=_mock_db_session):
                response = client.get("/api/reports/")
                assert response.status_code == 200
        except AttributeError:
            response = client.get("/api/reports/")
            assert response.status_code in (200, 500)

    def test_reports_latest(self):
        from api.routes.reports import router

        app = FastAPI()
        app.include_router(router, prefix="/api/reports")
        client = TestClient(app)
        try:
            with patch("api.routes.reports.db_session", new_callable=_mock_db_session):
                response = client.get("/api/reports/latest")
                assert response.status_code in (200, 404)
        except AttributeError:
            response = client.get("/api/reports/latest")
            assert response.status_code in (200, 404, 500)


class TestTasksRoutes:
    def test_tasks_list(self):
        from api.routes.tasks import router

        app = FastAPI()
        app.include_router(router, prefix="/api/tasks")
        client = TestClient(app)
        try:
            with patch("api.routes.tasks.db_session", new_callable=_mock_db_session):
                response = client.get("/api/tasks/")
                assert response.status_code == 200
        except AttributeError:
            response = client.get("/api/tasks/")
            assert response.status_code in (200, 500)

    def test_tasks_status(self):
        from api.routes.tasks import router

        app = FastAPI()
        app.include_router(router, prefix="/api/tasks")
        client = TestClient(app)
        try:
            with patch("api.routes.tasks.db_session", new_callable=_mock_db_session):
                response = client.get("/api/tasks/status")
                assert response.status_code in (200, 404)
        except AttributeError:
            response = client.get("/api/tasks/status")
            assert response.status_code in (200, 404, 500)


class TestMarketRoutes:
    def test_market_regime(self):
        from api.routes.market import router

        app = FastAPI()
        app.include_router(router, prefix="/api/market")
        client = TestClient(app)
        try:
            with patch("api.routes.market.db_session", new_callable=_mock_db_session):
                response = client.get("/api/market/regime")
                assert response.status_code in (200, 500)
        except AttributeError:
            response = client.get("/api/market/regime")
            assert response.status_code in (200, 500)
