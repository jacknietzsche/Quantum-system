"""A 股交易 Agent 图 — 参考 TradingAgents-CN + TradingAgents 改进

主入口类,关键改进:
1. 股票预验证 (验证代码有效性)
2. 股票市场检测 (A股/港股/美股自动识别)
3. 详细的日志追踪
4. 进度回调支持
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from agents_v2.memory import TradingMemory
from agents_v2.utils.logging_init import get_logger
from agents_v2.utils.stock_utils import StockUtils
from agents_v2.utils.stock_validator import validate_stock
from graph_v2.checkpointer import (
    checkpoint_step,
    clear_checkpoint,
    get_checkpointer,
    thread_id,
)
from graph_v2.conditional_logic import ConditionalLogic
from graph_v2.default_config import get_default_config
from graph_v2.propagation import Propagator
from graph_v2.reflection import Reflector
from graph_v2.setup import GraphSetup
from graph_v2.signal_processing import SignalProcessor
from llm_clients.factory import create_llm_client

logger = get_logger("graph")


class AShareTradingGraph:
    """A 股多 Agent 交易决策图

    Usage:
        graph = AShareTradingGraph()
        decision, signal = graph.propagate("600519", "2026-05-30")
    """

    def __init__(
        self,
        selected_analysts: list[str] | None = None,
        debug: bool = False,
        config: dict[str, Any] | None = None,
    ):
        self.debug = debug
        self.config = config or get_default_config()

        if selected_analysts is None:
            selected_analysts = self.config.get(
                "selected_analysts", ["market", "sentiment", "news", "fundamentals"]
            )
        self.selected_analysts = selected_analysts

        # 创建目录
        os.makedirs(self.config.get("results_dir", "results"), exist_ok=True)
        os.makedirs(self.config.get("data_cache_dir", "data/cache"), exist_ok=True)

        # 初始化 LLM
        self.quick_llm = self._create_llm("quick_think_llm")
        self.deep_llm = self._create_llm("deep_think_llm")

        # 初始化记忆系统
        memory_config = {
            "memory_log_path": self.config.get("memory_log_path"),
            "memory_log_max_entries": self.config.get("memory_log_max_entries"),
        }
        self.memory = TradingMemory(memory_config)

        # 初始化组件
        self.conditional_logic = ConditionalLogic(
            max_debate_rounds=self.config.get("max_debate_rounds", 1),
            max_risk_discuss_rounds=self.config.get("max_risk_discuss_rounds", 1),
        )
        self.propagator = Propagator(
            max_recur_limit=self.config.get("max_recur_limit", 100),
        )
        self.reflector = Reflector(self.quick_llm)
        self.signal_processor = SignalProcessor()

        # 构建图
        tool_nodes = {}
        self.graph_setup = GraphSetup(
            quick_thinking_llm=self.quick_llm,
            deep_thinking_llm=self.deep_llm,
            tool_nodes=tool_nodes,
            conditional_logic=self.conditional_logic,
            analyst_concurrency_limit=self.config.get("analyst_concurrency_limit", 1),
        )

        self.workflow = self.graph_setup.setup_graph(selected_analysts)
        self.graph = self.workflow.compile()

        # 状态追踪
        self.curr_state = None
        self.log_states_dict: dict[str, Any] = {}

        logger.info(f"[初始化] 完成. 分析师: {selected_analysts}")

    def _create_llm(self, role: str) -> Any:
        """创建 LLM 实例"""
        provider = self.config.get("llm_provider", "siliconflow")
        model = self.config.get(role, "deepseek-ai/DeepSeek-V3")
        api_key = self.config.get(f"{provider}_api_key") or os.environ.get(
            f"{provider.upper()}_API_KEY", ""
        )
        base_url = self.config.get(f"{provider}_base_url")

        client = create_llm_client(
            provider=provider,
            model=model,
            base_url=base_url,
            api_key=api_key,
        )
        return client.get_llm()

    def propagate(
        self,
        stock_code: str,
        trade_date: str,
        stock_name: str = "",
        asset_type: str = "stock",
        validate: bool = True,
    ) -> tuple[str, dict[str, Any]]:
        """运行完整决策工作流

        Args:
            stock_code: 股票代码
            trade_date: 分析日期
            stock_name: 股票名称 (可选)
            asset_type: 资产类型
            validate: 是否预验证股票代码

        Returns:
            (final_decision_text, signal_dict)
        """
        # 1. 股票预验证
        if validate:
            _market_info = StockUtils.get_market_info(stock_code)
            result = validate_stock(stock_code)
            if not result.is_valid:
                logger.error(f"[验证失败] {result.error_message}")
                error_decision = f"ERROR: {result.error_message}. 建议: {result.suggestion}"
                return error_decision, {
                    "action": "error",
                    "confidence": 0,
                    "reasoning": result.error_message,
                }

            if result.stock_name and not stock_name:
                stock_name = result.stock_name
            logger.info(f"[验证通过] {stock_code} ({result.market_type}) {stock_name}")

        # 2. 获取历史记忆
        past_context = self.memory.get_past_context(stock_code)

        # 3. 构建 instrument_context
        instrument_context = f"{stock_name} ({stock_code})" if stock_name else stock_code

        # 4. 创建初始状态
        init_state = self.propagator.create_initial_state(
            stock_code=stock_code,
            stock_name=stock_name,
            trade_date=trade_date,
            asset_type=asset_type,
            past_context=past_context,
            instrument_context=instrument_context,
        )

        args = self.propagator.get_graph_args()

        # 5. 检查点支持
        if self.config.get("checkpoint_enabled"):
            tid = thread_id(stock_code, str(trade_date))
            args.setdefault("config", {}).setdefault("configurable", {})["thread_id"] = tid
            data_dir = self.config.get("data_cache_dir", "data/cache")

            step = checkpoint_step(data_dir, stock_code, str(trade_date))
            if step is not None:
                logger.info(f"[恢复] 从步骤 {step} 恢复: {stock_code} {trade_date}")
                with get_checkpointer(data_dir, stock_code) as saver:
                    compiled = self.workflow.compile(checkpointer=saver)
                    final_state = compiled.invoke(init_state, **args)
            else:
                logger.info(f"[新分析] {stock_code} {trade_date}")
                final_state = self.graph.invoke(init_state, **args)
        elif self.debug:
            trace = []
            for chunk in self.graph.stream(init_state, **args):
                messages = chunk.get("messages", [])
                if messages:
                    msg = messages[-1]
                    if hasattr(msg, "pretty_print"):
                        msg.pretty_print()
                    trace.append(chunk)
            final_state = {}
            for chunk in trace:
                final_state.update(chunk)
        else:
            final_state = self.graph.invoke(init_state, **args)

        self.curr_state = final_state

        # 6. 保存决策日志
        self._log_state(trade_date, final_state)

        # 7. 存储到记忆系统
        final_decision = final_state.get("final_trade_decision", "")
        self.memory.store_decision(
            stock_code=stock_code,
            trade_date=trade_date,
            final_trade_decision=final_decision,
        )

        # 8. 清除成功完成的检查点
        if self.config.get("checkpoint_enabled"):
            data_dir = self.config.get("data_cache_dir", "data/cache")
            clear_checkpoint(data_dir, stock_code, str(trade_date))

        # 9. 提取信号
        signal = self.signal_processor.process_signal(final_decision)

        logger.info(f"[完成] {stock_code} 决策: {signal.get('action', 'unknown')}")
        return final_decision, signal

    def _log_state(self, trade_date: str, final_state: dict[str, Any]) -> None:
        """记录完整状态到 JSON 文件"""
        master_views = final_state.get("master_views", []) or []
        log_entry = {
            "stock_code": final_state.get("stock_code", ""),
            "stock_name": final_state.get("stock_name", ""),
            "trade_date": trade_date,
            "master_council_report": final_state.get("master_council_report", "")[:2000],
            "master_views": master_views[:10],
            "skill_context": final_state.get("skill_context", "")[:2000],
            "market_report": final_state.get("market_report", "")[:2000],
            "sentiment_report": final_state.get("sentiment_report", "")[:2000],
            "news_report": final_state.get("news_report", "")[:2000],
            "fundamentals_report": final_state.get("fundamentals_report", "")[:2000],
            "northbound_report": final_state.get("northbound_report", "")[:1000],
            "sector_report": final_state.get("sector_report", "")[:1000],
            "investment_debate_state": {
                "bull_history": final_state.get("investment_debate_state", {}).get(
                    "bull_history", ""
                )[-1000:],
                "bear_history": final_state.get("investment_debate_state", {}).get(
                    "bear_history", ""
                )[-1000:],
                "judge_decision": final_state.get("investment_debate_state", {}).get(
                    "judge_decision", ""
                ),
            },
            "trader_investment_plan": final_state.get("trader_investment_plan", "")[:1000],
            "risk_debate_state": {
                "aggressive_history": final_state.get("risk_debate_state", {}).get(
                    "aggressive_history", ""
                )[-500:],
                "conservative_history": final_state.get("risk_debate_state", {}).get(
                    "conservative_history", ""
                )[-500:],
                "neutral_history": final_state.get("risk_debate_state", {}).get(
                    "neutral_history", ""
                )[-500:],
            },
            "investment_plan": final_state.get("investment_plan", "")[:1000],
            "final_trade_decision": final_state.get("final_trade_decision", ""),
        }

        self.log_states_dict[str(trade_date)] = log_entry

        stock_code = final_state.get("stock_code", "UNKNOWN")
        results_dir = self.config.get("results_dir", "results")
        directory = Path(results_dir) / stock_code / "logs"
        directory.mkdir(parents=True, exist_ok=True)

        log_path = directory / f"full_states_log_{trade_date}.json"
        with open(log_path, "w", encoding="utf-8") as f:
            json.dump(log_entry, f, indent=4, ensure_ascii=False)

        logger.debug(f"[日志] 保存到 {log_path}")
