"""providers/sources/ 适配器单元测试。"""

from __future__ import annotations

import builtins
from unittest.mock import MagicMock, patch

from providers.sources.akshare_src import AKShareAdapter
from providers.sources.sina import SinaAdapter
from providers.sources.tencent import TencentAdapter
from providers.sources.yfinance_src import YFinanceAdapter


class TestSinaAdapter:
    """新浪适配器测试。"""

    def test_init(self):
        adapter = SinaAdapter()
        assert adapter.name == "sina"
        assert adapter.priority == 2
        assert adapter.client.headers["Referer"] == "https://finance.sina.com.cn"

    def test_to_sina_code(self):
        adapter = SinaAdapter()
        assert adapter._to_sina_code("600519") == "sh600519"
        assert adapter._to_sina_code("000001") == "sz000001"

    def test_fetch_kline_success(self):
        adapter = SinaAdapter()
        mock_resp = MagicMock()
        mock_resp.json.return_value = [
            {"day": "2026-06-22", "open": "1", "high": "2", "low": "0.5", "close": "1.5", "volume": "1000"}
        ]
        with patch.object(adapter.client, "get", return_value=mock_resp):
            data = adapter.fetch_kline("600519", days=1)

        assert data is not None
        assert len(data) == 1
        assert data[0]["close"] == 1.5

    def test_fetch_kline_empty(self):
        adapter = SinaAdapter()
        mock_resp = MagicMock()
        mock_resp.json.return_value = []
        with patch.object(adapter.client, "get", return_value=mock_resp):
            assert adapter.fetch_kline("600519") is None

    def test_fetch_basic_success(self):
        adapter = SinaAdapter()
        mock_resp = MagicMock()
        mock_resp.text = 'var hq_str_sh600519="茅台,10.0,9.0,11.0,12.0,9.5,0,0,1000,5000,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0"'
        with patch.object(adapter.client, "get", return_value=mock_resp):
            data = adapter.fetch_basic("600519")

        assert data is not None
        assert data["stock_name"] == "茅台"
        assert data["latest_price"] == 11.0
        assert data["volume"] == 1000.0

    def test_fetch_basic_malformed(self):
        adapter = SinaAdapter()
        mock_resp = MagicMock()
        mock_resp.text = "no equals sign"
        with patch.object(adapter.client, "get", return_value=mock_resp):
            assert adapter.fetch_basic("600519") is None

    def test_fetch_basic_too_few_fields(self):
        adapter = SinaAdapter()
        mock_resp = MagicMock()
        mock_resp.text = 'var hq_str_sh600519="a,b,c"'
        with patch.object(adapter.client, "get", return_value=mock_resp):
            assert adapter.fetch_basic("600519") is None

    def test_test_connect_success(self):
        adapter = SinaAdapter()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        with patch.object(adapter.client, "get", return_value=mock_resp):
            assert adapter.test_connect() is True

    def test_test_connect_failure(self):
        adapter = SinaAdapter()
        with patch.object(adapter.client, "get", side_effect=Exception("timeout")):
            assert adapter.test_connect() is False


