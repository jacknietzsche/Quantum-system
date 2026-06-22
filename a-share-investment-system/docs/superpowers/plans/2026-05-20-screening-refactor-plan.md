# 选股模块重构实施计划 — AI 深度分析 + 交易计划生成

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development or executing-plans to implement this plan task-by-task.

**Goal:** 重构 StockScreener 的深度分析阶段，让 AI Agent 通过 Tool calling 自主调用 MasterAgent 和 SkillEngine 对初筛候选股进行深度分析，并结合持仓生成完整交易计划

**Architecture:** 保留现有 HardFilter 初筛层 → 新增三层 AI Agent 流水线 (StockAgent → PortfolioAgent → DecisionAgent)，通过 OpenAI-compatible function calling 实现 Agent 自主选择大师和技能

**Tech Stack:** httpx (已有), Pydantic, asyncio, deepseek.com:deepseek-v4-pro (主力) / chatanywhere.com.cn:gpt-4o-mini (降级)

**模型测试确认:**
- ✅ DeepSeek-v4-pro (deepseek.com) — 支持 function calling，主力模型
- ✅ gpt-4o-mini (chatanywhere.com.cn) — 支持 function calling，降级模型
- ✗ DeepSeek-R1 (SiliconFlow) — 推理模型不支持 function calling，从默认配置移除

---

### Task 1: 新增 LLM 提供者配置 (scnet.cn / chatanywhere.com.cn)

**Files:**
- Modify: `shared/config.py` — 新增 deepseek.com 和 chatanywhere.com.cn 提供者端点
- Modify: `config/config.yaml` — 添加新的 API 密钥和默认模型

**Step 1: Read existing config structure**

Read `shared/config.py` to understand how LLM providers are configured.

**Step 2: Identify the LLM configuration pattern**

Find the `_llm` or model/provider related configuration in `shared/config.py` and `config/config.yaml`.

**Step 3: Read `services/agent_workflow.py` LLM section**

Read lines 40-85 of `services/agent_workflow.py` to understand how LLM HTTP calls are currently made.

---

### Task 2: 构建 Tool-calling 基础设施

**Files:**
- Create: `services/agents/base_agent.py` — Tool 注册 + function calling 循环基类
- Create: `services/agents/tool_registry.py` — MasterAgent/SkillEngine/Data 工具注册表
- Test: `tests/test_tool_calling.py`

**Step 1: Write the failing test**

Create `tests/test_tool_calling.py`:

```python
"""测试 Tool calling 循环"""
import pytest
from services.agents.base_agent import AgentTool, AgentExecutor

def test_tool_registry():
    """测试工具注册和调用"""
    registry = AgentTool.create_registry()
    tool = AgentTool(
        name="calculator",
        description="Simple calculator",
        parameters={
            "a": 0, "b": 0, "op": "add"
        },
        required_params=["a", "b", "op"],
        fn=lambda a,b,op: {"result": eval(f"{a}{'+' if op=='add' else '-' if op=='sub' else '*' if op=='mul' else '/'}{b}")}
    )
    registry["calculator"] = tool
    result = tool.fn(2, 2, "add")
    assert result == {"result": 4}
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/test_tool_calling.py -v
Expected: FAIL with ModuleNotFoundError
```

**Step 3: Create base_agent.py**

