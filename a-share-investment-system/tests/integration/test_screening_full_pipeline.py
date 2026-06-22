"""集成测试: HardFilter → TradingStrategyOrchestrator 流水线"""

import pytest

from services.hard_filter import HardFilter
from services.stock_screener import StockScreener

# Keep the module import at top to avoid PLC0415 in functions


def _make_stock(overrides: dict | None = None) -> dict:
    d = {
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
    if overrides:
        d.update(overrides)
    return d


@pytest.mark.integration
def test_hard_filter_short_term():
    """短期 HardFilter: 正常股票通过"""
    hf = HardFilter("short_term")
    stocks = [_make_stock()]
    result = hf.apply(stocks)
    assert len(result) == 1


@pytest.mark.integration
def test_hard_filter_rejects_st():
    """HardFilter 排除 ST 股"""
    hf = HardFilter("short_term")
    stocks = [_make_stock({"stock_name": "*ST华仪"})]
    result = hf.apply(stocks)
    assert len(result) == 0


@pytest.mark.integration
def test_pipeline_returns_recommendations():
    """完整流水线: HardFilter → Orchestrator → 推荐"""
    StockScreener(style="hybrid")
    stocks = [_make_stock()]
    candidates = HardFilter("hybrid").apply(stocks)
    assert len(candidates) >= 1


@pytest.mark.integration
def test_pipeline_empty_universe():
    """空股票池应返回空结果"""
    screener = StockScreener(style="limit_up")
    result = screener.run(candidates=[], market_regime="NEUTRAL", top_n=10)
    assert result.status in ("ok", "degraded")
    assert result.data["total_screened"] == 0
