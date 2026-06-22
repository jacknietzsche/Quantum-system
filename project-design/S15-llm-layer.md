# S15 — LLM调用封装层

> **职责**: 所有Agent共享的LLM基础设施。统一接口、token计数、费用追踪、结构化输出、重试降级。

## 15.1 架构定位

```
Agent层 (S04)
    │
    ▼
┌─────────────────────────────┐
│     LLMClient (本模块)       │
│  ┌───────────┐ ┌───────────┐│
│  │ quick_think│ │deep_think ││  ← 模型路由
│  └───────────┘ └───────────┘│
│  ┌──────────────────────────┐│
│  │ TokenCounter + CostTracker││  ← 计量
│  └──────────────────────────┘│
│  ┌──────────────────────────┐│
│  │ RetryManager + Fallback  ││  ← 容错
│  └──────────────────────────┘│
└─────────────────────────────┘
    │
    ▼
providers (DeepSeek / Qwen / GLM API)
```

## 15.2 LLMClient接口

```python
class LLMClient:
    """统一LLM调用入口，所有Agent通过此接口调用LLM"""

    def __init__(self, config: LLMConfig, counter: TokenCounter):
        self.config = config
        self.counter = counter
        self.providers = {}               # name → Provider实例

    async def complete(
        self,
        messages: list[dict],
        model_tier: Literal["quick", "deep"] = "quick",
        temperature: float = 0.7,
        max_tokens: int = 4000,
        response_format: Optional[type[BaseModel]] = None,  # Pydantic schema
        agent_name: str = "unknown",
    ) -> LLMResponse:
        """
        统一调用入口。
        - model_tier: "quick"用日常模型，"deep"用推理模型
        - response_format: 如果提供，尝试结构化输出；失败则fallback到free-text
        - 返回LLMResponse，包含content + token_usage
        """
        ...

    async def complete_with_retry(
        self,
        messages: list[dict],
        **kwargs,
    ) -> LLMResponse:
        """带重试的调用（内部调用complete）"""
        ...
```

## 15.3 模型路由

```python
class LLMConfig(BaseModel):
    quick_think: ModelConfig             # 日常分析（分析师/研究员/交易员）
    deep_think: ModelConfig              # 复杂推理（研究经理/组合经理）

class ModelConfig(BaseModel):
    provider: str                        # deepseek / qwen / glm
    model: str                           # 模型ID（如 deepseek-v4-flash）
    api_key: str                         # 从.env加载
    temperature: float = 0.7
    max_tokens: int = 4000
    timeout: float = 60.0                # 单次调用超时（秒）
    enable_cache: bool = True            # 启用 prompt 缓存，命中价大幅降低
```

### Agent → 模型映射

| Agent | model_tier | 原因 |
|-------|-----------|------|
| 市场分析师 | quick | 数据驱动，不需要深度推理 |
| 基本面分析师 | quick | 同上 |
| 新闻分析师 | quick | 同上 |
| 情绪分析师 | quick | 同上 |
| 看涨研究员 | quick | 辩论需要快速响应 |
| 看跌研究员 | quick | 同上 |
| 研究经理 | **deep** | 综合判断需要深度推理 |
| 交易员 | quick | 按固定步骤转化 |
| 激进/保守/中性分析师 | quick | 辩论需要快速响应 |
| 投资组合经理 | **deep** | 最终决策需要深度推理 |
| 大师Agent | quick | 信号格式简单 |

## 15.4 结构化输出

```python
class LLMResponse(BaseModel):
    content: str                         # 原始文本内容
    parsed: Optional[dict]               # 结构化解析结果（如果有）
    token_usage: TokenUsage
    model: str                           # 实际使用的模型
    latency_ms: float                    # 调用耗时

class TokenUsage(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
```

### 结构化输出策略（完整版）

