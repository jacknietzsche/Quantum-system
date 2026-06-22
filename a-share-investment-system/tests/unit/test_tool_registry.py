"""Tool Registry 单元测试 — 数据工具 + 大师工具 + 技能工具"""

from services.agents.tool_registry import (
    create_default_tools,
    get_financials_tool,
    get_master_analyze_tool,
    get_master_list_tool,
    get_sentiment_tool,
    get_skill_knowledge_tool,
    get_technical_tool,
)


class TestMasterTool:
    def test_get_master_list_returns_masters(self):
        tool = get_master_list_tool()
        result = tool.fn()
        assert "masters" in result
        assert result["count"] > 0

    def test_master_list_content(self):
        tool = get_master_list_tool()
        result = tool.fn()
        master_str = " ".join(result["masters"]).lower()
        assert "cathie_wood" in master_str or "buffett" in master_str

    def test_master_analyze_tool_has_required_params(self):
        tool = get_master_analyze_tool()
        assert "stock_code" in tool.required_params
        assert "master_names" in tool.required_params

    def test_master_analyze_handles_unknown_code(self):
        tool = get_master_analyze_tool()
        result = tool.fn(stock_code="999999", master_names=["cathie_wood"])
        assert "results" in result


class TestSkillTool:
    def test_skill_knowledge_tool_has_params(self):
        tool = get_skill_knowledge_tool()
        assert "skill_name" in tool.required_params

    def test_skill_knowledge_handles_unknown_skill(self):
        tool = get_skill_knowledge_tool()
        result = tool.fn(skill_name="nonexistent_skill_xyz")
        assert "error" in result or "knowledge" in result


class TestFinancialsTool:
    """Tests for get_financials_tool — mock DB to avoid hangs."""

    def test_get_financials_has_required_params(self):
        tool = get_financials_tool()
        assert "stock_code" in tool.required_params

    def test_get_financials_handles_unknown_code(self, monkeypatch):
        from services.agents import tool_registry

        monkeypatch.setattr(
            tool_registry,
            "DatabaseBackedDataBus",
            lambda: type("MockBus", (), {"get_stock_basic": lambda self, code: None})(),
        )
        monkeypatch.setattr(
            tool_registry,
            "get_session",
            lambda: type(
                "MockSession",
                (),
                {
                    "query": lambda self, *a: type(
                        "Q",
                        (),
                        {
                            "filter_by": lambda self, **kw: type(
                                "R", (), {"first": lambda self: None}
                            )()
                        },
                    )(),
                    "close": lambda self: None,
                },
            )(),
        )
        tool = get_financials_tool()
        result = tool.fn(stock_code="999999")
        assert isinstance(result, dict)

    def test_get_financials_returns_error_or_data(self, monkeypatch):
        from services.agents import tool_registry

        monkeypatch.setattr(
            tool_registry,
            "DatabaseBackedDataBus",
            lambda: type("MockBus", (), {"get_stock_basic": lambda self, code: None})(),
        )
        monkeypatch.setattr(
            tool_registry,
            "get_session",
            lambda: type(
                "MockSession",
                (),
                {
                    "query": lambda self, *a: type(
                        "Q",
                        (),
                        {
                            "filter_by": lambda self, **kw: type(
                                "R", (), {"first": lambda self: None}
                            )()
                        },
                    )(),
                    "close": lambda self: None,
                },
            )(),
        )
        tool = get_financials_tool()
        result = tool.fn(stock_code="INVALID")
        assert "error" in result or "financials" in result


class TestTechnicalTool:
    """Tests for get_technical_tool — mock DB to avoid hangs."""

    def test_get_technical_has_required_params(self):
        tool = get_technical_tool()
        assert "stock_code" in tool.required_params

    def test_get_technical_handles_unknown_code(self, monkeypatch):
        from services.agents import tool_registry

        monkeypatch.setattr(
            tool_registry,
            "DatabaseBackedDataBus",
            lambda: type("MockBus", (), {"get_kline": lambda self, code, days=90: []})(),
        )
        tool = get_technical_tool()
        result = tool.fn(stock_code="999999")
        assert isinstance(result, dict)

    def test_get_technical_days_default(self, monkeypatch):
        from services.agents import tool_registry

        monkeypatch.setattr(
            tool_registry,
            "DatabaseBackedDataBus",
            lambda: type("MockBus", (), {"get_kline": lambda self, code, days=90: []})(),
        )
        tool = get_technical_tool()
        result = tool.fn(stock_code="999999", days=5)
        assert isinstance(result, dict)


class TestSentimentTool:
    """Tests for get_sentiment_tool — mock network to avoid hangs."""

    def test_get_sentiment_has_required_params(self):
        tool = get_sentiment_tool()
        assert "stock_code" in tool.required_params

    def test_get_sentiment_returns_dict(self, monkeypatch):
        from services.agents import tool_registry

        monkeypatch.setattr(tool_registry, "get_adapter", lambda name: None)
        tool = get_sentiment_tool()
        result = tool.fn(stock_code="999999")
        assert isinstance(result, dict)
        assert "hot_score" in result


class TestDefaultTools:
    def test_create_default_tools_returns_all(self):
        tools = create_default_tools()
        assert len(tools) >= 6

    def test_default_tools_have_unique_names(self):
        tools = create_default_tools()
        names = [t.name for t in tools]
        assert len(names) == len(set(names))