```python
"""Agent Tool calling 基础设施 — OpenAI-compatible function calling 循环"""
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger(__name__)


@dataclass
class AgentTool:
    """Agent 工具定义"""
    name: str
    description: str
    parameters: dict
    fn: Callable
    required_params: list = field(default_factory=list)

    def to_openai_tool(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        k: {"type": "string" if isinstance(v, str) else "number"}
                        for k, v in self.parameters.items()
                    },
                    "required": self.required_params,
                }
            }
        }

    @staticmethod
    def create_registry() -> dict[str, "AgentTool"]:
        return {}


class AgentExecutor:
    """通用 Agent 执行器 — 支持 function calling 循环"""

    def __init__(self, llm_config: dict, tools: list[AgentTool], max_turns: int = 8):
        self.llm_config = llm_config
        self.tool_map = {t.name: t for t in tools}
        self.max_turns = max_turns

    def run(self, system_prompt: str, user_message: str) -> dict:
        """执行 agent 工具循环，返回最终响应"""
        import httpx
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]
        tool_defs = [t.to_openai_tool() for t in self.tool_map.values()]

        turn = 0
        while turn < self.max_turns:
            turn += 1
            resp = httpx.post(
                f"{self.llm_config['base_url']}/chat/completions",
                headers={"Authorization": f"Bearer {self.llm_config['api_key']}",
                         "Content-Type": "application/json"},
                json={"model": self.llm_config["model"],
                      "messages": messages,
                      "tools": tool_defs,
                      "tool_choice": "auto"},
                timeout=60,
            )
            data = resp.json()
            choice = data["choices"][0]
            msg = choice["message"]

            if choice.get("finish_reason") == "tool_calls":
                messages.append(msg)
                for tc in msg.get("tool_calls", []):
                    tool_name = tc["function"]["name"]
                    args = json.loads(tc["function"]["arguments"])
                    tool = self.tool_map.get(tool_name)
                    if tool:
                        try:
                            result = tool.fn(**args)
                            messages.append({
                                "role": "tool",
                                "tool_call_id": tc["id"],
                                "content": json.dumps(result, ensure_ascii=False),
                            })
                        except Exception as e:
                            messages.append({
                                "role": "tool",
                                "tool_call_id": tc["id"],
                                "content": json.dumps({"error": str(e)}),
                            })
            else:
                return {"content": msg.get("content", ""), "turns": turn, "finish_reason": choice.get("finish_reason")}

        return {"content": "Max turns reached", "turns": turn, "finish_reason": "max_turns"}
```

**Step 4: Run test to verify it passes**

```bash
pytest tests/test_tool_calling.py -v
Expected: PASS
```

---

### Task 3: 注册 Agent 工具集 (MasterAgent + SkillEngine + Data)

**Files:**
- Create: `services/agents/tool_registry.py`
- Test: `tests/test_tool_registry.py`

**Step 1: Write tool_registry.py**

```python
"""Agent Tool 注册表 — 将 MasterAgent / SkillEngine / Data 包装为 AgentTool"""
from services.agents.base_agent import AgentTool
from services.master_agents import get_master_agents
from services.skill_engine import get_skill_engine


def get_master_list_tool() -> AgentTool:
    """工具: 列出所有可用大师"""
    registry = get_master_agents()
    masters = registry.get_all_names()
    master_descriptions = {
        "cathie_wood": "高增长成长股分析",
        "bill_ackman": "维权投资+管理层驱动",
        "michael_burry": "逆向价值+尾部风险",
        "stanley_druckenmiller": "宏观趋势+动量",
        "aswath_damodaran": "DCF估值+风险溢价",
        "phil_fisher": "成长型+管理层质量",
        "rakesh_jhunjhunwala": "印度式价值投资",
        "howard_marks": "市场周期+第二层思维",
        "joel_greenblatt": "魔法公式(高ROIC+低估值)",
        "peter_lynch_growth": "GARP成长+十倍股",
        "risk_sentinel": "综合风险评估",
        "limit_up_master": "短线涨停博弈",
        "turtle_master": "趋势突破+ATR仓位",
        "candlestick_master": "K线形态识别",
        "trader_vic_master": "1-2-3法则趋势分析",
        "livermore_master": "关键点+金字塔仓位",
        "momentum_master": "中期趋势+动量",
    }
    master_list = [f"{name}({master_descriptions.get(name, '')})" for name in masters]
    return AgentTool(
        name="get_master_list",
        description="获取所有可用的投资大师分析器列表",
        parameters={},
        fn=lambda: {"masters": master_list, "count": len(master_list)},
    )


def get_master_analyze_tool() -> AgentTool:
    """工具: 调用指定大师分析股票"""
    registry = get_master_agents()
    def _analyze(stock_code: str, master_names: list) -> dict:
        from services.quant_analyzers import QuantAnalyzers
        qa = QuantAnalyzers()
        results = registry.analyze_selected(stock_code, {"pe_ratio": 0}, master_names)
        return {"results": [r for r in results if r]}
    return AgentTool(
        name="master_analyze",
        description="调用指定的投资大师分析器对股票进行量化评估",
        parameters={"stock_code": "股票代码(如600519)", "master_names": "大师名称列表"},
        required_params=["stock_code", "master_names"],
        fn=_analyze,
    )


def get_skill_knowledge_tool() -> AgentTool:
    """工具: 获取技能知识"""
    engine = get_skill_engine()
    def _knowledge(skill_name: str, context: str) -> dict:
        known_skills = engine.get_all_skill_names()
        if skill_name not in known_skills:
            available = [s for s in known_skills if skill_name.lower() in s.lower()]
            if not available:
                return {"error": f"Unknown skill: {skill_name}", "available": known_skills}
            skill_name = available[0]
        knowledge = engine.inject_knowledge(skill_name, context)
        return {"skill": skill_name, "knowledge": knowledge[:3000]}
    return AgentTool(
        name="skill_knowledge",
        description="获取指定投资技能的分析框架和知识。可用技能包括: buffett(巴菲特价值投资), munger-perspective(芒格思维), taleb-perspective(塔勒布反脆弱), financial-health(财务健康), industry-competition-moat(行业竞争护城河), risk-warning-catalysts(风险预警), valuation-investment-strategy(估值策略)",
        parameters={"skill_name": "技能名称", "context": "上下文(股票代码或分析焦点)"},
        required_params=["skill_name"],
        fn=_knowledge,
    )


def create_default_tools() -> list[AgentTool]:
    """创建默认的工具集"""
    return [
        get_master_list_tool(),
        get_master_analyze_tool(),
        get_skill_knowledge_tool(),
    ]
```

