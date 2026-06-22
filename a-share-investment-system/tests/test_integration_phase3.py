"""阶段3端到端集成测试"""

import os
import tempfile

import numpy as np
import pandas as pd

from services.execution_mode import ExecutionModeManager, ReviewScheduler
from services.portfolio_optimizer import (
    ConstraintPrecomputer,
    PortfolioOptimizer,
    RebalanceEngine,
    SignalAggregator,
)
from services.risk_engine import RiskEngine
from services.trade_executor import KillSwitch, TradeExecutor


class TestTradeExecutor:
    """TradeExecutor核心功能测试"""

    def test_generate_orders_with_cost_filtering(self):
        te = TradeExecutor()
        te.set_initial_cash(500000)
        signals = [
            {
                "stock_code": "600519",
                "stock_name": "贵州茅台",
                "action": "买入",
                "confidence": 0.8,
                "target_price": 1800,
                "reason": "价值低估",
            },
            {"stock_code": "000001", "stock_name": "平安银行", "action": "持有", "confidence": 0.5},
        ]
        result = te.generate_orders(signals, cash=500000)
        assert result.status == "ok"
        assert result.data["orders_generated"] >= 1
        assert result.data["orders_skipped"] >= 1

    def test_execute_paper_with_commissions(self):
        te = TradeExecutor()
        te.set_initial_cash(500000)
        orders = [
            {
                "order_id": "TEST-001",
                "stock_code": "600519",
                "stock_name": "茅台",
                "direction": "买入",
                "quantity": 100,
                "limit_price": 1800,
            }
        ]
        prices = {"600519": 1805}
        result = te.execute_paper(orders, prices, "2026-05-08")
        assert result.status == "ok"
        assert result.data["total_fills"] == 1
        assert result.data["total_commission"] > 0

    def test_position_tracking_after_execution(self):
        te = TradeExecutor()
        te.set_initial_cash(500000)
        orders = [
            {
                "order_id": "TEST-002",
                "stock_code": "600519",
                "stock_name": "茅台",
                "direction": "买入",
                "quantity": 100,
                "limit_price": 1800,
            }
        ]
        te.execute_paper(orders, {"600519": 1805}, "2026-05-08")
        te.update_market_prices({"600519": 1850})
        pos = te.get_positions()
        assert pos.data["position_count"] == 1
        assert pos.data["total_asset"] > 0

    def test_kill_switch_normal(self):
        te = TradeExecutor()
        te.set_initial_cash(500000)
        ks = te.check_kill_switch()
        assert ks.data["level"] in ("normal",)
        assert not ks.data.get("active", True)

    def test_kill_switch_blacklist(self):
        ks = KillSwitch()
        status = ks.check(0.0)
        assert status.level == "normal"
        ks.record_stop_loss("000001")
        ks.record_stop_loss("000001")
        ks.record_stop_loss("000001")
        assert ks.is_blacklisted("000001")

    def test_cost_estimation_rejects_low_edge(self):
        te = TradeExecutor()
        te.set_initial_cash(500000)
        signals = [
            {
                "stock_code": "600519",
                "stock_name": "茅台",
                "action": "买入",
                "confidence": 0.1,
                "target_price": 1800,
                "reason": "test",
            }
        ]
        result = te.generate_orders(signals, cash=500000)
        assert result.data["orders_generated"] <= result.data["total_signals"]


class TestRiskEngine:
    """RiskEngine核心功能测试"""

    def test_full_audit_bull_market(self):
        re = RiskEngine()
        portfolio = [
            {
                "stock_code": "600519",
                "stock_name": "茅台",
                "current_value": 100000,
                "industry": "白酒",
                "debt_to_equity": 20,
                "pledge_ratio": 0,
                "cash_to_assets": 25,
            },
            {
                "stock_code": "600036",
                "stock_name": "招商银行",
                "current_value": 100000,
                "industry": "银行",
                "debt_to_equity": 8,
                "pledge_ratio": 0,
                "cash_to_assets": 10,
            },
            {
                "stock_code": "300750",
                "stock_name": "宁德时代",
                "current_value": 100000,
                "industry": "新能源",
                "debt_to_equity": 12,
                "pledge_ratio": 0,
                "cash_to_assets": 30,
            },
            {
                "stock_code": "601318",
                "stock_name": "中国平安",
                "current_value": 100000,
                "industry": "保险",
                "debt_to_equity": 6,
                "pledge_ratio": 0,
                "cash_to_assets": 15,
            },
            {
                "stock_code": "000651",
                "stock_name": "格力电器",
                "current_value": 100000,
                "industry": "家电",
                "debt_to_equity": 10,
                "pledge_ratio": 0,
                "cash_to_assets": 20,
            },
        ]
        result = re.full_audit(portfolio, {"regime": "BULL", "total_score": 1.5})
        assert result.status == "ok"
        assert result.data["market_risk"]["level"] == "LOW"
        assert result.data["pass"] is True

    def test_full_audit_panic_market(self):
        re = RiskEngine()
        result = re.full_audit([], {"regime": "PANIC", "total_score": -1.8})
        assert result.data["market_risk"]["level"] == "EXTREME"
        assert result.data["pass"] is False

    def test_volatility_limit_calculation(self):
        re = RiskEngine()
        dates = pd.date_range("2024-01-01", periods=100, freq="B")
        df = pd.DataFrame(
            {
                "stock_A": 100 * (1 + np.random.randn(100).cumsum() * 0.005),
            },
            index=dates,
        )
        vol_limit = re._volatility_limit(df)
        assert 0.05 <= vol_limit <= 0.25

    def test_correlation_multiplier(self):
        re = RiskEngine()
        dates = pd.date_range("2024-01-01", periods=100, freq="B")
        df = pd.DataFrame(
            {
                "A": 100 * (1 + np.random.randn(100).cumsum() * 0.01),
                "B": 100 * (1 + np.random.randn(100).cumsum() * 0.01),
            },
            index=dates,
        )
        corr_mult = re._correlation_multiplier(df)
        assert 0.70 <= corr_mult <= 1.10

    def test_stress_test_scenarios(self):
        re = RiskEngine()
        portfolio = [
            {"stock_code": "600519", "current_value": 500000},
        ]
        result = re._stress_test(portfolio)
        assert result["scenario"] == "20% market decline"
        assert result["estimated_loss_pct"] == -20.0
        assert result["crash_scenario_loss_pct"] == -40.0


