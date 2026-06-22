"""双层股票分析缓存 单元测试"""

import pytest

from services.stock_cache import (
    MAX_SEMANTIC_ENTRIES,
    StockAnalysisCache,
    _norm,
    cosine_similarity,
    extract_feature_vector,
)


class TestFeatureExtraction:
    def test_extract_feature_vector_returns_10d(self):
        data = {
            "pe": 15,
            "pb": 2,
            "roe": 20,
            "market_cap": 500,
            "turnover_rate": 5,
            "volume_ratio": 1.5,
            "change_pct_5d": 10,
            "change_pct_60d": 30,
            "debt_to_equity": 50,
            "gross_margin": 40,
        }
        vec = extract_feature_vector(data)
        assert len(vec) == 10
        assert all(0 <= v <= 1 for v in vec)

    def test_norm_clamps_values(self):
        assert _norm(1000, 0, 100) == 1.0
        assert _norm(-100, 0, 100) == 0.0
        assert _norm(50, 0, 100) == 0.5
        assert _norm(None, 0, 100) == 0.5

    def test_cosine_similarity_identical(self):
        a = [1, 0, 1, 0, 0.5, 0.5, 1, 0, 0, 0]
        assert cosine_similarity(a, a) == pytest.approx(1.0, abs=0.001)

    def test_cosine_similarity_orthogonal(self):
        a = [1, 0, 0, 0, 0, 0, 0, 0, 0, 0]
        b = [0, 1, 0, 0, 0, 0, 0, 0, 0, 0]
        assert cosine_similarity(a, b) == 0.0


class TestStockAnalysisCache:
    def test_l1_exact_match(self):
        cache = StockAnalysisCache()
        data = {"score": 85, "signal": "买入"}
        cache.set_exact("000001", "hybrid", data, price=10.0)
        result = cache.get_exact("000001", "hybrid")
        assert result is not None
        assert result["score"] == 85

    def test_l1_miss_returns_none(self):
        cache = StockAnalysisCache()
        assert cache.get_exact("999999", "unknown") is None

    def test_l2_semantic_similar(self):
        cache = StockAnalysisCache()
        data1 = {
            "score": 80,
            "pe": 15,
            "pb": 2,
            "roe": 20,
            "market_cap": 500,
            "turnover_rate": 3,
            "volume_ratio": 1.2,
            "change_pct_5d": 8,
            "change_pct_60d": 25,
            "debt_to_equity": 40,
            "gross_margin": 35,
        }
        cache._add_to_l2("000001", "hybrid", data1, price=10.0)

        data2 = {
            "score": 0,
            "pe": 16,
            "pb": 2.1,
            "roe": 19,
            "market_cap": 480,
            "turnover_rate": 3.2,
            "volume_ratio": 1.3,
            "change_pct_5d": 7.5,
            "change_pct_60d": 24,
            "debt_to_equity": 42,
            "gross_margin": 36,
        }
        result = cache.get_semantic("000002", "hybrid", data2)
        assert result is not None
        assert result["score"] == 80

    def test_l2_dissimilar_returns_none(self):
        cache = StockAnalysisCache()
        data1 = {
            "score": 80,
            "pe": 15,
            "pb": 2,
            "roe": 20,
            "market_cap": 500,
            "turnover_rate": 3,
            "volume_ratio": 1.2,
            "change_pct_5d": 8,
            "change_pct_60d": 25,
            "debt_to_equity": 40,
            "gross_margin": 35,
        }
        cache._add_to_l2("000001", "hybrid", data1, price=10.0)

        data2 = {
            "score": 0,
            "pe": 80,
            "pb": 15,
            "roe": -5,
            "market_cap": 10,
            "turnover_rate": 0.1,
            "volume_ratio": 0.2,
            "change_pct_5d": -15,
            "change_pct_60d": -40,
            "debt_to_equity": 300,
            "gross_margin": 5,
        }
        result = cache.get_semantic("000002", "hybrid", data2)
        assert result is None

    def test_invalidate_by_code(self):
        cache = StockAnalysisCache()
        cache._add_to_l2("000001", "hybrid", {"score": 80}, price=10.0)
        cache.invalidate("000001")
        assert len(cache._l2_entries) == 0

    def test_invalidate_by_price_change(self):
        cache = StockAnalysisCache()
        cache._add_to_l2("000001", "hybrid", {"score": 80}, price=10.0)
        cache.invalidate("000001", price=15.0)
        assert len(cache._l2_entries) == 0

    def test_invalidate_by_market_state(self):
        cache = StockAnalysisCache()
        cache._add_to_l2("000001", "hybrid", {"score": 80}, price=10.0)
        cache.invalidate_by_market_state("BULL", "BEAR")
        assert len(cache._l2_entries) == 0

    def test_invalidate_same_state_keeps_entries(self):
        cache = StockAnalysisCache()
        cache._add_to_l2("000001", "hybrid", {"score": 80}, price=10.0)
        cache.invalidate_by_market_state("BULL", "BULL")
        assert len(cache._l2_entries) > 0

    def test_max_entries_enforced(self):
        cache = StockAnalysisCache()
        for i in range(100):
            cache._add_to_l2(f"{i:06d}", "hybrid", {"score": i}, price=10.0)
        with cache._lock:
            assert len(cache._l2_entries) <= MAX_SEMANTIC_ENTRIES + 100