class TestTencentAdapter:
    """腾讯适配器测试。"""

    def test_init(self):
        adapter = TencentAdapter()
        assert adapter.name == "tencent"
        assert adapter.priority == 1

    def test_to_tencent_code(self):
        adapter = TencentAdapter()
        assert adapter._to_tencent_code("600519") == "sh600519"
        assert adapter._to_tencent_code("000001") == "sz000001"

    def test_fetch_kline_success(self):
        adapter = TencentAdapter()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "data": {"sh600519": {"qfqday": [["2026-06-22", "1", "1.5", "2", "0.5", "1000"]]}}
        }
        with patch.object(adapter.client, "get", return_value=mock_resp):
            data = adapter.fetch_kline("600519", days=1)

        assert data is not None
        assert len(data) == 1
        assert data[0]["close"] == 1.5

    def test_fetch_kline_no_data(self):
        adapter = TencentAdapter()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"data": {}}
        with patch.object(adapter.client, "get", return_value=mock_resp):
            assert adapter.fetch_kline("600519") is None

    def test_fetch_kline_day_fallback(self):
        adapter = TencentAdapter()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "data": {"sh600519": {"day": [["2026-06-22", "1", "1.5", "2", "0.5", "1000"]]}}
        }
        with patch.object(adapter.client, "get", return_value=mock_resp):
            data = adapter.fetch_kline("600519", days=1)

        assert data is not None
        assert data[0]["close"] == 1.5

    def test_fetch_kline_short_row_skipped(self):
        adapter = TencentAdapter()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "data": {"sh600519": {"qfqday": [["2026-06-22", "1"]]}}
        }
        with patch.object(adapter.client, "get", return_value=mock_resp):
            assert adapter.fetch_kline("600519") is None

    def test_fetch_basic_success(self):
        adapter = TencentAdapter()
        mock_resp = MagicMock()
        fields = [""] * 47
        fields[1] = "茅台"
        fields[3] = "100.0"
        fields[32] = "1.5"
        fields[6] = "1000"
        fields[37] = "100000"
        fields[39] = "20.0"
        fields[46] = "3.0"
        fields[38] = "1.5"
        mock_resp.text = f'v_sh600519="{"~".join(fields)}"'
        with patch.object(adapter.client, "get", return_value=mock_resp):
            data = adapter.fetch_basic("600519")

        assert data is not None
        assert data["stock_name"] == "茅台"
        assert data["latest_price"] == 100.0
        assert data["pe_ratio"] == 20.0

    def test_fetch_basic_malformed(self):
        adapter = TencentAdapter()
        mock_resp = MagicMock()
        mock_resp.text = "no equals sign"
        with patch.object(adapter.client, "get", return_value=mock_resp):
            assert adapter.fetch_basic("600519") is None

    def test_fetch_basic_too_few_fields(self):
        adapter = TencentAdapter()
        mock_resp = MagicMock()
        mock_resp.text = 'v_sh600519="a~b~c"'
        with patch.object(adapter.client, "get", return_value=mock_resp):
            assert adapter.fetch_basic("600519") is None

    def test_test_connect_success(self):
        adapter = TencentAdapter()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        with patch.object(adapter.client, "get", return_value=mock_resp):
            assert adapter.test_connect() is True

    def test_test_connect_failure(self):
        adapter = TencentAdapter()
        with patch.object(adapter.client, "get", side_effect=Exception("timeout")):
            assert adapter.test_connect() is False