class TestPortfolioOptimizer:
    """PortfolioOptimizer核心功能测试"""

    def test_constraint_precompute(self):
        cp = ConstraintPrecomputer()
        result = cp.compute(
            [
                {
                    "stock_code": "600519",
                    "quantity": 100,
                    "current_value": 180000,
                    "market_value": 180000,
                    "cost_value": 170000,
                }
            ],
            [
                {
                    "stock_code": "600519",
                    "stock_name": "茅台",
                    "action": "持有",
                    "confidence": 0.5,
                    "target_price": 1800,
                }
            ],
            cash=500000,
        )
        cons = result["constraints"]["600519"]
        assert "持有" in cons["allowed_actions"]
        assert "卖出" in cons["allowed_actions"]
        assert result["skip_llm_count"] >= 0

    def test_signal_aggregation_weighted_fusion(self):
        sa = SignalAggregator()
        result = sa.aggregate(
            [{"stock_code": "600519", "stock_name": "茅台", "action": "持有", "confidence": 0.5}],
            {"constraints": {"600519": {"allowed_actions": ["买入", "持有", "卖出"]}}},
            debate_results={"600519": {"verdict": "买入", "confidence": 0.8}},
            factor_scores={"600519": {"signal": "bullish", "composite_score": 70}},
        )
        assert len(result) == 1
        assert result[0]["action"] in ("买入", "持有", "卖出")
        assert "scores" in result[0]

    def test_rebalance_plan_generation(self):
        re = RebalanceEngine()
        plan = re.plan(
            [
                {
                    "stock_code": "600519",
                    "stock_name": "茅台",
                    "current_value": 180000,
                    "market_value": 180000,
                    "industry": "白酒",
                }
            ],
            [{"stock_code": "600519", "action": "卖出"}],
            total_value=500000,
        )
        assert len(plan["actions"]) >= 1
        assert plan["actions"][0]["priority"] == "高"
        assert "barbell_status" in plan

    def test_full_optimization_pipeline(self):
        po = PortfolioOptimizer()
        result = po.optimize(
            [
                {
                    "stock_code": "600519",
                    "stock_name": "茅台",
                    "quantity": 100,
                    "current_value": 180000,
                    "market_value": 180000,
                    "cost_value": 170000,
                }
            ],
            [{"stock_code": "600519", "stock_name": "茅台", "action": "持有", "confidence": 0.6}],
            cash=500000,
        )
        assert result.status == "ok"
        assert result.data["total_signals"] >= 1
        assert result.data["prefill_count"] >= 0


class TestExecutionMode:
    """ExecutionMode和ReviewScheduler测试"""

    def test_mode_switching(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_path = os.path.join(tmp, "mode.json")
            em = ExecutionModeManager(config_path=config_path)
            assert em.get_mode().data["mode"] == "semi_auto"
            em.set_mode("full_auto")
            assert em.get_mode().data["mode"] == "full_auto"
            em.set_mode("semi_auto")

    def test_order_filtering_full_auto(self):
        with tempfile.TemporaryDirectory() as tmp:
            em = ExecutionModeManager(config_path=os.path.join(tmp, "mode.json"))
            em.set_mode("full_auto")
            orders = [
                {"stock_code": "A", "signal_confidence": 0.8},
                {"stock_code": "B", "signal_confidence": 0.4},
            ]
            result = em.filter_orders_for_mode(orders)
            assert result.data["auto_count"] == 1
            assert result.data["approval_count"] == 1

    def test_review_scheduling_and_execution(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "data"), exist_ok=True)
            orig_cwd = os.getcwd()
            try:
                os.chdir(tmp)
                rs = ReviewScheduler()
                rs.add_pending_review(
                    {
                        "stock_code": "600519",
                        "stock_name": "茅台",
                        "decision": "买入",
                        "confidence": 0.8,
                        "review_date": "2020-01-01",
                        "actual_return_pct": 5.0,
                        "regime": "BULL",
                        "pe": 25,
                        "roe": 18,
                        "industry": "白酒",
                    }
                )
                result = rs.execute_due_reviews("2026-05-08")
                assert result.data["reviewed"] >= 1
            finally:
                os.chdir(orig_cwd)
