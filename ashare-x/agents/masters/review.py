"""大师Agent工作流节点。

Phase 7.3: 将大师Agent接入LangGraph工作流。
master_selector 根据股票特征选择3个最相关大师，master_review 执行分析并汇总。
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable

from core.llm_client import LLMClient
from core.state import AgentState

logger = logging.getLogger(__name__)

# 大师创建函数映射
_MASTER_FACTORIES = {
    "buffett": "agents.masters.buffett.create_buffett",
    "munger": "agents.masters.munger.create_munger",
    "taleb": "agents.masters.taleb.create_taleb",
    "lynch": "agents.masters.lynch.create_lynch",
    "burry": "agents.masters.burry.create_burry",
    "druckenmiller": "agents.masters.druckenmiller.create_druckenmiller",
    "fisher": "agents.masters.fisher.create_fisher",
    "wood": "agents.masters.wood.create_wood",
}

# 大师中文名
_MASTER_NAMES = {
    "buffett": "巴菲特",
    "munger": "芒格",
    "taleb": "塔勒布",
    "lynch": "林奇",
    "burry": "伯里",
    "druckenmiller": "德鲁肯米勒",
    "fisher": "费雪",
    "wood": "伍德",
}


def create_master_selector(llm_client: LLMClient) -> Callable[[AgentState], dict]:
    """大师选择器节点：根据股票特征选择3个最相关大师。"""

    def selector_node(state: AgentState) -> dict:
        from agents.masters.selector import select_masters

        # 从state中提取股票特征
        fundamentals = state.get("fundamentals", {})
        stock_profile = {
            "pe_ratio": fundamentals.get("pe_ratio", 20),
            "roe": fundamentals.get("roe", 15),
            "volatility": fundamentals.get("volatility", 0.3),
            "revenue_growth": fundamentals.get("revenue_yoy", 0.1),
        }

        selected = select_masters(stock_profile)
        logger.info("大师选择: %s (profile: %s)", selected, stock_profile)

        return {"selected_masters": selected}

    return selector_node


def create_master_review(llm_client: LLMClient) -> Callable[[AgentState], dict]:
    """大师评审节点：执行选中大师的分析并汇总信号。"""

    def review_node(state: AgentState) -> dict:
        import importlib

        selected = state.get("selected_masters", [])
        if not selected:
            logger.info("无选中大师，跳过评审")
            return {"master_signals": {}}

        signals: dict[str, dict] = {}
        reports: dict[str, str] = {}

        # 收集前序Agent报告给大师参考
        prior_reports = []
        for key in ("market_analyst_report", "fundamentals_analyst_report",
                     "news_analyst_report", "sentiment_analyst_report",
                     "portfolio_manager_report"):
            report = state.get(key, "")
            if report:
                prior_reports.append(f"### {key}\n{report[:500]}")  # type: ignore[typeddict-item, index]

        prior_context = "\n\n".join(prior_reports) if prior_reports else ""

        for master_name in selected:
            factory_path = _MASTER_FACTORIES.get(master_name)
            if not factory_path:
                continue

            try:
                if callable(factory_path):
                    factory = factory_path
                else:
                    module_path, func_name = factory_path.rsplit(".", 1)
                    module = importlib.import_module(module_path)
                    factory = getattr(module, func_name)
                agent_fn = factory(llm_client)

                # 将前序报告摘要注入 state，供大师Agent参考
                review_state = dict(state)
                review_state["master_prior_context"] = prior_context

                # 执行大师Agent
                result = agent_fn(review_state)
                report_key = f"{master_name}_report"
                report_text = result.get(report_key, "")

                if report_text:
                    reports[master_name] = report_text

                    # 尝试解析JSON信号
                    try:
                        import re

                        json_match = re.search(
                            r"\{[^{}]*\}", report_text.replace("\n", " ")
                        )
                        if json_match:
                            signal_data = json.loads(json_match.group())
                            signals[master_name] = {
                                "signal": signal_data.get("signal", "neutral"),
                                "confidence": signal_data.get("confidence", 50),
                                "reasoning": signal_data.get("reasoning", ""),
                                "agent": master_name,
                            }
                    except (json.JSONDecodeError, AttributeError):
                        signals[master_name] = {
                            "signal": "neutral",
                            "confidence": 50,
                            "reasoning": report_text[:200],
                            "agent": master_name,
                        }

                logger.info("大师 %s 分析完成", master_name)

            except Exception as e:
                logger.warning("大师 %s 执行失败: %s", master_name, e)

        # 汇总大师报告
        master_names_cn = [_MASTER_NAMES.get(m, m) for m in selected]
        summary_lines = [
            f"## 大师评审汇总 ({', '.join(master_names_cn)})",
        ]

        bull_count = sum(1 for s in signals.values() if s.get("signal") == "bullish")
        bear_count = sum(1 for s in signals.values() if s.get("signal") == "bearish")
        neutral_count = sum(1 for s in signals.values() if s.get("signal") == "neutral")

        summary_lines.append(
            f"### 信号汇总: 看多{bull_count} | 看空{bear_count} | 中性{neutral_count}"
        )

        for name, signal in signals.items():
            cn_name = _MASTER_NAMES.get(name, name)
            summary_lines.append(
                f"- {cn_name}: {signal.get('signal', 'N/A')} "
                f"(置信度: {signal.get('confidence', 0)}%) — "
                f"{signal.get('reasoning', '')[:100]}"
            )

        master_report = "\n".join(summary_lines)

        return {
            "master_signals": signals,
            "master_review_report": master_report,
        }

    return review_node
