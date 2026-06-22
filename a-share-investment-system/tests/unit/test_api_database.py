"""Tests for api.routes.database - comprehensive mock tests."""

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
        q.scalar.return_value = ""
        mock_db.query.return_value = q
        yield mock_db

    return _db_session


def _make_client():
    from api.routes.database import router

    app = FastAPI()
    app.include_router(router, prefix="/api/db")
    return TestClient(app)


class TestDatabaseRoutes:
    @patch("api.routes.database.db_session")
    def test_source_test(self, mock_db):
        from api.routes.database import router

        app = FastAPI()
        app.include_router(router, prefix="/api/db")
        client = TestClient(app)
        with patch("api.routes.database.MarketDataProvider") as MockProvider:
            mock_p = MagicMock()
            mock_p.test_all_sources.return_value = {"test_source": {"ok": True, "latency": 100}}
            MockProvider.return_value = mock_p
            response = client.get("/api/db/source-test")
            assert response.status_code == 200

    @patch("api.routes.database.db_session")
    def test_source_status(self, mock_db):
        client = _make_client()
        with patch("api.routes.database.MarketDataProvider") as MockProvider:
            mock_p = MagicMock()
            mock_p.get_source_status.return_value = {"source1": "ok"}
            MockProvider.return_value = mock_p
            response = client.get("/api/db/source-status")
            assert response.status_code == 200

    @patch("api.routes.database.db_session", new_callable=_mock_db_session)
    def test_db_stats(self, mock_db):
        client = _make_client()
        with patch("api.routes.database.MarketDataProvider") as MockProvider:
            mock_p = MagicMock()
            mock_p.get_source_status.return_value = {}
            MockProvider.return_value = mock_p
            response = client.get("/api/db/stats")
            assert response.status_code == 200

    @patch("api.routes.database.db_session", new_callable=_mock_db_session)
    def test_stockinfo_list(self, mock_db):
        client = _make_client()
        response = client.get("/api/db/stockinfo")
        assert response.status_code == 200

    @patch("api.routes.database.db_session", new_callable=_mock_db_session)
    def test_stockinfo_search(self, mock_db):
        client = _make_client()
        response = client.get("/api/db/stockinfo?search=600519")
        assert response.status_code == 200

    @patch("api.routes.database.db_session", new_callable=_mock_db_session)
    def test_stockinfo_add(self, mock_db):
        client = _make_client()
        response = client.post(
            "/api/db/stockinfo", json={"stock_code": "600519", "stock_name": "Moutai"}
        )
        assert response.status_code == 200

    @patch("api.routes.database.db_session", new_callable=_mock_db_session)
    def test_get_stock_edit(self, mock_db):
        client = _make_client()
        response = client.put("/api/db/stockinfo/600519", json={"stock_name": "Moutai"})
        assert response.status_code == 200

    @patch("api.routes.database.db_session", new_callable=_mock_db_session)
    def test_edit_stock(self, mock_db):
        client = _make_client()
        response = client.put("/api/db/stockinfo/600519", json={"stock_name": "Kweichow Moutai"})
        assert response.status_code == 200

    @patch("api.routes.database.db_session", new_callable=_mock_db_session)
    def test_delete_stock(self, mock_db):
        client = _make_client()
        response = client.delete("/api/db/stockinfo/600519")
        assert response.status_code == 200

    @patch("api.routes.database.db_session", new_callable=_mock_db_session)
    def test_get_kline(self, mock_db):
        client = _make_client()
        response = client.get("/api/db/kline/600519?days=30")
        assert response.status_code == 200

    @patch("api.routes.database.db_session", new_callable=_mock_db_session)
    def test_snapshot(self, mock_db):
        client = _make_client()
        response = client.get("/api/db/snapshots")
        assert response.status_code == 200

    @patch("api.routes.database.DataInitializer")
    @patch("api.routes.database.db_session", new_callable=_mock_db_session)
    def test_hot_stocks(self, mock_db, MockDI):
        client = _make_client()
        mock_di = MagicMock()
        mock_di.populate_stock_list.return_value = MagicMock(data={"success": 0}, status="ok")
        MockDI.return_value = mock_di
        response = client.get("/api/db/hot-stocks?limit=10")
        assert response.status_code == 200

    @patch("api.routes.database.db_session", new_callable=_mock_db_session)
    def test_hot_rank(self, mock_db):
        client = _make_client()
        response = client.get("/api/db/hot-rank?limit=10")
        assert response.status_code == 200

    @patch("api.routes.database.db_session", new_callable=_mock_db_session)
    def test_industry_distribution(self, mock_db):
        client = _make_client()
        response = client.get("/api/db/industry-distribution")
        assert response.status_code == 200

    @patch("api.routes.database.db_session", new_callable=_mock_db_session)
    def test_board_rank(self, mock_db):
        client = _make_client()
        response = client.get("/api/db/board-rank")
        assert response.status_code == 200

    @patch("api.routes.database.db_session", new_callable=_mock_db_session)
    def test_cache_status(self, mock_db):
        client = _make_client()
        response = client.get("/api/db/cache-status")
        assert response.status_code == 200

    @patch("api.routes.database.db_session", new_callable=_mock_db_session)
    def test_data_quality(self, mock_db):
        client = _make_client()
        response = client.get("/api/db/data-quality")
        assert response.status_code == 200

    @patch("api.routes.database.db_session", new_callable=_mock_db_session)
    def test_estimate_refresh(self, mock_db):
        client = _make_client()
        response = client.get("/api/db/explorer/estimate?stocks=100")
        assert response.status_code == 200

    @patch("api.routes.database.db_session", new_callable=_mock_db_session)
    def test_zt_pool(self, mock_db):
        client = _make_client()
        response = client.get("/api/db/zt-pool")
        assert response.status_code == 200

    @patch("api.routes.database.db_session", new_callable=_mock_db_session)
    def test_lhb(self, mock_db):
        client = _make_client()
        response = client.get("/api/db/lhb")
        assert response.status_code == 200

    @patch("api.routes.database.db_session", new_callable=_mock_db_session)
    def test_lhb_list(self, mock_db):
        client = _make_client()
        response = client.get("/api/db/lhb/list")
        assert response.status_code == 200

    @patch("api.routes.database.db_session", new_callable=_mock_db_session)
    def test_data_quality_scan(self, mock_db):
        client = _make_client()
        response = client.get("/api/db/data-quality/scan")
        assert response.status_code == 200

    @patch("api.routes.database.db_session", new_callable=_mock_db_session)
    def test_data_by_date(self, mock_db):
        client = _make_client()
        response = client.get("/api/db/data-by-date?table=stock_info")
        assert response.status_code == 200

    @patch("api.routes.database.db_session", new_callable=_mock_db_session)
    def test_table_info(self, mock_db):
        client = _make_client()
        response = client.get("/api/db/table-info?table=stock_info")
        assert response.status_code == 200

    @patch("api.routes.database.db_session", new_callable=_mock_db_session)
    def test_batch_repair(self, mock_db):
        client = _make_client()
        response = client.post("/api/db/batch-repair")
        assert response.status_code == 200

    @patch("api.routes.database.db_session", new_callable=_mock_db_session)
    def test_clean_stale(self, mock_db):
        client = _make_client()
        response = client.post("/api/db/clean-stale")
        assert response.status_code == 200

    @patch("api.routes.database.MarketDataProvider")
    @patch("api.routes.database.DataInitializer")
    @patch("api.routes.database.db_session", new_callable=_mock_db_session)
    def test_refresh_post(self, mock_db, MockDI, MockMD):
        client = _make_client()
        mock_di = MagicMock()
        mock_di.refresh_hot_stocks.return_value = MagicMock(data={"success": 10}, status="ok")
        MockDI.return_value = mock_di
        mock_md = MagicMock()
        mock_md.get_source_status.return_value = {"akshare": {"available": True}}
        MockMD.return_value = mock_md
        response = client.post("/api/db/refresh", json={"mode": "hot"})
        assert response.status_code == 200
