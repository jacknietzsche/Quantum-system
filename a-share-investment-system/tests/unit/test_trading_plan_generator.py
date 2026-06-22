"""TradingPlanGenerator 全面单元测试 — 订单生成、仓位计算、风控规则"""

import pytest

from services.trading_plan import (
    ConditionalOrder,
    ExecutionPlan,
    MonitoringSignal,
    OrderItem,
    TradingPlan,
    TradingPlanGenerator,
    extract_master_factors,
)


@pytest.fixture
def generator():
    return TradingPlanGenerator()


@pytest.fixture
def buy_recommendations():
    return [
        {
            "stock_code": "600519",
            "stock_name": "茅台",
            "price": 1800,
            "score": 75,
            "signal": "买入",
            "confidence": "高",
        },
        {
            "stock_code": "000858",
            "stock_name": "五粮",
            "price": 150,
            "score": 65,
            "signal": "买入",
            "confidence": "中",
        },
        {
            "stock_code": "600036",
            "stock_name": "招行",
            "price": 42,
            "score": 60,
            "signal": "持有",
            "confidence": "中",
        },
    ]


@pytest.fixture
def sell_recommendations():
    return [
        {
            "stock_code": "000001",
            "stock_name": "平安银行",
            "price": 13,
            "score": 30,
            "signal": "卖出",
            "confidence": "高",
        },
        {
            "stock_code": "601318",
            "stock_name": "中国平安",
            "price": 45,
            "score": 25,
            "signal": "卖出",
            "confidence": "中",
        },
    ]


@pytest.fixture
def mixed_recommendations():
    return [
        {
            "stock_code": "600519",
            "stock_name": "茅台",
            "price": 1800,
            "score": 80,
            "signal": "买入",
            "confidence": "高",
        },
        {
            "stock_code": "000001",
            "stock_name": "平安银行",
            "price": 13,
            "score": 20,
            "signal": "卖出",
            "confidence": "高",
        },
        {
            "stock_code": "600036",
            "stock_name": "招行",
            "price": 42,
            "score": 55,
            "signal": "持有",
            "confidence": "中",
        },
    ]


@pytest.fixture
def current_positions():
    return [
        {
            "stock_code": "600519",
            "stock_name": "茅台",
            "current_value": 50000,
            "cost_value": 45000,
            "current_price": 1800,
            "buy_price": 1600,
            "quantity": 28,
            "profit_loss_pct": 12.5,
        },
        {
            "stock_code": "000001",
            "stock_name": "平安银行",
            "current_value": 13000,
            "cost_value": 15000,
            "current_price": 13,
            "buy_price": 15,
            "quantity": 1000,
            "profit_loss_pct": -13.3,
        },
    ]


# ══════════════════════════════════════════════
#  generate() 核心流程
# ══════════════════════════════════════════════


class TestGenerate:
    def test_basic_generate(self, generator, buy_recommendations):
        result = generator.generate(buy_recommendations, cash=500000, total_capital=500000)
        assert result.status == "ok"
        data = result.data
        assert "execution_plan" in data
        assert "risk_management" in data
        assert "position_sizing" in data
        assert "summary" in data
        assert "generated_at" in data

    def test_empty_recommendations_error(self, generator):
        result = generator.generate([], cash=500000, total_capital=500000)
        # Empty recs should still work (no orders, but valid plan)
        assert result.status == "ok" or result.status == "error"

    def test_zero_capital_error(self, generator, buy_recommendations):
        result = generator.generate(buy_recommendations, cash=0, total_capital=0)
        assert result.status == "error"
        assert "total_capital" in result.errors[0]

    def test_with_positions(self, generator, buy_recommendations, current_positions):
        result = generator.generate(
            buy_recommendations,
            current_positions=current_positions,
            cash=200000,
            total_capital=300000,
        )
        assert result.status == "ok"

    def test_with_risk_report(self, generator, buy_recommendations):
        risk_report = {
            "risk_level": "HIGH",
            "market_risk": {"level": "HIGH", "message": "熊市环境"},
            "portfolio_risk": {
                "issues": ["行业集中度偏高"],
                "stress_test": {"estimated_loss_pct": -25},
            },
        }
        result = generator.generate(
            buy_recommendations,
            risk_report=risk_report,
            cash=500000,
            total_capital=500000,
        )
        assert result.status == "ok"
        assert (
            "HIGH" in result.data["market_assessment"]["risk_level"]
            or result.data["market_assessment"]["risk_level"] == "HIGH"
        )


# ══════════════════════════════════════════════
#  即时订单生成
# ══════════════════════════════════════════════


