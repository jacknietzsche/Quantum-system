"""Tests for services.indicator_refresher - IndicatorRefresher."""

from unittest.mock import MagicMock, patch


class TestIndicatorRefresher:
    def test_init(self):
        from services.indicator_refresher import IndicatorRefresher

        mock_provider = MagicMock()
        ir = IndicatorRefresher(provider=mock_provider)
        assert ir is not None

    def test_get_metrics(self):
        from services.indicator_refresher import IndicatorRefresher

        mock_provider = MagicMock()
        ir = IndicatorRefresher(provider=mock_provider)
        metrics = ir.get_metrics()
        assert isinstance(metrics, dict)

    def test_health_check(self):
        from services.indicator_refresher import IndicatorRefresher

        mock_provider = MagicMock()
        ir = IndicatorRefresher(provider=mock_provider)
        result = ir.health_check()
        assert isinstance(result, bool)

    @patch("shared.models.get_session")
    def test_refresh_indicators_batch_empty(self, mock_session):
        from services.indicator_refresher import IndicatorRefresher

        mock_provider = MagicMock()
        mock_db = MagicMock()
        mock_session.return_value = mock_db
        mock_db.query.return_value.filter.return_value.limit.return_value.all.return_value = []
        ir = IndicatorRefresher(provider=mock_provider)
        result = ir.refresh_indicators_batch(max_stocks=0)
        assert isinstance(result, dict)

    def test_provider_attribute(self):
        from services.indicator_refresher import IndicatorRefresher

        mock_provider = MagicMock()
        ir = IndicatorRefresher(provider=mock_provider)
        assert ir.provider is not None
