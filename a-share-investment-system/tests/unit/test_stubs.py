"""Unit tests for workflows.stubs utility classes."""


class TestTokenBudget:
    def test_allocate_basic(self):
        from workflows.stubs import TokenBudget

        tb = TokenBudget(max_tokens=100)
        assert tb.allocate(30) == 30
        assert tb.allocate(30) == 30
        assert tb.used == 60

    def test_allocate_exceeds_remaining(self):
        from workflows.stubs import TokenBudget

        tb = TokenBudget(max_tokens=50)
        assert tb.allocate(30) == 30
        assert tb.allocate(30) == 20  # only 20 remaining

    def test_exhausted(self):
        from workflows.stubs import TokenBudget

        tb = TokenBudget(max_tokens=10)
        assert not tb.exhausted
        tb.allocate(10)
        assert tb.exhausted

    def test_zero_budget(self):
        from workflows.stubs import TokenBudget

        tb = TokenBudget(max_tokens=0)
        assert tb.allocate(10) == 0
        assert tb.exhausted


class TestTieredVoter:
    def test_should_activate_fincept_low_consistency(self):
        from workflows.stubs import TieredVoter

        tv = TieredVoter(high_threshold=0.8)
        assert tv.should_activate_fincept({"consistency": 0.5}) is True

    def test_should_not_activate_fincept_high_consistency(self):
        from workflows.stubs import TieredVoter

        tv = TieredVoter(high_threshold=0.8)
        assert tv.should_activate_fincept({"consistency": 0.9}) is False

    def test_evaluate_consistency_unanimous(self):
        from workflows.stubs import TieredVoter

        tv = TieredVoter()
        votes = {"a": {"signal": "buy"}, "b": {"signal": "buy"}, "c": {"signal": "buy"}}
        assert tv.evaluate_consistency(votes) == 1.0

    def test_evaluate_consistency_split(self):
        from workflows.stubs import TieredVoter

        tv = TieredVoter()
        votes = {"a": {"signal": "buy"}, "b": {"signal": "sell"}}
        assert tv.evaluate_consistency(votes) == 0.5

    def test_evaluate_consistency_empty(self):
        from workflows.stubs import TieredVoter

        tv = TieredVoter()
        assert tv.evaluate_consistency({}) == 0.0

    def test_evaluate_consistency_non_dict_value(self):
        from workflows.stubs import TieredVoter

        tv = TieredVoter()
        votes = {"a": "not_a_dict", "b": "also_not"}
        assert tv.evaluate_consistency(votes) == 0.0


class TestRiskQuadrantEngine:
    def test_low_risk_expansion(self):
        from workflows.stubs import RiskQuadrantEngine

        mcq = RiskQuadrantEngine()
        result = mcq.evaluate(30, "expansion")
        assert "quadrant" in result
        assert result["max_position_pct"] > 0

    def test_high_risk_trough(self):
        from workflows.stubs import RiskQuadrantEngine

        mcq = RiskQuadrantEngine()
        result = mcq.evaluate(70, "trough")
        assert result["max_position_pct"] <= 0.30

    def test_unknown_cycle_returns_default(self):
        from workflows.stubs import RiskQuadrantEngine

        mcq = RiskQuadrantEngine()
        result = mcq.evaluate(30, "unknown_cycle_xyz")
        assert "quadrant" in result


class TestStrategyMonitor:
    def test_calculate_metrics_empty(self):
        from workflows.stubs import StrategyMonitor

        sm = StrategyMonitor()
        result = sm.calculate_metrics([])
        assert result["sharpe_ratio"] == 0
        assert result["max_drawdown"] == 0

    def test_calculate_metrics_single(self):
        from workflows.stubs import StrategyMonitor

        sm = StrategyMonitor()
        result = sm.calculate_metrics([0.01])
        assert result["sharpe_ratio"] == 0

    def test_calculate_metrics_positive_returns(self):
        from workflows.stubs import StrategyMonitor

        sm = StrategyMonitor()
        returns = [0.01, 0.02, -0.01, 0.015, -0.005, 0.01, 0.02, -0.01, 0.005, 0.01]
        result = sm.calculate_metrics(returns)
        assert result["win_rate"] > 0
        assert result["max_drawdown"] <= 0

    def test_check_alerts_low_sharpe(self):
        from workflows.stubs import StrategyMonitor

        sm = StrategyMonitor()
        alerts = sm.check_alerts({"sharpe_ratio": 0.2})
        assert len(alerts) >= 1
        assert "sharpe" in alerts[0]["message"].lower() or "WARNING" in alerts[0]["level"]

    def test_check_alerts_high_drawdown(self):
        from workflows.stubs import StrategyMonitor

        sm = StrategyMonitor()
        alerts = sm.check_alerts({"sharpe_ratio": 1.0, "max_drawdown": -0.30})
        assert any("CRITICAL" in a["level"] for a in alerts)

    def test_check_alerts_no_alerts(self):
        from workflows.stubs import StrategyMonitor

        sm = StrategyMonitor()
        alerts = sm.check_alerts({"sharpe_ratio": 1.5, "max_drawdown": -0.05})
        assert len(alerts) == 0


class TestFaultTolerantNode:
    def test_success_passthrough(self):
        from workflows.stubs import FaultTolerantNode

        ft = FaultTolerantNode(node_name="test")

        @ft
        def my_func():
            return {"result": "ok"}

        assert my_func() == {"result": "ok"}

    def test_failure_returns_default(self):
        from workflows.stubs import FaultTolerantNode

        ft = FaultTolerantNode(default={"fallback": True}, node_name="test")

        @ft
        def my_func():
            raise ValueError("boom")

        result = my_func()
        assert result == {"fallback": True}

    def test_preserves_name(self):
        from workflows.stubs import FaultTolerantNode

        ft = FaultTolerantNode(node_name="test")

        @ft
        def my_func():
            return 1

        assert my_func.__name__ == "my_func"
        assert my_func._fault_tolerant is True


class TestLookAheadBiasAuditor:
    def test_no_warnings(self):
        from workflows.stubs import LookAheadBiasAuditor

        auditor = LookAheadBiasAuditor()
        state = {"logs": [], "date": "2025-01-15", "_data_dates": ["2025-01-14", "2025-01-13"]}
        result = auditor.audit(state)
        assert result["pass"] is True
        assert len(result["warnings"]) == 0

    def test_future_data_warning(self):
        from workflows.stubs import LookAheadBiasAuditor

        auditor = LookAheadBiasAuditor()
        state = {"logs": [], "date": "2025-01-15", "_data_dates": ["2025-01-16", "2025-01-14"]}
        result = auditor.audit(state)
        assert result["pass"] is False
        assert len(result["warnings"]) == 1

    def test_empty_dates(self):
        from workflows.stubs import LookAheadBiasAuditor

        auditor = LookAheadBiasAuditor()
        state = {"logs": [], "date": "2025-01-15", "_data_dates": []}
        result = auditor.audit(state)
        assert result["pass"] is True
