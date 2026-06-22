"""测试 Tool calling 循环"""

import pytest

from services.agents.base_agent import AgentTool


def test_tool_creation():
    """测试工具创建"""
    tool = AgentTool(
        name="calculator",
        description="Simple calculator",
        parameters={"a": "number", "b": "number", "op": "string"},
        required_params=["a", "b", "op"],
        fn=lambda a, b, op: {"result": a + b if op == "add" else a - b},
    )
    assert tool.name == "calculator"
    assert tool.fn(2, 2, "add") == {"result": 4}


def test_to_openai_tool():
    """测试 OpenAI 工具格式转换"""
    tool = AgentTool(
        name="test_tool",
        description="A test tool",
        parameters={"param1": "string"},
        required_params=["param1"],
        fn=lambda param1: {"result": param1},
    )
    ot = tool.to_openai_tool()
    assert ot["type"] == "function"
    assert ot["function"]["name"] == "test_tool"


def test_tool_error_handling():
    """测试工具异常处理"""
    tool = AgentTool(
        name="failing",
        description="A tool that fails",
        parameters={},
        fn=lambda: 1 / 0,
    )
    with pytest.raises(ZeroDivisionError):
        tool.fn()