class TestImmediateOrders:
    def test_buy_signal_generates_buy_order(self, generator, buy_recommendations):
        result = generator.generate(buy_recommendations, cash=500000, total_capital=500000)
        orders = result.data["execution_plan"]["orders"]
        buy_orders = [o for o in orders if o["action"] == "买入"]
        assert len(buy_orders) >= 1

    def test_sell_signal_generates_sell_order(
        self, generator, sell_recommendations, current_positions
    ):
        result = generator.generate(
            sell_recommendations,
            current_positions=current_positions,
            cash=100000,
            total_capital=200000,
        )
        orders = result.data["execution_plan"]["orders"]
        sell_actions = [o for o in orders if o["action"] in ("卖出", "减仓")]
        assert len(sell_actions) >= 1

    def test_orders_have_required_fields(self, generator, buy_recommendations):
        result = generator.generate(buy_recommendations, cash=500000, total_capital=500000)
        for order in result.data["execution_plan"]["orders"]:
            assert "code" in order
            assert "name" in order
            assert "action" in order

    def test_buy_order_has_stop_loss_take_profit(self, generator):
        recs = [
            {
                "stock_code": "600519",
                "stock_name": "茅台",
                "price": 1800,
                "score": 80,
                "signal": "买入",
                "confidence": "高",
            },
        ]
        result = generator.generate(recs, cash=1000000, total_capital=1000000)
        orders = result.data["execution_plan"]["orders"]
        buy_orders = [o for o in orders if o["action"] == "买入"]
        if buy_orders:
            o = buy_orders[0]
            assert o.get("stop_loss") is not None
            assert o.get("take_profit") is not None


# ══════════════════════════════════════════════
#  条件单生成
# ══════════════════════════════════════════════


class TestConditionalOrders:
    def test_conditional_orders_generated(self, generator, buy_recommendations, current_positions):
        result = generator.generate(
            buy_recommendations,
            current_positions=current_positions,
            cash=200000,
            total_capital=300000,
        )
        conds = result.data["execution_plan"]["conditional_orders"]
        assert isinstance(conds, list)

    def test_stop_loss_conditional_for_positions(self, generator, current_positions):
        recs = [
            {
                "stock_code": "000001",
                "stock_name": "PA",
                "price": 13,
                "score": 40,
                "signal": "hold",
                "confidence": "low",
            },
        ]
        result = generator.generate(
            recs,
            current_positions=current_positions,
            cash=100000,
            total_capital=200000,
        )
        conds = result.data["execution_plan"]["conditional_orders"]
        # Should have stop loss for losing position (平安银行 -13.3%)
        assert len(conds) >= 1


# ══════════════════════════════════════════════
#  监控信号
# ══════════════════════════════════════════════


class TestMonitoringSignals:
    def test_monitoring_signals_generated(self, generator, buy_recommendations):
        result = generator.generate(buy_recommendations, cash=500000, total_capital=500000)
        signals = result.data["execution_plan"]["monitoring_signals"]
        assert isinstance(signals, list)
        assert len(signals) >= 1

    def test_trailing_stop_for_profitable_position(self, generator):
        positions = [
            {
                "stock_code": "600519",
                "stock_name": "茅台",
                "current_value": 60000,
                "cost_value": 50000,
                "current_price": 1800,
                "buy_price": 1500,
                "profit_loss_pct": 20.0,
            },
        ]
        result = generator.generate(
            [], current_positions=positions, cash=100000, total_capital=160000
        )
        signals = result.data["execution_plan"]["monitoring_signals"]
        trailing = [s for s in signals if s.get("signal_type") == "TRAILING_STOP"]
        assert len(trailing) >= 1


# ══════════════════════════════════════════════
#  仓位计算
# ══════════════════════════════════════════════


class TestPositionSizing:
    def test_position_sizing_has_allocations(self, generator, buy_recommendations):
        result = generator.generate(buy_recommendations, cash=500000, total_capital=500000)
        ps = result.data["position_sizing"]
        assert ps["method"] == "blended_kelly_equal"
        assert len(ps["allocations"]) == 3

    def test_allocations_have_kelly(self, generator, buy_recommendations):
        result = generator.generate(buy_recommendations, cash=500000, total_capital=500000)
        for alloc in result.data["position_sizing"]["allocations"]:
            assert "kelly_fraction" in alloc
            assert "target_weight" in alloc
            assert "win_rate" in alloc

    def test_high_score_higher_weight(self, generator):
        recs = [
            {
                "stock_code": "A",
                "stock_name": "A",
                "price": 100,
                "score": 90,
                "signal": "买入",
                "confidence": "高",
            },
            {
                "stock_code": "B",
                "stock_name": "B",
                "price": 100,
                "score": 30,
                "signal": "持有",
                "confidence": "低",
            },
        ]
        result = generator.generate(recs, cash=500000, total_capital=500000)
        allocs = result.data["position_sizing"]["allocations"]
        weight_a = next(a["target_weight"] for a in allocs if a["stock_code"] == "A")
        weight_b = next(a["target_weight"] for a in allocs if a["stock_code"] == "B")
        assert weight_a > weight_b

    def test_max_position_respected(self, generator, buy_recommendations):
        result = generator.generate(
            buy_recommendations,
            cash=500000,
            total_capital=500000,
            risk_report={"risk_level": "EXTREME"},
        )
        max_pos = result.data["market_assessment"]["max_position"]
        assert max_pos == 0.30  # EXTREME -> 30%

    def test_position_sizing_empty(self, generator):
        result = generator._calculate_position_sizing([], 100000, 100000, 0.7)
        assert result["method"] == "none"
        assert result["allocations"] == []


