"""core/state.py 单元测试。"""

from __future__ import annotations

from core.state import AgentState, make_initial_state


class TestInitialState:
    def test_has_empty_containers(self):
        s = make_initial_state()
        assert s["analyst_signals"] == {}
        assert s["debate_messages"] == []
        assert s["messages"] == []
        assert s["errors"] == []
        assert s["mode"] == "full"

    def test_ticker_optional(self):
        assert "ticker" not in make_initial_state()
        s = make_initial_state(ticker="600519")
        assert s["ticker"] == "600519"

    def test_extra_kwargs_merged(self):
        s = make_initial_state(mode="fast", stocks=["000001", "600519"])
        assert s["mode"] == "fast"
        assert s["stocks"] == ["000001", "600519"]


class TestTypedDictShape:
    def test_node_merge_pattern(self):
        """模拟 LangGraph 节点返回值 merge 到 state 的模式。"""
        s = make_initial_state(ticker="600519")
        # 节点返回部分字段
        node_output: AgentState = {"analyst_signals": {"market": {"signal": "bullish"}}}
        s.update(node_output)
        assert s["analyst_signals"]["market"]["signal"] == "bullish"
        # 其他字段不受影响
        assert s["ticker"] == "600519"
        assert s["errors"] == []

    def test_analyst_signal_shape(self):
        sig = {"signal": "neutral", "confidence": 40.0, "reasoning": "数据不足", "agent": "news"}
        s = make_initial_state()
        s["analyst_signals"]["news"] = sig  # type: ignore[index]
        assert s["analyst_signals"]["news"]["confidence"] == 40.0
