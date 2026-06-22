"""Tests for PortfolioService - holdings, trades, add/sell positions."""

from unittest.mock import MagicMock


class TestPortfolioServiceInterface:
    """Test PortfolioService class interface and basic operations."""

    def test_class_exists(self):
        from services.portfolio import PortfolioService

        assert PortfolioService is not None

    def test_init_requires_db_factory(self):
        from services.portfolio import PortfolioService

        mock_factory = MagicMock()
        svc = PortfolioService(mock_factory)
        assert svc._get_db == mock_factory

    def test_has_get_holdings(self):
        from services.portfolio import PortfolioService

        assert hasattr(PortfolioService, "get_holdings")

    def test_has_add_position(self):
        from services.portfolio import PortfolioService

        assert hasattr(PortfolioService, "add_position")

    def test_has_sell_position(self):
        from services.portfolio import PortfolioService

        assert hasattr(PortfolioService, "sell_position")

    def test_has_get_portfolio_summary(self):
        from services.portfolio import PortfolioService

        assert hasattr(PortfolioService, "get_portfolio_summary")

    def test_has_search_stocks(self):
        from services.portfolio import PortfolioService

        assert hasattr(PortfolioService, "search_stocks")

    def test_has_get_holdings_map(self):
        from services.portfolio import PortfolioService

        assert hasattr(PortfolioService, "get_holdings_map")

    def test_has_get_trades(self):
        from services.portfolio import PortfolioService

        assert hasattr(PortfolioService, "get_trades")

    def test_has_reset_portfolio(self):
        from services.portfolio import PortfolioService

        assert hasattr(PortfolioService, "reset_portfolio")

    def test_has_get_nav(self):
        from services.portfolio import PortfolioService

        assert hasattr(PortfolioService, "get_nav")

    def test_has_record_nav(self):
        from services.portfolio import PortfolioService

        assert hasattr(PortfolioService, "record_nav")

    def test_has_update_prices(self):
        from services.portfolio import PortfolioService

        assert hasattr(PortfolioService, "update_prices")


class TestGetHoldings:
    """Test get_holdings with mocked DB."""

    def test_empty_holdings(self):
        from services.portfolio import PortfolioService

        mock_db = MagicMock()
        mock_db.query.return_value.filter_by.return_value.filter_by.return_value.all.return_value = []
        mock_db.query.return_value.filter_by.return_value.all.return_value = []

        svc = PortfolioService(lambda: mock_db)
        result = svc.get_holdings()
        assert result["status"] == "ok"
        assert result["positions"] == []
        assert result["total"] == 0

    def test_with_holdings(self):
        from services.portfolio import PortfolioService

        mock_holding = MagicMock()
        mock_holding.stock_code = "600519"
        mock_holding.stock_name = "贵州茅台"
        mock_holding.buy_date = "2025-01-15"
        mock_holding.buy_price = 1800.0
        mock_holding.quantity = 100
        mock_holding.current_price = 1900.0
        mock_holding.cost_value = 180000.0
        mock_holding.current_value = 190000.0
        mock_holding.profit_loss = 10000.0
        mock_holding.profit_loss_pct = 5.56

        mock_info = MagicMock()
        mock_info.industry = "白酒"
        mock_info.trend = "up"

        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_query.filter_by.return_value = mock_query
        mock_query.all.return_value = [mock_holding]
        mock_db.query.return_value = mock_query
        mock_db.query.return_value.filter_by.return_value.first.return_value = mock_info

        svc = PortfolioService(lambda: mock_db)
        result = svc.get_holdings()
        assert result["status"] == "ok"
        assert result["total"] == 1
        assert result["positions"][0]["stock_code"] == "600519"

    def test_with_portfolio_type_filter(self):
        from services.portfolio import PortfolioService

        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_query.filter_by.return_value = mock_query
        mock_query.all.return_value = []
        mock_db.query.return_value = mock_query

        svc = PortfolioService(lambda: mock_db)
        result = svc.get_holdings(portfolio_type="value")
        assert result["status"] == "ok"
        assert result["portfolio_type"] == "value"


