"""默认配置 — 参考 TradingAgents/default_config.py

环境变量覆盖模式:
  ASHARE_LLM_PROVIDER=siliconflow
  ASHARE_DEEP_THINK_LLM=deepseek-ai/DeepSeek-R1
  ASHARE_QUICK_THINK_LLM=deepseek-ai/DeepSeek-V3
"""

import os

_ASHARE_HOME = os.path.join(os.path.expanduser("~"), ".ashare-x")

# ─── 环境变量 → 配置键映射 ───
_ENV_OVERRIDES = {
    "ASHARE_LLM_PROVIDER": "llm_provider",
    "ASHARE_DEEP_THINK_LLM": "deep_think_llm",
    "ASHARE_QUICK_THINK_LLM": "quick_think_llm",
    "ASHARE_LLM_BACKEND_URL": "backend_url",
    "ASHARE_OUTPUT_LANGUAGE": "output_language",
    "ASHARE_MAX_DEBATE_ROUNDS": "max_debate_rounds",
    "ASHARE_MAX_RISK_ROUNDS": "max_risk_discuss_rounds",
    "ASHARE_CHECKPOINT_ENABLED": "checkpoint_enabled",
    "ASHARE_TEMPERATURE": "temperature",
    "ASHARE_RESULTS_DIR": "results_dir",
    "ASHARE_CACHE_DIR": "data_cache_dir",
    "ASHARE_MEMORY_PATH": "memory_log_path",
}


def _coerce(value: str, reference):
    """类型强制转换: bool/int/float/string"""
    if isinstance(reference, bool):
        return value.strip().lower() in ("true", "1", "yes", "on")
    if isinstance(reference, int) and not isinstance(reference, bool):
        return int(value)
    if isinstance(reference, float):
        return float(value)
    return value


def _apply_env_overrides(config: dict) -> dict:
    """应用 ASHARE_* 环境变量覆盖"""
    for env_var, key in _ENV_OVERRIDES.items():
        raw = os.environ.get(env_var)
        if raw is None or raw == "":
            continue
        config[key] = _coerce(raw, config.get(key))
    return config


DEFAULT_CONFIG = _apply_env_overrides(
    {
        # ─── 路径 ───
        "project_dir": os.path.abspath(os.path.join(os.path.dirname(__file__), "..")),
        "results_dir": os.getenv("ASHARE_RESULTS_DIR", os.path.join(_ASHARE_HOME, "logs")),
        "data_cache_dir": os.getenv("ASHARE_CACHE_DIR", os.path.join(_ASHARE_HOME, "cache")),
        "memory_log_path": os.getenv(
            "ASHARE_MEMORY_PATH", os.path.join(_ASHARE_HOME, "memory", "trading_memory.md")
        ),
        "memory_log_max_entries": None,  # None = 不旋转
        # ─── LLM 设置 ───
        "llm_provider": "siliconflow",
        "deep_think_llm": "deepseek-ai/DeepSeek-R1",
        "quick_think_llm": "deepseek-ai/DeepSeek-V3",
        "backend_url": None,
        "temperature": None,
        # ─── 检查点 ───
        "checkpoint_enabled": False,
        # ─── 输出 ───
        "output_language": "Chinese",
        # ─── 辩论设置 ───
        "max_debate_rounds": 1,
        "max_risk_discuss_rounds": 1,
        "max_recur_limit": 100,
        "analyst_concurrency_limit": 1,
        # ─── 分析师选择 ───
        "selected_analysts": ["market", "sentiment", "news", "fundamentals"],
        # 可选: "northbound", "sector" (A 股特色分析师)
        # ─── 数据源 ───
        "data_vendors": {
            "core_stock_apis": "efinance",
            "technical_indicators": "efinance",
            "fundamental_data": "akshare",
            "news_data": "akshare",
        },
        # ─── A 股参数 ───
        "market": {
            "benchmark": "000300",  # 沪深300
            "trading_hours": {"start": "09:30", "end": "15:00"},
            "price_limit": {"main_board": 0.10, "gem_star": 0.20},
        },
    }
)


def get_default_config() -> dict:
    """返回默认配置的深拷贝"""
    import copy

    return copy.deepcopy(DEFAULT_CONFIG)
