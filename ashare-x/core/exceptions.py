"""异常分层 (见 S04 §4.28 错误分层, DEFECTS.md C5)。

层级:
    AShareXError                  所有自定义异常的根
    ├── ConfigError               配置加载/解析错误
    ├── DataError                 数据层错误
    │   ├── DataSourceError       数据源不可用 (断路器 OPEN 等)
    │   ├── DataNotFoundError     数据缺失
    │   └── DataValidationError   数据格式/范围校验失败
    ├── LLMError                  LLM 调用错误
    │   ├── LLMTimeoutError       超时
    │   ├── LLMRateLimitError     限流 (可重试)
    │   └── LLMResponseError      响应解析失败 (JSON/schema 不合法)
    └── WorkflowError             工作流编排错误
        └── BudgetExceededError   预算超限 (见 core/llm_client.py BudgetState)

每条异常携带 i18n key, 由 core/i18n.py 渲染为用户语言消息 (见 exp12.1)。
"""

from __future__ import annotations


class AShareXError(Exception):
    """所有 AShare-X 自定义异常的基类。

    Attributes:
        i18n_key: 国际化消息 key (见 core/i18n.py)
        details: 额外上下文 (供日志/排查, 不直接展示给用户)
    """

    i18n_key: str = "error.generic"

    def __init__(
        self, message: str = "", *, i18n_key: str | None = None, details: dict | None = None
    ) -> None:
        super().__init__(message)
        if i18n_key is not None:
            self.i18n_key = i18n_key
        self.details: dict = details or {}


# ── 配置 ──────────────────────────────────────────────────────────
class ConfigError(AShareXError):
    i18n_key = "error.config"


# ── 数据层 ────────────────────────────────────────────────────────
class DataError(AShareXError):
    i18n_key = "error.data"


class DataSourceError(DataError):
    """数据源不可用 (断路器熔断 / 网络错误 / 鉴权失败)。"""

    i18n_key = "error.data_source"
    retryable: bool = True

    def __init__(self, message: str = "", *, source: str | None = None, **kwargs) -> None:
        super().__init__(message, **kwargs)
        if source:
            self.details["source"] = source


class DataNotFoundError(DataError):
    """请求的数据不存在 (如某股票无 K 线)。"""

    i18n_key = "error.data_not_found"


class DataValidationError(DataError):
    """数据校验失败 (NaN/越界/格式错)。"""

    i18n_key = "error.data_validation"


# ── LLM ──────────────────────────────────────────────────────────
class LLMError(AShareXError):
    i18n_key = "error.llm"


class LLMTimeoutError(LLMError):
    """LLM 调用超时。可重试。"""

    i18n_key = "error.llm_timeout"
    retryable: bool = True


class LLMRateLimitError(LLMError):
    """LLM 限流 (HTTP 429)。可重试 (指数退避)。"""

    i18n_key = "error.llm_rate_limit"
    retryable: bool = True

    def __init__(self, message: str = "", *, retry_after: float | None = None, **kwargs) -> None:
        super().__init__(message, **kwargs)
        if retry_after is not None:
            self.details["retry_after"] = retry_after


class LLMResponseError(LLMError):
    """LLM 响应解析失败 (非 JSON / schema 不合法)。不可重试 (换策略, 见 S15)。"""

    i18n_key = "error.llm_response"
    retryable: bool = False


# ── 工作流 ────────────────────────────────────────────────────────
class WorkflowError(AShareXError):
    i18n_key = "error.workflow"


class BudgetExceededError(WorkflowError):
    """月预算超限 (见 core/llm_client.py BudgetState)。当 policy() == 'halt' 时抛出。"""

    i18n_key = "error.budget_exceeded"

    def __init__(
        self,
        message: str = "",
        *,
        used_rmb: float = 0.0,
        budget_rmb: float = 0.0,
        **kwargs,
    ) -> None:
        super().__init__(message, **kwargs)
        self.details["used_rmb"] = used_rmb
        self.details["budget_rmb"] = budget_rmb


def is_retryable(exc: BaseException) -> bool:
    """判断异常是否值得重试 (有 retryable=True 属性且为 True)。"""
    return bool(getattr(exc, "retryable", False))