```python
import re
import json

async def complete_structured(
    self,
    messages: list[dict],
    schema: type[BaseModel],
    agent_name: str = "unknown",
    **kwargs,
) -> LLMResponse:
    """
    结构化输出四阶段策略:
    1. JSON模式 → Pydantic验证
    2. Prompt引导JSON → 正则提取 → Pydantic验证
    3. Free-text → 关键字段正则提取 → 构造对象
    4. 全部失败 → default_factory
    """
    # 策略1: JSON模式（DeepSeek/Qwen支持）
    try:
        response = await self.complete(
            messages, response_format={"type": "json_object"}, **kwargs
        )
        parsed = schema.model_validate_json(response.content)
        return LLMResponse(content=response.content, parsed=parsed.model_dump(), ...)
    except Exception:
        pass

    # 策略2: Prompt引导 + 正则提取
    json_prompt = messages + [{
        "role": "system",
        "content": f"请严格以JSON格式输出，schema: {schema.model_json_schema()}"
    }]
    try:
        response = await self.complete(json_prompt, **kwargs)
        # 从可能包含markdown代码块的文本中提取JSON
        json_match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', response.content, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
        else:
            json_match = re.search(r'\{.*\}', response.content, re.DOTALL)
            json_str = json_match.group() if json_match else response.content

        parsed = schema.model_validate_json(json_str)
        return LLMResponse(content=response.content, parsed=parsed.model_dump(), ...)
    except Exception:
        pass

    # 策略3: Free-text正则提取
    try:
        response = await self.complete(messages, **kwargs)
        extracted = extract_fields_from_text(response.content, schema)
        if extracted:
            return LLMResponse(content=response.content, parsed=extracted, ...)
    except Exception:
        pass

    # 策略4: 默认值
    default_obj = create_default_response(schema)
    return LLMResponse(content="", parsed=default_obj.model_dump(), ...)


def extract_fields_from_text(text: str, schema: type[BaseModel]) -> dict | None:
    """从free-text中提取Pydantic schema定义的字段"""
    result = {}

    # 提取signal/bandwidth (Literal类型)
    for field_name, field_info in schema.model_fields.items():
        annotation = field_info.annotation
        if hasattr(annotation, "__origin__") and annotation.__origin__ == Literal:
            # 尝试从文本中匹配允许的值
            for allowed in annotation.__args__:
                if allowed.lower() in text.lower():
                    result[field_name] = allowed
                    break

    # 提取数字字段
    number_patterns = {
        "confidence": r'(?:置信度|confidence)[:\s]*(\d+)',
        "entry_price": r'(?:入场价|entry)[:\s]*(\d+\.?\d*)',
        "stop_loss": r'(?:止损|stop.?loss)[:\s]*(\d+\.?\d*)',
        "take_profit": r'(?:止盈|take.?profit)[:\s]*(\d+\.?\d*)',
        "position_pct": r'(?:仓位|position)[:\s]*(\d+\.?\d*)%?',
    }

    for field, pattern in number_patterns.items():
        if field in schema.model_fields:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                result[field] = float(match.group(1))

    # 提取文本字段
    text_fields = ["reasoning", "executive_summary", "investment_thesis"]
    for field in text_fields:
        if field in schema.model_fields and field not in result:
            # 取前200字作为reasoning
            sentences = re.split(r'[。！？]', text)
            result[field] = '。'.join(sentences[:3]) + '。' if sentences else text[:200]

    return result if result else None
```

## 15.5 Token计数器

```python
class TokenCounter:
    """全局token使用追踪，支持预算控制"""

    def __init__(self, daily_budget: int = 400000):
        self.daily_budget = daily_budget
        self.daily_used = 0               # 当日累计
        self.per_stock_used = {}          # {ticker: int}
        self._lock = asyncio.Lock()

    async def record(self, agent: str, ticker: str, usage: TokenUsage):
        """记录一次调用的token使用"""
        async with self._lock:
            self.daily_used += usage.total_tokens
            self.per_stock_used[ticker] = (
                self.per_stock_used.get(ticker, 0) + usage.total_tokens
            )

    def remaining(self) -> int:
        """当日剩余预算"""
        return max(0, self.daily_budget - self.daily_used)

    def should_fast_mode(self) -> bool:
        """是否应启用快速模式（达到预算90%）"""
        return self.daily_used >= self.daily_budget * 0.9

    def stock_budget_remaining(self, ticker: str, per_stock_limit: int = 25000) -> int:
        """单股剩余预算"""
        used = self.per_stock_used.get(ticker, 0)
        return max(0, per_stock_limit - used)

    def reset_daily(self):
        """每日重置"""
        self.daily_used = 0
        self.per_stock_used.clear()

    def get_stats(self) -> dict:
        """获取统计信息"""
        return {
            "daily_used": self.daily_used,
            "daily_budget": self.daily_budget,
            "remaining": self.remaining(),
            "utilization_pct": round(self.daily_used / self.daily_budget * 100, 1),
            "per_stock": dict(self.per_stock_used),
        }
```

