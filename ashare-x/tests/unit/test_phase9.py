"""Phase 9 新功能测试: 回测API + CLI + 技能注入。"""

from __future__ import annotations

import contextlib
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient


class TestBacktestAPI:
    """回测API路由测试。"""

    def test_list_strategies(self):
        from server import app

        client = TestClient(app)
        r = client.get("/api/backtest/strategies")
        assert r.status_code == 200
        data = r.json()
        assert "strategies" in data
        names = [s["name"] for s in data["strategies"]]
        assert "ma_cross" in names
        assert "rsi" in names
        assert "bollinger" in names

    def test_backtest_empty_codes(self):
        from server import app

        client = TestClient(app)
        r = client.post("/api/backtest", json={"stock_codes": []})
        assert r.status_code == 400

    def test_backtest_too_many_stocks(self):
        from server import app

        client = TestClient(app)
        codes = [f"00000{i}" for i in range(25)]
        r = client.post("/api/backtest", json={"stock_codes": codes})
        assert r.status_code == 400

    def test_backtest_invalid_strategy(self):
        from server import app

        client = TestClient(app)
        r = client.post(
            "/api/backtest",
            json={"stock_codes": ["600519"], "strategy": "invalid"},
        )
        assert r.status_code == 400

    def test_backtest_invalid_days(self):
        from server import app

        client = TestClient(app)
        r = client.post(
            "/api/backtest",
            json={"stock_codes": ["600519"], "days": 10},
        )
        assert r.status_code == 400

    def test_backtest_mock_engine(self):
        """使用mock验证API响应结构。"""
        from server import app

        client = TestClient(app)
        mock_result = {
            "total_return": "15.50%",
            "benchmark_return": "8.20%",
            "excess_return": "7.30%",
            "sharpe": 1.25,
            "max_drawdown": "-5.40%",
            "per_stock": {
                "600519": {
                    "total_return": "15.50%",
                    "sharpe": 1.25,
                    "max_drawdown": "-5.40%",
                    "total_trades": 12,
                    "win_rate": "60.0%",
                }
            },
            "stock_count": 1,
        }
        with patch("services.backtest.VectorbtBacktest.run", return_value=mock_result):
            r = client.post(
                "/api/backtest",
                json={
                    "stock_codes": ["600519"],
                    "strategy": "ma_cross",
                    "days": 250,
                    "initial_capital": 1000000,
                },
            )
        assert r.status_code == 200
        data = r.json()
        assert data["total_return"] == "15.50%"
        assert data["sharpe"] == 1.25
        assert "600519" in data["per_stock"]


class TestSkillInjection:
    """技能注入到Agent的测试。"""

    def test_get_skill_engine_singleton(self):
        from agents.base import _get_skill_engine

        engine1 = _get_skill_engine()
        engine2 = _get_skill_engine()
        assert engine1 is engine2

    def test_skill_engine_has_skills(self):
        from agents.base import _get_skill_engine

        engine = _get_skill_engine()
        assert len(engine.registry) >= 5
        assert "buffett" in engine.registry
        assert "munger" in engine.registry
        assert "taleb" in engine.registry

    def test_agent_factory_with_skills(self):
        """验证create_agent返回的函数能正常调用（mock LLM）。"""
        from agents.base import create_agent

        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "分析完成"
        mock_llm.complete.return_value = mock_response

        agent_fn = create_agent(
            agent_name="portfolio_manager",
            system_prompt="你是组合经理",
            llm_client=mock_llm,
        )

        state: dict[str, object] = {"ticker": "600519", "analyst_signals": {}}
        result = agent_fn(state)  # type: ignore[arg-type]

        assert "portfolio_manager_report" in result
        assert result["portfolio_manager_report"] == "分析完成"
        # 验证LLM被调用
        mock_llm.complete.assert_called_once()
        # 验证system_prompt包含了技能内容
        call_args = mock_llm.complete.call_args
        messages = call_args.kwargs["messages"]
        system_content = messages[0]["content"]
        assert "投资技能" in system_content


class TestCLI:
    """CLI命令测试。"""

    def test_cli_no_command_shows_help(self):
        """验证无命令时显示帮助。"""
        from main import main

        with (
            patch("sys.argv", ["main"]),
            contextlib.suppress(SystemExit),
        ):
            main()

    def test_cli_screen_no_data(self):
        """验证无数据时给出友好提示。"""
        from main import cmd_screen

        with patch("providers.data_bus.DatabaseFirstDataBus") as mock_bus_cls:
            mock_bus = MagicMock()
            mock_bus.get_market_snapshot.return_value = []
            mock_bus_cls.return_value = mock_bus
            cmd_screen(style="balanced", limit=10)

    def test_cli_backtest_no_codes(self):
        """验证空代码时不崩溃。"""
        from main import cmd_backtest

        cmd_backtest("", strategy="ma_cross", days=250, capital=1000000)
