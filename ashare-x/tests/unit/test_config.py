"""core/config.py 单元测试。

覆盖: 单例、yaml 加载、点号嵌套读取、env 覆盖、类型推断、热更新、缺省值、损坏文件容错。
全部离线, 不触碰真实 config/config.yaml (用 isolated_env 写临时文件)。
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from core.config import Config, _coerce


@pytest.fixture(autouse=True)
def _reset_singleton():
    """每个测试前后重置单例, 隔离相互影响。"""
    Config.reset()
    yield
    Config.reset()


def _write_cfg(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


class TestConfigLoad:
    def test_load_yaml_nested(self, isolated_env: Path):
        cfg_path = isolated_env / "config.yaml"
        _write_cfg(cfg_path, "llm:\n  monthly_budget_rmb: 50\n  deep_think:\n    model: pro\n")
        cfg = Config(config_path=cfg_path)
        assert cfg.get("llm.monthly_budget_rmb") == 50
        assert cfg.get("llm.deep_think.model") == "pro"

    def test_missing_file_uses_env_and_defaults(self, isolated_env: Path, monkeypatch):
        monkeypatch.setenv("ASHARE_X_MONTHLY_BUDGET_RMB", "200")
        cfg = Config(config_path=isolated_env / "nope.yaml")
        assert cfg.get("llm.monthly_budget_rmb") == 200

    def test_missing_key_returns_default(self, isolated_env: Path):
        _write_cfg(isolated_env / "config.yaml", "llm:\n  x: 1\n")
        cfg = Config(config_path=isolated_env / "config.yaml")
        assert cfg.get("llm.nonexistent", "fallback") == "fallback"

    def test_none_value_returns_default(self, isolated_env: Path):
        _write_cfg(isolated_env / "config.yaml", "llm:\n  model: null\n")
        cfg = Config(config_path=isolated_env / "config.yaml")
        assert cfg.get("llm.model", "default-model") == "default-model"

    def test_non_dict_root_logged_and_kept_empty(self, isolated_env: Path, caplog):
        _write_cfg(isolated_env / "config.yaml", "- a\n- b\n")
        with caplog.at_level("ERROR"):
            cfg = Config(config_path=isolated_env / "config.yaml")
        assert cfg.get("anything", "d") == "d"
        assert any("配置根节点必须是 dict" in r.message for r in caplog.records)

    def test_corrupt_yaml_keeps_old_value(self, isolated_env: Path, caplog):
        cfg_path = isolated_env / "config.yaml"
        _write_cfg(cfg_path, "llm:\n  x: 1\n")
        cfg = Config(config_path=cfg_path)
        assert cfg.get("llm.x") == 1
        # 写入损坏 yaml
        _write_cfg(cfg_path, "llm:\n  x: [unterminated\n")
        with caplog.at_level("ERROR"):
            cfg.load()
        # 旧值保留
        assert cfg.get("llm.x") == 1


class TestEnvOverride:
    def test_env_overrides_yaml(self, isolated_env: Path, monkeypatch):
        _write_cfg(isolated_env / "config.yaml", "llm:\n  monthly_budget_rmb: 50\n")
        monkeypatch.setenv("ASHARE_X_MONTHLY_BUDGET_RMB", "150")
        cfg = Config(config_path=isolated_env / "config.yaml")
        assert cfg.get("llm.monthly_budget_rmb") == 150

    def test_api_key_injected_into_nested(self, isolated_env: Path, monkeypatch):
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test-123")
        cfg = Config(config_path=isolated_env / "nope.yaml")
        assert cfg.get("llm.deepseek.api_key") == "sk-test-123"

    def test_empty_env_not_applied(self, isolated_env: Path, monkeypatch):
        _write_cfg(isolated_env / "config.yaml", "llm:\n  monthly_budget_rmb: 50\n")
        monkeypatch.setenv("ASHARE_X_MONTHLY_BUDGET_RMB", "")
        cfg = Config(config_path=isolated_env / "config.yaml")
        assert cfg.get("llm.monthly_budget_rmb") == 50


class TestCoerce:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("100", 100),
            ("99.5", 99.5),
            ("true", True),
            ("False", False),
            ("yes", True),
            ("0", False),
            ("deepseek-chat", "deepseek-chat"),
        ],
    )
    def test_coerce_types(self, raw, expected):
        assert _coerce(raw) == expected


class TestHotReload:
    def test_mtime_change_triggers_reload(self, isolated_env: Path):
        cfg_path = isolated_env / "config.yaml"
        _write_cfg(cfg_path, "llm:\n  monthly_budget_rmb: 10\n")
        cfg = Config(config_path=cfg_path)
        assert cfg.get("llm.monthly_budget_rmb") == 10
        # 修改文件 (确保 mtime 变化)
        time.sleep(0.05)
        _write_cfg(cfg_path, "llm:\n  monthly_budget_rmb: 20\n")
        # get() 内部触发热重载
        assert cfg.get("llm.monthly_budget_rmb") == 20

    def test_no_reload_when_unchanged(self, isolated_env: Path):
        cfg_path = isolated_env / "config.yaml"
        _write_cfg(cfg_path, "llm:\n  x: 1\n")
        cfg = Config(config_path=cfg_path)
        assert cfg.reload_if_changed() is False


class TestSingleton:
    def test_singleton_returns_same_instance(self, isolated_env: Path):
        _write_cfg(isolated_env / "config.yaml", "x: 1\n")
        a = Config(config_path=isolated_env / "config.yaml")
        b = Config()  # 不传 path, 复用单例
        assert a is b
