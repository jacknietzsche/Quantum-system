"""Tests for services.screening.stages."""

from unittest.mock import MagicMock


class TestStage1:
    def test_empty_universe(self):
        from services.screening.stages.stage1 import stage1_quant_filter

        config = MagicMock()
        config.top_n = 10
        config.score_min = 3
        config.turnover_min = 0.0
        config.market_cap_min = 0.0
        config.max_market_cap = 999999.0
        config.volatility_max = 99.0
        config.st_filter = True
        config.require_ma_uptrend = False
        result = stage1_quant_filter([], config)
        assert isinstance(result, list)

    def test_with_stocks(self):
        from services.screening.stages.stage1 import stage1_quant_filter

        config = MagicMock()
        config.top_n = 10
        config.score_min = 3
        config.turnover_min = 0.0
        config.market_cap_min = 0.0
        config.max_market_cap = 999999.0
        config.volatility_max = 99.0
        config.st_filter = True
        config.require_ma_uptrend = False
        stocks = [
            {"stock_code": "600519", "score": 80, "change_pct": 2.5, "turnover_rate": 1.5},
            {"stock_code": "000858", "score": 40, "change_pct": 1.0, "turnover_rate": 0.3},
        ]
        result = stage1_quant_filter(stocks, config)
        assert isinstance(result, list)


class TestStage2:
    def test_empty_candidates(self):
        from services.screening.stages.stage2 import stage2_fundamental_filter

        config = MagicMock()
        config.top_n = 10
        config.score_min = 4
        config.min_volume_ratio = 0.0
        config.min_roe = 0.0
        config.roe_high = 25.0
        config.roe_medium = 15.0
        config.roe_low = 10.0
        config.min_revenue_growth = -999.0
        config.min_gross_margin = 0.0
        config.max_debt_to_equity = 999.0
        config.max_pe = 999.0
        config.max_pb = 999.0
        config.min_fcf = -999999.0
        config.min_cagr = -999.0
        result = stage2_fundamental_filter([], config)
        assert isinstance(result, list)

    def test_with_candidates(self):
        from services.screening.stages.stage2 import stage2_fundamental_filter

        config = MagicMock()
        config.top_n = 10
        config.score_min = 4
        config.min_volume_ratio = 0.0
        config.min_roe = 0.0
        config.roe_high = 25.0
        config.roe_medium = 15.0
        config.roe_low = 10.0
        config.min_revenue_growth = -999.0
        config.min_gross_margin = 0.0
        config.max_debt_to_equity = 999.0
        config.max_pe = 999.0
        config.max_pb = 999.0
        config.min_fcf = -999999.0
        config.min_cagr = -999.0
        stocks = [
            {"stock_code": "600519", "score": 80, "roe": 25, "pe_ratio": 35, "pb_ratio": 12},
        ]
        result = stage2_fundamental_filter(stocks, config)
        assert isinstance(result, list)


class TestStage4:
    def test_stage4_agent_workflow(self):
        from services.screening.stages.stage4 import stage4_agent_workflow

        config = MagicMock()
        config.enabled = False
        result = stage4_agent_workflow([], config)
        assert isinstance(result, list)
