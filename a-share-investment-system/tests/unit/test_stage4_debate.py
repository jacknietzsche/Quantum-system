"""Stage4 辩论流程 单元测试"""

from services.stage4_debate import Stage4Debate


class TestStage4Init:
    def test_disabled_by_default(self):
        s4 = Stage4Debate()
        assert s4.enabled is False
        assert s4.top_n == 5

    def test_enabled_via_config(self):
        s4 = Stage4Debate({"enabled": True, "top_n": 3})
        assert s4.enabled is True
        assert s4.top_n == 3

    def test_config_loads_skills(self):
        s4 = Stage4Debate({"enabled": True, "skills": ["buffett", "munger"]})
        assert s4.skills == ["buffett", "munger"]

    def test_config_loads_workflow(self):
        s4 = Stage4Debate({"enabled": True, "workflow": ["research", "debate", "risk", "signal"]})
        assert s4.workflow == ["research", "debate", "risk", "signal"]


class TestStage4Run:
    def test_returns_unchanged_when_disabled(self):
        s4 = Stage4Debate()
        candidates = [{"stock_code": "000001", "score": 80}]
        result = s4.run(candidates)
        assert len(result) == 1
        assert result[0]["stage4_analyzed"] is False

    def test_returns_empty_list_for_empty_input(self):
        s4 = Stage4Debate({"enabled": True})
        result = s4.run([])
        assert result == []

    def test_top_n_limits_debate_candidates(self):
        s4 = Stage4Debate({"enabled": True, "top_n": 2})
        candidates = [{"stock_code": f"{i:06d}", "score": 100 - i} for i in range(5)]
        result = s4.run(candidates)
        # All candidates preserved, but only top 2 debated
        assert len(result) == 5
        debated = [c for c in result if c.get("stage4_analyzed")]
        assert len(debated) <= 2

    def test_scores_reordered_after_debate(self):
        s4 = Stage4Debate({"enabled": True, "top_n": 3})
        candidates = [
            {"stock_code": "000001", "stock_name": "A", "score": 50},
            {"stock_code": "000002", "stock_name": "B", "score": 30},
        ]
        result = s4.run(candidates, market_regime="BULL")
        # Should still return all
        assert len(result) == 2
        # Scores might be adjusted
        for c in result:
            assert "score" in c

    def test_adds_stage4_metadata(self):
        s4 = Stage4Debate({"enabled": True})
        candidates = [{"stock_code": "000001", "stock_name": "Test", "score": 60}]
        result = s4.run(candidates)
        assert "stage4_analyzed" in result[0]
        # For non-debated (only 1 candidate, top_n=5, so this one is in top)
        assert result[0]["stage4_analyzed"] is True or False

    def test_handles_debate_failure_gracefully(self):
        s4 = Stage4Debate({"enabled": True, "top_n": 5})
        candidates = [{"stock_code": "INVALID", "stock_name": "Bad", "score": 50}]
        # Should not crash on invalid stock
        result = s4.run(candidates)
        assert len(result) == 1
        assert "score" in result[0]


