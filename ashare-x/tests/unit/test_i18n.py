"""core/i18n.py 单元测试。"""

from __future__ import annotations

import pytest

from core import i18n
from core.exceptions import BudgetExceededError, DataSourceError


@pytest.fixture(autouse=True)
def _reset_lang():
    i18n.set_lang("zh")
    yield
    i18n.set_lang("zh")


class TestTranslate:
    def test_zh_default(self):
        assert "发生错误" in i18n.translate("error.generic", message="boom")

    def test_en_when_lang_en(self):
        i18n.set_lang("en")
        assert "An error occurred" in i18n.translate("error.generic", message="boom")

    def test_missing_key_returns_key(self):
        assert i18n.translate("error.nonexistent") == "error.nonexistent"

    def test_missing_placeholder_kept_as_is(self):
        # 模板含 {source} 但不传 -> 安全回退到原模板
        result = i18n.translate("error.data_source", message="down")
        assert "down" in result


class TestSetLang:
    def test_unsupported_lang_raises(self):
        with pytest.raises(ValueError, match="不支持的语言"):
            i18n.set_lang("ja")

    def test_case_insensitive(self):
        i18n.set_lang("EN")
        assert i18n.get_lang() == "en"


class TestTranslateException:
    def test_data_source_exception(self):
        exc = DataSourceError("连接超时", source="akshare")
        i18n.set_lang("zh")
        msg = i18n.translate_exception(exc)
        assert "akshare" in msg
        assert "连接超时" in msg

    def test_budget_exception_formats_rmb(self):
        exc = BudgetExceededError("halt", used_rmb=120.5, budget_rmb=100.0)
        msg = i18n.translate_exception(exc)
        assert "¥120.50" in msg
        assert "¥100.00" in msg

    def test_bare_exception_falls_back(self):
        msg = i18n.translate_exception(ValueError("plain"))
        # 无 i18n_key -> 走 generic
        assert "plain" in msg