---

### Task 4: 新建 TradingPlan 数据模型

**Files:**
- Create: `services/trading_plan.py`
- Test: `tests/test_trading_plan.py`

**Step 1: Write trading_plan.py**

```python
"""交易计划数据模型 — 选股模块的最终输出"""
from dataclasses import dataclass, field
from typing import Optional

@dataclass
class OrderItem:
    """单笔交易指令"""
    code: str
    name: str
    action: str  # 买入/卖出/加仓/减仓/持有
    quantity: Optional[int] = None
    weight: Optional[str] = None  # "15%"
    limit_price: Optional[str] = None
    stop_loss: Optional[str] = None
    take_profit: Optional[str] = None
    reasoning: str = ""
    confidence: str = "中"  # 高/中/低
    masters_used: list = field(default_factory=list)
    skills_injected: list = field(default_factory=list)

@dataclass
class ConditionalOrder:
    """条件单"""
    condition: str
    action: str
    timing: str = ""

@dataclass
class ExecutionPlan:
    """执行计划"""
    immediate_summary: str = ""
    immediate_orders: list = field(default_factory=list)
    conditional_orders: list = field(default_factory=list)
    monitoring_signals: list = field(default_factory=list)

@dataclass
class RiskManagement:
    """风控规则"""
    circuit_breaker: str = ""
    portfolio_stop: str = ""
    key_risks: list = field(default_factory=list)

@dataclass
class PortfolioPosition:
    """持仓位置建议"""
    code: str
    weight: float
    action: str

@dataclass
class TradingPlan:
    """完整的交易计划"""
    market_regime: str = ""
    risk_level: str = "中等"
    max_position: float = 0.7
    portfolio_assessment: dict = field(default_factory=dict)
    current_positions: list = field(default_factory=list)
    execution: ExecutionPlan = field(default_factory=ExecutionPlan)
    risk: RiskManagement = field(default_factory=RiskManagement)

    def to_dict(self) -> dict:
        import json
        return json.loads(json.dumps(self, default=lambda o: o.__dict__ if hasattr(o, '__dict__') else str(o)))
```

---

### Task 5: 新建 StockAgent — AI 个股分析师

**Files:**
- Create: `services/agents/stock_agent.py`
- Test: `tests/test_stock_agent.py`

**Step 1: Write stock_agent.py**

