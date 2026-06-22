"""集成测试 — HardFilter 完整管道"""

from services.hard_filter import HardFilter


def _make_stock(overrides: dict) -> dict:
    defaults = {
        "stock_code": "000001",
        "stock_name": "平安银行",
        "price": 12.0,
        "amount": 2e8,
        "turnover_rate": 2.0,
        "change_pct_5d": 8,
        "change_pct_20d": 15,
        "change_pct_60d": 25,
        "volume_ratio": 2.0,
        "market_cap": 200,
        "pe": 10,
        "pb": 1.2,
        "roe": 18,
        "ma5": 12.5,
        "ma10": 12.0,
        "ma20": 11.5,
        "ma60": 11.0,
        "ma250": 10.0,
        "free_cash_flow": 1e9,
        "debt_to_equity": 0.8,
        "gross_margin": 40,
        "industry": "银行",
        "earnings_growth_3y": 15,
        "revenue_growth_3y": 12,
    }
    defaults.update(overrides)
    return defaults


class TestScreeningIntegration:
    def test_hard_filter_short_term_runs(self):
        """短期策略集成测试 — 正确过滤掉成交额/涨幅不足的股票"""
        stocks = [
            _make_stock({"stock_code": "000001", "amount": 2e8, "change_pct_5d": 8}),
            _make_stock({"stock_code": "000002", "amount": 5e6, "change_pct_5d": 1}),
        ]
        hf = HardFilter("short_term")
        filtered = hf._filter_short_term(stocks)
        assert len(filtered) == 1
        assert filtered[0]["stock_code"] == "000001"
        # apply 完整流程: fallback 会补充低阈值 stock, 但至少过第一关的股票应排在前面
        result = hf.apply(stocks)
        assert result[0]["stock_code"] == "000001"

    def test_hard_filter_fallback(self):
        """兜底逻辑: 过滤结果太少应从 universe 补充"""
        stocks = [
            _make_stock({"pe": -1, "stock_code": "000001"}),
            _make_stock({"pe": -1, "stock_code": "000002"}),
        ]
        result = HardFilter("short_term").apply(stocks)
        assert len(result) >= 2  # fallback adds all since <50 passed

    def test_hard_filter_fallback_excludes_zero_price(self):
        """Fallback 不应补充零价股"""
        stocks = [
            _make_stock({"pe": -1, "stock_code": "000001"}),
            _make_stock({"pe": -1, "stock_code": "000002", "price": 0}),
        ]
        result = HardFilter("short_term").apply(stocks)
        assert len(result) == 1
