"""PerformanceEngine 单元测试 — 绩效指标、NAV曲线、归因计算"""

from unittest.mock import patch

import pytest

from services.factor_validator import FactorValidator
from services.performance import AttributionResult, PerformanceEngine


@pytest.fixture
def engine():
    return PerformanceEngine()


@pytest.fixture
def nav_series_10d():
    """10天净值序列, 模拟上涨行情"""
    return [
        {
            "date": f"2024-01-{i:02d}",
            "nav": 1000000 + i * 5000,
            "daily_return": 0.005 if i > 0 else 0,
        }
        for i in range(1, 11)
    ]


@pytest.fixture
def nav_series_with_drawdown():
    """带回撤的净值序列"""
    return [
        {"date": "2024-01-01", "nav": 1000000, "daily_return": 0},
        {"date": "2024-01-02", "nav": 1050000, "daily_return": 0.05},
        {"date": "2024-01-03", "nav": 1100000, "daily_return": 0.0476},
        {"date": "2024-01-04", "nav": 990000, "daily_return": -0.1},
        {"date": "2024-01-05", "nav": 1020000, "daily_return": 0.0303},
        {"date": "2024-01-06", "nav": 1080000, "daily_return": 0.0588},
    ]


# ── 基础指标计算 ──


class TestPerformanceMetrics:
    """绩效指标计算测试"""

    def test_total_return_basic(self, engine, nav_series_10d):
        metrics = engine._calc_metrics(nav_series_10d, [])
        assert metrics.total_return_pct > 0
        assert metrics.trading_days == 10

    def test_total_return_zero(self, engine):
        series = [
            {"date": "2024-01-01", "nav": 1000000, "daily_return": 0},
            {"date": "2024-01-02", "nav": 1000000, "daily_return": 0},
        ]
        metrics = engine._calc_metrics(series, [])
        assert metrics.total_return_pct == 0.0

    def test_max_drawdown(self, engine, nav_series_with_drawdown):
        metrics = engine._calc_metrics(nav_series_with_drawdown, [])
        # Peak 1100000, trough 990000, drawdown = 10%
        assert metrics.max_drawdown_pct > 9.0
        assert metrics.max_drawdown_pct < 11.0

    def test_max_drawdown_date(self, engine, nav_series_with_drawdown):
        metrics = engine._calc_metrics(nav_series_with_drawdown, [])
        assert metrics.max_drawdown_date == "2024-01-04"

    def test_sharpe_ratio_positive_for_positive_returns(self, engine, nav_series_10d):
        metrics = engine._calc_metrics(nav_series_10d, [])
        assert metrics.sharpe_ratio > 0

    def test_annualized_return(self, engine, nav_series_10d):
        metrics = engine._calc_metrics(nav_series_10d, [])
        # Should be positive for upward series
        assert metrics.annualized_return_pct > 0

    def test_win_rate(self, engine, nav_series_10d):
        metrics = engine._calc_metrics(nav_series_10d, [])
        # All daily returns are positive (0.005)
        assert metrics.win_rate_pct == 100.0

    def test_calmar_ratio(self, engine, nav_series_with_drawdown):
        metrics = engine._calc_metrics(nav_series_with_drawdown, [])
        if metrics.max_drawdown_pct > 0:
            expected = metrics.annualized_return_pct / metrics.max_drawdown_pct
            assert abs(metrics.calmar_ratio - expected) < 0.01

    def test_metrics_to_dict(self, engine, nav_series_10d):
        metrics = engine._calc_metrics(nav_series_10d, [])
        d = metrics.to_dict()
        assert "total_return_pct" in d
        assert "sharpe_ratio" in d
        assert "max_drawdown_pct" in d
        assert "win_rate_pct" in d
        assert isinstance(d["total_return_pct"], float)

    def test_insufficient_data(self, engine):
        series = [{"date": "2024-01-01", "nav": 1000000, "daily_return": 0}]
        metrics = engine._calc_metrics(series, [])
        assert metrics.trading_days == 1
        assert metrics.total_return_pct == 0.0


# ── 统计工具 ──


class TestStatisticalTools:
    """统计工具函数测试"""

    def test_std_basic(self):
        values = [1.0, 2.0, 3.0, 4.0, 5.0]
        result = PerformanceEngine._std(values)
        assert abs(result - 1.5811) < 0.01

    def test_std_single_value(self):
        assert PerformanceEngine._std([1.0]) == 0.0

    def test_std_empty(self):
        assert PerformanceEngine._std([]) == 0.0

    def test_max_drawdown_no_drawdown(self):
        series = [
            {"date": "2024-01-01", "nav": 100},
            {"date": "2024-01-02", "nav": 200},
            {"date": "2024-01-03", "nav": 300},
        ]
        dd = PerformanceEngine._max_drawdown(series)
        assert dd["max_drawdown_pct"] == 0.0

    def test_max_drawdown_full(self):
        series = [
            {"date": "2024-01-01", "nav": 100},
            {"date": "2024-01-02", "nav": 50},
        ]
        dd = PerformanceEngine._max_drawdown(series)
        assert abs(dd["max_drawdown_pct"] - 50.0) < 0.01

    def test_beta_identical_returns(self):
        returns = [0.01, -0.02, 0.03, -0.01, 0.02] * 5
        assert abs(PerformanceEngine._beta(returns, returns) - 1.0) < 0.01

    def test_beta_uncorrelated(self):
        p = [0.01, -0.01, 0.01, -0.01] * 10
        b = [0.0, 0.0, 0.0, 0.0] * 10
        beta = PerformanceEngine._beta(p, b)
        # Should be 0 or undefined
        assert isinstance(beta, float)

    def test_rank_correlation_perfect(self):
        x = [1, 2, 3, 4, 5]
        y = [10, 20, 30, 40, 50]
        corr = FactorValidator._rank_correlation(x, y)
        assert abs(corr - 1.0) < 0.01

    def test_rank_correlation_inverse(self):
        x = [1, 2, 3, 4, 5]
        y = [50, 40, 30, 20, 10]
        corr = FactorValidator._rank_correlation(x, y)
        assert abs(corr - (-1.0)) < 0.01

    def test_pearson_correlation_perfect(self):
        x = [1.0, 2.0, 3.0, 4.0, 5.0]
        y = [2.0, 4.0, 6.0, 8.0, 10.0]
        corr = FactorValidator._pearson_correlation(x, y)
        assert abs(corr - 1.0) < 0.01

    def test_pearson_correlation_short(self):
        assert FactorValidator._pearson_correlation([1.0], [2.0]) == 0.0


