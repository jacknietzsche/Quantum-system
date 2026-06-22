"""测试交易计划数据模型"""

from services.trading_plan import ExecutionPlan, OrderItem, RiskManagement, TradingPlan


def test_trading_plan_defaults():
    plan = TradingPlan()
    assert plan.risk_level == "中等"
    assert plan.max_position == 0.7


def test_trading_plan_with_orders():
    plan = TradingPlan()
    plan.execution.immediate_orders.append(OrderItem(code="000001", name="平安银行", action="买入"))
    d = plan.to_dict()
    assert len(d["execution_plan"]["orders"]) == 1


def test_execution_plan_to_dict():
    ep = ExecutionPlan()
    ep.immediate_summary = "测试"
    ep.immediate_orders.append(
        OrderItem(code="000001", name="平安银行", action="买入", confidence="高")
    )
    d = ep.to_dict()
    assert d["immediate_summary"] == "测试"
    assert len(d["orders"]) == 1
    assert d["orders"][0]["action"] == "买入"


def test_risk_management_to_dict():
    rm = RiskManagement(circuit_breaker="单股亏损>8%止损", key_risks=["政策风险"])
    d = rm.to_dict()
    assert "circuit_breaker" in d
    assert len(d["key_risks"]) == 1


def test_trading_plan_with_master_position_factor():
    """master_position_factor should scale position weights multiplicatively"""
    from services.trading_plan import TradingPlanGenerator

    generator = TradingPlanGenerator()
    recommendations = [
        dict(
            stock_code="600519",
            stock_name="茅台",
            price=1500,
            score=55,
            signal="持有",
            confidence="中",
        ),
        dict(
            stock_code="000001",
            stock_name="平安",
            price=12,
            score=52,
            signal="持有",
            confidence="中",
        ),
        dict(
            stock_code="601318",
            stock_name="国平",
            price=45,
            score=58,
            signal="持有",
            confidence="中",
        ),
        dict(
            stock_code="000858",
            stock_name="五粮",
            price=130,
            score=54,
            signal="持有",
            confidence="中",
        ),
        dict(
            stock_code="600036",
            stock_name="招行",
            price=35,
            score=56,
            signal="持有",
            confidence="中",
        ),
        dict(
            stock_code="000333",
            stock_name="美的",
            price=60,
            score=53,
            signal="持有",
            confidence="中",
        ),
        dict(
            stock_code="002415",
            stock_name="海康",
            price=30,
            score=51,
            signal="持有",
            confidence="中",
        ),
        dict(
            stock_code="600276",
            stock_name="恒瑞",
            price=50,
            score=57,
            signal="持有",
            confidence="中",
        ),
        dict(
            stock_code="601888",
            stock_name="中免",
            price=80,
            score=55,
            signal="持有",
            confidence="中",
        ),
        dict(
            stock_code="000568",
            stock_name="老窖",
            price=200,
            score=56,
            signal="持有",
            confidence="中",
        ),
    ]
    r_low = generator.generate(
        recommendations=recommendations,
        cash=1000000,
        total_capital=1000000,
        master_position_factor=0.7,
    )
    r_mid = generator.generate(
        recommendations=recommendations,
        cash=1000000,
        total_capital=1000000,
        master_position_factor=1.0,
    )
    r_high = generator.generate(
        recommendations=recommendations,
        cash=1000000,
        total_capital=1000000,
        master_position_factor=1.3,
    )
    s_low = sum(a["target_weight"] for a in r_low.data["position_sizing"]["allocations"])
    s_mid = sum(a["target_weight"] for a in r_mid.data["position_sizing"]["allocations"])
    s_high = sum(a["target_weight"] for a in r_high.data["position_sizing"]["allocations"])
    assert s_high > s_mid > s_low


def test_trading_plan_with_master_weight_factor():
    """master_weight_factor should adjust scores before position sizing"""
    from services.trading_plan import TradingPlanGenerator, compute_factor_from_recommendations

    generator = TradingPlanGenerator()
    recommendations = [
        dict(
            stock_code="600519",
            stock_name="茅台",
            price=1500,
            score=80,
            signal="买入",
            confidence="高",
        ),
        dict(
            stock_code="000001",
            stock_name="平安",
            price=12,
            score=60,
            signal="持有",
            confidence="中",
        ),
        dict(
            stock_code="601318",
            stock_name="国平",
            price=45,
            score=40,
            signal="卖出",
            confidence="中",
        ),
    ]
    _factors = compute_factor_from_recommendations(recommendations)
    r1 = generator.generate(
        recommendations=recommendations,
        cash=500000,
        total_capital=500000,
        master_weight_factor=0.8,
        master_position_factor=0.8,
    )
    r2 = generator.generate(
        recommendations=recommendations,
        cash=500000,
        total_capital=500000,
        master_weight_factor=1.0,
        master_position_factor=1.0,
    )
    r3 = generator.generate(
        recommendations=recommendations,
        cash=500000,
        total_capital=500000,
        master_weight_factor=1.2,
        master_position_factor=1.2,
    )
    s1 = sum(a["target_weight"] for a in r1.data["position_sizing"]["allocations"])
    s2 = sum(a["target_weight"] for a in r2.data["position_sizing"]["allocations"])
    s3 = sum(a["target_weight"] for a in r3.data["position_sizing"]["allocations"])
    assert s3 > s2 > s1


def test_compute_factor_from_recommendations():
    from services.trading_plan import compute_factor_from_recommendations

    # All buy signals
    buy_recs = [dict(score=80, signal="买入")] * 5
    factors = compute_factor_from_recommendations(buy_recs)
    assert factors["master_weight_factor"] > 1.0
    assert factors["master_position_factor"] > 1.0

    # All sell signals
    sell_recs = [dict(score=30, signal="卖出")] * 5
    factors = compute_factor_from_recommendations(sell_recs)
    assert factors["master_weight_factor"] < 1.0
    assert factors["master_position_factor"] < 1.0

    # Empty
    factors = compute_factor_from_recommendations([])
    assert factors["master_weight_factor"] == 1.0
    assert factors["master_position_factor"] == 1.0
