"""Unit tests for skills.py registry and base classes."""

from unittest.mock import MagicMock

import pytest


class TestSkillRegistry:
    def test_register_and_get(self):
        from skills import BaseSkill, SkillRegistry

        reg = SkillRegistry()

        class MySkill(BaseSkill):
            @property
            def name(self):
                return "test_skill"

        reg.register(MySkill())
        assert reg.get("test_skill") is not None
        assert reg.get("nonexistent") is None

    def test_count(self):
        from skills import BaseSkill, SkillRegistry

        reg = SkillRegistry()
        assert reg.count() == 0

        class S1(BaseSkill):
            @property
            def name(self):
                return "s1"

        class S2(BaseSkill):
            @property
            def name(self):
                return "s2"

        reg.register(S1())
        reg.register(S2())
        assert reg.count() == 2

    def test_get_all_names(self):
        from skills import BaseSkill, SkillRegistry

        reg = SkillRegistry()

        class S1(BaseSkill):
            @property
            def name(self):
                return "alpha"

        class S2(BaseSkill):
            @property
            def name(self):
                return "beta"

        reg.register(S1())
        reg.register(S2())
        names = reg.get_all_names()
        assert "alpha" in names
        assert "beta" in names

    def test_get_by_category(self):
        from skills import BaseSkill, SkillRegistry

        reg = SkillRegistry()

        class ValueSkill(BaseSkill):
            @property
            def name(self):
                return "v1"

            @property
            def category(self):
                return "value"

        class RiskSkill(BaseSkill):
            @property
            def name(self):
                return "r1"

            @property
            def category(self):
                return "risk"

        reg.register(ValueSkill())
        reg.register(RiskSkill())
        values = reg.get_by_category("value")
        assert len(values) == 1
        assert values[0].name == "v1"

    def test_execute_found(self):
        from skills import BaseSkill, SkillRegistry

        reg = SkillRegistry()

        class EchoSkill(BaseSkill):
            @property
            def name(self):
                return "echo"

            def execute(self, context):
                return {"echo": context.get("input")}

        reg.register(EchoSkill())
        result = reg.execute("echo", {"input": "hello"})
        assert result["echo"] == "hello"

    def test_execute_not_found(self):
        from skills import SkillRegistry

        reg = SkillRegistry()
        result = reg.execute("missing", {})
        assert result["status"] == "not_found"

    def test_execute_error(self):
        from skills import BaseSkill, SkillRegistry

        reg = SkillRegistry()

        class BadSkill(BaseSkill):
            @property
            def name(self):
                return "bad"

            def execute(self, context):
                raise ValueError("boom")

        reg.register(BadSkill())
        result = reg.execute("bad", {})
        assert result["status"] == "error"
        assert "boom" in result["error"]

    def test_execute_all(self):
        from skills import BaseSkill, SkillRegistry

        reg = SkillRegistry()

        class S1(BaseSkill):
            @property
            def name(self):
                return "s1"

            @property
            def category(self):
                return "value"

            def execute(self, ctx):
                return {"v": 1}

        class S2(BaseSkill):
            @property
            def name(self):
                return "s2"

            @property
            def category(self):
                return "risk"

            def execute(self, ctx):
                return {"v": 2}

        reg.register(S1())
        reg.register(S2())
        all_results = reg.execute_all({})
        assert len(all_results) == 2
        # Filter by category
        value_results = reg.execute_all({}, categories=["value"])
        assert len(value_results) == 1
        assert "s1" in value_results

    def test_execute_all_with_error(self):
        from skills import BaseSkill, SkillRegistry

        reg = SkillRegistry()

        class BadSkill(BaseSkill):
            @property
            def name(self):
                return "bad"

            def execute(self, ctx):
                raise RuntimeError("fail")

        reg.register(BadSkill())
        results = reg.execute_all({})
        assert results["bad"]["status"] == "error"


class TestBaseSkill:
    def test_default_properties(self):
        from skills import BaseSkill

        s = BaseSkill()
        assert s.name == ""
        assert s.description == ""
        assert s.category == "general"

    def test_execute_raises(self):
        from skills import BaseSkill

        s = BaseSkill()
        with pytest.raises(NotImplementedError):
            s.execute({})


class TestLLMEnhancedSkill:
    def test_execute_returns_fallback(self):
        from skills import LLMEnhancedSkill

        class MyLLMSkill(LLMEnhancedSkill):
            @property
            def name(self):
                return "my_llm"

        s = MyLLMSkill()
        result = s.execute({})
        assert result["skill"] == "my_llm"

    def test_execute_catches_exception(self):
        from skills import LLMEnhancedSkill

        class BadLLMSkill(LLMEnhancedSkill):
            @property
            def name(self):
                return "bad_llm"

            def _fallback_execute(self, ctx):
                raise RuntimeError("LLM down")

        s = BadLLMSkill()
        result = s.execute({})
        assert result["status"] == "error"


class TestRiskFirewall:
    def test_check_no_risks(self):
        from skills import RiskFirewall

        fw = RiskFirewall()
        outputs = {
            "skill_a": {"signal": "bullish", "score": 80},
            "skill_b": {"signal": "neutral", "score": 50},
        }
        result = fw.check(outputs)
        assert result["pass"] is True
        assert result["total_risks"] == 0

    def test_check_bearish_signal(self):
        from skills import RiskFirewall

        fw = RiskFirewall()
        outputs = {"skill_a": {"signal": "bearish", "score": 50}}
        result = fw.check(outputs)
        assert result["total_risks"] >= 1
        assert any("bearish" in r["message"] for r in result["risks"])

    def test_check_low_score(self):
        from skills import RiskFirewall

        fw = RiskFirewall()
        outputs = {"skill_a": {"signal": "bullish", "score": 10}}
        result = fw.check(outputs)
        assert result["pass"] is False
        assert any(r["level"] == "critical" for r in result["risks"])

    def test_check_non_dict_skipped(self):
        from skills import RiskFirewall

        fw = RiskFirewall()
        outputs = {"skill_a": "not_a_dict", "skill_b": {"signal": "bullish", "score": 80}}
        result = fw.check(outputs)
        assert result["total_risks"] == 0


class TestAdapterProperties:
    def test_buffett_adapter(self):
        from skills import BuffettSkillAdapter

        s = BuffettSkillAdapter()
        assert s.name == "buffett"
        assert s.category == "value"
        assert len(s.description) > 0

    def test_munger_adapter(self):
        from skills import MungerSkillAdapter

        s = MungerSkillAdapter()
        assert s.name == "munger"
        assert s.category == "risk"

    def test_taleb_adapter(self):
        from skills import TalebSkillAdapter

        s = TalebSkillAdapter()
        assert s.name == "taleb"
        assert s.category == "risk"

    def test_china_stock_research_adapter(self):
        from skills import ChinaStockResearchAdapter

        s = ChinaStockResearchAdapter()
        assert s.name == "china_stock_research"
        assert s.category == "analysis"

    def test_trading_agents_adapter(self):
        from skills import TradingAgentsAShareAdapter

        s = TradingAgentsAShareAdapter()
        assert s.name == "trading_agents_ashare"


class TestCreateGenericAdapter:
    def test_creates_adapter(self):
        from skills import BaseSkill, _create_generic_adapter

        meta = MagicMock()
        meta.description = "Test description"
        meta.category = "test"
        meta.source_project = "test_project"
        adapter = _create_generic_adapter("generic_test", meta)
        assert isinstance(adapter, BaseSkill)
        assert adapter.name == "generic_test"
        assert adapter.category == "test"
