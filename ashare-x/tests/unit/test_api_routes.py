"""API 路由层单元测试。

使用 FastAPI TestClient 覆盖所有 /api 端点，外部依赖全部 mock。
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """构造已禁用 lifespan 初始化的 TestClient。"""
    # 阻止 lifespan 里初始化真实数据库与数据总线
    monkeypatch.setattr("db.engine.init_db", lambda: None)
    monkeypatch.setattr(
        "providers.data_bus.DatabaseFirstDataBus",
        lambda *args, **kwargs: MagicMock(),
    )

    from server import app

    return TestClient(app)


class TestHealth:
    def test_health(self, client: TestClient):
        resp = client.get("/api/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


class TestAnalysisRoutes:
    @pytest.fixture()
    def mock_run(self, monkeypatch: pytest.MonkeyPatch):
        """把分析后台任务替换为立即完成的版本。"""
        from api.routes import analysis

        async def fake_run(job_id: str, ticker: str, fast_mode: bool, enable_masters: bool):
            job = analysis._jobs[job_id]
            job["progress"] = 100
            job["status"] = "completed"
            job["result"] = {"ticker": ticker, "action": "Buy"}

        monkeypatch.setattr(analysis, "_run_analysis", fake_run)

    def test_start_analysis(self, client: TestClient, mock_run):
        resp = client.post("/api/analysis", json={"ticker": "600519"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["ticker"] == "600519"
        assert data["status"] == "running"

    def test_get_analysis(self, client: TestClient, mock_run):
        created = client.post("/api/analysis", json={"ticker": "000001"}).json()
        resp = client.get(f"/api/analysis/{created['job_id']}")
        assert resp.status_code == 200
        assert resp.json()["ticker"] == "000001"

    def test_get_analysis_not_found(self, client: TestClient):
        resp = client.get("/api/analysis/no-such-id")
        assert resp.status_code == 404

    def test_cancel_analysis(self, client: TestClient, mock_run):
        created = client.post("/api/analysis", json={"ticker": "000001"}).json()
        resp = client.delete(f"/api/analysis/{created['job_id']}")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    def test_cancel_analysis_not_found(self, client: TestClient):
        resp = client.delete("/api/analysis/no-such-id")
        assert resp.status_code == 404

    def test_stream_analysis(self, client: TestClient, mock_run):
        created = client.post("/api/analysis", json={"ticker": "000001"}).json()
        resp = client.get(f"/api/stream/{created['job_id']}", headers={"Accept": "text/event-stream"})
        assert resp.status_code == 200
        text = resp.text
        assert "event: progress" in text
        assert "event: done" in text

    def test_stream_analysis_not_found(self, client: TestClient):
        resp = client.get("/api/stream/no-such-id")
        assert resp.status_code == 404


class TestBacktestRoutes:
    @pytest.fixture()
    def mock_backtest(self, monkeypatch: pytest.MonkeyPatch):
        from services import backtest as bt_mod

        def fake_run(self, *, stock_codes, strategy, days):
            return {
                "stock_codes": stock_codes,
                "strategy": strategy,
                "total_return": 0.1,
            }

        monkeypatch.setattr(bt_mod.VectorbtBacktest, "run", fake_run)

    def test_list_strategies(self, client: TestClient):
        resp = client.get("/api/backtest/strategies")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["strategies"]) == 3
        names = {s["name"] for s in data["strategies"]}
        assert names == {"ma_cross", "rsi", "bollinger"}

    def test_run_backtest(self, client: TestClient, mock_backtest):
        resp = client.post(
            "/api/backtest",
            json={"stock_codes": ["600519"], "strategy": "rsi", "days": 60},
        )
        assert resp.status_code == 200
        assert resp.json()["strategy"] == "rsi"

    def test_run_backtest_empty_codes(self, client: TestClient):
        resp = client.post("/api/backtest", json={"stock_codes": []})
        assert resp.status_code == 400

    def test_run_backtest_too_many_codes(self, client: TestClient):
        resp = client.post("/api/backtest", json={"stock_codes": ["600000"] * 21})
        assert resp.status_code == 400

    def test_run_backtest_invalid_days(self, client: TestClient):
        resp = client.post("/api/backtest", json={"stock_codes": ["600000"], "days": 10})
        assert resp.status_code == 400

    def test_run_backtest_invalid_strategy(self, client: TestClient):
        resp = client.post(
            "/api/backtest",
            json={"stock_codes": ["600000"], "strategy": "unknown"},
        )
        assert resp.status_code == 400


class TestDataRoutes:
    @pytest.fixture()
    def mock_bus(self, monkeypatch: pytest.MonkeyPatch, tmp_path):
        from providers import data_bus as db_mod

        fake_bus = MagicMock()
        fake_bus.db_path = str(tmp_path / "test.db")
        fake_bus.get_kline.return_value = [
            {
                "trade_date": "2026-06-20",
                "open": 1.0,
                "high": 2.0,
                "low": 0.5,
                "close": 1.5,
                "volume": 1000,
            }
        ]
        fake_bus.get_stock_info.return_value = {"stock_name": "Test"}

        monkeypatch.setattr(db_mod, "DatabaseFirstDataBus", lambda: fake_bus)
        return fake_bus

    @pytest.fixture()
    def mock_updater(self, monkeypatch: pytest.MonkeyPatch):
        from services import updater as up_mod

        fake_updater = MagicMock()
        fake_updater.update_single_stock.return_value = {"inserted": 5}
        fake_updater.run_daily_update.return_value = {"inserted": 10}
        fake_updater.incremental_refresh.return_value = {"refreshed": 3}
        monkeypatch.setattr(up_mod, "DailyUpdater", lambda: fake_updater)
        return fake_updater

    def test_get_kline(self, client: TestClient, mock_bus):
        resp = client.get("/api/data/kline?code=600519&days=30")
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == "600519"
        assert len(data["kline"]) == 1

    def test_get_kline_empty(self, client: TestClient, mock_bus):
        mock_bus.get_kline.return_value = []
        resp = client.get("/api/data/kline?code=600519&days=30")
        assert resp.json()["total"] == 0

    def test_refresh_data_single(self, client: TestClient, mock_updater):
        resp = client.post("/api/data/refresh?code=600519")
        assert resp.status_code == 200
        assert resp.json()["code"] == "600519"

    def test_refresh_data_all(self, client: TestClient, mock_updater):
        resp = client.post("/api/data/refresh")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_incremental_refresh(self, client: TestClient, mock_updater):
        resp = client.post("/api/data/incremental-refresh?days=30")
        assert resp.status_code == 200
        assert resp.json()["stats"]["refreshed"] == 3

    def test_get_stats_empty_db(self, client: TestClient, mock_bus):
        resp = client.get("/api/data/stats")
        assert resp.status_code == 200
        assert resp.json()["db_size"] == "0 MB"

    def test_get_stats_with_db(self, client: TestClient, mock_bus, tmp_path):
        import sqlite3

        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE kline_daily (stock_code TEXT, trade_date TEXT)")
        conn.execute("INSERT INTO kline_daily VALUES ('600519', '2026-06-20')")
        conn.commit()
        conn.close()

        resp = client.get("/api/data/stats")
        assert resp.status_code == 200
        assert resp.json()["kline_count"] == 1

    def test_check_health(self, client: TestClient, mock_bus):
        resp = client.get("/api/data/health")
        assert resp.status_code == 200
        data = resp.json()
        assert "sources" in data


class TestPortfolioRoutes:
    def test_get_portfolio_empty(self, client: TestClient, tmp_path, monkeypatch):
        from providers import data_bus as db_mod

        fake_bus = MagicMock()
        fake_bus.db_path = str(tmp_path / "test.db")
        monkeypatch.setattr(db_mod, "DatabaseFirstDataBus", lambda: fake_bus)

        resp = client.get("/api/portfolio")
        assert resp.status_code == 200
        assert resp.json()["holdings"] == []

    def test_get_portfolio_with_holdings(self, client: TestClient, tmp_path, monkeypatch):
        import sqlite3

        from providers import data_bus as db_mod

        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute(
            "CREATE TABLE portfolio ("
            "stock_code TEXT, stock_name TEXT, shares REAL, cost_price REAL, current_price REAL)"
        )
        conn.execute("INSERT INTO portfolio VALUES ('600519', '茅台', 100, 1000, 1100)")
        conn.commit()
        conn.close()

        fake_bus = MagicMock()
        fake_bus.db_path = str(db_path)
        monkeypatch.setattr(db_mod, "DatabaseFirstDataBus", lambda: fake_bus)

        resp = client.get("/api/portfolio")
        assert resp.status_code == 200
        assert len(resp.json()["holdings"]) == 1

    def test_rebalance(self, client: TestClient, monkeypatch):
        from services import market_perception as mp_mod

        monkeypatch.setattr(mp_mod, "get_market_state", lambda: "bull")
        monkeypatch.setattr(
            mp_mod, "_adaptive_params", lambda state: {"target_position_pct": 0.8}
        )

        resp = client.post("/api/portfolio/rebalance")
        assert resp.status_code == 200
        assert resp.json()["market_state"] == "bull"


class TestReportsRoutes:
    @pytest.fixture()
    def mock_report_gen(self, monkeypatch: pytest.MonkeyPatch):
        from services import report as rp_mod

        fake_gen = MagicMock()
        fake_gen.get_recent_reports.return_value = [
            {"id": "r1", "ticker": "600519", "date": "2026-06-20"},
            {"id": "r2", "ticker": "000001", "date": "2026-06-21"},
        ]
        monkeypatch.setattr(rp_mod, "ReportGenerator", lambda: fake_gen)
        return fake_gen

    def test_list_reports(self, client: TestClient, mock_report_gen):
        resp = client.get("/api/reports?limit=10")
        assert resp.status_code == 200
        assert resp.json()["total"] == 2

    def test_list_reports_filter_by_ticker(self, client: TestClient, mock_report_gen):
        resp = client.get("/api/reports?ticker=600519")
        assert resp.status_code == 200
        assert len(resp.json()["reports"]) == 1

    def test_get_report_detail(self, client: TestClient, mock_report_gen):
        resp = client.get("/api/reports/r1")
        assert resp.status_code == 200
        assert resp.json()["id"] == "r1"

    def test_get_report_detail_not_found(self, client: TestClient, mock_report_gen):
        resp = client.get("/api/reports/no-such-id")
        assert resp.status_code == 404


class TestScreeningRoutes:
    @pytest.fixture()
    def mock_screening_deps(self, monkeypatch: pytest.MonkeyPatch, tmp_path):
        import sqlite3

        from providers import data_bus as db_mod
        from services import screening as sc_mod

        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE stock_info (stock_code TEXT, stock_name TEXT)")
        conn.execute("INSERT INTO stock_info VALUES ('600519', '茅台')")
        conn.commit()
        conn.close()

        fake_bus = MagicMock()
        fake_bus.db_path = str(db_path)
        fake_bus.get_stock_info.return_value = {"industry": "白酒"}
        monkeypatch.setattr(db_mod, "DatabaseFirstDataBus", lambda: fake_bus)

        def fake_rank(stocks, style, top_n):
            return [
                {
                    "stock_code": s["stock_code"],
                    "stock_name": s["stock_name"],
                    "score": 90.0,
                    "value_score": 80.0,
                    "growth_score": 85.0,
                    "momentum_score": 90.0,
                    "quality_score": 88.0,
                }
                for s in stocks
            ]

        monkeypatch.setattr(sc_mod, "rank_stocks", fake_rank)

    def test_get_screening(self, client: TestClient, mock_screening_deps):
        resp = client.get("/api/screening?style=balanced&limit=10")
        assert resp.status_code == 200
        assert len(resp.json()["stocks"]) == 1

    def test_run_screening(self, client: TestClient, mock_screening_deps):
        resp = client.post("/api/screening/run?style=value")
        assert resp.status_code == 200
        assert resp.json()["style"] == "value"


class TestSettingsRoutes:
    @pytest.fixture()
    def clean_user_config(self, monkeypatch: pytest.MonkeyPatch, tmp_path):
        from api.routes import settings as st_mod

        monkeypatch.setattr(st_mod, "USER_CONFIG_PATH", tmp_path / "user_config.yaml")

    def test_get_settings(self, client: TestClient, clean_user_config):
        resp = client.get("/api/settings")
        assert resp.status_code == 200
        data = resp.json()
        assert data["llm_provider"] == "deepseek"
        assert "has_api_key" in data

    def test_update_settings(self, client: TestClient, clean_user_config):
        resp = client.put(
            "/api/settings",
            json={"llm_provider": "qwen", "debate_rounds": 3},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_send_test_email(self, client: TestClient, monkeypatch):
        from services import email_sender as es_mod

        fake_sender = MagicMock()
        fake_sender.send_test_email.return_value = {"ok": True}
        monkeypatch.setattr(es_mod, "EmailSender", lambda: fake_sender)

        resp = client.post("/api/settings/send-test-email", json={"recipient": "a@qq.com"})
        assert resp.status_code == 200
        assert resp.json()["ok"] is True


class TestTradingPlanRoutes:
    @pytest.fixture()
    def mock_plan_deps(self, monkeypatch: pytest.MonkeyPatch):
        from services import daily_plan as dp_mod
        from services import email_sender as es_mod
        from services import market_scanner as ms_mod
        from services import paper_portfolio as pp_mod

        fake_gen = MagicMock()
        fake_gen.get_today_plan.return_value = {"date": "2026-06-22", "action": "Buy"}
        fake_gen.get_plan_history.return_value = [{"date": "2026-06-21"}]
        fake_gen.generate.return_value = {"date": "2026-06-22", "action": "Buy"}
        monkeypatch.setattr(dp_mod, "DailyPlanGenerator", lambda: fake_gen)

        fake_pp = MagicMock()
        fake_pp.get_account.return_value = {"cash": 100000}
        fake_pp.get_holdings.return_value = [{"code": "600519"}]
        fake_pp.get_trade_history.return_value = [{"id": 1}]
        monkeypatch.setattr(pp_mod, "PaperPortfolio", lambda: fake_pp)

        fake_scanner = MagicMock()
        fake_scanner.get_watchlist.return_value = [{"code": "600519"}]
        monkeypatch.setattr(ms_mod, "MarketScanner", lambda: fake_scanner)

        fake_sender = MagicMock()
        fake_sender.send_plan.return_value = {"ok": True}
        monkeypatch.setattr(es_mod, "EmailSender", lambda: fake_sender)

        return fake_gen

    def test_get_today_plan(self, client: TestClient, mock_plan_deps):
        resp = client.get("/api/trading-plan/today")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    def test_get_history(self, client: TestClient, mock_plan_deps):
        resp = client.get("/api/trading-plan/history?limit=10")
        assert resp.status_code == 200
        assert resp.json()["total"] == 1

    def test_run_daily_plan(self, client: TestClient, mock_plan_deps):
        resp = client.post("/api/trading-plan/run", json={"fast_mode": True})
        assert resp.status_code == 200
        assert resp.json()["status"] == "running"

    def test_get_job_status(self, client: TestClient, mock_plan_deps, monkeypatch):
        from api.routes import trading_plan as tp_mod

        async def fake_run(job_id: str, fast_mode: bool):
            pass  # 保持任务处于 running 状态

        monkeypatch.setattr(tp_mod, "_run_plan", fake_run)

        created = client.post("/api/trading-plan/run", json={"fast_mode": True}).json()
        resp = client.get(f"/api/trading-plan/run/{created['job_id']}")
        assert resp.status_code == 200
        assert resp.json()["status"] == "running"

    def test_get_job_status_not_found(self, client: TestClient, mock_plan_deps):
        resp = client.get("/api/trading-plan/run/no-such-id")
        assert resp.json()["ok"] is False

    def test_get_portfolio(self, client: TestClient, mock_plan_deps):
        resp = client.get("/api/trading-plan/portfolio")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    def test_get_trades(self, client: TestClient, mock_plan_deps):
        resp = client.get("/api/trading-plan/trades?limit=10")
        assert resp.status_code == 200
        assert resp.json()["total"] == 1

    def test_get_watchlist(self, client: TestClient, mock_plan_deps):
        resp = client.get("/api/trading-plan/watchlist")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    def test_get_plan_by_date(self, client: TestClient, mock_plan_deps, tmp_path, monkeypatch):
        import sqlite3

        from core.config import Config

        db_path = tmp_path / "investment.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE daily_plans (id TEXT PRIMARY KEY, plan_json TEXT)")
        conn.execute(
            "INSERT INTO daily_plans VALUES (?, ?)",
            ("2026-06-22", json.dumps({"date": "2026-06-22"})),
        )
        conn.commit()
        conn.close()

        original_get = Config.get

        def fake_get(self, key, default=None):
            if key == "runtime.db_path":
                return str(db_path)
            return original_get(self, key, default)

        monkeypatch.setattr(Config, "get", fake_get)

        resp = client.get("/api/trading-plan/plan/2026-06-22")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    def test_send_plan_email(self, client: TestClient, mock_plan_deps):
        resp = client.post("/api/trading-plan/send-email", json={"recipient": "a@qq.com"})
        assert resp.status_code == 200
        assert resp.json()["ok"] is True
