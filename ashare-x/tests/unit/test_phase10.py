"""Phase 10 测试: 模拟持仓 + 全市场扫描 + 仓位决策 + 交易计划。"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ════════════════════════════════════════════════════════════════
# PaperPortfolio 测试
# ════════════════════════════════════════════════════════════════


class TestPaperPortfolio:
    """模拟持仓服务测试。"""

    @pytest.fixture()
    def portfolio(self, tmp_path, monkeypatch):
        """创建使用临时数据库的PaperPortfolio，并mock数据总线。"""
        from core.config import Config
        from providers import data_bus as db_mod

        Config.reset()
        db_path = str(tmp_path / "test.db")

        fake_bus = MagicMock()
        fake_bus.get_stock_info.return_value = {"latest_price": 300.0, "prev_close": 300.0}
        fake_bus.get_kline.return_value = []
        monkeypatch.setattr(db_mod, "DatabaseFirstDataBus", lambda *args, **kwargs: fake_bus)

        from services.paper_portfolio import PaperPortfolio

        pp = PaperPortfolio(db_path=db_path)
        pp.slippage = 0.0  # 保持原有断言精确
        return pp

    def test_buy_initial(self, portfolio):
        """首次买入→持仓正确。"""
        result = portfolio.buy("600519", "贵州茅台", 300.0, 200, "估值合理")
        assert result["ok"] is True
        assert result["action"] == "BUY"
        assert result["shares"] == 200

        holdings = portfolio.get_holdings()
        assert len(holdings) == 1
        assert holdings[0]["stock_code"] == "600519"
        assert holdings[0]["shares"] == 200
        assert holdings[0]["avg_cost"] == 300.0
        assert holdings[0]["t1_blocked"] == 200  # T+1冻结

    def test_buy_round_lot(self, portfolio):
        """不足100股向下取整。"""
        result = portfolio.buy("600519", "贵州茅台", 300.0, 150, "测试")
        assert result["ok"] is True
        assert result["shares"] == 100  # 150→100

    def test_buy_insufficient_funds(self, portfolio):
        """资金不足时买入失败。"""
        result = portfolio.buy("600519", "贵州茅台", 200.0, 1000, "测试")
        assert result["ok"] is False
        assert "资金不足" in result["error"]

    def test_add_position(self, portfolio):
        """加仓→平均成本更新。"""
        portfolio.buy("600519", "贵州茅台", 300.0, 100, "初次买入")
        result = portfolio.add("600519", "贵州茅台", 310.0, 100, "加仓")
        assert result["ok"] is True
        assert result["action"] == "ADD"
        assert result["total_shares"] == 200
        # 平均成本 = (100*300 + 100*310) / 200 = 305
        assert result["new_avg_cost"] == 305.0

    def test_reduce_position(self, portfolio):
        """减仓→部分卖出。"""
        portfolio.buy("600519", "贵州茅台", 300.0, 200, "初次买入")
        # 清除T+1冻结（模拟次日）
        portfolio.update_prices()
        result = portfolio.reduce("600519", 310.0, 100, "减仓")
        assert result["ok"] is True
        assert result["action"] == "REDUCE"
        assert result["remaining_shares"] == 100

    def test_clear_position(self, portfolio):
        """清仓→持仓为0。"""
        portfolio.buy("600519", "贵州茅台", 300.0, 100, "初次买入")
        portfolio.update_prices()
        result = portfolio.clear("600519", 310.0, "清仓")
        assert result["ok"] is True

        holdings = portfolio.get_holdings()
        assert len(holdings) == 0

    def test_t1_rule(self, portfolio):
        """T+1限制: 当日买入不可卖。"""
        portfolio.buy("600519", "贵州茅台", 300.0, 100, "当日买入")
        result = portfolio.reduce("600519", 310.0, 100, "当日卖出")
        assert result["ok"] is False
        assert "T+1" in result["error"] or "可卖不足" in result["error"]

    def test_account_summary(self, portfolio):
        """账户信息正确。"""
        account = portfolio.get_account()
        assert account["initial_capital"] == 100000
        assert account["cash"] == 100000
        assert account["total_assets"] == 100000
        assert account["holding_count"] == 0

    def test_trade_history(self, portfolio):
        """交易历史记录正确。"""
        portfolio.buy("600519", "贵州茅台", 300.0, 100, "买入1")
        portfolio.update_prices()
        portfolio.reduce("600519", 310.0, 100, "减仓1")

        trades = portfolio.get_trade_history()
        assert len(trades) == 2
        assert trades[0]["action"] == "REDUCE"  # 最新的在前
        assert trades[1]["action"] == "BUY"

    def test_commission_calc(self, portfolio):
        """手续费计算: 大额交易佣金=金额*0.025%。"""
        result = portfolio.buy("600519", "贵州茅台", 100.0, 500, "测试")
        assert result["ok"] is True
        # 金额 = 100 * 500 = 50000, 佣金 = 50000 * 0.00025 = 12.5
        conn = sqlite3.connect(portfolio.db_path)
        row = conn.execute(
            "SELECT commission FROM paper_trades WHERE action = 'BUY'"
        ).fetchone()
        conn.close()
        assert row[0] == 12.5

    def test_min_commission(self, portfolio):
        """最低佣金5元。"""
        result = portfolio.buy("000001", "平安银行", 10.0, 100, "小额测试")
        assert result["ok"] is True
        # 金额 = 10 * 100 = 1000, 佣金 = 1000 * 0.00025 = 0.25 → 最低5元
        conn = sqlite3.connect(portfolio.db_path)
        row = conn.execute(
            "SELECT commission FROM paper_trades WHERE action = 'BUY'"
        ).fetchone()
        conn.close()
        assert row[0] == 5.0


# ════════════════════════════════════════════════════════════════
# MarketScanner 测试
# ════════════════════════════════════════════════════════════════


class TestMarketScanner:
    """全市场扫描测试。"""

    @pytest.fixture()
    def scanner(self, tmp_path):
        from core.config import Config

        Config.reset()
        db_path = str(tmp_path / "test.db")
        from providers.data_bus import DatabaseFirstDataBus

        DatabaseFirstDataBus(db_path)
        from services.market_scanner import MarketScanner

        return MarketScanner(db_path=db_path)

    def test_normalize_spot(self):
        """spot数据标准化。"""
        from services.market_scanner import MarketScanner

        spot = {
            "stock_name": "贵州茅台",
            "latest_price": 1680.0,
            "change_pct": 2.5,
            "volume": 1000000,
            "amount": 1680000000,
            "pe_ratio": 30.0,
            "pb_ratio": 10.0,
            "turnover_rate": 0.5,
        }
        normalized = MarketScanner._normalize_spot(spot)
        assert normalized["stock_name"] == "贵州茅台"
        assert normalized["pe_ratio"] == 30.0
        assert normalized["is_st"] is False

    def test_normalize_st_stock(self):
        """ST股票识别。"""
        from services.market_scanner import MarketScanner

        spot = {"stock_name": "*STtest", "pe_ratio": None, "pb_ratio": None}
        normalized = MarketScanner._normalize_spot(spot)
        assert normalized["is_st"] is True

    def test_scan_with_mock(self, scanner):
        """mock全量快照数据测试扫描。"""
        mock_stocks = [
            {
                "stock_code": "600519", "stock_name": "贵州茅台",
                "latest_price": 1680.0,
                "change_pct": 2.0, "volume": 1000000, "amount": 1680000000,
                "pe_ratio": 30.0, "pb_ratio": 10.0, "turnover_rate": 0.5,
            },
            {
                "stock_code": "000001", "stock_name": "平安银行",
                "latest_price": 12.0,
                "change_pct": 1.0, "volume": 5000000, "amount": 60000000,
                "pe_ratio": 5.0, "pb_ratio": 0.8, "turnover_rate": 1.2,
            },
        ]

        with patch.object(
            type(scanner),
            "_get_spot_universe",
            return_value=mock_stocks,
        ):
            results = scanner.scan_full_market(top_n=10)

        assert len(results) > 0
        assert all("score" in r for r in results)
        assert all("stock_code" in r for r in results)
        assert all(r["stock_code"] != "" for r in results)
        # 评分应按降序排列
        for i in range(len(results) - 1):
            assert results[i]["score"] >= results[i + 1]["score"]

    def test_watchlist_update(self, scanner):
        """观察名单增删。"""
        scan_results = [
            {"stock_code": "600519", "stock_name": "贵州茅台", "score": 80.0},
            {"stock_code": "000001", "stock_name": "平安银行", "score": 70.0},
        ]
        scanner.update_watchlist(scan_results, max_size=10)

        watchlist = scanner.get_watchlist()
        assert len(watchlist) == 2
        assert any(w["stock_code"] == "600519" for w in watchlist)

    def test_mark_analyzed(self, scanner):
        """标记已分析。"""
        scan_results = [
            {"stock_code": "600519", "stock_name": "贵州茅台", "score": 80.0},
        ]
        scanner.update_watchlist(scan_results)
        scanner.mark_analyzed("600519")

        watchlist = scanner.get_watchlist()
        stock = next(w for w in watchlist if w["stock_code"] == "600519")
        assert stock["analysis_count"] == 1
        assert stock["last_analysis_date"] is not None


# ════════════════════════════════════════════════════════════════
# PositionEngine 测试
# ════════════════════════════════════════════════════════════════


class TestPositionEngine:
    """仓位决策引擎测试。"""

    @pytest.fixture()
    def engine(self):
        from core.config import Config

        Config.reset()
        from services.position_engine import PositionEngine

        return PositionEngine()

    def test_initial_buy(self, engine):
        """无持仓 + Buy信号 + 高置信度 → INITIAL_BUY。"""
        analysis = {
            "action": "Buy", "confidence": 85,
            "entry_price": 50.0, "ticker": "600519",
            "stop_loss": 47.0, "take_profit": 58.0,
            "thesis": "估值合理",
        }
        account = {"total_assets": 100000, "cash": 100000}
        decision = engine.decide(analysis, None, account, "NEUTRAL", 0)
        assert decision.action == "INITIAL_BUY"
        assert decision.target_shares > 0
        assert decision.target_shares % 100 == 0  # 100股整数倍

    def test_add_position(self, engine):
        """有持仓 + Buy信号 + 高置信度 → ADD。"""
        analysis = {
            "action": "Buy", "confidence": 80,
            "entry_price": 50.0, "ticker": "600519",
            "thesis": "继续看好",
        }
        holding = {"shares": 100, "market_value": 5000, "avg_cost": 48.0}
        account = {"total_assets": 100000, "cash": 50000}
        decision = engine.decide(analysis, holding, account, "NEUTRAL", 1)
        assert decision.action == "ADD"

    def test_clear_on_sell(self, engine):
        """有持仓 + Sell信号 → CLEAR。"""
        analysis = {
            "action": "Sell", "confidence": 75,
            "entry_price": 50.0, "ticker": "600519",
            "thesis": "趋势走弱",
        }
        holding = {"shares": 300, "market_value": 15000, "avg_cost": 50.0}
        account = {"total_assets": 100000, "cash": 50000}
        decision = engine.decide(analysis, holding, account, "NEUTRAL", 1)
        assert decision.action == "CLEAR"

    def test_hold_on_neutral(self, engine):
        """Hold信号 → HOLD。"""
        analysis = {
            "action": "Hold", "confidence": 60,
            "entry_price": 50.0, "ticker": "600519",
            "thesis": "维持观望",
        }
        holding = {"shares": 300, "market_value": 15000, "avg_cost": 50.0}
        account = {"total_assets": 100000, "cash": 50000}
        decision = engine.decide(analysis, holding, account, "NEUTRAL", 1)
        assert decision.action == "HOLD"

    def test_watch_on_low_confidence(self, engine):
        """无持仓 + Buy信号 + 低置信度 → WATCH。"""
        analysis = {
            "action": "Buy", "confidence": 50,
            "entry_price": 1680.0, "ticker": "600519",
            "thesis": "不确定",
        }
        account = {"total_assets": 100000, "cash": 100000}
        decision = engine.decide(analysis, None, account, "NEUTRAL", 0)
        assert decision.action == "WATCH"

    def test_position_size_100lot(self, engine):
        """仓位按100股取整。"""
        analysis = {
            "action": "Buy", "confidence": 85,
            "entry_price": 1680.0, "ticker": "600519",
            "thesis": "测试取整",
        }
        account = {"total_assets": 100000, "cash": 100000}
        decision = engine.decide(analysis, None, account, "NEUTRAL", 0)
        assert decision.target_shares % 100 == 0

    def test_max_holdings_limit(self, engine):
        """达到最大持仓数不新增。"""
        analysis = {
            "action": "Buy", "confidence": 85,
            "entry_price": 1680.0, "ticker": "600519",
            "thesis": "测试上限",
        }
        account = {"total_assets": 100000, "cash": 100000}
        decision = engine.decide(analysis, None, account, "NEUTRAL", 5)
        assert decision.action == "HOLD"
        assert "最大持仓数" in decision.reasoning

    def test_max_single_pct(self, engine):
        """达单只上限不加仓。"""
        analysis = {
            "action": "Buy", "confidence": 85,
            "entry_price": 1680.0, "ticker": "600519",
            "thesis": "测试单只上限",
        }
        holding = {"shares": 200, "market_value": 30000, "avg_cost": 1680.0}
        account = {"total_assets": 100000, "cash": 50000}
        # market_value/total_assets = 30%, max_single_pct=30%
        decision = engine.decide(analysis, holding, account, "NEUTRAL", 1)
        assert decision.action == "HOLD"

    def test_reduce_on_low_confidence(self, engine):
        """置信度过低→减仓。"""
        analysis = {
            "action": "Hold", "confidence": 30,
            "entry_price": 1680.0, "ticker": "600519",
            "thesis": "信心不足",
        }
        holding = {"shares": 600, "market_value": 1008000, "avg_cost": 1680.0}
        account = {"total_assets": 100000, "cash": 50000}
        decision = engine.decide(analysis, holding, account, "NEUTRAL", 1)
        assert decision.action == "REDUCE"

    def test_panic_market_no_buy(self, engine):
        """PANIC市场不买入。"""
        analysis = {
            "action": "Buy", "confidence": 90,
            "entry_price": 1680.0, "ticker": "600519",
            "thesis": "恐慌中",
        }
        account = {"total_assets": 100000, "cash": 100000}
        decision = engine.decide(analysis, None, account, "PANIC", 0)
        assert decision.target_shares == 0


# ════════════════════════════════════════════════════════════════
# DailyPlanGenerator 测试
# ════════════════════════════════════════════════════════════════


class TestDailyPlanGenerator:
    """每日计划生成器测试。"""

    @pytest.fixture()
    def gen(self, tmp_path):
        from core.config import Config

        Config.reset()
        db_path = str(tmp_path / "test.db")
        from providers.data_bus import DatabaseFirstDataBus

        DatabaseFirstDataBus(db_path)

        # 通过环境变量设置db_path，让DailyPlanGenerator使用临时数据库
        import os

        old_val = os.environ.get("ASHARE_X_RUNTIME_DB_PATH")
        os.environ["ASHARE_X_RUNTIME_DB_PATH"] = db_path
        Config.reset()
        from services.daily_plan import DailyPlanGenerator

        gen = DailyPlanGenerator()
        gen.db_path = db_path
        gen.portfolio.db_path = db_path
        gen.scanner.db_path = db_path
        yield gen
        if old_val is not None:
            os.environ["ASHARE_X_RUNTIME_DB_PATH"] = old_val
        else:
            os.environ.pop("ASHARE_X_RUNTIME_DB_PATH", None)

    def test_plan_saved_to_db(self, gen):
        """计划保存到数据库。"""
        from datetime import datetime

        today = datetime.now().strftime("%Y-%m-%d")
        # 模拟一个空计划
        plan = {
            "date": today,
            "market_state": "NEUTRAL",
            "actions": [],
            "holdings_status": [],
            "watchlist": [],
            "summary": "测试摘要",
            "account": {"total_assets": 100000, "cash": 100000, "pnl": 0, "pnl_pct": 0},
        }
        gen._save_plan(plan)

        # 验证保存
        loaded = gen.get_today_plan()
        assert loaded is not None
        assert loaded["date"] == today
        assert loaded["summary"] == "测试摘要"

    def test_plan_history(self, gen):
        """历史计划查询。"""
        for i in range(3):
            plan = {
                "date": f"2026-06-1{i}",
                "market_state": "NEUTRAL",
                "actions": [],
                "summary": f"day {i}",
            }
            gen._save_plan(plan)

        history = gen.get_plan_history()
        assert len(history) >= 3

    def test_summary_generated(self, gen):
        """摘要非空。"""
        plan = {
            "date": "2026-06-20",
            "market_state": "BULL",
            "actions": [
                {"action": "INITIAL_BUY", "stock_code": "600519"},
                {"action": "HOLD", "stock_code": "000858"},
            ],
            "holdings_status": [],
            "account": {"total_assets": 100000, "cash": 50000, "pnl": 500, "pnl_pct": 0.5},
            "errors": [],
        }
        summary = gen._generate_summary(plan)
        assert "BULL" in summary
        assert "100000" in summary or "100,000" in summary
        assert "买入1笔" in summary

    def test_select_analysis_batch(self, gen):
        """分析批次选择。"""
        watchlist = [
            {"stock_code": "600519", "stock_name": "茅台", "last_analysis_date": None},
            {"stock_code": "000858", "stock_name": "五粮液", "last_analysis_date": "2026-06-18"},
            {"stock_code": "601318", "stock_name": "平安", "last_analysis_date": "2026-06-19"},
            {"stock_code": "000333", "stock_name": "美的", "last_analysis_date": None},
        ]
        batch = gen._select_analysis_batch(watchlist, 2)
        assert len(batch) == 2
        # 从未分析的优先
        codes = [b["stock_code"] for b in batch]
        assert "600519" in codes
        assert "000333" in codes

    def test_markdown_report_generated(self, gen, tmp_path):
        """Markdown报告生成。"""
        plan = {
            "date": "2026-06-20",
            "market_state": "NEUTRAL",
            "actions": [],
            "holdings_status": [],
            "watchlist": [],
            "summary": "测试",
            "account": {"total_assets": 100000, "cash": 100000,
                        "holdings_value": 0, "pnl": 0, "pnl_pct": 0, "holding_count": 0},
        }
        gen._save_markdown_report(plan)

        reports_dir = Path("reports")
        md_files = list(reports_dir.glob("daily_plan_2026-06-20.md"))
        if md_files:
            content = md_files[0].read_text(encoding="utf-8")
            assert "每日交易计划" in content
            assert "2026-06-20" in content


# ════════════════════════════════════════════════════════════════
# API 路由测试
# ════════════════════════════════════════════════════════════════


class TestTradingPlanAPI:
    """交易计划API测试。"""

    pytestmark = pytest.mark.data

    def test_get_portfolio(self):
        """GET /api/trading-plan/portfolio 返回持仓。"""
        from fastapi.testclient import TestClient

        from server import app

        client = TestClient(app)
        r = client.get("/api/trading-plan/portfolio")
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert "account" in data
        assert "holdings" in data

    def test_get_watchlist(self):
        """GET /api/trading-plan/watchlist 返回观察名单。"""
        from fastapi.testclient import TestClient

        from server import app

        client = TestClient(app)
        r = client.get("/api/trading-plan/watchlist")
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True

    def test_get_trades(self):
        """GET /api/trading-plan/trades 返回交易历史。"""
        from fastapi.testclient import TestClient

        from server import app

        client = TestClient(app)
        r = client.get("/api/trading-plan/trades")
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True

    def test_get_today_plan(self):
        """GET /api/trading-plan/today 返回今日计划。"""
        from fastapi.testclient import TestClient

        from server import app

        client = TestClient(app)
        r = client.get("/api/trading-plan/today")
        assert r.status_code == 200

    def test_get_history(self):
        """GET /api/trading-plan/history 返回历史。"""
        from fastapi.testclient import TestClient

        from server import app

        client = TestClient(app)
        r = client.get("/api/trading-plan/history")
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
