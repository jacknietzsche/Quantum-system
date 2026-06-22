"""TradingCalendar 单元测试 — 交易日判断、前后交易日、数据日期"""

from datetime import datetime

from services.trading_calendar import TradingCalendar


class TestIsTradingDay:
    def setup_method(self):
        self.cal = TradingCalendar()

    def test_weekday_is_trading_day(self):
        # 2026-06-01 is Monday
        assert self.cal.is_trading_day("2026-06-01") is True

    def test_weekend_is_not_trading_day(self):
        # 2026-06-06 is Saturday
        assert self.cal.is_trading_day("2026-06-06") is False
        # 2026-06-07 is Sunday
        assert self.cal.is_trading_day("2026-06-07") is False

    def test_string_date_input(self):
        assert isinstance(self.cal.is_trading_day("2026-06-01"), bool)

    def test_datetime_input(self):
        dt = datetime(2026, 6, 1)
        assert self.cal.is_trading_day(dt) is True

    def test_none_uses_today(self):
        result = self.cal.is_trading_day()
        assert isinstance(result, bool)

    def test_returns_bool(self):
        assert isinstance(self.cal.is_trading_day("2026-01-01"), bool)


class TestPreviousTradingDay:
    def setup_method(self):
        self.cal = TradingCalendar()

    def test_monday_returns_friday(self):
        # 2026-06-01 is Monday -> previous should be 2026-05-29 (Friday)
        result = self.cal.previous_trading_day("2026-06-01")
        assert result == "2026-05-29"

    def test_saturday_returns_friday(self):
        result = self.cal.previous_trading_day("2026-06-06")
        assert result == "2026-06-05"

    def test_sunday_returns_friday(self):
        result = self.cal.previous_trading_day("2026-06-07")
        assert result == "2026-06-05"

    def test_returns_string_format(self):
        result = self.cal.previous_trading_day("2026-06-01")
        assert isinstance(result, str)
        assert len(result) == 10
        assert result[4] == "-"
        assert result[7] == "-"


class TestNextTradingDay:
    def setup_method(self):
        self.cal = TradingCalendar()

    def test_friday_returns_monday(self):
        result = self.cal.next_trading_day("2026-06-05")
        assert result == "2026-06-08"

    def test_saturday_returns_monday(self):
        result = self.cal.next_trading_day("2026-06-06")
        assert result == "2026-06-08"

    def test_returns_string_format(self):
        result = self.cal.next_trading_day("2026-06-01")
        assert isinstance(result, str)
        assert len(result) == 10


class TestEffectiveDataDate:
    def setup_method(self):
        self.cal = TradingCalendar()

    def test_returns_string(self):
        result = self.cal.effective_data_date()
        assert isinstance(result, str)
        assert len(result) == 10

    def test_returns_past_or_today(self):
        result = self.cal.effective_data_date()
        today = datetime.now().strftime("%Y-%m-%d")
        assert result <= today


class TestHelperMethods:
    def setup_method(self):
        self.cal = TradingCalendar()

    def test_today_str_format(self):
        result = self.cal.today_str()
        assert isinstance(result, str)
        assert len(result) == 10

    def test_is_market_closed_today_returns_bool(self):
        result = self.cal.is_market_closed_today()
        assert isinstance(result, bool)
