"""Unit tests for services.screening.styles."""

from unittest.mock import MagicMock


class TestStageConfigs:
    def test_stage1_defaults(self):
        from services.screening.styles import Stage1Config

        c = Stage1Config()
        assert c.top_n == 200
        assert c.st_filter is True

    def test_stage2_defaults(self):
        from services.screening.styles import Stage2Config

        c = Stage2Config()
        assert c.top_n == 30
        assert c.score_min == 4

    def test_stage3_defaults(self):
        from services.screening.styles import Stage3Config

        c = Stage3Config()
        assert c.deep_top == 15
        assert "buffett" in c.weights

    def test_stage4_defaults(self):
        from services.screening.styles import Stage4Config

        c = Stage4Config()
        assert c.enabled is False
        assert c.top_n == 5

    def test_style_config_defaults(self):
        from services.screening.styles import StyleConfig

        sc = StyleConfig()
        assert sc.name == "hybrid"
        assert sc.stage1.top_n == 200


class TestLoadStyleConfig:
    def test_load_hybrid(self):
        from services.screening.styles import load_style_config

        mock_config = MagicMock()
        mock_config.get = lambda k, d=None: d
        sc = load_style_config("hybrid", config=mock_config)
        assert sc.name == "hybrid"

    def test_load_limit_up(self):
        from services.screening.styles import load_style_config

        mock_config = MagicMock()
        mock_config.get = lambda k, d=None: d if not isinstance(d, dict) else {}
        sc = load_style_config("limit_up", config=mock_config)
        assert sc.name == "limit_up"
        assert len(sc.stage3.master_agents) > 0

    def test_load_momentum(self):
        from services.screening.styles import load_style_config

        mock_config = MagicMock()
        mock_config.get = lambda k, d=None: d if not isinstance(d, dict) else {}
        sc = load_style_config("momentum", config=mock_config)
        assert sc.name == "momentum"

    def test_load_unknown_style(self):
        from services.screening.styles import load_style_config

        mock_config = MagicMock()
        mock_config.get = lambda k, d=None: d if not isinstance(d, dict) else {}
        sc = load_style_config("unknown_style", config=mock_config)
        assert sc.name == "unknown_style"