class TestAKShareAdapter:
    """AKShare适配器测试。"""

    def test_init(self):
        adapter = AKShareAdapter()
        assert adapter.name == "akshare"
        assert adapter.priority == 4

    def _mock_akshare(self, hist_df=None, spot_df=None):
        """构造一个 mocked akshare 模块。"""
        mock_ak = MagicMock()
        if hist_df is not None:
            mock_ak.stock_zh_a_hist.return_value = hist_df
        if spot_df is not None:
            mock_ak.stock_zh_a_spot_em.return_value = spot_df
        mock_ak.stock_zh_index_daily.return_value = MagicMock(empty=False)
        return mock_ak

    def test_fetch_kline_success(self):
        adapter = AKShareAdapter()
        df = MagicMock()
        df.empty = False
        df.tail.return_value = MagicMock(
            iterrows=lambda: iter([
                (None, {"日期": "2026-06-22", "开盘": 1.0, "最高": 2.0, "最低": 0.5, "收盘": 1.5, "成交量": 1000, "成交额": 1500})
            ])
        )
        mock_ak = self._mock_akshare(hist_df=df)

        original_import = builtins.__import__

        def _mock_import(name, *args, **kwargs):
            if name == "akshare":
                return mock_ak
            return original_import(name, *args, **kwargs)

        with patch.object(builtins, "__import__", _mock_import):
            data = adapter.fetch_kline("600519", days=1)

        assert data is not None
        assert data[0]["close"] == 1.5
        assert data[0]["amount"] == 1500.0

    def test_fetch_kline_empty(self):
        adapter = AKShareAdapter()
        df = MagicMock()
        df.empty = True
        mock_ak = self._mock_akshare(hist_df=df)

        original_import = builtins.__import__

        def _mock_import(name, *args, **kwargs):
            if name == "akshare":
                return mock_ak
            return original_import(name, *args, **kwargs)

        with patch.object(builtins, "__import__", _mock_import):
            assert adapter.fetch_kline("600519") is None

    def test_fetch_kline_import_error(self):
        adapter = AKShareAdapter()
        with patch.object(builtins, "__import__", side_effect=ImportError("no akshare")):
            assert adapter.fetch_kline("600519") is None

    def test_fetch_basic_success(self):
        adapter = AKShareAdapter()
        df = MagicMock()
        df.empty = False
        df.__getitem__ = lambda self, key: MagicMock(
            empty=False,
            iloc=[MagicMock(
                get=lambda k, default="": {
                    "名称": "茅台",
                    "最新价": 100.0,
                    "涨跌幅": 1.0,
                    "成交量": 1000,
                    "成交额": 100000,
                    "市盈率-动态": 20.0,
                    "市净率": 3.0,
                    "换手率": 1.5,
                }.get(k, default)
            )]
        )
        mock_ak = self._mock_akshare(spot_df=df)

        original_import = builtins.__import__

        def _mock_import(name, *args, **kwargs):
            if name == "akshare":
                return mock_ak
            return original_import(name, *args, **kwargs)

        with patch.object(builtins, "__import__", _mock_import):
            data = adapter.fetch_basic("600519")

        assert data is not None
        assert data["stock_name"] == "茅台"
        assert data["latest_price"] == 100.0
        assert data["is_st"] == 0

    def test_fetch_basic_st_stock(self):
        adapter = AKShareAdapter()
        df = MagicMock()
        df.empty = False
        df.__getitem__ = lambda self, key: MagicMock(
            empty=False,
            iloc=[MagicMock(
                get=lambda k, default="": {
                    "名称": "*ST茅台",
                    "最新价": 100.0,
                    "涨跌幅": 1.0,
                    "成交量": 1000,
                    "成交额": 100000,
                    "市盈率-动态": 20.0,
                    "市净率": 3.0,
                    "换手率": 1.5,
                }.get(k, default)
            )]
        )
        mock_ak = self._mock_akshare(spot_df=df)

        original_import = builtins.__import__

        def _mock_import(name, *args, **kwargs):
            if name == "akshare":
                return mock_ak
            return original_import(name, *args, **kwargs)

        with patch.object(builtins, "__import__", _mock_import):
            data = adapter.fetch_basic("600519")

        assert data is not None
        assert data["is_st"] == 1

    def test_fetch_basic_empty(self):
        adapter = AKShareAdapter()
        df = MagicMock()
        df.empty = True
        mock_ak = self._mock_akshare(spot_df=df)

        original_import = builtins.__import__

        def _mock_import(name, *args, **kwargs):
            if name == "akshare":
                return mock_ak
            return original_import(name, *args, **kwargs)

        with patch.object(builtins, "__import__", _mock_import):
            assert adapter.fetch_basic("600519") is None

    def test_test_connect_success(self):
        adapter = AKShareAdapter()
        mock_ak = self._mock_akshare()

        original_import = builtins.__import__

        def _mock_import(name, *args, **kwargs):
            if name == "akshare":
                return mock_ak
            return original_import(name, *args, **kwargs)

        with patch.object(builtins, "__import__", _mock_import):
            assert adapter.test_connect() is True

    def test_test_connect_failure(self):
        adapter = AKShareAdapter()
        mock_ak = MagicMock()
        mock_ak.stock_zh_index_daily.side_effect = Exception("timeout")

        original_import = builtins.__import__

        def _mock_import(name, *args, **kwargs):
            if name == "akshare":
                return mock_ak
            return original_import(name, *args, **kwargs)

        with patch.object(builtins, "__import__", _mock_import):
            assert adapter.test_connect() is False


