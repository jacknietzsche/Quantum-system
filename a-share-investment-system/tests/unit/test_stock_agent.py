"""StockAgent 单元测试 — 提示词结构、工具列表、解析逻辑"""

import json

from services.agents.base_agent import extract_json
from services.agents.stock_agent import STOCK_AGENT_SYSTEM_PROMPT, StockAgent
from services.agents.tool_registry import (
    create_default_tools,
    get_financials_tool,
    get_sentiment_tool,
    get_technical_tool,
)


class TestStockAgentInit:
    def test_agent_creates_with_empty_llm_config(self):
        agent = StockAgent({"base_url": "http://test", "api_key": "test", "model": "test"})
        assert agent.llm_config is not None

    def test_agent_has_default_tools(self):
        agent = StockAgent({"base_url": "http://test", "api_key": "test", "model": "test"})
        assert len(agent.tools) >= 6

    def test_tools_contain_get_financials(self):
        agent = StockAgent({"base_url": "http://test", "api_key": "test", "model": "test"})
        tool_names = [t.name for t in agent.tools]
        assert "get_financials" in tool_names

    def test_tools_contain_get_technical(self):
        agent = StockAgent({"base_url": "http://test", "api_key": "test", "model": "test"})
        tool_names = [t.name for t in agent.tools]
        assert "get_technical" in tool_names

    def test_tools_contain_get_sentiment(self):
        agent = StockAgent({"base_url": "http://test", "api_key": "test", "model": "test"})
        tool_names = [t.name for t in agent.tools]
        assert "get_sentiment" in tool_names

    def test_tools_contain_get_master_list(self):
        agent = StockAgent({"base_url": "http://test", "api_key": "test", "model": "test"})
        tool_names = [t.name for t in agent.tools]
        assert "get_master_list" in tool_names

    def test_tools_contain_master_analyze(self):
        agent = StockAgent({"base_url": "http://test", "api_key": "test", "model": "test"})
        tool_names = [t.name for t in agent.tools]
        assert "master_analyze" in tool_names

    def test_tools_contain_skill_knowledge(self):
        agent = StockAgent({"base_url": "http://test", "api_key": "test", "model": "test"})
        tool_names = [t.name for t in agent.tools]
        assert "skill_knowledge" in tool_names

    def test_all_tools_have_unique_names(self):
        tools = create_default_tools()
        names = [t.name for t in tools]
        assert len(names) == len(set(names))

    def test_all_tools_have_descriptions(self):
        tools = create_default_tools()
        for tool in tools:
            assert tool.description, f"{tool.name} missing description"


class TestStockAgentParse:
    def test_extract_json_plain(self):
        result = extract_json('{"overall_score": 85, "signal": "买入"}')
        assert "overall_score" in result

    def test_extract_json_with_markdown_fence(self):
        text = '```json\n{"overall_score": 70, "signal": "持有"}\n```'
        result = extract_json(text)
        assert '"overall_score": 70' in result

    def test_extract_json_no_braces_returns_raw(self):
        result = extract_json("不是JSON内容")
        assert result == "不是JSON内容"

    def test_extract_json_nested_braces(self):
        text = '{"data": {"score": 90, "signal": "买入"}}'
        result = extract_json(text)
        assert '"score": 90' in result

    def test_stock_agent_prompt_has_data_sources(self):
        assert "data_sources" in STOCK_AGENT_SYSTEM_PROMPT

    def test_stock_agent_prompt_has_expected_fields(self):
        for field in ["overall_score", "signal", "reasoning", "masters_used"]:
            assert field in STOCK_AGENT_SYSTEM_PROMPT

    def test_stock_agent_prompt_lists_tools(self):
        for tool in [
            "get_financials",
            "get_technical",
            "get_sentiment",
            "get_master_list",
            "master_analyze",
            "skill_knowledge",
        ]:
            assert tool in STOCK_AGENT_SYSTEM_PROMPT


class TestStockAgentAnalyze:
    def test_analyze_returns_dict_for_real_stock(self, monkeypatch):
        agent = StockAgent({"base_url": "http://test", "api_key": "test", "model": "test"})
        stock = {
            "stock_code": "600519",
            "stock_name": "贵州茅台",
            "price": 1500,
            "pe": 30,
            "pb": 8,
            "roe": 25,
            "market_cap": 20000,
            "turnover_rate": 0.5,
            "change_pct": 1.5,
        }
        mock_content = json.dumps(
            {
                "overall_score": 80,
                "signal": "买入",
                "confidence": "高",
                "masters_used": [],
                "skills_injected": [],
                "data_sources": [],
                "entry": {},
                "stop_loss": "5%",
                "take_profit": "15%",
                "position_size": "中仓",
                "reasoning": "test",
            },
            ensure_ascii=False,
        )
        mock_response = {"content": mock_content, "turns": 1, "finish_reason": "stop"}
        from services.agents import base_agent

        monkeypatch.setattr(
            base_agent.AgentExecutor,
            "run",
            lambda self, prompt, msg: mock_response,
        )
        result = agent.analyze(stock)
        assert isinstance(result, dict)
        assert result.get("stock_code") == "600519"

    def test_analyze_handles_empty_stock(self, monkeypatch):
        agent = StockAgent({"base_url": "http://test", "api_key": "test", "model": "test"})
        mock_content = json.dumps(
            {
                "overall_score": 50,
                "signal": "观望",
                "confidence": "低",
                "reasoning": "no data",
            },
            ensure_ascii=False,
        )
        mock_response = {"content": mock_content, "turns": 1, "finish_reason": "stop"}
        from services.agents import base_agent

        monkeypatch.setattr(
            base_agent.AgentExecutor,
            "run",
            lambda self, prompt, msg: mock_response,
        )
        result = agent.analyze({})
        assert isinstance(result, dict)


class TestToolRegistryDataTools:
    def test_get_financials_return_format(self, monkeypatch):
        from services.agents import tool_registry

        monkeypatch.setattr(
            tool_registry,
            "DatabaseBackedDataBus",
            lambda: type(
                "MockBus",
                (),
                {
                    "get_stock_basic": lambda self, code: None,
                },
            )(),
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
                                "R",
                                (),
                                {
                                    "first": lambda self: None,
                                },
                            )(),
                        },
                    )(),
                    "close": lambda self: None,
                },
            )(),
        )
        tool = get_financials_tool()
        result = tool.fn(stock_code="999999")
        assert "stock_code" in result
        assert result["stock_code"] == "999999"

    def test_get_technical_return_format(self, monkeypatch):
        from services.agents import tool_registry

        monkeypatch.setattr(
            tool_registry,
            "DatabaseBackedDataBus",
            lambda: type(
                "MockBus",
                (),
                {
                    "get_kline": lambda self, code, days=90: [],
                },
            )(),
        )
        tool = get_technical_tool()
        result = tool.fn(stock_code="999999", days=5)
        assert "stock_code" in result

    def test_get_sentiment_return_format(self, monkeypatch):
        from services.agents import tool_registry

        monkeypatch.setattr(tool_registry, "get_adapter", lambda name: None)
        tool = get_sentiment_tool()
        result = tool.fn(stock_code="999999")
        assert "hot_score" in result
        assert "lhb" in result