## 15.6 费用追踪

```python
class CostTracker:
    """每次LLM调用的费用追踪（2026-06 V4 定价，美元/1M token）"""

    # 来源: https://api-docs.deepseek.com/quick_start/pricing
    PRICING = {
        # V4 系列（主用）
        "deepseek-v4-flash": {"input": 0.14, "output": 0.28, "cached_input": 0.014},
        "deepseek-v4-pro":   {"input": 1.74, "output": 3.48, "cached_input": 0.174},  # 分层低档；高档更高
        # 备选
        "qwen-turbo":        {"input": 0.30, "output": 0.60, "cached_input": 0.03},
        "glm-4-flash":       {"input": 0.10, "output": 0.10, "cached_input": 0.01},
    }

    def record_call(self, model: str, usage: TokenUsage, latency_ms: float, cache_hit: bool = False):
        """记录一次调用的费用和延迟。

        cache_hit=True 时输入按 cached_input 价计（仅命中部分）。
        """
        pricing = self.PRICING.get(model, {"input": 0.14, "output": 0.28, "cached_input": 0.014})
        input_price = pricing["cached_input"] if cache_hit else pricing["input"]
        cost = (
            usage.prompt_tokens * input_price / 1_000_000
            + usage.completion_tokens * pricing["output"] / 1_000_000
        )
        # 写入日志（含 cache_hit 标记，便于事后分析缓存命中率）
        self._log(model, usage, cost, latency_ms, cache_hit)

    def get_daily_summary(self) -> dict:
        """当日费用汇总：总成本、按模型拆分、缓存命中率"""
        ...
```

> **注意**：早期版本曾把 PRICING 全部写为 0.0（基于"免费额度内"假设），这是事实错误。真实按量计费如上表。但因个人用量极低（见 S11.4 实测约 $1.5-3/月），费用追踪主要价值在**预算监控与缓存命中率优化**，而非省钱本身。

## 15.7 重试与降级

```python
class RetryManager:
    """LLM调用重试管理"""

    def __init__(self, config: RetryConfig):
        self.max_attempts = config.max_attempts       # 默认2
        self.base_delay = config.base_delay           # 默认2.0秒
        self.backoff_multiplier = config.backoff_multiplier  # 默认2.0
        self.max_delay = config.max_delay             # 默认30秒

    async def execute(self, fn, fallback=None):
        """
        执行函数，失败时重试，最终降级到fallback。
        重试策略: 指数退避 + jitter
        """
        last_error = None
        for attempt in range(self.max_attempts + 1):
            try:
                return await fn()
            except (TimeoutError, RateLimitError) as e:
                last_error = e
                if attempt < self.max_attempts:
                    delay = min(
                        self.base_delay * (self.backoff_multiplier ** attempt),
                        self.max_delay,
                    )
                    jitter = delay * 0.1 * (2 * random.random() - 1)  # ±10%
                    await asyncio.sleep(delay + jitter)
                    continue
            except (AuthenticationError, PermanentError):
                raise  # 不重试

        # 所有重试失败，降级
        if fallback is not None:
            return fallback()
        raise last_error
```

### 异常层级

```python
class LLMError(Exception):
    """LLM调用异常基类"""

class TimeoutError(LLMError):
    """调用超时"""

class RateLimitError(LLMError):
    """API限流（429）"""

class AuthenticationError(LLMError):
    """认证失败（401/403）"""

class PermanentError(LLMError):
    """不可恢复错误（模型不存在、参数错误等）"""

class ResponseParseError(LLMError):
    """结构化输出解析失败"""
```