# ── 归因计算 ──


class TestAttribution:
    """收益归因测试"""

    def test_attribution_empty_holdings(self, engine):
        with patch("shared.models.get_session") as mock_session:
            mock_session.return_value.query.return_value.filter_by.return_value.all.return_value = []
            result = engine._calc_attribution("value", [])
            assert result.selection_return_pct == 0.0
            assert result.top_contributors == []


# ── 完整流程 ──


class TestComputePerformance:
    """完整绩效计算流程测试"""

    def test_compute_with_no_nav(self, engine):
        with patch.object(engine, "_get_nav_series", return_value=[]):
            result = engine.compute_performance("value")
            assert result.status == "degraded"

    def test_compute_with_nav(self, engine, nav_series_10d):
        with (
            patch.object(engine, "_get_nav_series", return_value=nav_series_10d),
            patch.object(engine, "_get_benchmark_series", return_value=[]),
            patch.object(engine, "_calc_attribution", return_value=AttributionResult()),
        ):
            result = engine.compute_performance("value")
            assert result.status == "ok"
            assert "metrics" in result.data
            assert "nav_curve" in result.data

    def test_yearly_breakdown_empty(self, engine):
        with patch.object(engine, "_get_nav_series", return_value=[]):
            result = engine.get_yearly_breakdown("value")
            assert result.status == "ok"


class TestAttributionWithHoldings:
    """Attribution with actual holdings data"""

    def test_attribution_single_holding(self, engine):
        """Single holding with known return"""

        nav_series = [
            {"date": "2024-01-02", "nav": 1_000_000, "daily_return": 0},
            {"date": "2024-01-03", "nav": 1_010_000, "daily_return": 0.01},
            {"date": "2024-01-04", "nav": 1_005_000, "daily_return": -0.005},
        ]
        with (
            patch.object(engine, "_get_nav_series", return_value=nav_series),
            patch.object(engine, "_get_benchmark_series", return_value=[]),
        ):
            result = engine.compute_performance("value", days=10)

        assert result.status == "ok"
        assert "attribution" in result.data

    def test_compute_with_benchmark(self, engine):
        """Performance with benchmark comparison"""
        nav_series = [
            {"date": f"2024-01-{d:02d}", "nav": 1_000_000 + d * 1000, "daily_return": 0.001}
            for d in range(2, 32)
        ]
        benchmark = [{"date": f"2024-01-{d:02d}", "nav": 1_000_000 + d * 500} for d in range(2, 32)]
        with (
            patch.object(engine, "_get_nav_series", return_value=nav_series),
            patch.object(engine, "_get_benchmark_series", return_value=benchmark),
        ):
            result = engine.compute_performance("value", days=50)

        assert result.status == "ok"
        metrics = result.data["metrics"]
        assert metrics["benchmark_return_pct"] != 0

    def test_compute_metrics_dict_fields(self, engine):
        """All expected metric fields present"""
        nav_series = [
            {"date": "2024-01-02", "nav": 100, "daily_return": 0},
            {"date": "2024-01-03", "nav": 110, "daily_return": 0.1},
            {"date": "2024-01-04", "nav": 105, "daily_return": -0.045},
        ]
        with (
            patch.object(engine, "_get_nav_series", return_value=nav_series),
            patch.object(engine, "_get_benchmark_series", return_value=[]),
        ):
            result = engine.compute_performance("value", days=10)

        m = result.data["metrics"]
        expected = [
            "total_return_pct",
            "sharpe_ratio",
            "max_drawdown_pct",
            "win_rate_pct",
            "calmar_ratio",
            "trading_days",
        ]
        for key in expected:
            assert key in m, f"Missing metric: {key}"


class TestGetNavCurve:
    """Test get_nav_curve method"""

    def test_nav_curve_basic(self, engine):
        nav_series = [
            {"date": "2024-01-02", "nav": 100, "daily_return": 0},
            {"date": "2024-01-03", "nav": 110, "daily_return": 0.1},
        ]
        with patch.object(engine, "_get_nav_series", return_value=nav_series):
            result = engine.get_nav_curve("value", days=10)
        assert result.status == "ok"
        assert len(result.data["nav_curve"]) == 2

    def test_nav_curve_empty(self, engine):
        with patch.object(engine, "_get_nav_series", return_value=[]):
            result = engine.get_nav_curve("value", days=10)
        assert result.status == "ok"
        assert result.data["nav_curve"] == []