class TestAddPosition:
    """Test add_position with mocked DB."""

    def test_add_new_position(self):
        from services.portfolio import PortfolioService

        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_query.filter_by.return_value = mock_query
        mock_query.first.return_value = None  # No existing position
        mock_db.query.return_value = mock_query

        svc = PortfolioService(lambda: mock_db)
        result = svc.add_position(
            portfolio_type="value",
            stock_code="600519",
            stock_name="贵州茅台",
            buy_price=1800.0,
            quantity=100,
        )
        assert result["status"] == "ok"
        assert "600519" in result["message"]
        mock_db.add.assert_called()
        mock_db.commit.assert_called_once()

    def test_add_duplicate_position_returns_error(self):
        from services.portfolio import PortfolioService

        mock_existing = MagicMock()
        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_query.filter_by.return_value = mock_query
        mock_query.first.return_value = mock_existing  # Existing position
        mock_db.query.return_value = mock_query

        svc = PortfolioService(lambda: mock_db)
        result = svc.add_position(
            portfolio_type="value",
            stock_code="600519",
            stock_name="贵州茅台",
            buy_price=1800.0,
            quantity=100,
        )
        assert result["status"] == "error"
        assert "already in portfolio" in result["message"]


class TestSellPosition:
    """Test sell_position with mocked DB."""

    def test_sell_existing_position(self):
        from services.portfolio import PortfolioService

        mock_holding = MagicMock()
        mock_holding.stock_name = "贵州茅台"
        mock_holding.buy_price = 1800.0
        mock_holding.quantity = 100

        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_query.filter_by.return_value = mock_query
        mock_query.first.return_value = mock_holding
        mock_db.query.return_value = mock_query

        svc = PortfolioService(lambda: mock_db)
        result = svc.sell_position(
            portfolio_type="value",
            stock_code="600519",
            sell_price=1900.0,
        )
        assert result["status"] == "ok"
        assert "600519" in result["message"]
        assert result["pnl_pct"] > 0  # Profit

    def test_sell_nonexistent_position(self):
        from services.portfolio import PortfolioService

        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_query.filter_by.return_value = mock_query
        mock_query.first.return_value = None  # No position found
        mock_db.query.return_value = mock_query

        svc = PortfolioService(lambda: mock_db)
        result = svc.sell_position(
            portfolio_type="value",
            stock_code="999999",
            sell_price=100.0,
        )
        assert result["status"] == "error"
        assert "not found" in result["message"]


class TestGetHoldingsMap:
    """Test get_holdings_map conversion."""

    def test_converts_list_to_map(self):
        from services.portfolio import PortfolioService

        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_query.filter_by.return_value = mock_query
        mock_query.all.return_value = []
        mock_db.query.return_value = mock_query

        svc = PortfolioService(lambda: mock_db)
        # Monkey-patch get_holdings to return test data
        svc.get_holdings = lambda portfolio_type=None: {
            "status": "ok",
            "positions": [
                {"stock_code": "600519", "stock_name": "茅台"},
                {"stock_code": "000858", "stock_name": "五粮液"},
            ],
        }
        result = svc.get_holdings_map()
        assert "600519" in result
        assert "000858" in result
        assert result["600519"]["stock_name"] == "茅台"


class TestSearchStocks:
    """Test search_stocks with mocked DB."""

    def test_search_with_query(self):
        from services.portfolio import PortfolioService

        mock_stock = MagicMock()
        mock_stock.stock_code = "600519"
        mock_stock.stock_name = "贵州茅台"
        mock_stock.industry = "白酒"
        mock_stock.latest_price = 1800.0
        mock_stock.change_pct = 1.5
        mock_stock.trend = "up"
        mock_stock.pe_ratio = 35.0

        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = [mock_stock]
        mock_db.query.return_value = mock_query

        svc = PortfolioService(lambda: mock_db)
        result = svc.search_stocks(query="茅台")
        assert result["status"] == "ok"
        assert result["total"] == 1


class TestGetStockInfo:
    """Test get_stock_info with mocked DB."""

    def test_found(self):
        from services.portfolio import PortfolioService

        mock_info = MagicMock()
        mock_info.stock_code = "600519"
        mock_info.stock_name = "贵州茅台"
        mock_info.category = "白酒"
        mock_info.industry = "食品饮料"
        mock_info.pe_ratio = 35.123
        mock_info.pb_ratio = 10.456
        mock_info.latest_price = 1800.5
        mock_info.change_pct = 2.345
        mock_info.trend = "up"
        mock_info.rsi_14 = 65.789
        mock_info.kline_count = 90
        mock_info.ma_alignment = "bullish"

        mock_db = MagicMock()
        mock_db.query.return_value.filter_by.return_value.first.return_value = mock_info

        svc = PortfolioService(lambda: mock_db)
        result = svc.get_stock_info("600519")
        assert result["status"] == "ok"
        data = result["data"]
        assert data["stock_code"] == "600519"
        assert data["stock_name"] == "贵州茅台"
        assert data["pe_ratio"] == 35.1
        assert data["latest_price"] == 1800.5

    def test_not_found(self):
        from services.portfolio import PortfolioService

        mock_db = MagicMock()
        mock_db.query.return_value.filter_by.return_value.first.return_value = None

        svc = PortfolioService(lambda: mock_db)
        result = svc.get_stock_info("999999")
        assert result["status"] == "error"
        assert "999999" in result["message"]


