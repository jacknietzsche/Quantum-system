"""单元测试 — hot-stocks 端点健壮性"""

from unittest.mock import MagicMock, patch

from api.routes.database import hot_stocks
from services.data_initializer import ServiceResult


def _make_stock(
    code: str, name: str, price: float, change: float, turnover: float, cap: float, amount: float
) -> MagicMock:
    s = MagicMock()
    s.stock_code = code
    s.stock_name = name
    s.latest_price = price
    s.change_pct = change
    s.turnover_rate = turnover
    s.total_market_cap = cap
    s.amount = amount
    return s


MOCK_STOCKS = [
    _make_stock("600519", "贵州茅台", 1888.0, 1.5, 0.5, 23700.0, 5e9),
    _make_stock("000858", "五粮液", 168.0, 0.8, 0.6, 6500.0, 3e9),
    _make_stock("300750", "宁德时代", 218.0, -0.3, 0.7, 9800.0, 4e9),
    _make_stock("601318", "中国平安", 48.5, 0.2, 0.3, 8800.0, 2e9),
    _make_stock("000333", "美的集团", 65.0, 0.5, 0.4, 4500.0, 1.5e9),
    _make_stock("600036", "招商银行", 36.0, -0.1, 0.2, 9000.0, 1.8e9),
    _make_stock("002415", "海康威视", 32.0, 0.6, 0.8, 3000.0, 1e9),
    _make_stock("600030", "中信证券", 20.0, 1.2, 1.0, 3000.0, 2.5e9),
    _make_stock("000001", "平安银行", 11.0, 0.3, 0.5, 2100.0, 0.8e9),
    _make_stock("600887", "伊利股份", 28.0, 0.4, 0.6, 1800.0, 0.9e9),
]


class TestHotStocks:
    """hot_stocks 端点行为测试"""

    @patch("shared.db_session.get_session")
    def test_returns_valid_stocks(self, mock_get_session):
        """从DB返回合法股票列表"""
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.count.return_value = 50
        mock_session.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = MOCK_STOCKS[
            :10
        ]
        mock_get_session.return_value = mock_session

        result = hot_stocks(limit=10)
        assert result["count"] > 0
        assert result["count"] <= 10
        assert result["source"] == "db+datainitializer"
        assert "stocks" in result
        s = result["stocks"][0]
        assert "code" in s
        assert "change_pct" in s

    @patch("shared.db_session.get_session")
    def test_required_fields_present(self, mock_get_session):
        """所有返回记录含必要字段"""
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.count.return_value = 50
        mock_session.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = MOCK_STOCKS[
            :5
        ]
        mock_get_session.return_value = mock_session

        REQUIRED = {"code", "name", "price", "change_pct", "market_cap"}
        result = hot_stocks(limit=10)
        for s in result.get("stocks", []):
            assert REQUIRED.issubset(s.keys()), f"Missing fields in {s}"

    @patch("shared.db_session.get_session")
    def test_limit_respected(self, mock_get_session):
        """limit参数有效"""
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.count.return_value = 50
        mock_session.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = MOCK_STOCKS[
            :5
        ]
        mock_get_session.return_value = mock_session

        result = hot_stocks(limit=5)
        assert result["count"] <= 5

    @patch("shared.db_session.get_session")
    @patch("services.data_initializer.DataInitializer.populate_stock_list")
    def test_empty_db_triggers_autofill(self, mock_populate, mock_get_session):
        """空库时自动填充被触发"""
        mock_populate.return_value = ServiceResult.ok(
            data={"total": 100, "success": 80, "failed": 20}
        )

        call_count = [0]

        def side_effect():
            call_count[0] += 1
            session = MagicMock()
            if call_count[0] == 1:
                session.query.return_value.filter.return_value.count.return_value = 0
            else:
                session.query.return_value.filter.return_value.count.return_value = 80
                session.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = MOCK_STOCKS[
                    :10
                ]
            return session

        mock_get_session.side_effect = side_effect

        result = hot_stocks(limit=10)
        assert result["count"] > 0
        assert result["source"] == "db+datainitializer"
        assert mock_populate.called

    @patch("shared.db_session.get_session")
    def test_empty_db_no_data_returns_empty(self, mock_get_session):
        """空库且自动填充无数据时返回空"""
        call_count = [0]

        def side_effect():
            call_count[0] += 1
            session = MagicMock()
            session.query.return_value.filter.return_value.count.return_value = 0
            session.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []
            return session

        mock_get_session.side_effect = side_effect

        with patch("services.data_initializer.DataInitializer.populate_stock_list") as mp:
            mp.return_value = ServiceResult.ok(data={"total": 0, "success": 0, "failed": 0})
            result = hot_stocks(limit=10)
            assert result["count"] == 0
            assert mp.called
