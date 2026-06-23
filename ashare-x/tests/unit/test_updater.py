"""DailyUpdater 单元测试。"""

from __future__ import annotations

import sqlite3
from unittest.mock import MagicMock

import pytest


@pytest.fixture()
def mock_bus(monkeypatch: pytest.MonkeyPatch):
    """替换 updater 模块内引用的 DatabaseFirstDataBus 为 mock 实例工厂。"""
    from services import updater as up_mod

    fake_bus = MagicMock()
    fake_bus.get_kline.return_value = [{"trade_date": "2026-06-20"}]
    fake_bus.get_stock_info.return_value = {"name": "Test"}
    fake_bus.get_fundamentals.return_value = {"pe": 10}
    fake_bus.get_news.return_value = [{"title": "News"}]
    fake_bus.get_social_sentiment.return_value = {"positive": 0.5}
    fake_bus.get_market_breadth.return_value = {"total": 100}
    fake_bus.get_market_overview.return_value = {"index": 3000}

    monkeypatch.setattr(up_mod, "DatabaseFirstDataBus", lambda *args, **kwargs: fake_bus)
    return fake_bus


@pytest.fixture()
def updater(mock_bus, tmp_path):
    """构造使用临时数据库的 DailyUpdater。"""
    from services.updater import DailyUpdater

    return DailyUpdater(db_path=str(tmp_path / "test.db"))


class TestDailyUpdate:
    def test_run_daily_update_with_codes(self, updater):
        stats = updater.run_daily_update(stock_codes=["600519"])
        assert stats["kline_updated"] == 1
        assert stats["stock_info_updated"] == 1
        assert stats["fundamentals_updated"] == 1
        assert stats["news_updated"] == 1
        assert stats["sentiment_updated"] == 1
        assert stats["market_breadth_updated"] is True
        assert len(stats["errors"]) == 0

    def test_run_daily_update_default_codes_when_db_empty(self, updater):
        stats = updater.run_daily_update()
        assert stats["kline_updated"] == 5  # 默认 5 只蓝筹股

    def test_run_daily_update_from_active_stocks(self, updater, tmp_path):
        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE stock_info (stock_code TEXT)")
        conn.execute("INSERT INTO stock_info VALUES ('000001')")
        conn.commit()
        conn.close()

        stats = updater.run_daily_update()
        assert stats["kline_updated"] == 1

    def test_run_daily_update_error_handling(self, updater, mock_bus):
        mock_bus.get_kline.side_effect = RuntimeError("network error")
        stats = updater.run_daily_update(stock_codes=["600519"])
        assert stats["kline_updated"] == 0
        assert len(stats["errors"]) > 0
        assert "network error" in stats["errors"][0]

    def test_run_daily_update_sentiment_none_values(self, updater, mock_bus):
        mock_bus.get_social_sentiment.return_value = {"positive": None}
        stats = updater.run_daily_update(stock_codes=["600519"])
        assert stats["sentiment_updated"] == 0


class TestUpdateSingleStock:
    def test_update_single_stock_success(self, updater):
        stats = updater.update_single_stock("600519")
        assert stats["kline"] is True
        assert stats["stock_info"] is True
        assert stats["fundamentals"] is True
        assert stats["news"] is True
        assert stats["sentiment"] is True

    def test_update_single_stock_partial_failure(self, updater, mock_bus):
        mock_bus.get_kline.return_value = None
        mock_bus.get_fundamentals.return_value = None
        stats = updater.update_single_stock("600519")
        assert stats["kline"] is False
        assert stats["stock_info"] is True
        assert stats["fundamentals"] is False
        assert stats["sentiment"] is True


class TestIncrementalRefresh:
    def test_incremental_refresh_skips_complete_data(self, updater, tmp_path):
        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute(
            "CREATE TABLE stock_info (stock_code TEXT)"
        )
        conn.execute(
            "CREATE TABLE kline_daily (stock_code TEXT, trade_date TEXT)"
        )
        conn.execute("INSERT INTO stock_info VALUES ('600519')")
        # 60 天预期交易日约 43 天，80% 即 34 条以上视为完整
        for i in range(40):
            conn.execute(
                "INSERT INTO kline_daily VALUES ('600519', ?)",
                (f"2026-05-{i+1:02d}",),
            )
        conn.commit()
        conn.close()

        stats = updater.incremental_refresh(days=60)
        assert stats["total"] == 1
        assert stats["skipped"] == 1
        assert stats["updated"] == 0

    def test_incremental_refresh_updates_incomplete_data(self, updater, tmp_path):
        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE stock_info (stock_code TEXT)")
        conn.execute("CREATE TABLE kline_daily (stock_code TEXT, trade_date TEXT)")
        conn.execute("INSERT INTO stock_info VALUES ('600519')")
        conn.execute("INSERT INTO kline_daily VALUES ('600519', '2026-06-20')")
        conn.commit()
        conn.close()

        stats = updater.incremental_refresh(days=60)
        assert stats["total"] == 1
        assert stats["skipped"] == 0
        assert stats["updated"] == 1

    def test_incremental_refresh_failed_when_no_data(self, updater, tmp_path, mock_bus):
        mock_bus.get_kline.return_value = None
        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE stock_info (stock_code TEXT)")
        conn.execute("CREATE TABLE kline_daily (stock_code TEXT, trade_date TEXT)")
        conn.execute("INSERT INTO stock_info VALUES ('600519')")
        conn.commit()
        conn.close()

        stats = updater.incremental_refresh(days=60)
        assert stats["failed"] == 1

    def test_incremental_refresh_uses_default_codes_when_db_empty(self, updater):
        stats = updater.incremental_refresh(days=60)
        assert stats["total"] == 5  # 默认 5 只蓝筹股


class TestGetStocksToCheck:
    def test_get_active_stocks_from_db(self, updater, tmp_path):
        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE stock_info (stock_code TEXT)")
        conn.execute("INSERT INTO stock_info VALUES ('000001')")
        conn.commit()
        conn.close()

        codes = updater._get_active_stocks()
        assert codes == ["000001"]

    def test_get_active_stocks_returns_empty_on_error(self, updater):
        # 数据库文件不存在时返回空列表
        codes = updater._get_active_stocks()
        assert codes == []

    def test_get_stocks_to_check_aggregates_sources(self, updater, tmp_path):
        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE stock_info (stock_code TEXT)")
        conn.execute("CREATE TABLE paper_holdings (stock_code TEXT)")
        conn.execute("CREATE TABLE watchlist (stock_code TEXT)")
        conn.execute("INSERT INTO stock_info VALUES ('600519')")
        conn.execute("INSERT INTO paper_holdings VALUES ('000001')")
        conn.execute("INSERT INTO watchlist VALUES ('000858')")
        conn.commit()
        conn.close()

        codes = updater._get_stocks_to_check()
        assert codes == ["000001", "000858", "600519"]
