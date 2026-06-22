from services.master_agents import get_master_agents


class TestNewMasters:
    def test_limit_up_master_exists(self):
        registry = get_master_agents()
        master = registry.get_agent("limit_up_master")
        assert master is not None
        assert master.name == "limit_up_master"

    def test_momentum_master_exists(self):
        registry = get_master_agents()
        master = registry.get_agent("momentum_master")
        assert master is not None
        assert master.name == "momentum_master"

    def test_limit_up_master_high_score(self):
        registry = get_master_agents()
        master = registry.get_agent("limit_up_master")
        result = master.analyze(
            "600519",
            {
                "turnover_rate": 15.0,
                "daily_volume_ratio": 2.5,
                "change_pct": 5.0,
                "pe_ratio": 20,
            },
        )
        assert result["score"] >= 70
        assert "买入" in result["signal"]

    def test_limit_up_master_low_score(self):
        registry = get_master_agents()
        master = registry.get_agent("limit_up_master")
        result = master.analyze(
            "600519",
            {
                "turnover_rate": 1.0,
                "daily_volume_ratio": 0.5,
                "change_pct": 0.5,
                "pe_ratio": -10,
            },
        )
        assert result["score"] < 50
        assert "观望" in result["signal"]

    def test_momentum_master_with_prices(self):
        registry = get_master_agents()
        master = registry.get_agent("momentum_master")
        prices = [10 + i * 0.3 for i in range(30)]  # uptrend
        result = master.analyze(
            "600519",
            {
                "roe": 20,
                "revenue_growth_3y": 25,
                "pe_ratio": 20,
            },
            prices,
        )
        assert "score" in result
        assert "signal" in result