class TestGetAllStockInfo:
    """Test get_all_stock_info with mocked DB."""

    def test_empty(self):
        from services.portfolio import PortfolioService

        mock_db = MagicMock()
        mock_db.query.return_value.order_by.return_value.all.return_value = []

        svc = PortfolioService(lambda: mock_db)
        result = svc.get_all_stock_info()
        assert result["status"] == "ok"
        assert result["total"] == 0
        assert result["positions"] == []

    def test_with_data(self):
        from services.portfolio import PortfolioService

        mock_s = MagicMock()
        mock_s.stock_code = "600519"
        mock_s.stock_name = "茅台"
        mock_s.industry = "白酒"
        mock_s.pe_ratio = 35.0
        mock_s.latest_price = 1800.0
        mock_s.change_pct = 1.5
        mock_s.trend = "up"
        mock_s.rsi_14 = 60.0

        mock_db = MagicMock()
        mock_db.query.return_value.order_by.return_value.all.return_value = [mock_s]

        svc = PortfolioService(lambda: mock_db)
        result = svc.get_all_stock_info()
        assert result["status"] == "ok"
        assert result["total"] == 1
        assert result["positions"][0]["stock_code"] == "600519"


class TestGetNav:
    """Test get_nav with mocked DB."""

    def test_empty_nav(self):
        from services.portfolio import PortfolioService

        mock_db = MagicMock()
        mock_db.query.return_value.filter_by.return_value.order_by.return_value.limit.return_value.all.return_value = []

        svc = PortfolioService(lambda: mock_db)
        result = svc.get_nav("limit_up")
        assert result["status"] == "ok"
        assert result["nav"] == []

    def test_with_nav_data(self):
        from services.portfolio import PortfolioService

        mock_nav = MagicMock()
        mock_nav.date = "2025-01-15"
        mock_nav.total_asset = 100000.0
        mock_nav.cash = 10000.0
        mock_nav.stock_value = 90000.0
        mock_nav.daily_return_pct = 1.5
        mock_nav.cumulative_return_pct = 5.0
        mock_nav.position_count = 3

        mock_db = MagicMock()
        mock_db.query.return_value.filter_by.return_value.order_by.return_value.limit.return_value.all.return_value = [
            mock_nav
        ]

        svc = PortfolioService(lambda: mock_db)
        result = svc.get_nav("limit_up")
        assert result["status"] == "ok"
        assert len(result["nav"]) == 1
        assert result["nav"][0]["date"] == "2025-01-15"
        assert result["nav"][0]["total_asset"] == 100000.0


class TestUpdatePrices:
    """Test update_prices with mocked DB."""

    def test_no_holdings(self):
        from services.portfolio import PortfolioService

        mock_db = MagicMock()
        mock_db.query.return_value.filter_by.return_value.all.return_value = []

        svc = PortfolioService(lambda: mock_db)
        result = svc.update_prices()
        assert result["status"] == "ok"
        assert result["updated"] == 0

    def test_updates_from_stock_info(self):
        from services.portfolio import PortfolioService

        mock_holding = MagicMock()
        mock_holding.stock_code = "600519"
        mock_holding.current_price = 1700.0

        mock_info = MagicMock()
        mock_info.latest_price = 1800.0

        mock_db = MagicMock()
        # First call: query(Portfolio).filter_by(status=HOLDING).all()
        # Second call: query(StockInfo).filter_by(stock_code=...).first()
        call_count = [0]

        def mock_query(model):
            call_count[0] += 1
            q = MagicMock()
            if call_count[0] == 1:
                q.filter_by.return_value.all.return_value = [mock_holding]
            else:
                q.filter_by.return_value.first.return_value = mock_info
            return q

        mock_db.query.side_effect = mock_query

        svc = PortfolioService(lambda: mock_db)
        result = svc.update_prices()
        assert result["status"] == "ok"
        assert result["updated"] == 1
        assert mock_holding.current_price == 1800.0
