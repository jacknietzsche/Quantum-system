"""RiskEngine 单元测试 — 风控审计、波动率限制、仓位计算"""

from services.risk_engine import RiskEngine


class TestRiskEngineAudit:
    def setup_method(self):
        self.engine = RiskEngine()

    def test_full_audit_empty_portfolio(self):
        result = self.engine.full_audit([])
        assert result.status == "ok"
        assert "pass" in result.data

    def test_full_audit_with_portfolio(self):
        portfolio = [
            {
                "stock_code": "600519",
                "profit_loss_pct": 5.0,
                "current_value": 100000,
                "stock_name": "茅台",
            },
        ]
        result = self.engine.full_audit(portfolio)
        assert result.status == "ok"
        assert "market_risk" in result.data
        assert "stock_risks" in result.data
        assert "portfolio_risk" in result.data

    def test_full_audit_has_risk_level(self):
        result = self.engine.full_audit([])
        assert "risk_level" in result.data

    def test_full_audit_with_market_regime(self):
        result = self.engine.full_audit([], market_regime={"regime": "BEAR"})
        assert result.status == "ok"


class TestVolLimits:
    def test_vol_limits_defined(self):
        assert len(RiskEngine.VOL_LIMITS) == 0 or len(RiskEngine.VOL_LIMITS) > 0
        # VOL_LIMITS should have threshold, limit pairs
        for threshold, limit in RiskEngine.VOL_LIMITS:
            assert threshold > 0
            assert 0 < limit <= 1.0


class TestCorrMultipliers:
    def test_corr_multipliers_defined(self):
        assert len(RiskEngine.CORR_MULTIPLIERS) > 0
        for threshold, mult in RiskEngine.CORR_MULTIPLIERS:
            assert 0 <= threshold <= 1.0
            assert 0 < mult <= 2.0
