"""Tests for services/trading_orchestrator.py"""

from __future__ import annotations

from unittest.mock import MagicMock, patch


class TestTradingStrategyOrchestrator:
    def _make(self, llm_configs=None):
        with (
            patch("services.trading_orchestrator.Config") as MC,
            patch("services.trading_orchestrator.get_router") as mrouter,
        ):
            cfg = MC.return_value
            cfg.get.side_effect = lambda k, d=None: {
                "screening.deep_analysis.ensemble_top_k": 8,
                "screening.deep_analysis.parallel_limit": 3,
                "screening.styles.hybrid.stage3": {
                    "max_adjustment": 15,
                    "force_dissent_review": False,
                },
                "llm_providers": {
                    "deepseek": {"api_key": "k", "base_url": "https://api.deepseek.com/v1"}
                },
                "screening.deep_analysis.models": ["deepseek:deepseek-v4-pro"],
            }.get(k, d)
            mock_router = MagicMock()
            mock_router.get_available_providers.return_value = []
            mrouter.return_value = mock_router
            from services.trading_orchestrator import TradingStrategyOrchestrator

            orch = TradingStrategyOrchestrator(style="hybrid")
            if llm_configs is not None:
                orch.llm_configs = llm_configs
            return orch

    def test_init(self):
        orch = self._make()
        assert orch.style == "hybrid"
        assert len(orch.llm_configs) >= 1

    def test_simple_plan(self):
        orch = self._make()
        result = orch._generate_simple_plan(
            [
                {"stock_code": "600519", "stock_name": "M", "score": 80},
                {"stock_code": "000858", "stock_name": "W", "score": 70},
            ]
        )
        assert result["style"] == "hybrid"
        assert len(result["stock_opinions"]) == 2

    def test_simple_plan_empty(self):
        orch = self._make()
        result = orch._generate_simple_plan([])
        assert len(result["stock_opinions"]) == 0

    def test_run_too_few(self):
        orch = self._make()
        orch._progress = MagicMock()
        result = orch.run([{"stock_code": "600519"}])
        assert "stock_opinions" in result

    def test_run_no_configs(self):
        orch = self._make(llm_configs=[])
        orch._progress = MagicMock()
        result = orch.run(
            [{"stock_code": "600519"}, {"stock_code": "000858"}, {"stock_code": "000001"}]
        )
        assert "stock_opinions" in result

    @patch("services.trading_orchestrator.get_router")
    @patch("services.trading_orchestrator.Config")
    def test_resolve_multi(self, MC, mr):
        cfg = MC.return_value
        cfg.get.side_effect = lambda k, d=None: {
            "llm_providers": {
                "deepseek": {"api_key": "k", "base_url": "https://api.deepseek.com/v1"}
            },
            "screening.deep_analysis.models": ["deepseek:deepseek-v4-pro"],
        }.get(k, d)
        mr.return_value.get_available_providers.return_value = []
        from services.trading_orchestrator import TradingStrategyOrchestrator

        configs = TradingStrategyOrchestrator.resolve_multi_llm_configs()
        assert len(configs) == 1

    @patch("services.trading_orchestrator.get_router")
    @patch("services.trading_orchestrator.Config")
    def test_resolve_multi_no_key(self, MC, mr):
        cfg = MC.return_value
        cfg.get.side_effect = lambda k, d=None: {
            "llm_providers": {"deepseek": {"api_key": ""}},
            "screening.deep_analysis.models": ["deepseek:model"],
        }.get(k, d)
        mr.return_value.get_available_providers.return_value = []
        from services.trading_orchestrator import TradingStrategyOrchestrator

        assert TradingStrategyOrchestrator.resolve_multi_llm_configs() == []

    def test_progress(self):
        orch = self._make()
        cb = MagicMock()
        orch.progress_callback = cb
        orch._progress(50, "test")
        cb.assert_called_once_with(50, "test")

    def test_simple_plan_opinions(self):
        orch = self._make()
        result = orch._generate_simple_plan(
            [
                {"stock_code": "600519", "stock_name": "M", "score": 80},
            ]
        )
        assert result["stock_opinions"][0]["overall_score"] == 80
        assert result["stock_opinions"][0]["signal"] == "\u89c2\u671b"