```python
"""StockAgent — AI 个股分析师，通过 Tool calling 自主调用大师和技能"""
import json
from services.agents.base_agent import AgentExecutor, AgentTool
from services.agents.tool_registry import create_default_tools

STOCK_AGENT_SYSTEM_PROMPT = """你是一位专业的 A 股股票分析师。你的任务是分析一只候选股票，给出是否值得买入的判断。

## 工作流程
1. **了解可用工具**: 调用 get_master_list() 查看可用的投资大师分析器
2. **调用大师分析**: 根据股票特征选择 2-4 个最合适的大师，调用 master_analyze()
3. **注入技能知识**: 需要特定分析框架时，调用 skill_knowledge() 获取方法论
4. **综合判断**: 结合大师评分和技能知识，输出分析结论

## 输出要求
分析完所有数据后，输出 JSON 格式的结论:
{
  "stock_code": "股票代码",
  "overall_score": 0-100,
  "signal": "买入/持有/观望/卖出",
  "confidence": "高/中/低",
  "masters_used": ["大师名(分数)"],
  "skills_injected": ["技能名"],
  "entry": {"price_range": "入场区间", "timing": "时机"},
  "stop_loss": "止损价位或比例",
  "take_profit": "目标价位或比例",
  "position_size": "仓位建议(重仓/中仓/轻仓/观望)",
  "reasoning": "综合分析推理过程(100-300字)"
}
"""


class StockAgent:
    """个股分析 Agent"""

    def __init__(self, llm_config: dict):
        self.llm_config = llm_config
        self.tools = create_default_tools()

    async def analyze(self, stock: dict) -> dict:
        """分析一只股票"""
        user_msg = json.dumps({
            "stock_code": stock.get("stock_code"),
            "stock_name": stock.get("stock_name"),
            "price": stock.get("price"),
            "pe": stock.get("pe"),
            "pb": stock.get("pb"),
            "roe": stock.get("roe"),
            "market_cap": stock.get("market_cap"),
            "turnover_rate": stock.get("turnover_rate"),
            "volume_ratio": stock.get("volume_ratio"),
            "change_pct": stock.get("change_pct"),
            "change_pct_5d": stock.get("change_pct_5d"),
            "change_pct_20d": stock.get("change_pct_20d"),
            "change_pct_60d": stock.get("change_pct_60d"),
            "industry": stock.get("industry"),
            "trend": stock.get("trend"),
            "ma_alignment": stock.get("ma_alignment"),
            "income_growth_3y": stock.get("earnings_growth_3y"),
            "revenue_growth_3y": stock.get("revenue_growth_3y"),
            "free_cash_flow": stock.get("free_cash_flow"),
            "debt_to_equity": stock.get("debt_to_equity"),
            "gross_margin": stock.get("gross_margin"),
            "hot_score": stock.get("hot_score", 0),
            "consecutive_limit_ups": stock.get("consecutive_limit_ups", 0),
        }, ensure_ascii=False)

        executor = AgentExecutor(self.llm_config, self.tools)
        result = executor.run(STOCK_AGENT_SYSTEM_PROMPT, user_msg)

        content = result.get("content", "")
        try:
            parsed = json.loads(content)
            if "stock_code" not in parsed:
                parsed["stock_code"] = stock.get("stock_code")
            return parsed
        except (json.JSONDecodeError, TypeError):
            return {
                "stock_code": stock.get("stock_code"),
                "overall_score": 50,
                "signal": "观望",
                "confidence": "低",
                "error": "parse_failed",
                "raw": content[:500],
            }
```

---

### Task 6: 新建 PortfolioAgent — 组合分析师

**Files:**
- Create: `services/agents/portfolio_agent.py`

**Step 1: Write portfolio_agent.py**

```python
"""PortfolioAgent — 组合级分析"""
import json
from services.agents.base_agent import AgentExecutor

PORTFOLIO_AGENT_SYSTEM_PROMPT = """你是一位专业的投资组合分析师。你的任务是根据已完成的个股分析结果和当前持仓，给出组合层面的建议。

## 输入数据
- stock_opinions: 每只候选股的 StockAgent 分析结果
- portfolio_holdings: 当前持仓(如有)

## 输出要求
输出 JSON:
{
  "portfolio_risk_score": 1-10,
  "sector_exposure": {"行业名": "占比%"},
  "total_candidates": 数量,
  "recommended_count": 建议关注的股票数量,
  "position_plan": [
    {"code": "代码", "weight": 0.15, "action": "新开仓/加仓/持有/减仓/清仓", "reason": "原因"}
  ],
  "warnings": ["风险警告列表"]
}
"""


class PortfolioAgent:
    """组合分析 Agent"""

    def __init__(self, llm_config: dict):
        self.llm_config = llm_config

    async def analyze(self, stock_opinions: list, portfolio_holdings: dict) -> dict:
        user_msg = json.dumps({
            "stock_opinions": stock_opinions,
            "portfolio_holdings": portfolio_holdings,
        }, ensure_ascii=False)

        executor = AgentExecutor(self.llm_config, [])
        result = executor.run(PORTFOLIO_AGENT_SYSTEM_PROMPT, user_msg)

        try:
            return json.loads(result.get("content", "{}"))
        except (json.JSONDecodeError, TypeError):
            return {"portfolio_risk_score": 5, "warnings": ["Analysis failed"]}
```

---

### Task 7: 新建 DecisionAgent — 交易计划生成器

**Files:**
- Create: `services/agents/decision_agent.py`

**Step 1: Write decision_agent.py**