## 15.8 异步并发控制

```python
class AsyncLLMClient(LLMClient):
    """异步版本，支持并发调用"""

    def __init__(self, config, counter, max_concurrent: int = 5):
        super().__init__(config, counter)
        self._semaphore = asyncio.Semaphore(max_concurrent)  # 最多5个并发

    async def complete(self, messages, **kwargs):
        async with self._semaphore:       # 并发控制
            return await super().complete(messages, **kwargs)
```

## 15.9 Provider实现

### DeepSeek Provider

```python
class DeepSeekProvider:
    """DeepSeek API适配器"""

    BASE_URL = "https://api.deepseek.com"

    async def chat(self, messages, model, temperature, max_tokens) -> dict:
        """调用deepseek-chat"""
        ...

    async def reason(self, messages, model, temperature, max_tokens) -> dict:
        """调用deepseek-reasoner（支持思考过程）"""
        ...
```

### Qwen Provider（备选）

```python
class QwenProvider:
    """阿里云DashScope适配器"""

    BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"

    async def chat(self, messages, model, temperature, max_tokens) -> dict:
        ...
```

### GLM Provider（备选）

```python
class GLMProvider:
    """智谱AI适配器"""

    BASE_URL = "https://open.bigmodel.cn/api/paas/v4"

    async def chat(self, messages, model, temperature, max_tokens) -> dict:
        ...
```

## 15.10 Provider工厂（借鉴TradingAgents v0.2.5）

### Provider分组

TradingAgents将所有OpenAI兼容的提供商统一处理，因为它们使用相同的API格式：

```python
# OpenAI兼容的提供商（共享同一个Client实现）
_OPENAI_COMPATIBLE = (
    "openai", "xai", "deepseek",
    "qwen", "qwen-cn",
    "glm", "glm-cn",
    "minimax", "minimax-cn",
    "ollama", "openrouter",
)

# 独立客户端的提供商
_INDEPENDENT = ("anthropic", "google", "azure")
```

### 懒加载工厂

```python
from typing import Optional

def create_llm_client(
    provider: str,
    model: str,
    base_url: Optional[str] = None,
    **kwargs,
) -> BaseLLMClient:
    """
    创建LLM客户端。
    - OpenAI兼容的提供商统一用OpenAICompatibleClient
    - 其他提供商独立导入
    - 懒加载：避免导入时加载所有SDK
    """
    provider_lower = provider.lower()

    if provider_lower in _OPENAI_COMPATIBLE:
        from .openai_compatible import OpenAICompatibleClient
        return OpenAICompatibleClient(model, base_url, provider=provider_lower, **kwargs)

    if provider_lower == "anthropic":
        from .anthropic_client import AnthropicClient
        return AnthropicClient(model, base_url, **kwargs)

    if provider_lower == "google":
        from .google_client import GoogleClient
        return GoogleClient(model, base_url, **kwargs)

    if provider_lower == "azure":
        from .azure_client import AzureOpenAIClient
        return AzureOpenAIClient(model, base_url, **kwargs)

    raise ValueError(f"Unsupported LLM provider: {provider}")
```

### OpenAI兼容客户端

```python
class OpenAICompatibleClient(BaseLLMClient):
    """统一处理所有OpenAI兼容API（DeepSeek/Qwen/GLM/Ollama等）"""

    # 各提供商的默认base_url
    DEFAULT_URLS = {
        "deepseek": "https://api.deepseek.com",
        "qwen": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "glm": "https://open.bigmodel.cn/api/paas/v4",
        "ollama": "http://localhost:11434/v1",
    }

    def __init__(self, model: str, base_url: Optional[str] = None, provider: str = "", **kwargs):
        self.model = model
        self.base_url = base_url or self.DEFAULT_URLS.get(provider, "")
        self.provider = provider
        self.extra_kwargs = kwargs

    def get_llm(self):
        """返回LangChain ChatOpenAI实例"""
        from langchain_openai import ChatOpenAI

        kwargs = {
            "model": self.model,
            "base_url": self.base_url,
            **self.extra_kwargs,
        }

        # 从环境变量加载API Key
        api_key_env = f"{self.provider.upper()}_API_KEY"
        import os
        api_key = os.environ.get(api_key_env)
        if api_key:
            kwargs["api_key"] = api_key

        return ChatOpenAI(**kwargs)
```

