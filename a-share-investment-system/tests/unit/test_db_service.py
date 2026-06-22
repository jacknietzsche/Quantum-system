"""Unit tests for shared.db_service utility functions."""

from unittest.mock import MagicMock

from shared.db_service import (
    count_stocks,
    get_portfolio_summary,
    get_price_map,
    get_recent_logs,
    get_stock_by_code,
    get_stock_by_code_batch,
    list_active_holdings,
    log_system_event,
    search_stocks,
)


class TestGetStockByCode:
    """Test get_stock_by_code function."""

    def test_found(self):
        mock_session = MagicMock()
        mock_stock = MagicMock()
        mock_session.query.return_value.filter_by.return_value.first.return_value = mock_stock

        result = get_stock_by_code(mock_session, "600519")
        assert result is mock_stock

    def test_not_found(self):
        mock_session = MagicMock()
        mock_session.query.return_value.filter_by.return_value.first.return_value = None

        result = get_stock_by_code(mock_session, "999999")
        assert result is None


class TestGetStockByCodeBatch:
    """Test get_stock_by_code_batch function."""

    def test_returns_dict(self):
        mock_session = MagicMock()
        mock_stock = MagicMock()
        mock_stock.stock_code = "600519"
        mock_session.query.return_value.filter.return_value.all.return_value = [mock_stock]

        result = get_stock_by_code_batch(mock_session, ["600519"])
        assert isinstance(result, dict)
        assert "600519" in result


class TestSearchStocks:
    """Test search_stocks function."""

    def test_returns_list(self):
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.limit.return_value.all.return_value = []

        result = search_stocks(mock_session, "茅台")
        assert isinstance(result, list)


class TestListActiveHoldings:
    """Test list_active_holdings function."""

    def test_returns_list(self):
        mock_session = MagicMock()
        mock_session.query.return_value.filter_by.return_value.all.return_value = []

        result = list_active_holdings(mock_session)
        assert isinstance(result, list)


class TestGetPortfolioSummary:
    """Test get_portfolio_summary function."""

    def test_returns_dict(self):
        mock_session = MagicMock()
        mock_session.query.return_value.filter_by.return_value.all.return_value = []

        result = get_portfolio_summary(mock_session)
        assert isinstance(result, dict)
        assert "total_value" in result
        assert "total_cost" in result


class TestGetPriceMap:
    """Test get_price_map function."""

    def test_returns_dict(self):
        mock_session = MagicMock()
        mock_stock = MagicMock()
        mock_stock.stock_code = "600519"
        mock_stock.latest_price = 1800.0
        mock_session.query.return_value.filter.return_value.all.return_value = [
            (mock_stock.stock_code, mock_stock.latest_price)
        ]

        result = get_price_map(mock_session, ["600519"])
        assert isinstance(result, dict)


class TestCountStocks:
    """Test count_stocks function."""

    def test_returns_int(self):
        mock_session = MagicMock()
        mock_session.query.return_value.scalar.return_value = 100

        result = count_stocks(mock_session)
        assert result == 100


class TestLogSystemEvent:
    """Test log_system_event function."""

    def test_adds_log(self):
        mock_session = MagicMock()

        log_system_event(mock_session, "test", "INFO", "test message")
        mock_session.add.assert_called_once()


class TestGetRecentLogs:
    """Test get_recent_logs function."""

    def test_returns_list(self):
        mock_session = MagicMock()
        mock_session.query.return_value.order_by.return_value.limit.return_value.all.return_value = []

        result = get_recent_logs(mock_session)
        assert isinstance(result, list)
