"""剩余 tools/ 模块单元测试（fundamentals/news_search/social_sentiment/stock_data）。"""

from __future__ import annotations

import builtins
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest


@pytest.fixture()
def fake_bus():
    bus = MagicMock()
    bus.get_fundamentals.return_value = {"pe_ratio": 10}
    bus.get_financial_statements.return_value = {"revenue": 100}
    bus.get_news.return_value = [{"title": "News"}]
    bus.get_social_sentiment.return_value = {"positive": 0.5}
    bus.get_market_breadth.return_value = {"total": 100}
    bus.get_kline.return_value = pd.DataFrame({
        "open": [1, 2],
        "high": [2, 3],
        "low": [0.5, 1.5],
        "close": [1.5, 2.5],
        "volume": [100, 200],
    })
    return bus


class TestFundamentals:
    def test_get_fundamentals(self, fake_bus, monkeypatch):
        import tools.fundamentals as fm

        monkeypatch.setattr(fm, "_bus", fake_bus)
        result = fm.get_fundamentals("600519")
        assert result == {"pe_ratio": 10}
        fake_bus.get_fundamentals.assert_called_once_with("600519")

    def test_get_financial_statements(self, fake_bus, monkeypatch):
        import tools.fundamentals as fm

        monkeypatch.setattr(fm, "_bus", fake_bus)
        result = fm.get_financial_statements("600519")
        assert result == {"revenue": 100}


class TestNewsSearch:
    def test_get_news(self, fake_bus, monkeypatch):
        import tools.news_search as ns

        monkeypatch.setattr(ns, "_bus", fake_bus)
        result = ns.get_news("600519", days=7)
        assert result == [{"title": "News"}]
        fake_bus.get_news.assert_called_once_with("600519", 7)

    def test_get_global_news_success(self):
        import tools.news_search as ns

        fake_ak = MagicMock()
        fake_df = pd.DataFrame({
            "title": ["Title1"],
            "content": ["Content1"],
            "date": ["2026-06-20 12:00"],
        })
        fake_ak.news_cctv.return_value = fake_df

        with patch.dict("sys.modules", {"akshare": fake_ak}):
            result = ns.get_global_news()

        assert len(result) == 1
        assert result[0]["title"] == "Title1"
        assert result[0]["source"] == "央视新闻"

    def test_get_global_news_import_error(self):
        import tools.news_search as ns

        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "akshare":
                raise ImportError("No module named akshare")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=fake_import):
            result = ns.get_global_news()

        assert result == []

    def test_get_global_news_empty(self):
        import tools.news_search as ns

        fake_ak = MagicMock()
        fake_ak.news_cctv.return_value = None
        with patch.dict("sys.modules", {"akshare": fake_ak}):
            result = ns.get_global_news()
        assert result == []


class TestSocialSentiment:
    def test_get_social_sentiment(self, fake_bus, monkeypatch):
        import tools.social_sentiment as ss

        monkeypatch.setattr(ss, "_bus", fake_bus)
        result = ss.get_social_sentiment("600519")
        assert result == {"positive": 0.5}

    def test_get_market_breadth(self, fake_bus, monkeypatch):
        import tools.social_sentiment as ss

        monkeypatch.setattr(ss, "_bus", fake_bus)
        result = ss.get_market_breadth()
        assert result == {"total": 100}


class TestStockData:
    def test_get_stock_data(self, fake_bus, monkeypatch):
        import tools.stock_data as sd

        monkeypatch.setattr(sd, "_bus", fake_bus)
        result = sd.get_stock_data("600519", days=60)
        assert "kline" in result
        assert "indicators" in result

    def test_get_stock_data_empty(self, fake_bus, monkeypatch):
        import tools.stock_data as sd

        fake_bus.get_kline.return_value = None
        monkeypatch.setattr(sd, "_bus", fake_bus)
        result = sd.get_stock_data("600519")
        assert result["kline"] is None
        assert result["indicators"] is None

    def test_get_indicators(self, fake_bus, monkeypatch):
        import tools.stock_data as sd

        monkeypatch.setattr(sd, "_bus", fake_bus)
        result = sd.get_indicators("600519")
        assert result is not None