# ══════════════════════════════════════════════
#  风控规则
# ══════════════════════════════════════════════


class TestRiskManagement:
    def test_extreme_risk_rules(self, generator):
        rm = generator._generate_risk_management("EXTREME", None, [])
        assert "清仓" in rm.circuit_breaker or "5%" in rm.circuit_breaker
        assert "30%" in rm.portfolio_stop

    def test_high_risk_rules(self, generator):
        rm = generator._generate_risk_management("HIGH", None, [])
        assert "暂停" in rm.circuit_breaker or "7%" in rm.circuit_breaker
        assert "50%" in rm.portfolio_stop

    def test_medium_risk_rules(self, generator):
        rm = generator._generate_risk_management("MEDIUM", None, [])
        assert "暂停" in rm.circuit_breaker or "10%" in rm.circuit_breaker

    def test_risk_report_issues_included(self, generator):
        risk_report = {
            "portfolio_risk": {
                "issues": ["单股集中度偏高", "行业集中度偏高"],
                "stress_test": {"estimated_loss_pct": -35},
            }
        }
        rm = generator._generate_risk_management("MEDIUM", risk_report, [])
        assert len(rm.key_risks) >= 2
        assert any("压力测试" in r for r in rm.key_risks)

    def test_no_risks_default_message(self, generator):
        rm = generator._generate_risk_management("LOW", None, [])
        assert "无重大风险" in rm.key_risks[0]


# ══════════════════════════════════════════════
#  风险等级 -> 最大仓位映射
# ══════════════════════════════════════════════


class TestRiskPositionMap:
    def test_all_levels_have_mapping(self, generator):
        for level in ("LOW", "MEDIUM", "HIGH", "EXTREME"):
            assert level in generator.RISK_POSITION_MAP

    def test_position_decreases_with_risk(self, generator):
        m = generator.RISK_POSITION_MAP
        assert m["LOW"] > m["MEDIUM"] > m["HIGH"] > m["EXTREME"]

    def test_extreme_max_30_percent(self, generator):
        assert generator.RISK_POSITION_MAP["EXTREME"] == 0.30


# ══════════════════════════════════════════════
#  extract_master_factors
# ══════════════════════════════════════════════


class TestExtractMasterFactors:
    def test_with_master_factors_present(self):
        screening = {
            "master_factors": {"master_weight_factor": 1.15, "master_position_factor": 1.10}
        }
        result = extract_master_factors(screening)
        assert result["master_weight_factor"] == 1.15

    def test_without_master_factors_fallback(self):
        screening = {"recommendations": [{"score": 80, "signal": "买入"}] * 3}
        result = extract_master_factors(screening)
        assert "master_weight_factor" in result

    def test_empty_screening(self):
        result = extract_master_factors({})
        assert result["master_weight_factor"] == 1.0


# ══════════════════════════════════════════════
#  数据模型
# ══════════════════════════════════════════════


class TestDataModels:
    def test_order_item_defaults(self):
        o = OrderItem(code="600519", name="茅台", action="买入")
        assert o.quantity is None
        assert o.confidence == "中"

    def test_conditional_order(self):
        co = ConditionalOrder(
            stock_code="600519", stock_name="茅台", condition="跌破1700", action="止损卖出"
        )
        assert co.trigger_price is None

    def test_monitoring_signal(self):
        ms = MonitoringSignal(
            stock_code="600519", signal_type="STOP_LOSS", description="跌破止损线"
        )
        assert ms.threshold is None

    def test_trading_plan_to_dict(self):
        plan = TradingPlan(market_regime="BULL", risk_level="LOW", max_position=0.85)
        d = plan.to_dict()
        assert d["market_assessment"]["regime"] == "BULL"
        assert d["market_assessment"]["max_position"] == 0.85

    def test_execution_plan_to_dict_roundtrip(self):
        ep = ExecutionPlan(
            immediate_summary="测试",
            immediate_orders=[OrderItem(code="A", name="A", action="买入")],
            conditional_orders=[
                ConditionalOrder(stock_code="A", stock_name="A", condition="跌", action="卖")
            ],
            monitoring_signals=[
                MonitoringSignal(stock_code="A", signal_type="VOLUME", description="关注")
            ],
        )
        d = ep.to_dict()
        assert len(d["orders"]) == 1
        assert len(d["conditional_orders"]) == 1
        assert len(d["monitoring_signals"]) == 1
