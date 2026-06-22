"""LLM Router - 多Provider智能路由引擎

按任务类型分流(复杂→premium/标准→standard/简单→budget),
健康评分动态排序,熔断保护,epsilon-greedy探索。

复用现有基础设施:
- Config.get_model() - 读取角色配置
- CircuitBreaker - provider级熔断
- LLMCaller - 底层调用
"""

import logging
import random
import threading
import time
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


# ── 任务分层定义 ──

TIER_CONFIG = {
    "premium": {
        "description": "复杂任务(辩论/决策/深度分析)",
        "models": ["primary"],
        "timeout": 120,
        "max_tokens": 8000,
    },
    "standard": {
        "description": "标准任务(个股分析/组合评估)",
        "models": ["secondary"],
        "timeout": 60,
        "max_tokens": 4000,
    },
    "budget": {
        "description": "简单任务(批量预筛/简单评分)",
        "models": ["fallback"],
        "timeout": 30,
        "max_tokens": 2000,
    },
}

TASK_TIER_MAP = {
    "debate": "premium",
    "decision": "premium",
    "deep_analysis": "premium",
    "stock_analysis": "standard",
    "portfolio": "standard",
    "pre_screen": "budget",
    "simple_score": "budget",
}

RELATIVE_COST = {
    "siliconflow": 10,
    "deepseek": 20,
    "juguang": 30,
    "chatanywhere": 15,
    "cherryin": 5,
}

DEFAULT_COST = 20


@dataclass
class ProviderStats:
    """Provider调用统计"""

    total_calls: int = 0
    success_count: int = 0
    failure_count: int = 0
    total_latency: float = 0.0
    recent_successes: list[bool] = field(default_factory=list)
    max_recent: int = 20

    @property
    def success_rate(self) -> float:
        if not self.recent_successes:
            return 0.5
        return sum(self.recent_successes) / len(self.recent_successes)

    @property
    def avg_latency(self) -> float:
        if self.total_calls == 0:
            return 1.0
        return self.total_latency / self.total_calls

    def record(self, success: bool, latency: float):
        self.total_calls += 1
        if success:
            self.success_count += 1
        else:
            self.failure_count += 1
        self.total_latency += latency
        self.recent_successes.append(success)
        if len(self.recent_successes) > self.max_recent:
            self.recent_successes.pop(0)


