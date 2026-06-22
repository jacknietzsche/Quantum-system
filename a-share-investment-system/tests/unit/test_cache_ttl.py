"""CacheTTL 单元测试 — 动态TTL计算"""

from datetime import datetime
from unittest.mock import patch

from services.cache_ttl import _BASE_TTL, get_dynamic_ttl, get_session_phase


class TestDynamicTTL:
    def test_indices_ttl_trading_hours(self):
        with patch("services.cache_ttl.get_session_phase", return_value="morning"):
            assert get_dynamic_ttl("indices") == _BASE_TTL["indices"]

    def test_indices_ttl_lunch(self):
        with patch("services.cache_ttl.get_session_phase", return_value="lunch"):
            assert get_dynamic_ttl("indices") > _BASE_TTL["indices"]

    def test_indices_ttl_post_market(self):
        with patch("services.cache_ttl.get_session_phase", return_value="post_market"):
            assert get_dynamic_ttl("indices") <= 14400

    def test_kline_daily_always_long(self):
        for phase in ["morning", "lunch", "post_market", "closed"]:
            with patch("services.cache_ttl.get_session_phase", return_value=phase):
                ttl = get_dynamic_ttl("kline_daily")
                assert ttl >= 86400 or phase == "morning"

    def test_unknown_data_type(self):
        with patch("services.cache_ttl.get_session_phase", return_value="morning"):
            assert get_dynamic_ttl("unknown_type") == 300

    def test_closed_day_long_ttl(self):
        with patch("services.cache_ttl.get_session_phase", return_value="closed"):
            assert get_dynamic_ttl("stock_quote") > _BASE_TTL["stock_quote"]

    def test_pre_market_no_realtime(self):
        with patch("services.cache_ttl.get_session_phase", return_value="pre_market"):
            assert get_dynamic_ttl("stock_quote") > _BASE_TTL["stock_quote"]


class TestSessionPhase:
    @patch("services.cache_ttl._now", return_value=datetime(2024, 1, 15, 10, 0))
    @patch("services.trading_calendar.TradingCalendar")
    def test_morning(self, MockCal, mock_now):
        MockCal.return_value.is_trading_day.return_value = True
        assert get_session_phase() == "morning"

    @patch("services.cache_ttl._now", return_value=datetime(2024, 1, 15, 12, 0))
    @patch("services.trading_calendar.TradingCalendar")
    def test_lunch(self, MockCal, mock_now):
        MockCal.return_value.is_trading_day.return_value = True
        assert get_session_phase() == "lunch"

    @patch("services.cache_ttl._now", return_value=datetime(2024, 1, 15, 14, 0))
    @patch("services.trading_calendar.TradingCalendar")
    def test_afternoon(self, MockCal, mock_now):
        MockCal.return_value.is_trading_day.return_value = True
        assert get_session_phase() == "afternoon"

    @patch("services.cache_ttl._now", return_value=datetime(2024, 1, 15, 16, 0))
    @patch("services.trading_calendar.TradingCalendar")
    def test_post_market(self, MockCal, mock_now):
        MockCal.return_value.is_trading_day.return_value = True
        assert get_session_phase() == "post_market"

    @patch("services.cache_ttl._now", return_value=datetime(2024, 1, 15, 8, 0))
    @patch("services.trading_calendar.TradingCalendar")
    def test_pre_market(self, MockCal, mock_now):
        MockCal.return_value.is_trading_day.return_value = True
        assert get_session_phase() == "pre_market"

    @patch("services.cache_ttl._now", return_value=datetime(2024, 1, 13, 10, 0))
    @patch("services.trading_calendar.TradingCalendar")
    def test_closed_weekend(self, MockCal, mock_now):
        MockCal.return_value.is_trading_day.return_value = False
        assert get_session_phase() == "closed"