class TestEastMoneyAdapter:
    """东方财富适配器测试。"""

    def test_init(self):
        from providers.sources.eastmoney_src import EastMoneyAdapter

        adapter = EastMoneyAdapter()
        assert adapter.name == "eastmoney"
        assert adapter.priority == 3

    def test_to_eastmoney_code(self):
        from providers.sources.eastmoney_src import EastMoneyAdapter

        adapter = EastMoneyAdapter()
        assert adapter._to_eastmoney_code("600519") == "1.600519"
        assert adapter._to_eastmoney_code("000001") == "0.000001"

    def test_fetch_kline_success(self):
        from providers.sources.eastmoney_src import EastMoneyAdapter

        adapter = EastMoneyAdapter()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "data": {
                "klines": [
                    "2026-06-22,1.0,1.5,2.0,0.5,1000,1500,5.0,1.0,0.5,1.5",
                ]
            }
        }
        with patch.object(adapter.client, "get", return_value=mock_resp):
            data = adapter.fetch_kline("600519", days=1)

        assert data is not None
        assert len(data) == 1
        assert data[0]["close"] == 1.5
        assert data[0]["volume"] == 1000.0

    def test_fetch_kline_empty(self):
        from providers.sources.eastmoney_src import EastMoneyAdapter

        adapter = EastMoneyAdapter()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"data": {"klines": []}}
        with patch.object(adapter.client, "get", return_value=mock_resp):
            assert adapter.fetch_kline("600519") is None

    def test_fetch_basic_success(self):
        from providers.sources.eastmoney_src import EastMoneyAdapter

        adapter = EastMoneyAdapter()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "data": {
                "diff": {
                    "0": {
                        "f12": "600519", "f14": "茅台", "f2": 100.0,
                        "f3": 1.5, "f4": 1.0, "f5": 1000.0, "f6": 100000.0,
                        "f9": 20.0, "f10": 1.5, "f23": 3.0,
                    }
                }
            }
        }
        with patch.object(adapter.client, "get", return_value=mock_resp):
            data = adapter.fetch_basic("600519")

        assert data is not None
        assert data["stock_name"] == "茅台"
        assert data["latest_price"] == 100.0
        assert data["pe_ratio"] == 20.0

    def test_fetch_universe_success(self):
        from providers.sources.eastmoney_src import EastMoneyAdapter

        adapter = EastMoneyAdapter()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "data": {
                "diff": {
                    "0": {"f12": "600519", "f14": "茅台", "f13": "1"},
                    "1": {"f12": "000001", "f14": "平安银行", "f13": "0"},
                }
            }
        }
        with patch.object(adapter.client, "get", return_value=mock_resp):
            data = adapter.fetch_universe()

        assert data is not None
        assert len(data) == 2
        assert data[0]["exchange"] == "SH"
        assert data[1]["exchange"] == "SZ"

    def test_test_connect_failure(self):
        from providers.sources.eastmoney_src import EastMoneyAdapter

        adapter = EastMoneyAdapter()
        with patch.object(adapter.client, "get", side_effect=Exception("timeout")):
            assert adapter.test_connect() is False