## 15.11 Agent级模型配置（借鉴AI Hedge Fund）

每个Agent可独立配置模型，覆盖全局默认值：

```python
# config.yaml中的Agent级模型配置
agent_models:
  # 全局默认
  default:
    quick_think: "deepseek-chat"
    deep_think: "deepseek-reasoner"

  # 单独覆盖
  market_analyst:
    quick_think: "deepseek-chat"        # 用快速模型
  research_manager:
    deep_think: "deepseek-reasoner"     # 用推理模型
  portfolio_manager:
    deep_think: "deepseek-reasoner"     # 用推理模型
  buffett_master:
    quick_think: "qwen-plus"            # 大师用不同提供商
```

### 实现

```python
class AgentModelRouter:
    """Agent级模型路由"""

    def __init__(self, global_config: dict, agent_models_config: dict):
        self.global_config = global_config
        self.agent_models = agent_models_config or {}

    def get_model(self, agent_name: str, tier: str = "quick") -> str:
        """
        获取Agent使用的模型。
        优先级: Agent级配置 > 全局配置
        """
        # 检查Agent级配置
        agent_config = self.agent_models.get(agent_name, {})
        if tier in agent_config:
            return agent_config[tier]

        # 使用全局配置
        tier_key = f"{tier}_think"
        return self.global_config.get(tier_key, "deepseek-chat")
```

## 15.12 Pydantic自动默认值（借鉴AI Hedge Fund）

根据Pydantic字段类型自动生成fallback值，无需为每个Agent手写default_factory：

```python
def create_default_response(model_class: type[BaseModel]) -> BaseModel:
    """
    根据Pydantic模型的字段类型，自动生成安全的默认响应。
    借鉴AI Hedge Fund的create_default_response模式。
    """
    default_values = {}

    for field_name, field_info in model_class.model_fields.items():
        annotation = field_info.annotation

        if annotation == str:
            default_values[field_name] = "数据不足，无法分析"
        elif annotation == int:
            default_values[field_name] = 0
        elif annotation == float:
            default_values[field_name] = 0.0
        elif annotation == bool:
            default_values[field_name] = False
        elif hasattr(annotation, "__origin__"):
            origin = annotation.__origin__
            if origin == list:
                default_values[field_name] = []
            elif origin == dict:
                default_values[field_name] = {}
            elif origin == Literal:
                # Literal类型：取第一个允许的值
                args = annotation.__args__
                if args:
                    default_values[field_name] = args[0]
        elif hasattr(annotation, "__args__"):
            # Optional类型：取内部类型
            args = annotation.__args__
            inner = args[0] if args else str
            if inner == str:
                default_values[field_name] = ""
            elif inner == float:
                default_values[field_name] = None
            elif inner == int:
                default_values[field_name] = None

    return model_class(**default_values)
```

### 使用示例

```python
# 无需手写default_factory
response = call_llm(
    prompt=messages,
    pydantic_model=PortfolioDecision,
    # default_factory自动根据PortfolioDecision的字段类型生成
)
```

## 15.13 使用示例

```python
# 在Agent工厂中使用
def create_market_analyst(llm_client: AsyncLLMClient):
    def market_analyst_node(state):
        ticker = state["company_of_interest"]

        # 检查预算
        if llm_client.counter.should_fast_mode():
            # 快速模式：简化prompt
            prompt = build_fast_prompt(state)
        else:
            prompt = build_full_prompt(state)

        # 调用LLM
        response = llm_client.complete(
            messages=prompt,
            model_tier="quick",
            agent_name="market_analyst",
        )

        # 记录token
        llm_client.counter.record("market_analyst", ticker, response.token_usage)

        return {"market_report": response.content, "messages": [response.content]}

    return market_analyst_node
```

---

**依赖**: S3(架构), S11(技术栈)
**被依赖**: S4(Agent), S6(工作流)
