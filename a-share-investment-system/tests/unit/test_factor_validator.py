"""FactorValidator 单元测试 — IC分析、相关性矩阵、样本外验证"""

import pytest

from services.factor_validator import FactorICResult, FactorValidator


@pytest.fixture
def validator():
    return FactorValidator()


@pytest.fixture
def sample_price_data():
    """模拟3只股票、20天的价格数据"""
    import random

    random.seed(42)
    data = {}
    for code in ["600519", "000001", "000858"]:
        bars = []
        price = 100.0
        for i in range(30):
            change = random.uniform(-0.03, 0.03)
            price *= 1 + change
            bars.append({"date": f"2024-01-{i + 1:02d}", "close": round(price, 2)})
        data[code] = bars
    return data


@pytest.fixture
def sample_factor_data():
    """模拟因子数据"""
    data = {}
    for i in range(30):
        date = f"2024-01-{i + 1:02d}"
        data[date] = {
            "momentum": 0.05 if i % 3 == 0 else -0.02,
            "value": 0.1 if i % 2 == 0 else -0.05,
            "quality": 0.03 if i > 15 else -0.01,
        }
    return data


# ── 单因子验证 ──


class TestSingleFactorValidation:
    def test_validate_single_basic(self, validator):
        factors = [
            0.1,
            0.2,
            -0.1,
            0.15,
            -0.05,
            0.3,
            -0.2,
            0.08,
            0.12,
            -0.03,
            0.25,
            -0.15,
            0.18,
            0.05,
            -0.08,
            0.22,
            -0.12,
            0.09,
            0.14,
            -0.06,
        ]
        returns = [
            0.02,
            0.03,
            -0.01,
            0.025,
            -0.005,
            0.04,
            -0.03,
            0.01,
            0.02,
            -0.003,
            0.03,
            -0.02,
            0.028,
            0.008,
            -0.01,
            0.035,
            -0.015,
            0.012,
            0.022,
            -0.008,
        ]
        result = validator.validate_single("test_factor", factors, returns)
        assert result.status == "ok"

    def test_validate_single_mismatch(self, validator):
        result = validator.validate_single("test", [1, 2, 3], [1, 2])
        assert result.status == "error"

    def test_validate_single_too_short(self, validator):
        result = validator.validate_single("test", [1, 2, 3], [1, 2, 3])
        assert result.status == "error"


# ── 全量验证 ──


class TestFullValidation:
    def test_validate_all_basic(self, validator, sample_price_data, sample_factor_data):
        result = validator.validate_all(sample_price_data, sample_factor_data)
        assert result.status == "ok"
        data = result.data
        assert "factor_results" in data
        assert "correlation" in data
        assert "significant_factors" in data
        assert "sample_info" in data

    def test_validate_all_factor_count(self, validator, sample_price_data, sample_factor_data):
        result = validator.validate_all(sample_price_data, sample_factor_data)
        assert len(result.data["factor_results"]) == 3  # momentum, value, quality

    def test_validate_all_empty_factor_data(self, validator):
        result = validator.validate_all({}, {})
        assert result.status == "error"

    def test_validate_all_insufficient_dates(self, validator):
        prices = {
            "600519": [{"date": "2024-01-01", "close": 100}, {"date": "2024-01-02", "close": 101}]
        }
        factors = {"2024-01-01": {"f1": 0.1}, "2024-01-02": {"f1": 0.2}}
        result = validator.validate_all(prices, factors)
        assert result.status == "error"

    def test_validate_all_sample_info(self, validator, sample_price_data, sample_factor_data):
        result = validator.validate_all(sample_price_data, sample_factor_data, train_ratio=0.7)
        info = result.data["sample_info"]
        assert info["factor_count"] == 3
        assert info["train_dates"] > 0
        assert info["test_dates"] > 0


# ── 相关性矩阵 ──


class TestCorrelationMatrix:
    def test_correlation_basic(self, validator, sample_factor_data):
        dates = sorted(sample_factor_data.keys())
        corr = validator._calc_correlation_matrix(["momentum", "value"], sample_factor_data, dates)
        assert len(corr.factors) == 2
        assert len(corr.matrix) == 2
        assert corr.matrix[0][0] == 1.0  # Self-correlation
        assert corr.matrix[1][1] == 1.0

    def test_correlation_high_pairs(self, validator):
        # Perfectly correlated factors
        data = {}
        for i in range(30):
            date = f"2024-01-{i + 1:02d}"
            val = 0.1 if i % 2 == 0 else -0.1
            data[date] = {"factor_a": val, "factor_b": val * 2}
        dates = sorted(data.keys())
        corr = validator._calc_correlation_matrix(["factor_a", "factor_b"], data, dates)
        assert len(corr.high_corr_pairs) > 0


# ── 统计工具 ──


class TestStatTools:
    def test_rank_correlation_perfect(self, validator):
        x = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
        y = [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
        corr = validator._rank_correlation(x, y)
        assert abs(corr - 1.0) < 0.01

    def test_rank_correlation_inverse(self, validator):
        x = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
        y = [100, 90, 80, 70, 60, 50, 40, 30, 20, 10]
        corr = validator._rank_correlation(x, y)
        assert abs(corr + 1.0) < 0.01

    def test_pearson_perfect_positive(self, validator):
        x = [1.0, 2.0, 3.0, 4.0, 5.0]
        y = [2.0, 4.0, 6.0, 8.0, 10.0]
        corr = validator._pearson_correlation(x, y)
        assert abs(corr - 1.0) < 0.001

    def test_pearson_short(self, validator):
        assert validator._pearson_correlation([1.0], [2.0]) == 0.0


# ── IC结果 ──


class TestICResult:
    def test_ic_result_to_dict(self):
        result = FactorICResult(
            factor_name="test",
            ic_mean=0.05,
            icir=1.2,
            is_significant=True,
        )
        d = result.to_dict()
        assert d["factor_name"] == "test"
        assert d["ic_mean"] == 0.05
        assert d["is_significant"] == True
