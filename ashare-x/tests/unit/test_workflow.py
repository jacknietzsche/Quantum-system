"""Phase 4 工作流+Skill+记忆测试。"""

from __future__ import annotations

from core.state import AgentState
from graph.conditional_logic import (
    route_after_pm,
    should_continue_investment_debate,
    should_continue_risk_debate,
)
from memory.decision_log import DecisionLog
from memory.injection import inject_memory
from skills.engine import SkillEngine


class TestConditionalLogic:
    def test_investment_debate_continues(self):
        state: AgentState = {"investment_debate_rounds": 0, "config": {}}
        assert should_continue_investment_debate(state) == "continue"

    def test_investment_debate_ends_at_max(self):
        state: AgentState = {"investment_debate_rounds": 2, "config": {}}
        assert should_continue_investment_debate(state) == "end"

    def test_risk_debate_ends_at_max(self):
        state: AgentState = {"risk_debate_rounds": 2, "config": {}}
        assert should_continue_risk_debate(state) == "end"

    def test_route_after_pm_no_masters(self):
        state: AgentState = {"config": {"features": {"enable_masters": False}}}
        assert route_after_pm(state) == "final"

    def test_route_after_pm_with_masters(self):
        state: AgentState = {"config": {"features": {"enable_masters": True}}}
        assert route_after_pm(state) == "with_masters"


class TestSkillEngine:
    def test_discover(self):
        engine = SkillEngine("C:/Users/21471/WorkBuddy/Trading agent and skill/ashare-x/skills")
        engine.discover()
        assert "buffett" in engine.registry

    def test_get_skill(self):
        engine = SkillEngine("C:/Users/21471/WorkBuddy/Trading agent and skill/ashare-x/skills")
        skill = engine.get_skill("buffett")
        assert skill is not None
        assert skill.metadata.name == "buffett"
        assert "能力圈" in skill.prompt

    def test_get_for_agent(self):
        engine = SkillEngine("C:/Users/21471/WorkBuddy/Trading agent and skill/ashare-x/skills")
        skills = engine.get_for_agent("fundamentals_analyst")
        assert len(skills) > 0

    def test_activate(self):
        engine = SkillEngine("C:/Users/21471/WorkBuddy/Trading agent and skill/ashare-x/skills")
        prompt = engine.activate("buffett")
        assert prompt is not None
        assert "能力圈" in prompt

    def test_discover_munger(self):
        engine = SkillEngine("C:/Users/21471/WorkBuddy/Trading agent and skill/ashare-x/skills")
        engine.discover()
        assert "munger" in engine.registry
        skill = engine.get_skill("munger")
        assert skill is not None
        assert "逆向思考" in skill.prompt

    def test_discover_taleb(self):
        engine = SkillEngine("C:/Users/21471/WorkBuddy/Trading agent and skill/ashare-x/skills")
        engine.discover()
        assert "taleb" in engine.registry
        skill = engine.get_skill("taleb")
        assert skill is not None
        assert "反脆弱" in skill.prompt

    def test_discover_china_stock_research(self):
        engine = SkillEngine("C:/Users/21471/WorkBuddy/Trading agent and skill/ashare-x/skills")
        engine.discover()
        assert "china-stock-research" in engine.registry
        skill = engine.get_skill("china-stock-research")
        assert skill is not None
        assert "财务健康度" in skill.prompt

    def test_discover_a_share_trading(self):
        engine = SkillEngine("C:/Users/21471/WorkBuddy/Trading agent and skill/ashare-x/skills")
        engine.discover()
        assert "a-share-trading" in engine.registry
        skill = engine.get_skill("a-share-trading")
        assert skill is not None
        assert "MACD" in skill.prompt

    def test_skills_for_bear_researcher(self):
        engine = SkillEngine("C:/Users/21471/WorkBuddy/Trading agent and skill/ashare-x/skills")
        skills = engine.get_for_agent("bear_researcher")
        names = [s.metadata.name for s in skills]
        assert "taleb" in names

    def test_skills_for_portfolio_manager(self):
        engine = SkillEngine("C:/Users/21471/WorkBuddy/Trading agent and skill/ashare-x/skills")
        skills = engine.get_for_agent("portfolio_manager")
        names = [s.metadata.name for s in skills]
        assert "munger" in names
        assert "buffett" in names

    def test_skills_for_trader(self):
        engine = SkillEngine("C:/Users/21471/WorkBuddy/Trading agent and skill/ashare-x/skills")
        skills = engine.get_for_agent("trader")
        names = [s.metadata.name for s in skills]
        assert "a-share-trading" in names


class TestDecisionLog:
    def test_add_and_get(self):
        log = DecisionLog(db_path=":memory:")
        log.add_entry("600519", "2026-01-01", "Buy", 80.0, 1500.0, 1425.0, "test thesis")
        history = log.get_history("600519")
        assert len(history) == 1
        assert history[0]["action"] == "Buy"

    def test_max_entries_rotation(self):
        log = DecisionLog(db_path=":memory:", max_entries=3)
        for i in range(5):
            log.add_entry("600519", f"2026-01-0{i + 1}", "Buy", 80.0)
        history = log.get_history("600519")
        assert len(history) == 3


class TestMemoryInjection:
    def test_inject_empty(self):
        log = DecisionLog(db_path=":memory:")
        result = inject_memory(log, "600519")
        assert result == ""

    def test_inject_with_history(self):
        log = DecisionLog(db_path=":memory:")
        log.add_entry("600519", "2026-01-01", "Buy", 80.0, 1500.0, 1425.0, "test")
        result = inject_memory(log, "600519")
        assert "历史决策记忆" in result
        assert "Buy" in result
