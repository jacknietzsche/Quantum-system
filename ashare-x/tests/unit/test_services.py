"""Phase 5 业务服务层测试。"""

from __future__ import annotations

from services.backtest import run_factor_backtest
from services.portfolio import check_industry_constraint, compute_rebalance, optimize_positions
from services.report import ReportGenerator
from services.risk_engine import assess_market_risk, assess_portfolio_risk, assess_stock_risk
from services.screening import compute_stock_score, hard_filter, rank_stocks
from services.trading_plan import generate_trading_plan


class TestScreening:
    def test_compute_score(self):
        stock = {
            "pe_ratio": 15,
            "roe": 20,
            "revenue_growth": 0.15,
            "rsi_14": 50,
            "change_pct_20d": 0.05,
        }
        score = compute_stock_score(stock)
        assert 0 <= score <= 100

    def test_hard_filter_pass(self):
        stock = {
            "code": "600519",
            "is_st": False,
            "listing_days": 1000,
            "amount": 10_000_000,
            "is_suspended": False,
        }
        assert hard_filter(stock) is True

    def test_hard_filter_reject_st(self):
        stock = {"code": "000001", "is_st": True, "listing_days": 1000, "amount": 10_000_000}
        assert hard_filter(stock) is False

    def test_rank_stocks(self):
        stocks = [
            {
                "code": "600519",
                "pe_ratio": 15,
                "roe": 20,
                "amount": 10_000_000,
                "listing_days": 1000,
            },
            {
                "code": "000858",
                "pe_ratio": 25,
                "roe": 15,
                "amount": 10_000_000,
                "listing_days": 1000,
            },
        ]
        result = rank_stocks(stocks, top_n=2)
        assert len(result) <= 2
        assert all("score" in s for s in result)


class TestPortfolio:
    def test_optimize_positions(self):
        candidates = [
            {"code": "600519", "industry": "白酒", "score": 85},
            {"code": "601318", "industry": "保险", "score": 75},
        ]
        result = optimize_positions(candidates, 1_000_000, market_state="NEUTRAL")
        assert len(result) > 0
        total_pct = sum(s["position_pct"] for s in result)
        assert total_pct <= 60

    def test_industry_constraint(self):
        portfolio = [
            {"code": "600519", "industry": "白酒"},
            {"code": "000858", "industry": "白酒"},
            {"code": "000568", "industry": "白酒"},
            {"code": "600809", "industry": "白酒"},
        ]
        violations = check_industry_constraint(portfolio, max_per_industry=3)
        assert len(violations) > 0

    def test_rebalance(self):
        current = [{"code": "600519", "position_pct": 15}]
        target = [{"code": "601318", "position_pct": 10}]
        ops = compute_rebalance(current, target)
        assert len(ops) > 0


class TestRiskEngine:
    def test_market_risk(self):
        data = {
            "sh_change_20d": 0.05,
            "advance_count": 2500,
            "decline_count": 1500,
            "volume": 4000,
            "volume_ma20": 3000,
            "north_flow_5d": 50,
        }
        result = assess_market_risk(data)
        assert "market_state" in result
        assert "position_cap" in result

    def test_stock_risk(self):
        data = {"volatility": 0.35, "volume": 1000000, "avg_volume": 1500000}
        result = assess_stock_risk(data)
        assert result["risk_level"] == "medium"

    def test_portfolio_risk(self):
        portfolio = [
            {"industry": "白酒", "position_pct": 20},
            {"industry": "保险", "position_pct": 15},
        ]
        result = assess_portfolio_risk(portfolio)
        assert "concentration_risk" in result


class TestTradingPlan:
    def test_generate_plan(self):
        plan = generate_trading_plan("600519", "贵州茅台", "Buy", 80, 1500.0)
        assert plan["ticker"] == "600519"
        assert plan["action"] == "Buy"
        assert plan["stop_loss"] < plan["entry_price"]
        assert plan["take_profit"] > plan["entry_price"]


class TestReport:
    def test_save_and_get(self):
        gen = ReportGenerator(db_path=":memory:")
        plan = {
            "ticker": "600519",
            "stock_name": "贵州茅台",
            "action": "Buy",
            "confidence": 80,
            "entry_price": 1500,
            "stop_loss": 1425,
            "take_profit": 1650,
            "position_pct": 5,
        }
        gen.save_report("rpt-001", plan)
        reports = gen.get_recent_reports()
        assert len(reports) == 1
        assert reports[0]["ticker"] == "600519"

    def test_generate_markdown(self):
        gen = ReportGenerator(db_path=":memory:")
        plan = {
            "ticker": "600519",
            "stock_name": "贵州茅台",
            "action": "Buy",
            "confidence": 80,
            "entry_price": 1500,
            "stop_loss": 1425,
            "take_profit": 1650,
            "position_pct": 5,
            "thesis": "test",
            "key_factors": ["f1"],
            "risks": ["r1"],
        }
        md = gen.generate_markdown(plan)
        assert "600519" in md
        assert "Buy" in md


class TestBacktest:
    def test_run_backtest(self):
        stocks = [{"code": "600519", "close": 1500}]
        metrics = run_factor_backtest(stocks)
        assert "total_return" in metrics