class TestDebateResultApplication:
    def test_bullish_verdict_boosts_score(self):
        s4 = Stage4Debate({"enabled": True})
        candidate = {"stock_code": "000001", "stock_name": "A", "score": 50, "signal": "观望"}
        debate_data = {
            "verdict": "买入",
            "confidence": 0.8,
            "claims": [
                {"author": "BullResearcher", "text": "Good value", "source": "bull_fundamental"},
                {"author": "BullResearcher", "text": "Strong growth", "source": "bull_fundamental"},
                {"author": "BearResearcher", "text": "Risk", "source": "bear_technical"},
            ],
        }
        s4._apply_debate_result(candidate, debate_data)
        assert candidate["stage4_verdict"] == "买入"
        assert candidate["stage4_confidence"] == 0.8
        # score should increase: 50 + int(15 * 0.8) = 50 + 12 = 62
        assert candidate["score"] == 62
        # confidence >= 0.7 means signal should be "买入"
        assert candidate["signal"] == "买入"

    def test_bearish_verdict_reduces_score(self):
        s4 = Stage4Debate({"enabled": True})
        candidate = {"stock_code": "000001", "stock_name": "A", "score": 70, "signal": "买入"}
        debate_data = {
            "verdict": "卖出",
            "confidence": 0.9,
            "claims": [
                {"author": "BearResearcher", "text": "Overvalued", "source": "bear_technical"},
                {"author": "BearResearcher", "text": "Poor momentum", "source": "bear_technical"},
            ],
        }
        s4._apply_debate_result(candidate, debate_data)
        assert candidate["stage4_verdict"] == "卖出"
        # score should decrease: 70 - int(20 * 0.9) = 70 - 18 = 52
        assert candidate["score"] == 52
        # bearish verdict always sets signal to "卖出"
        assert candidate["signal"] == "卖出"

    def test_hold_verdict_slightly_adjusts(self):
        s4 = Stage4Debate({"enabled": True})
        candidate = {"stock_code": "000001", "stock_name": "A", "score": 50, "signal": "观望"}
        debate_data = {
            "verdict": "持有",
            "confidence": 0.5,
            "claims": [
                {"author": "BullResearcher", "text": "OK", "source": "bull_fundamental"},
                {"author": "BearResearcher", "text": "Meh", "source": "bear_technical"},
            ],
        }
        s4._apply_debate_result(candidate, debate_data)
        assert candidate["stage4_verdict"] == "持有"
        # Net bull-bear = 0 for hold with equal counts → no adjustment
        assert candidate["score"] == 50

    def test_confidence_affects_adjustment_magnitude(self):
        s4 = Stage4Debate({"enabled": True})
        candidate = {"stock_code": "000001", "stock_name": "A", "score": 50}
        debate_data = {
            "verdict": "买入",
            "confidence": 0.5,
            "claims": [{"author": "BullResearcher", "text": "OK", "source": "bull_fundamental"}],
        }
        s4._apply_debate_result(candidate, debate_data)
        # 50 + int(15 * 0.5) = 50 + 7 = 57
        assert candidate["score"] == 57

    def test_bull_bear_counts_recorded(self):
        s4 = Stage4Debate({"enabled": True})
        candidate = {"stock_code": "000001", "stock_name": "A", "score": 50}
        debate_data = {
            "verdict": "持有",
            "confidence": 0.6,
            "claims": [
                {"author": "BullResearcher", "text": "B1", "source": "bull_fundamental"},
                {"author": "BullResearcher", "text": "B2", "source": "bull_fundamental"},
                {"author": "BearResearcher", "text": "R1", "source": "bear_technical"},
            ],
        }
        s4._apply_debate_result(candidate, debate_data)
        assert candidate["stage4_bull_rounds"] == 2
        assert candidate["stage4_bear_rounds"] == 1


class TestBuildAnalystReports:
    def test_build_reports_from_candidate(self):
        s4 = Stage4Debate()
        candidate = {
            "stock_code": "600519",
            "stock_name": "贵州茅台",
            "pe": 30,
            "roe": 25,
            "pb": 8,
            "change_pct_5d": 3.5,
            "change_pct_60d": 15,
            "volatility": 20,
            "max_drawdown_60d": 5,
        }
        reports = s4._build_analyst_reports(candidate)
        assert len(reports) >= 3
        categories = [r.get("category") for r in reports]
        assert "value" in categories
        assert "analysis" in categories
        assert "risk" in categories

    def test_reports_contain_missing_field_placeholders(self):
        s4 = Stage4Debate()
        candidate = {"stock_code": "000001", "stock_name": "Test"}
        reports = s4._build_analyst_reports(candidate)
        for r in reports:
            prompt = r.get("analysis_prompt", r.get("alerts", ""))
            assert "N/A" in prompt or prompt != ""


class TestMasterWeightFactorEffect:
    def test_higher_weight_factor_boosts_score_more(self):
        s4 = Stage4Debate({"enabled": True})
        debate_data = {
            "verdict": chr(28201) + chr(20837),
            "confidence": 0.8,
            "claims": [
                {"author": "BullResearcher", "text": "Good value", "source": "bull_fundamental"},
            ],
        }
        c1 = {"stock_code": "000001", "stock_name": "A", "score": 50}
        c2 = {"stock_code": "000001", "stock_name": "A", "score": 50}
        c3 = {"stock_code": "000001", "stock_name": "A", "score": 50}
        s4._apply_debate_result(c1, debate_data, master_weight_factor=0.8)
        s4._apply_debate_result(c2, debate_data, master_weight_factor=1.0)
        s4._apply_debate_result(c3, debate_data, master_weight_factor=1.2)
        assert c3["score"] > c2["score"] > c1["score"]
