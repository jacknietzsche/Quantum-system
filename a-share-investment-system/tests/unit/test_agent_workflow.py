"""Tests for services.agent_workflow - AgentWorkflowService."""


class TestAnalysisResult:
    def test_creation(self):
        from services.agent_workflow import AnalysisResult

        result = AnalysisResult(
            stock_code="600519",
            stock_name="Moutai",
            research="test research",
            debate="test debate",
            risk="low",
            signal="buy",
            error=None,
        )
        assert result.stock_code == "600519"
        assert result.signal == "buy"

    def test_defaults(self):
        from services.agent_workflow import AnalysisResult

        result = AnalysisResult(stock_code="600519", stock_name="Moutai")
        assert result.stock_code == "600519"


class TestAgentWorkflowService:
    def test_init(self):
        from services.agent_workflow import AgentWorkflowService

        svc = AgentWorkflowService()
        assert svc is not None

    def test_init_with_style(self):
        from services.agent_workflow import AgentWorkflowService

        svc = AgentWorkflowService(style="momentum")
        assert svc.style == "momentum"