```python
"""DecisionAgent — 生成最终交易计划"""
import json
from services.agents.base_agent import AgentExecutor
from services.trading_plan import TradingPlan, ExecutionPlan, RiskManagement, OrderItem

DECISION_AGENT_SYSTEM_PROMPT = """你是一位专业的投资组合经理。你的任务是根据个股分析和组合评估，制定一份完整的交易计划。

## 输入
- stock_opinions: 所有候选股的深度分析结果
- portfolio_assessment: 组合层面评估
- portfolio_holdings: 当前持仓(如有)

## 输出要求
输出 JSON:
{
  "market_assessment": {"regime": "震荡偏多/震荡偏空/单边上涨/单边下跌", "risk_level": "低/中/高", "max_position": 0.7},
  "execution_plan": {
    "immediate_summary": "今日操作概要",
    "orders": [
      {"code": "代码", "name": "名称", "action": "买入/卖出/加仓/减仓/持有",
       "quantity": 股数, "weight": "仓位比例", "limit_price": "限价",
       "stop_loss": "止损位", "take_profit": "目标位",
       "confidence": "高/中/低", "reasoning": "理由"}
    ],
    "conditional_orders": [
      {"condition": "触发条件", "action": "操作", "timing": "时间"}
    ]
  },
  "risk_management": {
    "circuit_breaker": "熔断条件",
    "portfolio_stop": "组合止损线",
    "key_risks": ["风险1", "风险2"]
  }
}
"""


class DecisionAgent:
    """交易计划制定 Agent"""

    def __init__(self, llm_config: dict):
        self.llm_config = llm_config

    async def decide(self, stock_opinions: list, portfolio_assessment: dict,
                     portfolio_holdings: dict) -> TradingPlan:
        user_msg = json.dumps({
            "stock_opinions": stock_opinions,
            "portfolio_assessment": portfolio_assessment,
            "portfolio_holdings": portfolio_holdings,
        }, ensure_ascii=False)

        executor = AgentExecutor(self.llm_config, [])
        result = executor.run(DECISION_AGENT_SYSTEM_PROMPT, user_msg)

        plan = TradingPlan()
        try:
            data = json.loads(result.get("content", "{}"))
            plan.market_regime = data.get("market_assessment", {}).get("regime", "")
            plan.risk_level = data.get("market_assessment", {}).get("risk_level", "中等")
            plan.max_position = data.get("market_assessment", {}).get("max_position", 0.7)
            exec_plan = data.get("execution_plan", {})
            plan.execution.immediate_summary = exec_plan.get("immediate_summary", "")
            for o in exec_plan.get("orders", []):
                plan.execution.immediate_orders.append(OrderItem(**o))
            for c in exec_plan.get("conditional_orders", []):
                plan.execution.conditional_orders.append(c)
            risk = data.get("risk_management", {})
            plan.risk = RiskManagement(
                circuit_breaker=risk.get("circuit_breaker", ""),
                portfolio_stop=risk.get("portfolio_stop", ""),
                key_risks=risk.get("key_risks", []),
            )
        except Exception as e:
            plan.risk.key_risks = [f"DecisionAgent parse error: {e}"]
        return plan
```

---

### Task 8: 新建 TradingStrategyOrchestrator — 编排器

**Files:**
- Create: `services/trading_orchestrator.py`
- Test: `tests/test_trading_orchestrator.py`

**Step 1: Write trading_orchestrator.py**

