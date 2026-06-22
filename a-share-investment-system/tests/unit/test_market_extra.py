"""Tests for services.market - MarketService."""

from unittest.mock import MagicMock


class TestMarketService:
    def test_init(self):
        from services.market import MarketService

        mock_session = MagicMock()
        svc = MarketService(db_session_factory=mock_session)
        assert svc is not None

    def test_empty_indices_response(self):
        from services.market import MarketService

        mock_session = MagicMock()
        svc = MarketService(db_session_factory=mock_session)
        result = svc._empty_indices_response()
        assert isinstance(result, dict)

    def test_format_indices_response(self):
        from services.market import MarketService

        mock_session = MagicMock()
        svc = MarketService(db_session_factory=mock_session)
        data = {"000001": {"name": "Shanghai", "price": 3200, "change_pct": 0.5}}
        result = svc._format_indices_response(data, "cached", "test")
        assert isinstance(result, dict)