class TestYFinanceAdapter:
    """yfinance适配器测试。"""

    def test_init(self):
        adapter = YFinanceAdapter()
        assert adapter.name == "yfinance"
        assert adapter.priority == 5

    def _mock_yf(self, history_df=None, info=None):
        """构造 mocked yfinance 模块。"""
        mock_ticker = MagicMock()
        if history_df is not None:
            mock_ticker.history.return_value = history_df
        mock_ticker.info = info

        mock_yf = MagicMock()
        mock_yf.Ticker.return_value = mock_ticker
        return mock_yf

    def test_fetch_kline_success(self):
        adapter = YFinanceAdapter()
        df = MagicMock()
        df.empty = False
        df.iterrows.return_value = iter([
            (
                MagicMock(strftime=lambda fmt: "2026-06-22"),
                {"Open": 1.0, "High": 2.0, "Low": 0.5, "Close": 1.5, "Volume": 1000},
            )
        ])
        mock_yf = self._mock_yf(history_df=df)

        original_import = builtins.__import__

        def _mock_import(name, *args, **kwargs):
            if name == "yfinance":
                return mock_yf
            return original_import(name, *args, **kwargs)

        with patch.object(builtins, "__import__", _mock_import):
            data = adapter.fetch_kline("600519", days=1)

        assert data is not None
        assert data[0]["close"] == 1.5
        assert data[0]["amount"] == 1500.0

    def test_fetch_kline_empty(self):
        adapter = YFinanceAdapter()
        df = MagicMock()
        df.empty = True
        mock_yf = self._mock_yf(history_df=df)

        original_import = builtins.__import__

        def _mock_import(name, *args, **kwargs):
            if name == "yfinance":
                return mock_yf
            return original_import(name, *args, **kwargs)

        with patch.object(builtins, "__import__", _mock_import):
            assert adapter.fetch_kline("600519") is None

    def test_fetch_kline_import_error(self):
        adapter = YFinanceAdapter()
        with patch.object(builtins, "__import__", side_effect=ImportError("no yfinance")):
            assert adapter.fetch_kline("600519") is None

    def test_fetch_basic_success(self):
        adapter = YFinanceAdapter()
        mock_yf = self._mock_yf(info={
            "shortName": "Moutai",
            "currentPrice": 100.0,
            "trailingPE": 20.0,
            "priceToBook": 3.0,
            "returnOnEquity": 0.15,
        })

        original_import = builtins.__import__

        def _mock_import(name, *args, **kwargs):
            if name == "yfinance":
                return mock_yf
            return original_import(name, *args, **kwargs)

        with patch.object(builtins, "__import__", _mock_import):
            data = adapter.fetch_basic("600519")

        assert data is not None
        assert data["stock_name"] == "Moutai"
        assert data["latest_price"] == 100.0
        assert data["pe_ratio"] == 20.0

    def test_fetch_basic_empty(self):
        adapter = YFinanceAdapter()
        mock_yf = self._mock_yf(info=None)

        original_import = builtins.__import__

        def _mock_import(name, *args, **kwargs):
            if name == "yfinance":
                return mock_yf
            return original_import(name, *args, **kwargs)

        with patch.object(builtins, "__import__", _mock_import):
            assert adapter.fetch_basic("600519") is None

    def test_test_connect_success(self):
        adapter = YFinanceAdapter()
        df = MagicMock()
        df.empty = False
        mock_yf = self._mock_yf(history_df=df)

        original_import = builtins.__import__

        def _mock_import(name, *args, **kwargs):
            if name == "yfinance":
                return mock_yf
            return original_import(name, *args, **kwargs)

        with patch.object(builtins, "__import__", _mock_import):
            assert adapter.test_connect() is True

    def test_test_connect_failure(self):
        adapter = YFinanceAdapter()
        mock_yf = MagicMock()
        mock_yf.Ticker.return_value.history.return_value = MagicMock(empty=True)

        original_import = builtins.__import__

        def _mock_import(name, *args, **kwargs):
            if name == "yfinance":
                return mock_yf
            return original_import(name, *args, **kwargs)

        with patch.object(builtins, "__import__", _mock_import):
            assert adapter.test_connect() is False
