"""Tests for services.data_initializer - DataInitializer."""

from unittest.mock import MagicMock, PropertyMock, patch


class TestDataInitializer:
    def test_init(self):
        from services.data_initializer import DataInitializer

        di = DataInitializer()
        assert di is not None

    def test_fallback_bluechips(self):
        from services.data_initializer import DataInitializer

        di = DataInitializer()
        result = di._fallback_bluechips()
        assert isinstance(result, list)
        assert len(result) > 0

    def test_default_stock_pool(self):
        from services.data_initializer import DataInitializer

        di = DataInitializer()
        result = di._default_stock_pool()
        assert isinstance(result, list)
        assert len(result) > 0

    @patch("services.data_initializer.DataInitializer.provider", new_callable=PropertyMock)
    def test_is_db_empty_with_empty_db(self, mock_provider):
        from services.data_initializer import DataInitializer

        mock_provider.return_value = MagicMock()
        di = DataInitializer()
        # Mock the session to return empty query
        with patch("shared.models.get_session") as mock_session:
            mock_db = MagicMock()
            mock_session.return_value = mock_db
            mock_db.query.return_value.count.return_value = 0
            result = di.is_db_empty()
            assert isinstance(result, bool)
