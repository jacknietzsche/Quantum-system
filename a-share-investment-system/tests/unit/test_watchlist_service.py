"""Unit tests for services.watchlist."""

from unittest.mock import MagicMock


class TestWatchlistService:
    def _make_service(self):
        from services.watchlist import WatchlistService

        mock_session_factory = MagicMock()
        mock_db = MagicMock()
        mock_session_factory.return_value = mock_db
        svc = WatchlistService(db_session_factory=mock_session_factory)
        return svc, mock_db

    def test_get_all_empty(self):
        svc, mock_db = self._make_service()
        mock_db.query.return_value.order_by.return_value.all.return_value = []
        result = svc.get_all()
        assert result["status"] == "ok"
        assert result["total"] == 0
        assert result["data"] == []

    def test_get_all_with_items(self):
        svc, mock_db = self._make_service()
        w = MagicMock()
        w.id = 1
        w.stock_code = "600519"
        w.stock_name = "Moutai"
        w.category = "stock"
        w.add_reason = "strong moat"
        w.created_at = "2025-01-15"
        mock_db.query.return_value.order_by.return_value.all.return_value = [w]
        mock_db.query.return_value.filter_by.return_value.first.return_value = None
        result = svc.get_all()
        assert result["status"] == "ok"
        assert result["total"] == 1

    def test_add_success(self):
        svc, mock_db = self._make_service()
        mock_db.query.return_value.filter_by.return_value.first.return_value = None
        result = svc.add("600519", "Moutai", "stock", "strong moat")
        assert result["status"] == "ok"
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()

    def test_add_duplicate(self):
        svc, mock_db = self._make_service()
        mock_db.query.return_value.filter_by.return_value.first.return_value = MagicMock()
        result = svc.add("600519", "Moutai")
        assert result["status"] == "error"

    def test_delete_found(self):
        svc, mock_db = self._make_service()
        mock_db.query.return_value.filter_by.return_value.delete.return_value = 1
        result = svc.delete("600519")
        assert result["status"] == "ok"
        mock_db.commit.assert_called_once()

    def test_delete_not_found(self):
        svc, mock_db = self._make_service()
        mock_db.query.return_value.filter_by.return_value.delete.return_value = 0
        result = svc.delete("999999")
        assert result["status"] == "error"

    def test_clear(self):
        svc, mock_db = self._make_service()
        mock_db.query.return_value.delete.return_value = 5
        result = svc.clear()
        assert result["status"] == "ok"

    def test_export_csv(self):
        svc, mock_db = self._make_service()
        w = MagicMock()
        w.stock_code = "600519"
        w.stock_name = "Moutai"
        w.category = "stock"
        w.add_reason = "test"
        w.created_at = "2025-01-15"
        mock_db.query.return_value.order_by.return_value.all.return_value = [w]
        result = svc.export_csv()
        assert "600519" in result
        assert "Moutai" in result
        assert "stock_code" in result

    def test_import_csv(self):
        svc, mock_db = self._make_service()
        mock_db.query.return_value.filter_by.return_value.first.return_value = None
        csv_text = "stock_code,stock_name,category,add_reason\n600519,Moutai,stock,test\n000858,Wuliangye,stock,test2"
        result = svc.import_csv(csv_text)
        assert result["status"] == "ok"
        assert result["added"] == 2

    def test_import_csv_skip_duplicate(self):
        svc, mock_db = self._make_service()
        mock_db.query.return_value.filter_by.return_value.first.return_value = MagicMock()
        csv_text = "stock_code,stock_name,category,add_reason\n600519,Moutai,stock,test"
        result = svc.import_csv(csv_text)
        assert result["status"] == "ok"
        assert result["skipped"] == 1
        assert result["added"] == 0
