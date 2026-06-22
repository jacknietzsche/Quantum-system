"""Unit tests for shared.config.Config (partial - uncovered methods)."""

import os


class TestConfigGet:
    def test_get_simple_key(self):
        from shared.config import Config

        c = Config()
        c._data["test_key"] = "test_value"
        assert c.get("test_key") == "test_value"
        del c._data["test_key"]

    def test_get_nested_key(self):
        from shared.config import Config

        c = Config()
        c._data["level1"] = {"level2": {"level3": "deep_value"}}
        assert c.get("level1.level2.level3") == "deep_value"
        del c._data["level1"]

    def test_get_missing_key_default(self):
        from shared.config import Config

        c = Config()
        assert c.get("nonexistent_key_xyz", "default_val") == "default_val"

    def test_get_missing_nested_default(self):
        from shared.config import Config

        c = Config()
        assert c.get("a.b.c", 42) == 42

    def test_get_none_value_returns_default(self):
        from shared.config import Config

        c = Config()
        c._data["null_key"] = None
        assert c.get("null_key", "fallback") == "fallback"
        del c._data["null_key"]


class TestConfigGetModel:
    def test_get_model_default_primary(self):
        from shared.config import Config

        c = Config()
        result = c.get_model("primary")
        assert "provider" in result
        assert "model" in result

    def test_get_model_unknown_role(self):
        from shared.config import Config

        c = Config()
        result = c.get_model("unknown_role_xyz")
        assert "provider" in result
        assert "model" in result

    def test_get_model_from_data(self):
        from shared.config import Config

        c = Config()
        old_llm = c._data.get("llm")
        c._data["llm"] = {"model_roles": {"test_role": "openai:gpt-4o"}}
        result = c.get_model("test_role")
        assert result["provider"] == "openai"
        assert result["model"] == "gpt-4o"
        if old_llm is not None:
            c._data["llm"] = old_llm
        else:
            del c._data["llm"]


class TestConfigGetApiKey:
    def test_get_api_key_from_env(self):
        from shared.config import Config

        c = Config()
        os.environ["TESTPROV_API_KEY"] = "test_key_123"
        result = c.get_api_key("testprov")
        assert result == "test_key_123"
        del os.environ["TESTPROV_API_KEY"]

    def test_get_api_key_missing(self):
        from shared.config import Config

        c = Config()
        result = c.get_api_key("nonexistent_provider")
        assert result == ""


class TestConfigGetBaseUrl:
    def test_get_base_url_default(self):
        from shared.config import Config

        c = Config()
        result = c.get_base_url("nonexistent")
        assert isinstance(result, str)


class TestConfigGetMode:
    def test_get_mode_default(self):
        from shared.config import Config

        c = Config()
        mode = c.get_mode()
        assert isinstance(mode, str)
        assert len(mode) > 0

    def test_get_mode_from_env(self):
        from shared.config import Config

        c = Config()
        os.environ["MODE"] = "aggressive"
        mode = c.get_mode()
        assert mode == "aggressive"
        del os.environ["MODE"]


class TestConfigGetScheduler:
    def test_get_scheduler(self):
        from shared.config import Config

        c = Config()
        result = c.get_scheduler()
        assert isinstance(result, dict)
        assert len(result) > 0


class TestConfigGetNotification:
    def test_get_notification(self):
        from shared.config import Config

        c = Config()
        result = c.get_notification()
        assert "enabled" in result
        assert "email" in result
        assert "wechat" in result


class TestConfigGetEmailConfig:
    def test_get_email_config(self):
        from shared.config import Config

        c = Config()
        result = c.get_email_config()
        assert "sender" in result
        assert "password" in result
        assert "receivers" in result


class TestConfigDataProperty:
    def test_data_property(self):
        from shared.config import Config

        c = Config()
        assert isinstance(c.data, dict)
