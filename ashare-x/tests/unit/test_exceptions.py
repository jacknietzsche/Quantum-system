"""core/exceptions.py 单元测试。"""

from __future__ import annotations

import pytest

from core.exceptions import (
    AShareXError,
    BudgetExceededError,
    DataNotFoundError,
    DataSourceError,
    LLMRateLimitError,
    LLMResponseError,
    LLMTimeoutError,
    is_retryable,
)


class TestHierarchy:
    def test_all_inherit_from_base(self):
        for exc_cls in [
            DataSourceError,
            DataNotFoundError,
            LLMTimeoutError,
            LLMRateLimitError,
            LLMResponseError,
            BudgetExceededError,
        ]:
            assert issubclass(exc_cls, AShareXError)

    def test_data_subclasses_under_dataerror(self):
        from core.exceptions import DataError

        for exc_cls in [DataSourceError, DataNotFoundError]:
            assert issubclass(exc_cls, DataError)

    def test_llm_subclasses_under_llmerror(self):
        from core.exceptions import LLMError

        for exc_cls in [LLMTimeoutError, LLMRateLimitError, LLMResponseError]:
            assert issubclass(exc_cls, LLMError)


class TestI18nKey:
    def test_each_has_i18n_key(self):
        assert DataSourceError.i18n_key == "error.data_source"
        assert LLMRateLimitError.i18n_key == "error.llm_rate_limit"
        assert BudgetExceededError.i18n_key == "error.budget_exceeded"

    def test_custom_i18n_key_override(self):
        exc = AShareXError("x", i18n_key="error.custom")
        assert exc.i18n_key == "error.custom"


class TestRetryable:
    @pytest.mark.parametrize(
        ("exc_cls", "expected"),
        [
            (LLMTimeoutError, True),
            (LLMRateLimitError, True),
            (DataSourceError, True),
            (LLMResponseError, False),
            (DataNotFoundError, False),
            (BudgetExceededError, False),
        ],
    )
    def test_retryable_flag(self, exc_cls, expected):
        assert getattr(exc_cls("x"), "retryable", False) is expected

    def test_is_retryable_helper(self):
        assert is_retryable(LLMTimeoutError("x")) is True
        assert is_retryable(LLMResponseError("x")) is False
        assert is_retryable(ValueError("not ours")) is False  # 无属性


class TestDetails:
    def test_data_source_carries_source(self):
        exc = DataSourceError("timeout", source="akshare")
        assert exc.details["source"] == "akshare"

    def test_rate_limit_carries_retry_after(self):
        exc = LLMRateLimitError("429", retry_after=5.0)
        assert exc.details["retry_after"] == 5.0

    def test_budget_carries_amounts(self):
        exc = BudgetExceededError("halt", used_rmb=120.0, budget_rmb=100.0)
        assert exc.details["used_rmb"] == 120.0
        assert exc.details["budget_rmb"] == 100.0

    def test_default_details_empty(self):
        assert AShareXError("x").details == {}