```python
"""TradingStrategyOrchestrator — AI 深度分析编排器"""
import asyncio
import logging
from shared.config import Config

logger = logging.getLogger(__name__)


class TradingStrategyOrchestrator:
    """编排 StockAgent → PortfolioAgent → DecisionAgent 完整流程"""

    def __init__(self, style: str = "hybrid", portfolio_holdings: dict = None):
        self.style = style
        self.portfolio_holdings = portfolio_holdings or {}
        self.llm_config = self._resolve_llm_config()

    def _resolve_llm_config(self) -> dict:
        """解析 LLM 配置，优先 deepseek-v4-pro → 降级 gpt-4o-mini"""
        cfg = Config()
        default_model = cfg.get("screening.deep_analysis.model", "deepseek.com:deepseek-v4-pro")

        provider_map = {
            "deepseek.com": {
                "base_url": "https://api.deepseek.com/v1",
                "api_key": "sk-3f68ce646cd74e9eaae605dcfa361657",
            },
            "chatanywhere.com.cn": {
                "base_url": "https://api.chatanywhere.com.cn/v1",
                "api_key": "sk-3mITKj9snpemnScU8dmNuulMHwfr9whgGtkNY3VOWK1uEz6z",
            },
        }

        if ":" in default_model:
            provider, model = default_model.split(":", 1)
        else:
            provider, model = "deepseek.com", default_model

        provider_cfg = provider_map.get(provider, provider_map["deepseek.com"])
        return {**provider_cfg, "model": model}

    async def run(self, candidates: list[dict]) -> dict:
        """执行完整分析流程"""
        from services.agents.stock_agent import StockAgent
        from services.agents.portfolio_agent import PortfolioAgent
        from services.agents.decision_agent import DecisionAgent

        parallel_limit = 3
        semaphore = asyncio.Semaphore(parallel_limit)
        stock_agent = StockAgent(self.llm_config)

        async def _analyze_one(stock: dict) -> dict:
            async with semaphore:
                try:
                    return await stock_agent.analyze(stock)
                except Exception as e:
                    logger.warning(f"StockAgent failed for {stock.get('stock_code')}: {e}")
                    return {
                        "stock_code": stock.get("stock_code"),
                        "stock_name": stock.get("stock_name"),
                        "overall_score": 40,
                        "signal": "观望",
                        "error": str(e),
                    }

        stock_opinions = await asyncio.gather(
            *[_analyze_one(s) for s in candidates]
        )

        portfolio_agent = PortfolioAgent(self.llm_config)
        try:
            portfolio_assessment = await portfolio_agent.analyze(
                stock_opinions, self.portfolio_holdings
            )
        except Exception as e:
            logger.warning(f"PortfolioAgent failed: {e}")
            portfolio_assessment = {"portfolio_risk_score": 5, "warnings": [str(e)]}

        decision_agent = DecisionAgent(self.llm_config)
        try:
            trading_plan = await decision_agent.decide(
                stock_opinions, portfolio_assessment, self.portfolio_holdings
            )
        except Exception as e:
            logger.warning(f"DecisionAgent failed: {e}")
            trading_plan = {}

        return {
            "style": self.style,
            "stock_opinions": stock_opinions,
            "portfolio_assessment": portfolio_assessment,
            "trading_plan": trading_plan.to_dict() if hasattr(trading_plan, 'to_dict') else trading_plan,
        }
```

---

### Task 9: 新增 HardFilter 层（基于用户量化标准）

**Files:**
- Create: `services/hard_filter.py`
- Test: `tests/test_hard_filter.py`

**Step 1: Write hard_filter.py**

