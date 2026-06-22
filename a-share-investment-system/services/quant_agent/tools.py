"""工具注册表 — 所有量化能力封装为 Tool, 供 QuantAgent 调用"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)


class ToolRegistry:
    """工具注册表

    所有可被AI调用的量化能力 (市场诊断/筛选/评分等) 注册于此。
    AI通过工具名 + 参数调用, 无需关心具体实现。
    """

    def __init__(self):
        self._tools: dict[str, Callable] = {}
        self._schemas: dict[str, dict] = {}
        self._descriptions: dict[str, str] = {}

    def register(
        self, name: str, func: Callable, description: str = "", schema: dict | None = None
    ):
        """注册工具

        Args:
            name: 工具唯一名 (如 'market:diagnose')
            func: 可调用对象
            description: 工具描述 (用于AI理解工具用途)
            schema: 参数 JSON Schema (用于结构化调用)
        """
        self._tools[name] = func
        self._descriptions[name] = description
        self._schemas[name] = schema or {
            "name": name,
            "description": description,
            "parameters": {"type": "object", "properties": {}},
        }
        logger.debug("[ToolRegistry] registered: %s", name)

    def call(self, name: str, **kwargs) -> Any:
        """调用工具"""
        func = self._tools.get(name)
        if func is None:
            raise KeyError(f"工具未注册: {name}")
        logger.debug("[ToolRegistry] calling: %s kwargs=%s", name, kwargs)
        return func(**kwargs)

    def list_tools(self) -> list[dict]:
        """返回所有工具列表 (供LLM function calling)"""
        return [
            {
                "name": n,
                "description": self._descriptions.get(n, ""),
                "parameters": self._schemas[n].get("parameters", {}),
            }
            for n in self._tools
        ]


def default_tool_registry() -> ToolRegistry:
    """创建默认工具注册表, 注册当前系统所有能力"""
    registry = ToolRegistry()

    # ── 1. 市场诊断 ──
    try:
        from services.screening.market_perception import MarketPerception

        mp = MarketPerception()
        registry.register(
            "market:diagnose",
            func=lambda force_refresh=False: mp.diagnose(force_refresh=force_refresh),
            description="诊断当前A股市场状态, 返回 BULL/BEAR/SHOCK/VOLATILE + 动态权重",
            schema={
                "name": "market_diagnose",
                "description": "诊断当前市场状态",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "force_refresh": {"type": "boolean", "description": "是否强制刷新缓存"}
                    },
                },
            },
        )
    except Exception as e:
        logger.warning("[ToolRegistry] market:diagnose 注册失败: %s", e)

    # ── 2. 行为活性筛选 (Stage 1) ──
    try:
        registry.register(
            "screen:active",
            func=lambda style="hybrid", top_n=200: _run_stage1(style, top_n),
            description="对全市场执行行为活性过滤, 返回活跃标的列表 (量价硬门槛)",
            schema={
                "name": "screen_active",
                "description": "行为活性过滤",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "style": {
                            "type": "string",
                            "enum": ["hybrid", "limit_up", "momentum", "value"],
                        },
                        "top_n": {"type": "integer", "description": "返回数量"},
                    },
                },
            },
        )
    except Exception as e:
        logger.warning("[ToolRegistry] screen:active 注册失败: %s", e)

    # ── 3. 四维评分 (Stage 2) ──
    try:
        registry.register(
            "factor:score",
            func=lambda stocks, style="hybrid", weights=None: _run_stage2(stocks, style, weights),
            description="对候选股执行四维评分 (趋势/资金/基本面/防御), 返回评分结果",
        )
    except Exception as e:
        logger.warning("[ToolRegistry] factor:score 注册失败: %s", e)

    # ── 4. AI 基本面分析 ──
    try:
        from services.screening.ai_analyst import score_from_available_data

        registry.register(
            "fundamental:analyze",
            func=lambda stocks: {
                s.get("stock_code", ""): score_from_available_data(s) for s in (stocks or [])
            },
            description="对候选股进行基本面推理分析, 返回每只股票的评分和信号",
        )
    except Exception as e:
        logger.warning("[ToolRegistry] fundamental:analyze 注册失败: %s", e)

    # ── 5. zzshare 热度因子 ──
    try:
        registry.register(
            "hot:check",
            func=_check_hot,
            description="检查股票是否在今日热搜/涨停名单中",
        )
    except Exception as e:
        logger.warning("[ToolRegistry] hot:check 注册失败: %s", e)

    return registry


# ── 辅助函数 ──


def _run_stage1(style: str = "hybrid", top_n: int = 200) -> list[dict]:
    from services.screening.compat import StockScreener
    from services.screening.stages.stage1 import stage1_quant_filter
    from services.screening.styles import load_style_config
    from shared.config import Config

    ss = StockScreener(style=style)
    universe = ss._load_universe()
    sc = load_style_config(style, Config())
    sc.stage1.top_n = top_n
    return stage1_quant_filter(universe, sc.stage1, style)


def _run_stage2(
    stocks: list[dict], style: str = "hybrid", weights: dict | None = None
) -> list[dict]:
    from services.screening.stages.stage2 import stage2_fundamental_filter
    from services.screening.styles import load_style_config
    from shared.config import Config

    sc = load_style_config(style, Config())
    return stage2_fundamental_filter(stocks, sc.stage2, style, weights=weights)


def _check_hot(code: str) -> dict:
    from services.screening.zzshare_factors import ZZShareFactors

    zf = ZZShareFactors()
    zf.load()
    return {"is_hot": zf.is_hot_stock(code), "is_limit_up": zf.is_limit_up_stock(code)}
