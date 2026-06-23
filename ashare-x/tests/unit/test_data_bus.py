"""providers/data_bus.py 单元测试。"""

from __future__ import annotations

import builtins
import sqlite3
from collections.abc import Generator
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from providers.data_bus import DatabaseFirstDataBus, _safe_float


@pytest.fixture()
def tmp_db(tmp_path: Path) -> Generator[DatabaseFirstDataBus, None, None]:
    """使用临时数据库的 DataBus 实例。"""
    db_path = tmp_path / "test.db"
    bus = DatabaseFirstDataBus(str(db_path))
    yield bus
    DatabaseFirstDataBus._spot_cache = None
    DatabaseFirstDataBus._spot_cache_time = None
    DatabaseFirstDataBus._spot_cache_failed = False
    DatabaseFirstDataBus._spot_cache_fail_time = None


class TestSafeFloat:
    """_safe_float 边界测试。"""

    def test_none_returns_none(self):
        assert _safe_float(None) is None

    def test_dash_returns_none(self):
        assert _safe_float("-") is None

    def test_empty_string_returns_none(self):
        assert _safe_float("") is None

    def test_valid_float(self):
        assert _safe_float("12.34") == 12.34

    def test_invalid_returns_none(self):
        assert _safe_float("abc") is None


class TestDatabaseFirstDataBusInit:
    """初始化与数据库建表测试。"""

    def test_ensure_db_creates_tables(self, tmp_db: DatabaseFirstDataBus):
        conn = sqlite3.connect(tmp_db.db_path)
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        conn.close()
        assert "kline_daily" in tables
        assert "stock_info" in tables
        assert "market_snapshot" in tables
        assert "fund_metric_hist" in tables
        assert "news_cache" in tables


