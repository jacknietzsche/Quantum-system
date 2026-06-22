"""LLM Router 单元测试"""

from services.llm_router import (
    TASK_TIER_MAP,
    TIER_CONFIG,
    LLMRouter,
    ProviderStats,
)


class TestProviderStats:
    def test_initial_success_rate_defaults_to_05(self):
        stats = ProviderStats()
        assert stats.success_rate == 0.5

    def test_success_rate_after_records(self):
        stats = ProviderStats()
        stats.record(True, 1.0)
        stats.record(True, 0.5)
        stats.record(False, 2.0)
        assert stats.success_rate == 2 / 3
        assert stats.total_calls == 3
        assert stats.avg_latency == (1.0 + 0.5 + 2.0) / 3

    def test_recent_successes_capped_at_20(self):
        stats = ProviderStats()
        for _ in range(25):
            stats.record(True, 0.5)
        assert len(stats.recent_successes) == 20


class TestHealthScore:
    def test_health_score_basic(self):
        router = LLMRouter()
        # No stats recorded yet → default health score
        score = router.health_score("siliconflow")
        assert 0 < score <= 100

    def test_health_score_successful_provider_higher(self):
        router = LLMRouter()
        for _ in range(10):
            router._record_success("provider_a", 0.5)
        for _ in range(5):
            router._record_failure("provider_b", 2.0)
        score_a = router.health_score("provider_a")
        score_b = router.health_score("provider_b")
        assert score_a > score_b


class TestTaskTierMap:
    def test_all_tasks_have_tier(self):
        for task in (
            "debate",
            "decision",
            "deep_analysis",
            "stock_analysis",
            "portfolio",
            "pre_screen",
            "simple_score",
        ):
            assert task in TASK_TIER_MAP, f"{task} missing from TASK_TIER_MAP"

    def test_tier_configs_exist(self):
        for tier in ("premium", "standard", "budget"):
            assert tier in TIER_CONFIG
            assert "models" in TIER_CONFIG[tier]
            assert "timeout" in TIER_CONFIG[tier]
            assert "max_tokens" in TIER_CONFIG[tier]
