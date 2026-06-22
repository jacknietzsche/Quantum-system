"""Test multi-style stock screener pipelines"""

from services.stock_screener import VALID_STYLES, StockScreener

SAMPLE_STOCK = {
    "stock_code": "600519",
    "stock_name": "贵州茅台",
    "industry": "白酒",
    "price": 150.0,
    "pe": 30.0,
    "pb": 10.0,
    "roe": 25.0,
    "market_cap": 200.0,
    "change_pct": 3.0,
    "turnover_rate": 5.0,
    "trend": "上升",
    "volatility": 20.0,
    "gross_margin": 90.0,
    "debt_to_equity": 0.5,
    "eps": 10.0,
    "bvps": 50.0,
    "earnings_growth_3y": 15.0,
    "revenue_growth_3y": 12.0,
    "free_cash_flow": 100.0,
    "net_income": 500.0,
    "change_pct_5d": 8.0,
    "change_pct_20d": 15.0,
    "change_pct_60d": 25.0,
    "volume_ratio": 2.0,
    "ma5": 155.0,
    "ma10": 152.0,
    "ma20": 148.0,
    "ma60": 140.0,
    "ma250": 130.0,
    "amount": 2e8,
}


class TestConstruction:
    def test_accepts_valid_style(self):
        for style in VALID_STYLES:
            s = StockScreener(style=style)
            assert s.style == style

    def test_rejects_invalid_style(self):
        s = StockScreener(style="invalid_style")
        assert s.style == "hybrid"


class TestRunPipeline:
    def test_pipeline_returns_service_result(self):
        """run() with candidates should return ok with recommendations"""
        s = StockScreener(style="hybrid")
        result = s.run(candidates=[SAMPLE_STOCK], market_regime="NEUTRAL", top_n=10)
        assert result.status == "ok"
        data = result.data
        assert "recommendations" in data
        assert data["style"] == "hybrid"

    def test_empty_universe_returns_empty(self):
        """run() with empty universe should return ok with 0 screened"""
        s = StockScreener(style="hybrid")
        result = s.run(stock_universe=[], market_regime="NEUTRAL", top_n=10)
        assert result.status == "ok"
        assert result.data["total_screened"] == 0
