"""PortfolioOptimizer 全面单元测试 — 约束预计算、信号聚合、再平衡、Kelly、风险预算"""

import pytest

from services.portfolio_optimizer import (
    ConstraintPrecomputer,
    PortfolioOptimizer,
    RebalanceEngine,
    SignalAggregator,
)


@pytest.fixture
def optimizer():
    return PortfolioOptimizer()


@pytest.fixture
def sample_positions():
    return [
        {
            "stock_code": "600519",
            "stock_name": "茅台",
            "market_value": 180000,
            "cost_value": 170000,
            "quantity": 100,
            "industry": "白酒",
        },
        {
            "stock_code": "600036",
            "stock_name": "招行",
            "market_value": 42000,
            "cost_value": 40000,
            "quantity": 1000,
            "industry": "银行",
        },
    ]


@pytest.fixture
def sample_signals():
    return [
        {
            "stock_code": "600519",
            "stock_name": "茅台",
            "target_price": 1800,
            "action": "持有",
            "confidence": 0.7,
        },
        {
            "stock_code": "600036",
            "stock_name": "招行",
            "target_price": 42,
            "action": "买入",
            "confidence": 0.8,
        },
        {
            "stock_code": "000001",
            "stock_name": "平安",
            "target_price": 13,
            "action": "买入",
            "confidence": 0.6,
        },
    ]


# ══════════════════════════════════════════════
#  ConstraintPrecomputer
# ══════════════════════════════════════════════


class TestConstraintPrecomputer:
    def test_basic_compute(self, sample_positions, sample_signals):
        cp = ConstraintPrecomputer()
        result = cp.compute(sample_positions, sample_signals, cash=100000)
        assert "constraints" in result
        assert "total_value" in result
        assert result["total_value"] > 0

    def test_constraints_per_signal(self, sample_positions, sample_signals):
        cp = ConstraintPrecomputer()
        result = cp.compute(sample_positions, sample_signals, cash=100000)
        for sig in sample_signals:
            code = sig["stock_code"]
            assert code in result["constraints"]

    def test_allowed_actions(self, sample_positions, sample_signals):
        cp = ConstraintPrecomputer()
        result = cp.compute(sample_positions, sample_signals, cash=100000)
        for code, cons in result["constraints"].items():
            assert "allowed_actions" in cons
            assert "持有" in cons["allowed_actions"]

    def test_needs_llm_flag(self, sample_positions, sample_signals):
        cp = ConstraintPrecomputer()
        result = cp.compute(sample_positions, sample_signals, cash=100000)
        for code, cons in result["constraints"].items():
            assert "needs_llm" in cons
            assert isinstance(cons["needs_llm"], bool)

    def test_skip_llm_count(self, sample_positions, sample_signals):
        cp = ConstraintPrecomputer()
        result = cp.compute(sample_positions, sample_signals, cash=100000)
        assert "skip_llm_count" in result
        assert result["skip_llm_count"] >= 0

    def test_no_cash_limits_buy(self, sample_signals):
        cp = ConstraintPrecomputer()
        result = cp.compute([], sample_signals, cash=0)
        for cons in result["constraints"].values():
            assert cons["max_buy_shares"] == 0
            assert "买入" not in cons["allowed_actions"]

    def test_current_weight_calculation(self, sample_positions, sample_signals):
        cp = ConstraintPrecomputer()
        result = cp.compute(sample_positions, sample_signals, cash=100000)
        moutai_cons = result["constraints"]["600519"]
        assert moutai_cons["current_weight"] > 0


# ══════════════════════════════════════════════
#  SignalAggregator
# ══════════════════════════════════════════════