```python
"""HardFilter — 三策略量化初筛 + 负面排除"""
from typing import Callable


class HardFilter:
    """量化初筛引擎 — 短期/中期/长期三策略 + 通用负面排除"""

    def __init__(self, style: str = "hybrid"):
        self.style = style

    def apply(self, universe: list[dict]) -> list[dict]:
        filter_fn = self._get_filter()
        candidates = filter_fn(universe)
        candidates = self._negative_exclusion(candidates)
        return self._fallback_if_empty(candidates, universe)

    def _get_filter(self) -> Callable:
        style_map = {
            "short_term": self._filter_short_term,
            "mid_term": self._filter_mid_term,
            "long_term": self._filter_long_term,
            "limit_up": self._filter_short_term,
            "momentum": self._filter_mid_term,
            "value": self._filter_long_term,
            "hybrid": self._filter_short_term,
        }
        return style_map.get(self.style, self._filter_hybrid)

    def _filter_short_term(self, stocks: list[dict]) -> list[dict]:
        """短期(1d-4w)：成交额>1亿, 5日涨幅>5%, 量比>1.5, 均线多头"""
        passed = []
        for s in stocks:
            if s.get("amount", 0) < 1e8: continue
            if s.get("change_pct_5d", -999) < 5: continue
            if s.get("volume_ratio", 0) < 1.5: continue
            ma20, ma60 = s.get("ma20", 0), s.get("ma60", 0)
            if ma20 <= 0 or ma60 <= 0: continue
            if s.get("price", 0) <= ma20 or ma20 <= ma60: continue
            passed.append(s)
        passed.sort(key=lambda x: x.get("amount", 0), reverse=True)
        return passed[:200]

    def _filter_mid_term(self, stocks: list[dict]) -> list[dict]:
        """中期(1-12m): 60日涨幅>20%, 股价>年线, PE>0, 市值50-500亿"""
        passed = []
        for s in stocks:
            if s.get("change_pct_60d", -999) < 20: continue
            ma250 = s.get("ma250", 0)
            if ma250 <= 0 or s.get("price", 0) <= ma250: continue
            if s.get("pe", 0) <= 0: continue
            mcap = s.get("market_cap", 0)
            if mcap < 50 or mcap > 500: continue
            passed.append(s)
        passed.sort(key=lambda x: x.get("change_pct_60d", 0), reverse=True)
        return passed[:200]

    def _filter_long_term(self, stocks: list[dict]) -> list[dict]:
        """长期(1y+): ROE>15%, FCF>0, 负债率<60%, PE>0"""
        passed = []
        for s in stocks:
            if s.get("roe", 0) < 15: continue
            if s.get("free_cash_flow", 0) <= 0: continue
            debt = s.get("debt_to_equity", 999)
            if 0 < debt < 1.5: continue
            if debt >= 1.5: continue
            if s.get("pe", 0) <= 0: continue
            passed.append(s)
        passed.sort(key=lambda x: x.get("roe", 0), reverse=True)
        return passed[:200]

    def _filter_hybrid(self, stocks: list[dict]) -> list[dict]:
        """混合: 流动性+趋势+基本面"""
        passed = []
        for s in stocks:
            if s.get("amount", 0) < 5e7: continue
            if s.get("turnover_rate", 0) < 0.5: continue
            ma20 = s.get("ma20", 0)
            if ma20 <= 0 or s.get("price", 0) <= ma20: continue
            if s.get("pe", 0) <= 0: continue
            if s.get("roe", 0) < 10: continue
            passed.append(s)
        passed.sort(key=lambda x: x.get("pe", 99999))
        return passed[:200]

    def _negative_exclusion(self, stocks: list[dict]) -> list[dict]:
        """通用负面排除"""
        return [
            s for s in stocks
            if not s.get("stock_name", "").startswith(("*ST", "ST", "退"))
            and s.get("price", 0) > 0
        ]

    @staticmethod
    def _fallback_if_empty(passed: list[dict], universe: list[dict]) -> list[dict]:
        if len(passed) >= 50:
            return passed
        passed_set = {id(s) for s in passed}
        extras = sorted(universe, key=lambda x: x.get("amount", 0), reverse=True)
        for s in extras:
            if id(s) in passed_set or s.get("price", 0) <= 0:
                continue
            passed.append(s)
            passed_set.add(id(s))
            if len(passed) >= 50:
                break
        return passed
```

---

### Task 10: 改造 StockScreener — 接入新流水线

**Files:**
- Modify: `services/stock_screener.py`
- Modify: `api/routes/screening.py`
- Deprecate: `services/agent_workflow.py`

**Step 1: Modify `services/stock_screener.py`**

Replace `_run_hybrid_pipeline`, `_run_value_pipeline`, `_run_limit_up_pipeline`, `_run_momentum_pipeline` with unified calls to `TradingStrategyOrchestrator`.

Remove: `_stage3_deep_analyze`, `_run_stage4_agent_workflow`, `_stage3_enhanced_*`

Replace pipeline methods with:

```python
def _run_analysis_pipeline(self, universe, regime, top_n):
    from services.trading_orchestrator import TradingStrategyOrchestrator
    from services.hard_filter import HardFilter

    hf = HardFilter(self.style)
    candidates = hf.apply(universe)

    orchestrator = TradingStrategyOrchestrator(
        style=self.style,
        portfolio_holdings=getattr(self, '_portfolio_holdings', None),
    )
    result = asyncio.run(orchestrator.run(candidates[:self.stage3_deep_top]))

    recommendations = []
    for i, opinion in enumerate(result.get("stock_opinions", [])[:top_n]):
        recommendations.append({
            "rank": i + 1,
            "stock_code": opinion.get("stock_code", ""),
            "stock_name": opinion.get("stock_name", ""),
            "score": opinion.get("overall_score", 50),
            "signal": opinion.get("signal", "观望"),
            "confidence": opinion.get("confidence", "低"),
            "masters_used": opinion.get("masters_used", []),
            "reasoning": opinion.get("reasoning", "")[:200],
        })

    self._save_trading_plan(result.get("trading_plan", {}))

    return ServiceResult.ok(data={
        "total_screened": len(universe),
        "filter_passed": len(candidates),
        "recommendations": recommendations,
        "style": self.style,
        "trading_plan": result.get("trading_plan", {}),
    })
```

