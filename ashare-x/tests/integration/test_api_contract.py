"""前后端API契约测试 — 验证每个端点返回的字段与前端期望完全匹配。

此测试文件是前后端接口的"活文档"：任何字段变更都会立即暴露。
前端文件参考: electron/src/pages/*.jsx 中实际使用的字段。

测试策略:
  - 使用 TestClient（不需要运行真实服务器）
  - mock 所有 service 层依赖（不依赖网络/LLM/真实数据）
  - 验证: status_code + 字段存在性 + 字段类型
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client():
    """TestClient with fresh app state."""
    from server import app

    return TestClient(app)


@pytest.fixture(autouse=True)
def _reset_config():
    """Reset Config singleton before each test."""
    from core.config import Config

    Config.reset()
    yield
    Config.reset()


# ── Helper ──────────────────────────────────────────────────────────


def assert_fields(data: dict, fields: list[str]) -> None:
    """Assert that all specified fields exist in the dict."""
    missing = [f for f in fields if f not in data]
    assert not missing, f"Missing fields: {missing}. Got keys: {list(data.keys())}"


# ── 1. Health ───────────────────────────────────────────────────────
# Frontend: Dashboard.jsx — expects {status, version, data_count, reports}


@pytest.mark.integration
class TestHealthContract:
    def test_health_returns_all_frontend_fields(self, client: TestClient):
        r = client.get("/api/health")
        assert r.status_code == 200
        data = r.json()
        assert_fields(data, ["status", "version", "data_count", "reports"])
        assert isinstance(data["status"], str)
        assert isinstance(data["version"], str)
        assert isinstance(data["data_count"], int)
        assert isinstance(data["reports"], int)


# ── 2. Settings ─────────────────────────────────────────────────────
# Frontend: Settings.jsx — uses {llm_provider, api_key, monthly_budget_rmb,
#   email_sender, email_password, email_recipient, has_api_key, has_email_password}


@pytest.mark.integration
class TestSettingsContract:
    def test_get_settings_returns_frontend_fields(self, client: TestClient):
        r = client.get("/api/settings")
        assert r.status_code == 200
        data = r.json()
        assert_fields(
            data,
            [
                "llm_provider",
                "api_key",
                "monthly_budget_rmb",
                "email_sender",
                "email_password",
                "email_recipient",
                "has_api_key",
                "has_email_password",
            ],
        )
        assert isinstance(data["llm_provider"], str)
        assert isinstance(data["monthly_budget_rmb"], int)
        assert isinstance(data["has_api_key"], bool)
        assert isinstance(data["has_email_password"], bool)

    def test_update_settings_returns_status_ok(self, client: TestClient):
        r = client.put(
            "/api/settings",
            json={
                "llm_provider": "deepseek",
                "monthly_budget_rmb": 200,
                "email_sender": "",
                "email_password": "",
                "email_recipient": "",
            },
        )
        assert r.status_code == 200
        data = r.json()
        assert_fields(data, ["status", "message"])
        assert data["status"] == "ok"


# ── 3. Screening ────────────────────────────────────────────────────
# Frontend: Screening.jsx — uses stocks[].{stock_code, stock_name, score, rank,
#   factors.{value, growth, momentum, quality}}


@pytest.mark.integration
class TestScreeningContract:
    def test_screening_returns_stock_fields(self, client: TestClient):
        mock_stocks = [
            {
                "stock_code": "600519",
                "stock_name": "贵州茅台",
                "score": 85.5,
                "value_score": 90,
                "growth_score": 80,
                "momentum_score": 75,
                "quality_score": 95,
            }
        ]
        with (
            patch("providers.data_bus.DatabaseFirstDataBus") as mock_bus_cls,
            patch("services.screening.rank_stocks", return_value=mock_stocks),
            patch("sqlite3.connect") as mock_connect,
        ):
            mock_bus = MagicMock()
            mock_bus.db_path = ":memory:"
            mock_bus.get_stock_info.return_value = {}
            mock_bus_cls.return_value = mock_bus

            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_cursor.fetchall.return_value = [("600519", "贵州茅台")]
            mock_conn.execute.return_value = mock_cursor
            mock_connect.return_value = mock_conn

            r = client.get("/api/screening?style=balanced&limit=10")
            assert r.status_code == 200
            data = r.json()
            assert_fields(data, ["stocks", "style"])
            assert isinstance(data["stocks"], list)
            if data["stocks"]:
                stock = data["stocks"][0]
                assert_fields(
                    stock,
                    ["stock_code", "stock_name", "score", "rank", "factors"],
                )
                assert_fields(
                    stock["factors"],
                    ["value", "growth", "momentum", "quality"],
                )


# ── 4. Backtest ─────────────────────────────────────────────────────
# Frontend: Backtest.jsx — uses {total_return, annualized_return,
#   max_drawdown, sharpe, trades}


@pytest.mark.integration
class TestBacktestContract:
    def test_strategies_returns_name_and_description(self, client: TestClient):
        r = client.get("/api/backtest/strategies")
        assert r.status_code == 200
        data = r.json()
        assert_fields(data, ["strategies"])
        assert isinstance(data["strategies"], list)
        for s in data["strategies"]:
            assert_fields(s, ["name", "description"])

    def test_backtest_returns_frontend_fields(self, client: TestClient):
        mock_result = {
            "total_return": "15.23%",
            "benchmark_return": "10.00%",
            "excess_return": "5.23%",
            "sharpe": 1.23,
            "max_drawdown": "-5.67%",
            "per_stock": {
                "600519": {
                    "total_return": "15.23%",
                    "sharpe": 1.5,
                    "max_drawdown": "-5.67%",
                    "total_trades": 10,
                    "win_rate": "60.0%",
                }
            },
            "stock_count": 1,
        }
        with patch("services.backtest.VectorbtBacktest") as mock_cls:
            mock_engine = MagicMock()
            mock_engine.run.return_value = mock_result
            mock_cls.return_value = mock_engine

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
            # Frontend expects these fields
            assert_fields(
                data,
                ["total_return", "annualized_return", "max_drawdown", "sharpe", "trades"],
            )
            assert isinstance(data["trades"], list)
            assert isinstance(data["sharpe"], (int, float))

    def test_backtest_validation_empty_codes(self, client: TestClient):
        r = client.post(
            "/api/backtest",
            json={"stock_codes": [], "strategy": "ma_cross", "days": 250},
        )
        assert r.status_code == 400

    def test_backtest_validation_invalid_strategy(self, client: TestClient):
        r = client.post(
            "/api/backtest",
            json={"stock_codes": ["600519"], "strategy": "invalid", "days": 250},
        )
        assert r.status_code == 400


# ── 5. Analysis ─────────────────────────────────────────────────────
# Frontend: Analysis.jsx — POST expects {job_id, ticker, status}
#   GET expects {job_id, ticker, status, progress, result, agents_status}


@pytest.mark.integration
class TestAnalysisContract:
    def test_start_analysis_returns_job_fields(self, client: TestClient):
        # Mock _run_analysis to prevent real LangGraph execution
        with patch("api.routes.analysis._run_analysis", new_callable=AsyncMock):
            r = client.post("/api/analysis", json={"ticker": "600519"})
            assert r.status_code == 200
            data = r.json()
            assert_fields(data, ["job_id", "ticker", "status"])
            assert isinstance(data["job_id"], str)
            assert data["ticker"] == "600519"
            assert data["status"] == "running"

    def test_get_analysis_returns_job_without_log_queue(self, client: TestClient):
        # Start a job with mocked background task
        with patch("api.routes.analysis._run_analysis", new_callable=AsyncMock):
            r1 = client.post("/api/analysis", json={"ticker": "600519"})
            job_id = r1.json()["job_id"]

            # GET must not include log_queue (asyncio.Queue — not serializable)
            r2 = client.get(f"/api/analysis/{job_id}")
            assert r2.status_code == 200
            data = r2.json()
            assert "log_queue" not in data
            assert_fields(data, ["job_id", "ticker", "status", "progress"])

    def test_analysis_not_found(self, client: TestClient):
        assert client.get("/api/analysis/nonexistent").status_code == 404

    def test_analysis_missing_ticker_validation(self, client: TestClient):
        assert client.post("/api/analysis", json={}).status_code == 422


# ── 6. Data Management ──────────────────────────────────────────────
# Frontend: Data.jsx — uses /data/stats {kline_count, stock_count, db_size}
#   /data/health {status, message, sources[].{name, status}}
#   /data/kline {code, kline[].{date,open,high,low,close,volume}, total}


@pytest.mark.integration
class TestDataContract:
    def test_stats_returns_frontend_fields(self, client: TestClient):
        r = client.get("/api/data/stats")
        assert r.status_code == 200
        data = r.json()
        assert_fields(data, ["kline_count", "stock_count", "db_size"])
        assert isinstance(data["kline_count"], int)
        assert isinstance(data["stock_count"], int)
        assert isinstance(data["db_size"], str)

    def test_health_returns_source_fields(self, client: TestClient):
        # Mock DatabaseFirstDataBus to prevent real DB/file access
        with (
            patch("providers.data_bus.DatabaseFirstDataBus") as mock_bus_cls,
            patch("importlib.import_module") as mock_import,
        ):
            mock_bus = MagicMock()
            mock_bus.db_path = ":memory:"
            mock_bus_cls.return_value = mock_bus

            # Mock adapter modules so test_connect doesn't hit network
            mock_mod = MagicMock()
            mock_adapter_cls = MagicMock()
            mock_adapter = MagicMock()
            mock_adapter.test_connect.return_value = True
            mock_adapter_cls.return_value = mock_adapter
            mock_mod.TencentAdapter = mock_adapter_cls
            mock_mod.SinaAdapter = mock_adapter_cls
            mock_mod.AKShareAdapter = mock_adapter_cls
            mock_mod.YFinanceAdapter = mock_adapter_cls
            mock_import.return_value = mock_mod

            r = client.get("/api/data/health")
            assert r.status_code == 200
            data = r.json()
            assert_fields(data, ["status", "message", "sources"])
            assert isinstance(data["sources"], list)
            for s in data["sources"]:
                assert_fields(s, ["name", "status", "last_update", "record_count"])

    def test_kline_returns_candle_fields(self, client: TestClient):
        mock_kline = [
            {
                "trade_date": "2024-01-01",
                "open": 100.0,
                "high": 105.0,
                "low": 98.0,
                "close": 103.0,
                "volume": 50000.0,
            }
        ]
        with patch("providers.data_bus.DatabaseFirstDataBus") as mock_bus_cls:
            mock_bus = MagicMock()
            mock_bus.get_kline.return_value = mock_kline
            mock_bus_cls.return_value = mock_bus
            r = client.get("/api/data/kline?code=600519&days=5")
            assert r.status_code == 200
            data = r.json()
            assert_fields(data, ["code", "kline", "total"])
            assert isinstance(data["kline"], list)
            if data["kline"]:
                candle = data["kline"][0]
                assert_fields(
                    candle, ["date", "open", "high", "low", "close", "volume"]
                )

    def test_refresh_returns_job_id(self, client: TestClient):
        """POST /data/refresh should return job_id immediately (async job)."""
        with patch("api.routes.data._run_refresh", new_callable=AsyncMock):
            r = client.post("/api/data/refresh?code=600519")
            assert r.status_code == 200
            data = r.json()
            assert_fields(data, ["job_id", "status"])
            assert data["status"] == "running"
            assert isinstance(data["job_id"], str)

    def test_refresh_status_not_found(self, client: TestClient):
        assert client.get("/api/data/refresh/nonexistent").status_code == 404


# ── 7. Reports ──────────────────────────────────────────────────────
# Frontend: Reports.jsx — uses reports[].{id, ticker, action, created_at,
#   confidence, position_pct, thesis}


@pytest.mark.integration
class TestReportsContract:
    def test_reports_returns_list_fields(self, client: TestClient):
        with patch("services.report.ReportGenerator") as mock_cls:
            mock_gen = MagicMock()
            # get_recent_reports returns a list (route wraps it)
            mock_gen.get_recent_reports.return_value = [
                {
                    "id": "rpt-001",
                    "ticker": "600519",
                    "action": "Buy",
                    "created_at": "2024-01-01",
                    "confidence": 85,
                    "position_pct": 10,
                    "thesis": "Strong fundamentals",
                }
            ]
            mock_cls.return_value = mock_gen

            r = client.get("/api/reports?limit=50")
            assert r.status_code == 200
            data = r.json()
            assert_fields(data, ["reports", "total"])
            assert isinstance(data["reports"], list)
            if data["reports"]:
                report = data["reports"][0]
                assert_fields(
                    report,
                    ["id", "ticker", "action", "created_at"],
                )


# ── 8. Trading Plan ─────────────────────────────────────────────────
# Frontend: TradingPlan.jsx — uses /today {ok, plan?.{date, market_state,
#   summary, actions[].{action, stock_code}}}
#   /history {ok, history[].{date, actions}}
#   POST /run {job_id, status}


@pytest.mark.integration
class TestTradingPlanContract:
    def test_today_returns_ok_and_plan(self, client: TestClient):
        with patch("services.daily_plan.DailyPlanGenerator") as mock_cls:
            mock_gen = MagicMock()
            mock_gen.get_today_plan.return_value = {
                "date": "2024-01-01",
                "market_state": "BULL",
                "summary": "Market looks good",
                "actions": [
                    {
                        "action": "INITIAL_BUY",
                        "stock_code": "600519",
                        "stock_name": "贵州茅台",
                        "confidence": 85,
                        "reasoning": "Strong buy signal",
                    }
                ],
            }
            mock_cls.return_value = mock_gen

            r = client.get("/api/trading-plan/today")
            assert r.status_code == 200
            data = r.json()
            assert "ok" in data
            if data.get("ok") and data.get("plan"):
                plan = data["plan"]
                assert_fields(plan, ["date", "market_state", "summary", "actions"])
                assert isinstance(plan["actions"], list)
                if plan["actions"]:
                    action = plan["actions"][0]
                    assert_fields(action, ["action", "stock_code"])

    def test_history_returns_list(self, client: TestClient):
        with patch("services.daily_plan.DailyPlanGenerator") as mock_cls:
            mock_gen = MagicMock()
            mock_gen.get_plan_history.return_value = [
                {"date": "2024-01-01", "actions": []}
            ]
            mock_cls.return_value = mock_gen

            r = client.get("/api/trading-plan/history?limit=10")
            assert r.status_code == 200
            data = r.json()
            assert "ok" in data
            if data.get("ok"):
                assert "history" in data
                assert isinstance(data["history"], list)

    def test_run_plan_returns_job(self, client: TestClient):
        with patch("services.daily_plan.DailyPlanGenerator") as mock_cls:
            mock_gen = MagicMock()
            mock_gen.generate.return_value = {"date": "2024-01-01", "actions": []}
            mock_cls.return_value = mock_gen

            r = client.post("/api/trading-plan/run", json={"fast_mode": True})
            assert r.status_code == 200
            data = r.json()
            assert_fields(data, ["job_id", "status"])


# ── 9. Portfolio ────────────────────────────────────────────────────
# Frontend: TradingPlan.jsx — uses /portfolio/rebalance {market_state,
#   position_cap, operations, message}


@pytest.mark.integration
class TestPortfolioContract:
    def test_rebalance_returns_fields(self, client: TestClient):
        with patch("services.market_perception.get_market_state") as mock_state:
            mock_state.return_value = {"state": "BULL", "position_cap": 0.3}
            r = client.post("/api/portfolio/rebalance")
            assert r.status_code == 200
            data = r.json()
            # Frontend checks for error first, then uses these fields
            if "error" not in data:
                assert_fields(
                    data, ["market_state", "position_cap", "operations", "message"]
                )

    def test_get_portfolio_returns_holdings(self, client: TestClient):
        r = client.get("/api/portfolio")
        assert r.status_code == 200
        data = r.json()
        assert_fields(data, ["holdings", "total_assets", "cash", "holding_count"])
        assert isinstance(data["holdings"], list)
