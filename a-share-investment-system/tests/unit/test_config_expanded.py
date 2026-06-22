"""Expanded tests for shared/config.py."""

from __future__ import annotations


class TestConfigExpanded:
    def test_config_get(self):
        from shared.config import Config

        cfg = Config()
        result = cfg.get("nonexistent.key", "default")
        assert result == "default"

    def test_config_get_api_key(self):
        from shared.config import Config

        cfg = Config()
        result = cfg.get_api_key("nonexistent")
        assert isinstance(result, str)

    def test_config_get_base_url(self):
        from shared.config import Config

        cfg = Config()
        result = cfg.get_base_url("nonexistent")
        assert isinstance(result, str)