**Step 2: Modify `api/routes/screening.py`**

Adjust SSE events to reflect new pipeline stages:

```python
# Replace stage names
EVENT_MAP = {
    0: "全市场加载中...",
    1: "量化初筛进行中...",
    2: "AI 个股分析中...",
    3: "组合分析中...",
    4: "生成交易计划中...",
}
```

Add new endpoint for trading plan:

```python
@router.get("/plan")
async def get_latest_plan():
    """获取最新交易计划"""
    from shared.models import AnalysisTask, get_session
    session = get_session()
    plan = session.query(AnalysisTask).filter(
        AnalysisTask.task_type == "trading_plan"
    ).order_by(AnalysisTask.id.desc()).first()
    session.close()
    if plan:
        return {"ok": True, "plan": json.loads(plan.result_json or "{}")}
    return {"ok": False, "error": "No plan found"}
```

**Step 3: Deprecate `services/agent_workflow.py`**

Add a deprecation warning at the top of `services/agent_workflow.py`:

```python
import warnings
warnings.warn(
    "agent_workflow.py is deprecated. Use services/trading_orchestrator.py instead.",
    DeprecationWarning,
    stacklevel=2,
)
```

---

### Task 11: 更新配置和 LLM 层

**Files:**
- Modify: `config/config.yaml`
- Modify: `shared/config.py` (if needed)

**Step 1: Update `config/config.yaml`**

```yaml
screening:
  hard_filter:
    short_term:
      min_amount: 100000000
      min_change_5d: 5
      min_volume_ratio: 1.5
      require_uptrend: true
    mid_term:
      min_change_60d: 20
      min_market_cap: 50
      max_market_cap: 500
      require_above_ma250: true
    long_term:
      min_roe: 15
      min_fcf: 1
      max_debt_equity: 1.5
  deep_analysis:
    enabled: true
    model: "deepseek.com:deepseek-v4-pro"
    fallback_model: "chatanywhere.com.cn:gpt-4o-mini"
    parallel_limit: 3
```

---

### Task 12: 集成测试

**Files:**
- Create: `tests/test_screening_integration.py`

```python
"""集成测试"""
import pytest
from services.hard_filter import HardFilter

class TestScreeningIntegration:
    def test_hard_filter_runs(self):
        hf = HardFilter("short_term")
        mock_stocks = [
            {"stock_code": "000001", "stock_name": "平安银行",
             "price": 12, "amount": 2e8, "change_pct_5d": 8,
             "volume_ratio": 2.0, "ma20": 11, "ma60": 10},
            {"stock_code": "000002", "stock_name": "万科A",
             "price": 8, "amount": 5e7, "change_pct_5d": 2,
             "volume_ratio": 0.8, "ma20": 9, "ma60": 8},
        ]
        result = hf.apply(mock_stocks)
        assert len(result) > 0
        assert result[0]["stock_code"] == "000001"
```

---

### Task 13: 验证

```bash
# 格式检查
ruff check services/agents/ tests/

# 类型检查
mypy services/agents/ services/trading_orchestrator.py

# 单元测试
pytest tests/test_tool_calling.py tests/test_hard_filter.py -v

# 集成测试
pytest tests/test_screening_integration.py -v
```

---

## 执行顺序摘要

| 顺序 | Task | 文件 | 行数 |
|------|------|------|------|
| 1 | Tool-calling 基类 | `services/agents/base_agent.py` | ~90 |
| 2 | Tool 注册表 | `services/agents/tool_registry.py` | ~90 |
| 3 | 交易计划模型 | `services/trading_plan.py` | ~70 |
| 4 | StockAgent | `services/agents/stock_agent.py` | ~80 |
| 5 | PortfolioAgent | `services/agents/portfolio_agent.py` | ~50 |
| 6 | DecisionAgent | `services/agents/decision_agent.py` | ~90 |
| 7 | Orchestrator | `services/trading_orchestrator.py` | ~100 |
| 8 | HardFilter | `services/hard_filter.py` | ~120 |
| 9 | 改造 StockScreener | `services/stock_screener.py` | ~50变更 |
| 10 | 改造 API 路由 | `api/routes/screening.py` | ~30变更 |
| 11 | 配置更新 | `config/config.yaml` | ~30 |
| 12 | 测试 | `tests/` | ~150 |

**总计: ~11 文件, ~950 行净新增**

**预估实施时间:** ~2-3小时(含测试和验证)