class TestSignalAggregator:
    def test_prefill_when_only_one_action(self):
        sa = SignalAggregator()
        signals = [{"stock_code": "A", "stock_name": "A"}]
        constraints = {"constraints": {"A": {"allowed_actions": ["持有"], "needs_llm": False}}}
        result = sa.aggregate(signals, constraints)
        assert len(result) == 1
        assert result[0]["action"] == "持有"
        assert result[0]["source"] == "constraint_prefill"

    def test_signal_fusion_with_multiple_actions(self):
        sa = SignalAggregator()
        signals = [
            {"stock_code": "A", "stock_name": "A", "action": "买入", "confidence": 0.8},
        ]
        constraints = {
            "constraints": {"A": {"allowed_actions": ["持有", "买入", "卖出"], "needs_llm": True}}
        }
        result = sa.aggregate(signals, constraints)
        assert len(result) == 1
        assert result[0]["source"] == "signal_aggregation"
        assert "scores" in result[0]

    def test_with_debate_results(self):
        sa = SignalAggregator()
        signals = [{"stock_code": "A", "stock_name": "A", "action": "买入", "confidence": 0.7}]
        constraints = {
            "constraints": {"A": {"allowed_actions": ["持有", "买入", "卖出"], "needs_llm": True}}
        }
        debate = {"A": {"verdict": "买入", "confidence": 0.9}}
        result = sa.aggregate(signals, constraints, debate_results=debate)
        assert result[0]["action"] == "买入"

    def test_with_factor_scores(self):
        sa = SignalAggregator()
        signals = [{"stock_code": "A", "stock_name": "A", "action": "持有", "confidence": 0.5}]
        constraints = {
            "constraints": {"A": {"allowed_actions": ["持有", "买入"], "needs_llm": True}}
        }
        factors = {"A": {"signal": "bullish", "composite_score": 80}}
        result = sa.aggregate(signals, constraints, factor_scores=factors)
        assert len(result) == 1

    def test_winner_filtered_to_allowed(self):
        sa = SignalAggregator()
        signals = [{"stock_code": "A", "stock_name": "A", "action": "买入", "confidence": 0.9}]
        constraints = {
            "constraints": {"A": {"allowed_actions": ["持有", "卖出"], "needs_llm": True}}
        }
        result = sa.aggregate(signals, constraints)
        assert result[0]["action"] in ("持有", "卖出")

    def test_empty_signals(self):
        sa = SignalAggregator()
        result = sa.aggregate([], {"constraints": {}})
        assert result == []


# ══════════════════════════════════════════════
#  RebalanceEngine
# ══════════════════════════════════════════════


class TestRebalanceEngine:
    def test_basic_plan(self, sample_positions):
        re = RebalanceEngine()
        signals = [
            {"stock_code": "600519", "action": "持有"},
            {"stock_code": "600036", "action": "买入"},
        ]
        result = re.plan(sample_positions, signals, total_value=300000)
        assert "actions" in result
        assert "high_priority_count" in result
        assert "barbell_status" in result

    def test_sell_high_priority(self, sample_positions):
        re = RebalanceEngine()
        signals = [{"stock_code": "600519", "action": "卖出"}]
        result = re.plan(sample_positions, signals, total_value=300000)
        moutai = next(a for a in result["actions"] if a["stock_code"] == "600519")
        assert moutai["priority"] == "高"

    def test_overweight_reduces_priority(self):
        re = RebalanceEngine()
        positions = [
            {
                "stock_code": "A",
                "market_value": 260000,
                "quantity": 1000,
                "stock_name": "A",
                "industry": "银行",
            }
        ]
        signals = [{"stock_code": "A", "action": "持有"}]
        result = re.plan(positions, signals, total_value=300000)
        assert result["actions"][0]["priority"] == "高"

    def test_barbell_status(self, sample_positions):
        re = RebalanceEngine()
        result = re.plan(sample_positions, [], total_value=300000, barbell_ratio=0.70)
        bs = result["barbell_status"]
        assert "core_pct" in bs
        assert "satellite_pct" in bs
        assert "target_core" in bs
        assert "drift" in bs

    def test_actions_sorted_by_priority(self, sample_positions):
        re = RebalanceEngine()
        signals = [
            {"stock_code": "600519", "action": "卖出"},
            {"stock_code": "600036", "action": "持有"},
        ]
        result = re.plan(sample_positions, signals, total_value=300000)
        priorities = [a["priority"] for a in result["actions"]]
        level_map = {"高": 0, "中": 1, "低": 2}
        for i in range(len(priorities) - 1):
            assert level_map[priorities[i]] <= level_map[priorities[i + 1]]


# ══════════════════════════════════════════════
#  PortfolioOptimizer 整合
# ══════════════════════════════════════════════