class LLMRouter:
    """多Provider智能路由引擎 - 健康评分 + 熔断 + 成本优化"""

    def __init__(self):
        from providers.source_base import CircuitBreaker

        self._circuit_breakers: dict[str, CircuitBreaker] = {}
        self._stats: dict[str, ProviderStats] = {}
        self._lock = threading.Lock()
        self._exploration_rate = 0.1  # epsilon-greedy

    def _get_cb(self, provider: str):
        if provider not in self._circuit_breakers:
            from providers.source_base import CircuitBreaker

            self._circuit_breakers[provider] = CircuitBreaker(
                name=f"llm_{provider}",
                failure_threshold=3,
                cooldown_seconds=120,
                half_open_max_calls=1,
            )
        return self._circuit_breakers[provider]

    def _get_stats(self, provider: str) -> ProviderStats:
        if provider not in self._stats:
            self._stats[provider] = ProviderStats()
        return self._stats[provider]

    def health_score(self, provider: str) -> float:
        """综合健康评分: 成功率(50%) + 延迟(10%) + 吞吐(20%) + 成本(20%)"""
        stats = self._get_stats(provider)
        cb = self._get_cb(provider)

        sr = stats.success_rate
        if cb.stats.state == "open":
            sr *= 0.3  # 熔断状态惩罚
        sr_score = sr * 50

        # 延迟 (10%) - 越低越好,归一化到 [0,10]
        lat = stats.avg_latency
        lat_score = max(0, 10 - lat / 10) if lat > 0 else 10

        # 吞吐 (20%) - total_calls 越多说明越可靠
        tp = min(stats.total_calls / 20, 1.0) * 20

        # 成本 (20%) - 低成本provider得分更高
        cost = RELATIVE_COST.get(provider, DEFAULT_COST)
        max_cost = max(RELATIVE_COST.values())
        cost_score = (1 - cost / max_cost) * 20

        return round(sr_score + lat_score + tp + cost_score, 1)

    def get_available_providers(self, tier: str) -> list[tuple[str, float]]:
        """获取指定层级的可用provider列表(按健康评分降序)"""
        from shared.config import Config

        tier_cfg = TIER_CONFIG.get(tier)
        if not tier_cfg:
            return []

        cfg = Config()
        scored = []
        for role in tier_cfg["models"]:
            model_info = cfg.get_model(role)
            provider = model_info.get("provider", "")
            if not provider:
                continue
            api_key = cfg.get_api_key(provider)
            if not api_key:
                continue
            cb = self._get_cb(provider)
            if not cb.peek_available():
                continue
            score = self.health_score(provider)
            scored.append((provider, model_info.get("model", ""), score))

        scored.sort(key=lambda x: x[2], reverse=True)
        return [(p, m) for p, m, s in scored]

    def route(
        self,
        task_type: str,
        prompt: str,
        system: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> dict | None:
        """执行路由: 按task_type分流 → provider轮询 → 降级

        Returns:
            {"content": str, "provider": str, "model": str, "tier": str, ...}
            or None if all providers failed
        """
        tier = TASK_TIER_MAP.get(task_type, "standard")
        max_tokens = max_tokens or TIER_CONFIG[tier]["max_tokens"]
        timeout = TIER_CONFIG[tier]["timeout"]

        # epsilon-greedy: 10%概率随机选择一个低分provider探索
        providers = self.get_available_providers(tier)
        if not providers:
            # 降级到下一个tier
            for lower_tier in ("standard", "budget"):
                providers = self.get_available_providers(lower_tier)
                if providers:
                    tier = lower_tier
                    max_tokens = TIER_CONFIG[tier]["max_tokens"]
                    timeout = TIER_CONFIG[tier]["timeout"]
                    logger.info(f"[LLMRouter] {task_type} 降级到 tier={tier}")
                    break

        if not providers:
            logger.warning(f"[LLMRouter] 无可用provider for {task_type}")
            return None

        provider, model = providers[0]
        # epsilon-greedy: 尝试探索（模型选择负载均衡，非加密场景）
        if len(providers) > 1 and random.random() < self._exploration_rate:  # noqa: S311
            logger.info(f"[LLMRouter] 探索模式: {provider}/{model}")

        try:
            result = self._call_provider(
                provider, model, prompt, system, temperature, max_tokens, timeout
            )
            if result and not result.get("error"):
                return {**result, "provider": provider, "model": model, "tier": tier}
            # 主provider失败,依次尝试其他
            for alt_provider, alt_model in providers[1:]:
                logger.info(f"[LLMRouter] {provider}失败, 切换到{alt_provider}")
                result = self._call_provider(
                    alt_provider, alt_model, prompt, system, temperature, max_tokens, timeout
                )
                if result and not result.get("error"):
                    return {**result, "provider": alt_provider, "model": alt_model, "tier": tier}
        except Exception as e:
            logger.error(f"[LLMRouter] 路由异常: {e}")

        return None

    def _call_provider(
        self,
        provider: str,
        model: str,
        prompt: str,
        system: str,
        temperature: float,
        max_tokens: int,
        timeout: int,
    ) -> dict | None:
        """调用单个provider,记录统计和熔断"""
        from shared.config import Config

        cfg = Config()
        api_key = cfg.get_api_key(provider)
        base_url = cfg.get_base_url(provider)
        if not api_key:
            return {"error": f"No API key for {provider}"}

        import requests

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        t0 = time.time()
        try:
            resp = requests.post(
                f"{base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                },
                timeout=timeout,
            )
            latency = time.time() - t0
            if resp.status_code == 200:
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                self._record_success(provider, latency)
                return {
                    "content": content,
                    "usage": data.get("usage", {}),
                    "latency": round(latency, 2),
                }
            self._record_failure(provider, latency)
            return {"error": f"HTTP {resp.status_code}: {resp.text[:200]}"}
        except Exception as e:
            latency = time.time() - t0
            self._record_failure(provider, latency)
            return {"error": str(e)[:200]}

    def _record_success(self, provider: str, latency: float):
        with self._lock:
            self._get_cb(provider).record_success()
            self._get_stats(provider).record(True, latency)
        try:
            from services.monitor import get_monitor

            get_monitor().record_llm_call(provider, "default", True, latency * 1000)
        except Exception:
            pass

    def _record_failure(self, provider: str, latency: float):
        with self._lock:
            self._get_cb(provider).record_failure()
            self._get_stats(provider).record(False, latency)
        try:
            from services.monitor import get_monitor

            get_monitor().record_llm_call(provider, "default", False, latency * 1000)
        except Exception:
            pass

    def status(self) -> dict:
        """返回所有provider状态"""
        result = {}
        for provider in list(self._stats.keys()):
            stats = self._get_stats(provider)
            cb = self._get_cb(provider)
            result[provider] = {
                "health_score": self.health_score(provider),
                "state": cb.stats.state,
                "total_calls": stats.total_calls,
                "success_rate": round(stats.success_rate, 2),
                "avg_latency": round(stats.avg_latency, 2),
            }
        return result

    def reset(self):
        """重置所有统计和熔断器"""
        self._stats.clear()
        for cb in self._circuit_breakers.values():
            cb.reset()


# 全局单例
_router: LLMRouter | None = None
_router_lock = threading.Lock()


def get_router() -> LLMRouter:
    global _router  # noqa: PLW0603
    if _router is None:
        with _router_lock:
            if _router is None:
                _router = LLMRouter()
    return _router
