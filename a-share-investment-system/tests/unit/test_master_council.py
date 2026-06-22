"""Master Council 单元测试"""

from graph_v2.master_council import build_master_council_report, build_master_views


class TestMasterCouncil:
    def test_build_master_views_returns_structured_items(self):
        state = {
            "stock_code": "600519",
            "stock_name": "贵州茅台",
            "pe_ratio": 30,
            "roe": 25,
        }
        views = build_master_views(state)
        assert isinstance(views, list)
        assert len(views) > 0
        first = views[0]
        for key in ("name", "display_name", "score", "signal"):
            assert key in first

    def test_master_council_report_contains_views_summary(self):
        views = [
            {
                "name": "buffett",
                "display_name": "Buffett",
                "style": "value",
                "score": 72,
                "signal": "bullish",
                "reasoning": "",
            },
            {
                "name": "taleb",
                "display_name": "Taleb",
                "style": "risk",
                "score": 40,
                "signal": "neutral",
                "reasoning": "",
            },
        ]
        report = build_master_council_report(views, "skill-context")
        assert "Master Council" in report
        assert "Buffett" in report
        assert "skill-context" in report


class TestMasterFactors:
    """Tests for compute_master_factors — pure Python, no external dependencies."""

    def test_bullish_consensus_increases_factors(self):
        from graph_v2.master_council import compute_master_factors

        views = [
            {
                "name": "buffett",
                "display_name": "Buffett",
                "style": "value",
                "score": 80,
                "signal": "bullish",
                "reasoning": "",
            },
            {
                "name": "munger",
                "display_name": "Munger",
                "style": "value",
                "score": 75,
                "signal": "bullish",
                "reasoning": "",
            },
            {
                "name": "taleb",
                "display_name": "Taleb",
                "style": "risk",
                "score": 60,
                "signal": "neutral",
                "reasoning": "",
            },
        ]
        factors = compute_master_factors(views)
        assert factors["master_weight_factor"] > 1.0
        assert factors["master_position_factor"] > 1.0

    def test_bearish_consensus_decreases_factors(self):
        from graph_v2.master_council import compute_master_factors

        views = [
            {
                "name": "buffett",
                "display_name": "Buffett",
                "style": "value",
                "score": 30,
                "signal": "bearish",
                "reasoning": "",
            },
            {
                "name": "munger",
                "display_name": "Munger",
                "style": "value",
                "score": 25,
                "signal": "bearish",
                "reasoning": "",
            },
            {
                "name": "taleb",
                "display_name": "Taleb",
                "style": "risk",
                "score": 40,
                "signal": "neutral",
                "reasoning": "",
            },
        ]
        factors = compute_master_factors(views)
        assert factors["master_weight_factor"] < 1.0
        assert factors["master_position_factor"] < 1.0

    def test_neutral_keeps_factors_near_one(self):
        from graph_v2.master_council import compute_master_factors

        views = [
            {
                "name": "buffett",
                "display_name": "Buffett",
                "style": "value",
                "score": 50,
                "signal": "neutral",
                "reasoning": "",
            },
            {
                "name": "munger",
                "display_name": "Munger",
                "style": "value",
                "score": 50,
                "signal": "neutral",
                "reasoning": "",
            },
            {
                "name": "taleb",
                "display_name": "Taleb",
                "style": "risk",
                "score": 50,
                "signal": "neutral",
                "reasoning": "",
            },
        ]
        factors = compute_master_factors(views)
        assert 0.9 <= factors["master_weight_factor"] <= 1.1
        assert 0.9 <= factors["master_position_factor"] <= 1.1

    def test_boundary_clamping(self):
        from graph_v2.master_council import compute_master_factors

        views = [
            {
                "name": "a",
                "display_name": "A",
                "style": "value",
                "score": 100,
                "signal": "bullish",
                "reasoning": "",
            },
            {
                "name": "b",
                "display_name": "B",
                "style": "value",
                "score": 100,
                "signal": "bullish",
                "reasoning": "",
            },
            {
                "name": "c",
                "display_name": "C",
                "style": "risk",
                "score": 100,
                "signal": "bullish",
                "reasoning": "",
            },
        ]
        factors = compute_master_factors(views)
        assert 0.70 <= factors["master_weight_factor"] <= 1.30
        assert 0.80 <= factors["master_position_factor"] <= 1.20

    def test_empty_views_returns_defaults(self):
        from graph_v2.master_council import compute_master_factors

        factors = compute_master_factors([])
        assert factors["master_weight_factor"] == 1.0
        assert factors["master_position_factor"] == 1.0
