"""trading_graph 工作流结构 + 基础运行测试。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from core.llm_client import LLMResponse
from core.state import make_initial_state
from graph.trading_graph import build_trading_graph


@pytest.fixture
def mock_llm():
    """返回一个总是返回固定JSON的LLM客户端。"""
    llm = MagicMock()
    llm.complete.return_value = LLMResponse(
        content='{"signal": "neutral", "confidence": 60, "reasoning": "test"}',
        tokens=50,
        model="test",
    )
    return llm


@pytest.fixture
def no_external_calls():
    """屏蔽所有外部调用，避免图执行时访问网络或磁盘。"""
    fake_engine = MagicMock()
    fake_engine.get_for_agent.return_value = []
    fake_gatherers = {
        "technical": lambda _t: "MA5=12, MA20=11, MACD=0.5, RSI14=55",
        "fundamentals": lambda _t: "PE: 20, PB: 3, ROE: 15",
        "news": lambda _t: "[2026-06-23] test news",
        "sentiment": lambda _t: "主力净流入: 1000000, 主力净占比: 8",
    }
    with (
        patch("agents.base._get_skill_engine", return_value=fake_engine),
        patch("agents.base._DATA_GATHERERS", fake_gatherers),
        patch("agents.base._gather_memory", return_value=""),
        patch("agents.base._gather_rag_context", return_value=""),
        patch("agents.base._gather_short_term_memory", return_value=""),
    ):
        yield


class TestTradingGraphStructure:
    def test_graph_compiles(self, mock_llm):
        graph = build_trading_graph(mock_llm)
        assert graph is not None

    def test_graph_has_core_nodes(self, mock_llm):
        graph = build_trading_graph(mock_llm)
        nodes = graph.nodes
        expected = {
            "market_analyst",
            "fundamentals_analyst",
            "news_analyst",
            "sentiment_analyst",
            "bull_researcher",
            "bear_researcher",
            "research_manager",
            "trader",
            "aggressive_analyst",
            "conservative_analyst",
            "neutral_analyst",
            "portfolio_manager",
        }
        missing = expected - set(nodes)
        assert not missing, f"缺少节点: {missing}"

    def test_graph_has_master_nodes(self, mock_llm):
        graph = build_trading_graph(mock_llm)
        assert "master_selector" in graph.nodes
        assert "master_review" in graph.nodes


class TestTradingGraphInvoke:
    def test_invoke_fast_mode(self, mock_llm, no_external_calls):
        graph = build_trading_graph(mock_llm)
        state = make_initial_state(ticker="600519", mode="fast")
        state["config"] = {
            "debate": {
                "investment": {"max_rounds": 1},
                "risk": {"max_rounds": 1},
            },
            "features": {"enable_masters": False},
        }
        final_state = graph.invoke(state, config={"configurable": {"thread_id": "test-fast"}})

        assert final_state.get("ticker") == "600519"
        assert "market_analyst_report" in final_state
        assert "portfolio_manager_report" in final_state
        assert final_state.get("investment_debate_rounds", 0) >= 1

    def test_invoke_with_masters(self, mock_llm, no_external_calls):
        from graph.trading_graph import route_after_pm

        state = make_initial_state(ticker="000001", mode="fast")
        state["config"] = {"features": {"enable_masters": True}}
        assert route_after_pm(state) == "with_masters"


class TestMasterNodes:
    """大师节点独立测试（避免完整 invoke 加载大量大师模块导致超时）。"""

    def test_master_selector_returns_masters(self, mock_llm):
        from agents.masters.review import create_master_selector

        state = make_initial_state(ticker="000001")
        state["fundamentals"] = {
            "pe_ratio": 12,
            "roe": 18,
            "volatility": 0.25,
            "revenue_yoy": 0.15,
        }
        selector = create_master_selector(mock_llm)
        result = selector(state)

        assert "selected_masters" in result
        assert isinstance(result["selected_masters"], list)
        assert len(result["selected_masters"]) > 0

    def test_master_review_aggregates_signals(self, mock_llm, no_external_calls):
        from agents.masters.review import create_master_review

        def fake_factory(_llm):
            def agent_fn(_state):
                return {
                    "buffett_report": '{"signal": "bullish", "confidence": 70, "reasoning": "test"}'
                }
            return agent_fn

        state = make_initial_state(ticker="000001")
        state["selected_masters"] = ["buffett"]
        state["market_analyst_report"] = "market"
        state["fundamentals_analyst_report"] = "fundamentals"
        state["portfolio_manager_report"] = "pm"

        with patch(
            "agents.masters.review._MASTER_FACTORIES",
            {"buffett": fake_factory},
        ):
            review = create_master_review(mock_llm)
            result = review(state)

        assert "master_signals" in result
        assert result["master_signals"]["buffett"]["signal"] == "bullish"
        assert "master_review_report" in result


class TestQuantSignals:
    def test_technical_signal_bullish(self):
        from agents.analysts.quant_signals import compute_technical_signal

        sig = compute_technical_signal({
            "ma5": 12.0, "ma20": 11.0, "ma60": 10.0,
            "macd": 0.5, "rsi_14": 55.0,
        })
        assert sig["signal"] == "bullish"
        assert sig["confidence"] > 50

    def test_fundamental_signal_bearish(self):
        from agents.analysts.quant_signals import compute_fundamental_signal

        sig = compute_fundamental_signal({
            "pe_ratio": 120.0, "pb_ratio": 10.0, "roe": 3.0,
            "revenue_yoy": -20.0, "net_income_yoy": -30.0,
        })
        assert sig["signal"] == "bearish"
        assert sig["confidence"] < 50

    def test_news_signal_empty(self):
        from agents.analysts.quant_signals import compute_news_signal

        sig = compute_news_signal([])
        assert sig["signal"] == "neutral"
        assert sig["confidence"] == 50

    def test_sentiment_signal_with_north_flow(self):
        from agents.analysts.quant_signals import compute_sentiment_signal

        sig = compute_sentiment_signal({
            "fund_flow": {"main_net_inflow": 1000000, "main_net_pct": 8.0},
            "north_flow": 50000,
        })
        assert sig["signal"] == "bullish"
