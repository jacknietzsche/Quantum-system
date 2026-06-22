"""Unit tests for agents_v2.utils.stock_utils."""


class TestStockMarket:
    def test_enum_values(self):
        from agents_v2.utils.stock_utils import StockMarket

        assert StockMarket.CHINA_A.value == "china_a"
        assert StockMarket.HONG_KONG.value == "hong_kong"
        assert StockMarket.US.value == "us"
        assert StockMarket.UNKNOWN.value == "unknown"


class TestStockUtilsIdentifyMarket:
    def test_china_a_stock(self):
        from agents_v2.utils.stock_utils import StockMarket, StockUtils

        assert StockUtils.identify_market("600519") == StockMarket.CHINA_A
        assert StockUtils.identify_market("000858") == StockMarket.CHINA_A
        assert StockUtils.identify_market("300750") == StockMarket.CHINA_A

    def test_hk_stock(self):
        from agents_v2.utils.stock_utils import StockMarket, StockUtils

        assert StockUtils.identify_market("0700.HK") == StockMarket.HONG_KONG
        assert StockUtils.identify_market("1810.HK") == StockMarket.HONG_KONG

    def test_hk_stock_digits_only(self):
        from agents_v2.utils.stock_utils import StockMarket, StockUtils

        assert StockUtils.identify_market("0700") == StockMarket.HONG_KONG

    def test_us_stock(self):
        from agents_v2.utils.stock_utils import StockMarket, StockUtils

        assert StockUtils.identify_market("AAPL") == StockMarket.US
        assert StockUtils.identify_market("TSLA") == StockMarket.US
        assert StockUtils.identify_market("NVDA") == StockMarket.US

    def test_unknown(self):
        from agents_v2.utils.stock_utils import StockMarket, StockUtils

        assert StockUtils.identify_market("") == StockMarket.UNKNOWN
        assert StockUtils.identify_market("ABC123XYZ") == StockMarket.UNKNOWN

    def test_none_input(self):
        from agents_v2.utils.stock_utils import StockMarket, StockUtils

        assert StockUtils.identify_market(None) == StockMarket.UNKNOWN


class TestStockUtilsHelpers:
    def test_is_china_stock(self):
        from agents_v2.utils.stock_utils import StockUtils

        assert StockUtils.is_china_stock("600519") is True
        assert StockUtils.is_china_stock("AAPL") is False

    def test_is_hk_stock(self):
        from agents_v2.utils.stock_utils import StockUtils

        assert StockUtils.is_hk_stock("0700.HK") is True
        assert StockUtils.is_hk_stock("600519") is False

    def test_is_us_stock(self):
        from agents_v2.utils.stock_utils import StockUtils

        assert StockUtils.is_us_stock("AAPL") is True
        assert StockUtils.is_us_stock("600519") is False

    def test_get_currency_info_china(self):
        from agents_v2.utils.stock_utils import StockUtils

        name, symbol = StockUtils.get_currency_info("600519")
        assert name is not None
        assert symbol is not None

    def test_get_currency_info_us(self):
        from agents_v2.utils.stock_utils import StockUtils

        name, symbol = StockUtils.get_currency_info("AAPL")
        assert name is not None

    def test_get_currency_info_unknown(self):
        from agents_v2.utils.stock_utils import StockUtils

        name, symbol = StockUtils.get_currency_info("XYZ123")
        assert name is not None

    def test_get_data_source_china(self):
        from agents_v2.utils.stock_utils import StockUtils

        assert StockUtils.get_data_source("600519") == "efinance"

    def test_get_data_source_us(self):
        from agents_v2.utils.stock_utils import StockUtils

        assert StockUtils.get_data_source("AAPL") == "yahoo_finance"

    def test_normalize_hk_ticker(self):
        from agents_v2.utils.stock_utils import StockUtils

        assert StockUtils.normalize_hk_ticker("0700") == "0700.HK"
        assert StockUtils.normalize_hk_ticker("0700.HK") == "0700.HK"
        assert StockUtils.normalize_hk_ticker("") == ""

    def test_get_market_info(self):
        from agents_v2.utils.stock_utils import StockUtils

        info = StockUtils.get_market_info("600519")
        assert info["ticker"] == "600519"
        assert info["market"] == "china_a"
        assert info["is_china"] is True

    def test_get_board_type(self):
        from agents_v2.utils.stock_utils import StockUtils

        assert StockUtils.get_board_type("600519") != "unknown"
        assert StockUtils.get_board_type("300750") != "unknown"
        assert StockUtils.get_board_type("688981") != "unknown"
        assert StockUtils.get_board_type("") == "unknown"

    def test_get_price_limit(self):
        from agents_v2.utils.stock_utils import StockUtils

        assert StockUtils.get_price_limit("main") in (0.10, 0.20)
        assert isinstance(StockUtils.get_price_limit("unknown_type"), float)


class TestStockUtilsEdgeCases:
    def test_identify_market_with_spaces(self):
        from agents_v2.utils.stock_utils import StockMarket, StockUtils

        assert StockUtils.identify_market("  600519  ") == StockMarket.CHINA_A

    def test_identify_market_lowercase(self):
        from agents_v2.utils.stock_utils import StockMarket, StockUtils

        assert StockUtils.identify_market("aapl") == StockMarket.US

    def test_get_market_info_hk(self):
        from agents_v2.utils.stock_utils import StockUtils

        info = StockUtils.get_market_info("0700.HK")
        assert info["is_hk"] is True

    def test_get_market_info_us(self):
        from agents_v2.utils.stock_utils import StockUtils

        info = StockUtils.get_market_info("TSLA")
        assert info["is_us"] is True