class TestIsStale:
    """_is_stale 过期判断测试。"""

    def test_none_is_stale(self, tmp_db: DatabaseFirstDataBus):
        assert tmp_db._is_stale(None, "kline") is True

    def test_future_is_fresh(self, tmp_db: DatabaseFirstDataBus):
        future = (datetime.now() + timedelta(hours=1)).isoformat()
        assert tmp_db._is_stale(future, "kline") is False

    def test_old_is_stale(self, tmp_db: DatabaseFirstDataBus):
        old = (datetime.now() - timedelta(hours=10)).isoformat()
        assert tmp_db._is_stale(old, "kline") is True

    def test_sqlite_datetime_format(self, tmp_db: DatabaseFirstDataBus):
        old = (datetime.now() - timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S")
        assert tmp_db._is_stale(old, "stock_info") is True


class TestSnapshotHelpers:
    """_save_snapshot / _query_snapshot 测试。"""

    def test_save_and_query_snapshot(self, tmp_db: DatabaseFirstDataBus):
        tmp_db._save_snapshot("test_snap", {"foo": "bar"})
        snap = tmp_db._query_snapshot("test_snap")
        assert snap is not None
        assert snap["data"] == {"foo": "bar"}
        assert "updated_at" in snap

    def test_query_missing_snapshot(self, tmp_db: DatabaseFirstDataBus):
        assert tmp_db._query_snapshot("missing") is None

    def test_save_snapshot_overwrites(self, tmp_db: DatabaseFirstDataBus):
        tmp_db._save_snapshot("test_snap", {"v": 1})
        tmp_db._save_snapshot("test_snap", {"v": 2})
        snap = tmp_db._query_snapshot("test_snap")
        assert snap is not None
        assert snap["data"] == {"v": 2}


class TestKline:
    """get_kline 数据流测试。"""

    def test_get_kline_from_db(self, tmp_db: DatabaseFirstDataBus):
        conn = sqlite3.connect(tmp_db.db_path)
        conn.execute(
            "INSERT INTO kline_daily "
            "(stock_code, trade_date, open, high, low, close, volume, amount) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("600519", "2026-06-22", 1.0, 2.0, 0.5, 1.5, 1000, 1500),
        )
        conn.commit()
        conn.close()

        data = tmp_db.get_kline("600519")
        assert data is not None
        assert len(data) == 1
        assert data[0]["close"] == 1.5

    def test_get_kline_from_api(self, tmp_db: DatabaseFirstDataBus):
        api_data = [
            {
                "trade_date": "2026-06-22",
                "open": 1.0,
                "high": 2.0,
                "low": 0.5,
                "close": 1.5,
                "volume": 1000,
                "amount": 1500,
            }
        ]
        with patch.object(
            tmp_db, "_fetch_kline_from_api", return_value=api_data
        ):
            data = tmp_db.get_kline("600519")

        assert data == api_data
        # 验证已入库
        conn = sqlite3.connect(tmp_db.db_path)
        rows = conn.execute(
            "SELECT trade_date FROM kline_daily WHERE stock_code=?", ("600519",)
        ).fetchall()
        conn.close()
        assert len(rows) == 1

    def test_get_kline_no_data(self, tmp_db: DatabaseFirstDataBus):
        with patch.object(tmp_db, "_fetch_kline_from_api", return_value=None):
            assert tmp_db.get_kline("600519") is None


class TestStockInfo:
    """get_stock_info 数据流测试。"""

    def test_get_stock_info_from_fresh_db(self, tmp_db: DatabaseFirstDataBus):
        now = datetime.now().isoformat()
        conn = sqlite3.connect(tmp_db.db_path)
        conn.execute(
            "INSERT INTO stock_info "
            "(stock_code, stock_name, pe_ratio, updated_at) "
            "VALUES (?, ?, ?, ?)",
            ("600519", "贵州茅台", 30.0, now),
        )
        conn.commit()
        conn.close()

        info = tmp_db.get_stock_info("600519")
        assert info is not None
        assert info["stock_name"] == "贵州茅台"
        assert info["pe_ratio"] == 30.0

    def test_get_stock_info_stale_then_api(
        self, tmp_db: DatabaseFirstDataBus
    ):
        old = (datetime.now() - timedelta(hours=2)).isoformat()
        conn = sqlite3.connect(tmp_db.db_path)
        conn.execute(
            "INSERT INTO stock_info "
            "(stock_code, stock_name, pe_ratio, updated_at) "
            "VALUES (?, ?, ?, ?)",
            ("600519", "OldName", 20.0, old),
        )
        conn.commit()
        conn.close()

        with (
            patch.object(
                tmp_db,
                "_fetch_kline_from_api",
                return_value=None,
            ),
            patch.object(
                tmp_db,
                "_load_adapters",
                return_value=[MagicMock(fetch_basic=lambda c: {"pe_ratio": 35.0})],
            ),
        ):
            info = tmp_db.get_stock_info("600519")

        assert info is not None
        assert info["pe_ratio"] == 35.0

    def test_get_stock_info_api_fail_fallback(
        self, tmp_db: DatabaseFirstDataBus
    ):
        old = (datetime.now() - timedelta(hours=2)).isoformat()
        conn = sqlite3.connect(tmp_db.db_path)
        conn.execute(
            "INSERT INTO stock_info "
            "(stock_code, stock_name, pe_ratio, updated_at) "
            "VALUES (?, ?, ?, ?)",
            ("600519", "贵州茅台", 30.0, old),
        )
        conn.commit()
        conn.close()

        with patch.object(
            tmp_db,
            "_load_adapters",
            return_value=[MagicMock(fetch_basic=lambda c: None)],
        ):
            info = tmp_db.get_stock_info("600519")

        assert info is not None
        assert info["stock_name"] == "贵州茅台"


class TestFundamentals:
    """get_fundamentals / get_financial_statements 测试。"""

    def test_get_fundamentals_db_sufficient(self, tmp_db: DatabaseFirstDataBus):
        now = datetime.now().isoformat()
        conn = sqlite3.connect(tmp_db.db_path)
        conn.execute(
            "INSERT INTO stock_info "
            "(stock_code, stock_name, pe_ratio, roe, updated_at) "
            "VALUES (?, ?, ?, ?, ?)",
            ("600519", "贵州茅台", 30.0, 15.0, now),
        )
        conn.execute(
            "INSERT INTO fund_metric_hist "
            "(stock_code, report_period, revenue, net_income) "
            "VALUES (?, ?, ?, ?)",
            ("600519", "2026-03-31", 100.0, 50.0),
        )
        conn.commit()
        conn.close()

        result = tmp_db.get_fundamentals("600519")
        assert result is not None
        assert result["pe_ratio"] == 30.0
        assert result["roe"] == 15.0
        assert result["revenue"] == 100.0

    def test_get_fundamentals_api_augment(self, tmp_db: DatabaseFirstDataBus):
        with patch.object(
            tmp_db,
            "_fetch_fundamentals_from_api",
            return_value={
                "pe_ratio": 25.0,
                "roe": 12.0,
                "report_period": "2026-03-31",
            },
        ):
            result = tmp_db.get_fundamentals("600519")

        assert result is not None
        assert result["pe_ratio"] == 25.0
        assert result["roe"] == 12.0
        assert result.get("dividend_yield") is None

    def test_get_fundamentals_api_fail_fallback(
        self, tmp_db: DatabaseFirstDataBus
    ):
        now = datetime.now().isoformat()
        conn = sqlite3.connect(tmp_db.db_path)
        conn.execute(
            "INSERT INTO stock_info "
            "(stock_code, stock_name, pe_ratio, roe, updated_at) "
            "VALUES (?, ?, ?, ?, ?)",
            ("600519", "贵州茅台", 30.0, 15.0, now),
        )
        conn.commit()
        conn.close()

        with patch.object(
            tmp_db, "_fetch_fundamentals_from_api", return_value=None
        ):
            result = tmp_db.get_fundamentals("600519")

        assert result is not None
        assert result["pe_ratio"] == 30.0

    def test_get_financial_statements_from_db(self, tmp_db: DatabaseFirstDataBus):
        conn = sqlite3.connect(tmp_db.db_path)
        conn.execute(
            "INSERT INTO fund_metric_hist "
            "(stock_code, report_period, roe, roa, gross_margin, "
            "net_margin, debt_to_equity, revenue, net_income) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("600519", "2026-03-31", 15.0, 8.0, 40.0, 25.0, 30.0, 100.0, 50.0),
        )
        conn.commit()
        conn.close()

        result = tmp_db.get_financial_statements("600519")
        assert result is not None
        assert result["roe"] == 15.0
        assert result["revenue"] == 100.0

    def test_get_financial_statements_from_api(self, tmp_db: DatabaseFirstDataBus):
        with patch.object(
            tmp_db,
            "_fetch_financial_statements_from_api",
            return_value={
                "report_period": "2026-03-31",
                "roe": 15.0,
                "roa": 8.0,
            },
        ):
            result = tmp_db.get_financial_statements("600519")

        assert result is not None
        assert result["roe"] == 15.0


class TestNews:
    """get_news 数据流测试。"""

    def test_get_news_from_fresh_db(self, tmp_db: DatabaseFirstDataBus):
        conn = sqlite3.connect(tmp_db.db_path)
        conn.execute(
            "INSERT INTO news_cache "
            "(stock_code, news_date, title, content, source, url) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("600519", "2026-06-22", "t1", "c1", "s1", "http://x"),
        )
        conn.commit()
        conn.close()
        tmp_db._save_snapshot("news_update_600519", {"updated_at": datetime.now().isoformat()})

        news = tmp_db.get_news("600519")
        assert len(news) == 1
        assert news[0]["title"] == "t1"

    def test_get_news_api_augment(self, tmp_db: DatabaseFirstDataBus):
        api_news = [
            {
                "title": "t2",
                "content": "c2",
                "source": "s2",
                "date": "2026-06-23",
                "url": "http://y",
            }
        ]
        with patch.object(
            tmp_db, "_fetch_news_from_api", return_value=api_news
        ):
            news = tmp_db.get_news("600519")

        assert any(n["title"] == "t2" for n in news)

    def test_get_news_api_fail_returns_empty(self, tmp_db: DatabaseFirstDataBus):
        with patch.object(tmp_db, "_fetch_news_from_api", return_value=None):
            assert tmp_db.get_news("600519") == []


class TestSentiment:
    """get_social_sentiment 测试。"""

    def test_get_sentiment_from_fresh_db(self, tmp_db: DatabaseFirstDataBus):
        tmp_db._save_snapshot(
            "sentiment_600519",
            {"north_flow": 100.0, "turnover_rate": 5.0},
        )

        result = tmp_db.get_social_sentiment("600519")
        assert result["north_flow"] == 100.0
        assert result["turnover_rate"] == 5.0

    def test_get_sentiment_from_api(self, tmp_db: DatabaseFirstDataBus):
        with patch.object(
            tmp_db,
            "_fetch_sentiment_from_api",
            return_value={"north_flow": 200.0, "turnover_rate": 6.0},
        ):
            result = tmp_db.get_social_sentiment("600519")

        assert result["north_flow"] == 200.0
        assert result["turnover_rate"] == 6.0

    def test_get_sentiment_api_fail_returns_default(self, tmp_db: DatabaseFirstDataBus):
        with patch.object(
            tmp_db, "_fetch_sentiment_from_api", return_value=None
        ):
            result = tmp_db.get_social_sentiment("600519")

        assert result["north_flow"] is None
        assert "dragon_tiger" in result


class TestMarketBreadth:
    """get_market_breadth 测试。"""

    def test_get_breadth_from_fresh_db(self, tmp_db: DatabaseFirstDataBus):
        tmp_db._save_snapshot(
            "market_breadth",
            {"total": 1000, "up": 600, "down": 300},
        )

        result = tmp_db.get_market_breadth()
        assert result["total"] == 1000
        assert result["up"] == 600

    def test_get_breadth_from_api(self, tmp_db: DatabaseFirstDataBus):
        with patch.object(
            tmp_db,
            "_fetch_market_breadth_from_api",
            return_value={"total": 1000, "up": 500, "down": 400},
        ):
            result = tmp_db.get_market_breadth()

        assert result["up"] == 500

    def test_get_breadth_api_fail_returns_default(self, tmp_db: DatabaseFirstDataBus):
        with patch.object(
            tmp_db, "_fetch_market_breadth_from_api", return_value=None
        ):
            result = tmp_db.get_market_breadth()

        assert result["total"] == 0
        assert result["up_ratio"] == 0.0


class TestMarketOverview:
    """get_market_overview 测试。"""

    def test_get_overview_from_fresh_db(self, tmp_db: DatabaseFirstDataBus):
        tmp_db._save_snapshot(
            "market_overview",
            {"indices": {"sh": {"price": 3000.0}}, "market_state": "BULL"},
        )

        result = tmp_db.get_market_overview()
        assert result["indices"]["sh"]["price"] == 3000.0

    def test_get_overview_from_api(self, tmp_db: DatabaseFirstDataBus):
        with patch.object(
            tmp_db,
            "_fetch_market_overview_from_api",
            return_value={
                "indices": {"sh": {"price": 3100.0}},
                "market_state": "BEAR",
            },
        ):
            result = tmp_db.get_market_overview()

        assert result["indices"]["sh"]["price"] == 3100.0

    def test_get_overview_api_fail_returns_default(self, tmp_db: DatabaseFirstDataBus):
        with patch.object(
            tmp_db, "_fetch_market_overview_from_api", return_value=None
        ):
            result = tmp_db.get_market_overview()

        assert result["market_state"] == "NEUTRAL"
        assert "indices" in result


class TestMarketSnapshot:
    """get_market_snapshot 全市场快照测试。"""

    def test_get_market_snapshot_from_db(self, tmp_db: DatabaseFirstDataBus):
        stocks = [{"stock_code": "600519", "stock_name": "茅台"}]
        tmp_db._save_snapshot("all_stocks", stocks)

        result = tmp_db.get_market_snapshot()
        assert result == stocks

    def test_get_market_snapshot_force_refresh(self, tmp_db: DatabaseFirstDataBus):
        tmp_db._save_snapshot("all_stocks", [{"stock_code": "old"}])

        with patch.object(
            tmp_db,
            "_fetch_market_breadth_from_api",
            return_value=None,
        ):
            # get_market_snapshot 内部直接调用 akshare，这里通过 mock builtins.__import__
            mock_ak = MagicMock()
            mock_ak.stock_zh_a_spot_em.return_value = MagicMock(
                empty=False,
                iterrows=lambda: iter(
                    [
                        (
                            None,
                            {
                                "代码": "600519",
                                "名称": "茅台",
                                "最新价": 100.0,
                                "涨跌幅": 1.0,
                                "成交量": 1000,
                                "成交额": 100000.0,
                                "市盈率-动态": 20.0,
                                "市净率": 3.0,
                                "换手率": 1.5,
                            },
                        )
                    ]
                ),
            )
            original_import = builtins.__import__

            def _mock_import(name, *args, **kwargs):
                if name == "akshare":
                    return mock_ak
                return original_import(name, *args, **kwargs)

            with patch.object(builtins, "__import__", _mock_import):
                result = tmp_db.get_market_snapshot(force_refresh=True)

        assert len(result) == 1
        assert result[0]["stock_code"] == "600519"

    def test_get_market_snapshot_api_fail_fallback(self, tmp_db: DatabaseFirstDataBus):
        tmp_db._save_snapshot("all_stocks", [{"stock_code": "fallback"}])

        def _raise_import(name, *args, **kwargs):
            if name == "akshare":
                raise ImportError("no akshare")
            return builtins.__import__(name, *args, **kwargs)

        with patch.object(builtins, "__import__", _raise_import):
            result = tmp_db.get_market_snapshot(force_refresh=True)

        assert len(result) == 1
        assert result[0]["stock_code"] == "fallback"


class TestSpotData:
    """_get_spot_data 缓存与 API 测试。"""

    def test_get_spot_data_cache_hit(self, tmp_db: DatabaseFirstDataBus):
        DatabaseFirstDataBus._spot_cache = {
            "600519": {"latest_price": 100.0, "stock_name": "茅台"}
        }
        DatabaseFirstDataBus._spot_cache_time = datetime.now()

        spot = tmp_db._get_spot_data("600519")
        assert spot is not None
        assert spot["latest_price"] == 100.0

    def test_get_spot_data_cache_miss(self, tmp_db: DatabaseFirstDataBus):
        mock_ak = MagicMock()
        mock_ak.stock_zh_a_spot_em.return_value = MagicMock(
            empty=False,
            iterrows=lambda: iter(
                [
                    (
                        None,
                        {
                            "代码": "600519",
                            "名称": "茅台",
                            "最新价": 200.0,
                            "涨跌幅": 2.0,
                            "成交量": 2000,
                            "成交额": 200000.0,
                            "市盈率-动态": 25.0,
                            "市净率": 4.0,
                            "换手率": 2.5,
                        },
                    )
                ]
            ),
        )
        original_import = builtins.__import__

        def _mock_import(name, *args, **kwargs):
            if name == "akshare":
                return mock_ak
            return original_import(name, *args, **kwargs)

        with patch.object(builtins, "__import__", _mock_import):
            spot = tmp_db._get_spot_data("600519")

        assert spot is not None
        assert spot["latest_price"] == 200.0

    def test_get_spot_data_recent_failure(self, tmp_db: DatabaseFirstDataBus):
        DatabaseFirstDataBus._spot_cache_failed = True
        DatabaseFirstDataBus._spot_cache_fail_time = datetime.now()

        assert tmp_db._get_spot_data("600519") is None


class TestStockUniverse:
    """get_stock_universe 全市场列表测试。"""

    def test_get_stock_universe_from_db_fresh(self, tmp_db: DatabaseFirstDataBus):
        stocks = [{"stock_code": "600519", "stock_name": "茅台", "exchange": "SH"}]
        tmp_db._save_snapshot("stock_universe", stocks)

        result = tmp_db.get_stock_universe()
        assert result == stocks

    def test_get_stock_universe_fallback_to_api(self, tmp_db: DatabaseFirstDataBus):
        fake_adapter = MagicMock()
        fake_adapter.fetch_universe.return_value = [
            {"stock_code": "000001", "stock_name": "平安银行", "exchange": "SZ"}
        ]

        with patch(
            "providers.sources.eastmoney_src.EastMoneyAdapter", return_value=fake_adapter
        ), patch(
            "providers.sources.tushare_src.TushareAdapter",
            return_value=MagicMock(fetch_universe=lambda: None),
        ), patch(
            "providers.sources.tickflow_src.TickFlowAdapter",
            return_value=MagicMock(fetch_universe=lambda: None),
        ):
            result = tmp_db.get_stock_universe(force_refresh=True)

        assert result is not None
        assert len(result) == 1
        assert result[0]["stock_code"] == "000001"

    def test_get_stock_universe_empty_returns_cached(self, tmp_db: DatabaseFirstDataBus):
        stocks = [{"stock_code": "600519", "stock_name": "茅台", "exchange": "SH"}]
        tmp_db._save_snapshot("stock_universe", stocks)

        original_import = builtins.__import__

        def _mock_import(name, *args, **kwargs):
            if name == "akshare":
                raise ImportError("no akshare")
            return original_import(name, *args, **kwargs)

        with patch(
            "providers.sources.eastmoney_src.EastMoneyAdapter",
            return_value=MagicMock(fetch_universe=lambda: None),
        ), patch(
            "providers.sources.tushare_src.TushareAdapter",
            return_value=MagicMock(fetch_universe=lambda: None),
        ), patch(
            "providers.sources.tickflow_src.TickFlowAdapter",
            return_value=MagicMock(fetch_universe=lambda: None),
        ), patch.object(builtins, "__import__", _mock_import):
            result = tmp_db.get_stock_universe(force_refresh=True)

        assert result == stocks


class TestLoadAdapters:
    """_load_adapters 加载与排序测试。"""

    def test_adapters_sorted_by_priority(self, tmp_db: DatabaseFirstDataBus):
        adapters = tmp_db._load_adapters()
        priorities = [getattr(a, "priority", 99) for a in adapters]
        assert priorities == sorted(priorities)

    def test_adapters_have_required_methods(self, tmp_db: DatabaseFirstDataBus):
        adapters = tmp_db._load_adapters()
        for adapter in adapters:
            assert callable(getattr(adapter, "fetch_kline", None))
            assert callable(getattr(adapter, "fetch_basic", None))
            assert callable(getattr(adapter, "test_connect", None))
