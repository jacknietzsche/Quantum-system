"""DebateEngine unit tests"""

import pytest

from services.debate_engine import Claim, DebateEngine


class TestClaim:
    def test_to_dict_roundtrip(self):
        c = Claim(
            claim_id="BULL-1-abc123",
            text="bull claim",
            source="bull_fundamental",
            confidence=0.8,
            evidence=["e1", "e2"],
            author="BullResearcher",
            round_num=1,
        )
        d = c.to_dict()
        assert d["id"] == "BULL-1-abc123"
        assert d["confidence"] == 0.8
        assert d["evidence"] == ["e1", "e2"]
        assert d["author"] == "BullResearcher"
        assert d["round"] == 1
        assert d["status"] == "open"

    def test_default_status_open(self):
        c = Claim("X", "t", "src", 0.5, [], "A", 1)
        assert c.status == "open"


class TestDebateEngineInit:
    def test_default_init(self):
        engine = DebateEngine()
        assert engine.MAX_ROUNDS == 2
        assert engine.SOURCE_OVERLAP_THRESHOLD == 0.5
        assert engine.memory_bank is not None
        assert engine.quant is not None

    def test_custom_memory_bank(self):
        from services.memory_bank import MemoryBank

        mb = MemoryBank()
        engine = DebateEngine(memory_bank=mb)
        assert engine.memory_bank is mb


class TestRunDebate:
    @pytest.fixture()
    def engine(self):
        return DebateEngine()

    @pytest.fixture()
    def reports(self):
        return [
            {"category": "analysis", "analysis_prompt": "ROE > 20%", "score": 85},
            {"category": "risk", "alerts": "PE 35x", "score": 60},
        ]

    @pytest.fixture()
    def ctx(self):
        return {
            "stock_name": "Moutai",
            "price": 1800.0,
            "pe_ratio": 30.0,
            "roe": 25.0,
            "pl_pct": 2.5,
        }

    def test_returns_ok_with_claims(self, engine, reports, ctx):
        result = engine.run_debate("600519", reports, ctx)
        assert result.ok
        assert "verdict" in result.data
        assert "confidence" in result.data
        assert "claims" in result.data
        assert len(result.data["claims"]) > 0

    def test_confidence_bounded(self, engine, reports, ctx):
        result = engine.run_debate("600519", reports, ctx)
        conf = result.data["confidence"]
        assert 0.0 <= conf <= 1.0

    def test_empty_reports_ok(self, engine, ctx):
        result = engine.run_debate("600519", [], ctx)
        assert result.ok
        assert "verdict" in result.data

    def test_max_rounds_1(self, engine, reports, ctx):
        result = engine.run_debate("600519", reports, ctx, max_rounds=1)
        assert result.ok
        assert len(result.data["claims"]) <= 2

    def test_llm_configs(self, engine, reports, ctx):
        result = engine.run_debate(
            "600519",
            reports,
            ctx,
            llm_configs=[{"model": "gpt-4o"}],
        )
        assert result.ok


class TestJudge:
    @pytest.fixture()
    def engine(self):
        return DebateEngine()

    def test_empty_claims_neutral(self, engine):
        v = engine._judge("600519", "M", [], {}, [])
        assert v["confidence"] == 0.4

    def test_bull_dominant(self, engine):
        claims = [
            Claim("B1", "t", "bull_fundamental", 0.9, [], "BullResearcher", 1),
            Claim("B2", "t", "bull_fundamental", 0.85, [], "BullResearcher", 2),
            Claim("R1", "t", "bear_technical", 0.3, [], "BearResearcher", 1),
        ]
        v = engine._judge("600519", "M", [], {}, claims)
        assert v["confidence"] > 0.5

    def test_bear_dominant(self, engine):
        claims = [
            Claim("R1", "t", "bear_technical", 0.9, [], "BearResearcher", 1),
            Claim("R2", "t", "bear_technical", 0.85, [], "BearResearcher", 2),
            Claim("B1", "t", "bull_fundamental", 0.3, [], "BullResearcher", 1),
        ]
        v = engine._judge("600519", "M", [], {}, claims)
        assert v["confidence"] > 0.5

    def test_balanced_neutral(self, engine):
        claims = [
            Claim("B1", "t", "bull_fundamental", 0.6, [], "BullResearcher", 1),
            Claim("R1", "t", "bear_technical", 0.6, [], "BearResearcher", 1),
        ]
        v = engine._judge("600519", "M", [], {}, claims)
        assert v["confidence"] == 0.5


class TestSourceOverlap:
    @pytest.fixture()
    def engine(self):
        return DebateEngine()

    def test_no_overlap(self, engine):
        claims = [
            Claim("B1", "t", "bull_fundamental", 0.8, [], "BullResearcher", 1),
            Claim("R1", "t", "bear_technical", 0.7, [], "BearResearcher", 1),
        ]
        assert engine._calc_source_overlap(claims) == 0.0

    def test_full_overlap(self, engine):
        claims = [
            Claim("B1", "t", "shared", 0.8, [], "BullResearcher", 1),
            Claim("R1", "t", "shared", 0.7, [], "BearResearcher", 1),
        ]
        assert engine._calc_source_overlap(claims) == 1.0

    def test_partial_overlap(self, engine):
        claims = [
            Claim("B1", "t", "a", 0.8, [], "BullResearcher", 1),
            Claim("B2", "t", "c", 0.7, [], "BullResearcher", 2),
            Claim("R1", "t", "a", 0.7, [], "BearResearcher", 1),
            Claim("R2", "t", "b", 0.6, [], "BearResearcher", 2),
        ]
        assert abs(engine._calc_source_overlap(claims) - 1 / 3) < 0.01

    def test_empty_claims(self, engine):
        assert engine._calc_source_overlap([]) == 0.0

    def test_only_bull(self, engine):
        claims = [Claim("B1", "t", "src", 0.8, [], "BullResearcher", 1)]
        assert engine._calc_source_overlap(claims) == 0.0