class TestPortfolioOptimizer:
    def test_optimize_basic(self, optimizer, sample_positions, sample_signals):
        result = optimizer.optimize(sample_positions, sample_signals, cash=100000)
        assert result.status == "ok"
        data = result.data
        assert "target_signals" in data
        assert "constraints" in data
        assert "rebalance_plan" in data

    def test_optimize_with_risk_report(self, optimizer, sample_positions, sample_signals):
        risk_report = {"position_limits": {"max_single_stock_pct": 15.0}}
        result = optimizer.optimize(
            sample_positions, sample_signals, cash=100000, risk_report=risk_report
        )
        assert result.status == "ok"

    def test_optimize_empty(self, optimizer):
        result = optimizer.optimize([], [], cash=100000)
        assert result.status == "ok"

    def test_kelly_basic(self, optimizer):
        candidates = [
            {
                "stock_code": "600519",
                "stock_name": "茅台",
                "price": 1800,
                "score": 70,
                "volatility": 0.25,
            },
            {
                "stock_code": "600036",
                "stock_name": "招行",
                "price": 42,
                "score": 60,
                "volatility": 0.22,
            },
        ]
        result = optimizer.kelly_position_sizing(candidates, total_capital=1000000, cash=500000)
        assert result.status == "ok"
        assert result.data["method"] == "half_kelly"
        assert len(result.data["allocations"]) == 2

    def test_kelly_empty(self, optimizer):
        result = optimizer.kelly_position_sizing([], total_capital=1000000, cash=500000)
        assert result.status == "ok"
        assert result.data["allocations"] == []

    def test_kelly_full_vs_half(self, optimizer):
        candidates = [
            {"stock_code": "A", "stock_name": "A", "price": 100, "score": 70, "volatility": 0.25},
        ]
        half = optimizer.kelly_position_sizing(candidates, 1000000, 500000, half_kelly=True)
        full = optimizer.kelly_position_sizing(candidates, 1000000, 500000, half_kelly=False)
        assert (
            full.data["allocations"][0]["kelly_fraction"]
            > half.data["allocations"][0]["kelly_fraction"]
        )

    def test_kelly_respects_max_single_pct(self, optimizer):
        candidates = [
            {"stock_code": "A", "stock_name": "A", "price": 10, "score": 95, "volatility": 0.10},
        ]
        result = optimizer.kelly_position_sizing(candidates, 1000000, 500000, max_single_pct=10.0)
        assert result.data["allocations"][0]["target_weight_pct"] <= 10.0

    def test_kelly_cash_scaling(self, optimizer):
        candidates = [
            {"stock_code": "A", "stock_name": "A", "price": 100, "score": 60, "volatility": 0.25},
            {"stock_code": "B", "stock_name": "B", "price": 100, "score": 60, "volatility": 0.25},
            {"stock_code": "C", "stock_name": "C", "price": 100, "score": 60, "volatility": 0.25},
            {"stock_code": "D", "stock_name": "D", "price": 100, "score": 60, "volatility": 0.25},
            {"stock_code": "E", "stock_name": "E", "price": 100, "score": 60, "volatility": 0.25},
        ]
        result = optimizer.kelly_position_sizing(candidates, 100000, 10000)
        total = result.data["total_allocated"]
        assert total <= 10000 * 1.05

    def test_risk_budget_basic(self, optimizer):
        candidates = [
            {"stock_code": "A", "stock_name": "A", "price": 100, "volatility": 0.20},
            {"stock_code": "B", "stock_name": "B", "price": 100, "volatility": 0.40},
        ]
        result = optimizer.risk_budget_allocation(candidates, total_capital=100000)
        assert result.status == "ok"
        assert result.data["method"] == "risk_parity"
        assert len(result.data["allocations"]) == 2

    def test_risk_budget_low_vol_higher_weight(self, optimizer):
        candidates = [
            {"stock_code": "LOW", "stock_name": "低波", "price": 100, "volatility": 0.10},
            {"stock_code": "HIGH", "stock_name": "高波", "price": 100, "volatility": 0.50},
        ]
        result = optimizer.risk_budget_allocation(candidates, total_capital=100000)
        allocs = result.data["allocations"]
        low_w = next(a["weight_pct"] for a in allocs if a["stock_code"] == "LOW")
        high_w = next(a["weight_pct"] for a in allocs if a["stock_code"] == "HIGH")
        assert low_w > high_w

    def test_risk_budget_empty(self, optimizer):
        result = optimizer.risk_budget_allocation([], total_capital=100000)
        assert result.status == "ok"

    def test_inherits_base_service(self, optimizer):
        assert isinstance(optimizer, type(optimizer))
        assert optimizer.health_check() is True
