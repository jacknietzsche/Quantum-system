"""信号处理增强 — 参考 TradingAgents-CN/signal_processing.py

关键改进:
1. LLM 辅助提取结构化决策 (JSON)
2. 智能价格推算 (从文本中提取当前价格和涨跌幅)
3. 完善的输入验证和降级处理
4. 市场感知 (A股/港股/美股不同处理)
"""

from __future__ import annotations

import re
from typing import Any

from agents_v2.utils.logging_init import get_logger

logger = get_logger("signal")


class SignalProcessor:
    """交易信号处理器 — 从自由文本决策中提取结构化信号"""

    def __init__(self, llm: Any = None):
        self.llm = llm

    def process_signal(self, full_signal: str, stock_code: str = "") -> dict[str, Any]:
        """处理交易信号,提取结构化决策

        Args:
            full_signal: 完整的交易信号文本
            stock_code: 股票代码 (用于市场感知)

        Returns:
            {
                "action": "买入"/"持有"/"卖出",
                "target_price": float | None,
                "confidence": 0.0-1.0,
                "risk_score": 0.0-1.0,
                "reasoning": str,
            }
        """
        # 输入验证
        if not full_signal or not isinstance(full_signal, str) or len(full_signal.strip()) == 0:
            logger.error("[信号] 输入信号为空或无效")
            return self._default_decision("输入信号无效")

        full_signal = full_signal.strip()

        # 检测市场类型
        from agents_v2.utils.stock_utils import StockUtils

        market_info = StockUtils.get_market_info(stock_code) if stock_code else {}
        is_china = market_info.get("is_china", True)
        currency = market_info.get("currency_name", "人民币")

        logger.info(
            f"[信号] 处理: 股票={stock_code}, 市场={market_info.get('market_name', '未知')}"
        )

        # 优先: 使用 LLM 提取结构化信息
        if self.llm:
            result = self._llm_extract(full_signal, stock_code, market_info, currency)
            if result:
                return result

        # 降级: 简单文本提取  # noqa: ERA001
        return self._simple_extract(full_signal, is_china)

    def _llm_extract(
        self, text: str, stock_code: str, market_info: dict, currency: str
    ) -> dict[str, Any] | None:
        """使用 LLM 提取结构化决策"""
        try:
            import json

            currency_symbol = market_info.get("currency_symbol", "¥")

            messages = [
                (
                    "system",
                    f"""你是一位专业的金融分析助手,从交易分析报告中提取结构化投资决策.

请以 JSON 格式返回:
{{
    "action": "买入/持有/卖出",
    "target_price": 数字({currency}价格,必须提供具体数值),
    "confidence": 数字(0-1),
    "risk_score": 数字(0-1),
    "reasoning": "决策理由摘要(中文)"
}}

要求:
1. action 必须是"买入"/"持有"/"卖出"之一
2. target_price 必须是具体的 {currency_symbol} 价格
3. 股票代码: {stock_code or "未知"}, 市场: {market_info.get("market_name", "A股")}""",
                ),
                ("human", text),
            ]

            response = self.llm.invoke(messages)
            response_text = response.content if hasattr(response, "content") else str(response)

            # 提取 JSON
            json_match = re.search(r"\{.*\}", response_text, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group())

                # 验证和规范化
                action = result.get("action", "持有")
                if action not in ("买入", "持有", "卖出"):
                    action = self._normalize_action(action)

                return {
                    "action": action,
                    "target_price": self._safe_float(result.get("target_price")),
                    "confidence": max(0, min(1, self._safe_float(result.get("confidence")) or 0.7)),
                    "risk_score": max(0, min(1, self._safe_float(result.get("risk_score")) or 0.5)),
                    "reasoning": result.get("reasoning", "基于综合分析的投资建议"),
                }
        except Exception as e:
            logger.warning(f"[信号] LLM 提取失败: {e}")
        return None

    def _simple_extract(self, text: str, is_china: bool = True) -> dict[str, Any]:
        """简单文本提取 (降级方案)"""
        # 提取动作
        action = "持有"
        if re.search(r"强烈买入|STRONG.?BUY", text, re.IGNORECASE) or re.search(
            r"买入|BUY|建仓|加仓", text, re.IGNORECASE
        ):
            action = "买入"
        elif re.search(r"强烈卖出|STRONG.?SELL", text, re.IGNORECASE) or re.search(
            r"卖出|SELL|减仓|清仓", text, re.IGNORECASE
        ):
            action = "卖出"
        elif re.search(r"持有|HOLD|观望", text, re.IGNORECASE):
            action = "持有"

        # 提取目标价格
        target_price = self._extract_price(text)

        # 如果没有目标价格,尝试智能推算
        if target_price is None:
            target_price = self._smart_price_estimation(text, action, is_china)

        # 提取置信度
        confidence = self._extract_confidence(text)

        return {
            "action": action,
            "target_price": target_price,
            "confidence": confidence,
            "risk_score": 0.5,
            "reasoning": text[:200] + ("..." if len(text) > 200 else ""),
        }

    def _extract_price(self, text: str) -> float | None:
        """从文本中提取价格"""
        patterns = [
            r"目标价[位格]?[：:]\s*[¥\$]?(\d+(?:\.\d+)?)",
            r"\*\*目标价[位格]?\*\*[：:]\s*[¥\$]?(\d+(?:\.\d+)?)",
            r"目标[：:]\s*[¥\$]?(\d+(?:\.\d+)?)",
            r"价格[：:]\s*[¥\$]?(\d+(?:\.\d+)?)",
            r"[¥\$](\d+(?:\.\d+)?)",
            r"(\d+(?:\.\d+)?)元",
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                try:
                    return float(match.group(1))
                except ValueError:
                    continue
        return None

    def _smart_price_estimation(self, text: str, action: str, is_china: bool) -> float | None:
        """智能价格推算"""
        # 提取当前价格
        current_price = None
        current_patterns = [
            r"当前价[格位]?[：:]?\s*[¥\$]?(\d+(?:\.\d+)?)",
            r"现价[：:]?\s*[¥\$]?(\d+(?:\.\d+)?)",
            r"股价[：:]?\s*[¥\$]?(\d+(?:\.\d+)?)",
            r"最新价[：:]?\s*[¥\$]?(\d+(?:\.\d+)?)",
        ]
        for pattern in current_patterns:
            match = re.search(pattern, text)
            if match:
                try:
                    current_price = float(match.group(1))
                    break
                except ValueError:
                    continue

        if current_price is None:
            return None

        # 提取涨跌幅
        pct_change = None
        pct_patterns = [
            r"上涨\s*(\d+(?:\.\d+)?)%",
            r"涨幅\s*(\d+(?:\.\d+)?)%",
            r"增长\s*(\d+(?:\.\d+)?)%",
        ]
        for pattern in pct_patterns:
            match = re.search(pattern, text)
            if match:
                try:
                    pct_change = float(match.group(1)) / 100
                    break
                except ValueError:
                    continue

        # 推算目标价
        if pct_change:
            if action == "买入":
                return round(current_price * (1 + pct_change), 2)
            if action == "卖出":
                return round(current_price * (1 - pct_change), 2)

        # 默认推算
        multiplier_map = {
            "买入": 1.15 if is_china else 1.12,
            "卖出": 0.95 if is_china else 0.92,
            "持有": 1.0,
        }
        return round(current_price * multiplier_map.get(action, 1.0), 2)

    def _extract_confidence(self, text: str) -> float:
        """提取置信度"""
        patterns = [
            r"置信度[：:]\s*(\d+(?:\.\d+)?)%",
            r"confidence[：:]\s*(\d+(?:\.\d+)?)%",
            r"置信[度率][：:]\s*(\d+(?:\.\d+)?)",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                val = float(match.group(1))
                return val / 100 if val > 1 else val
        return 0.7

    def _normalize_action(self, action: str) -> str:
        """规范化动作"""
        action_upper = action.upper()
        if action_upper in ("BUY", "STRONG BUY", "STRONG_BUY"):
            return "买入"
        if action_upper in ("SELL", "STRONG SELL", "STRONG_SELL"):
            return "卖出"
        return "持有"

    def _safe_float(self, value: Any) -> float | None:
        """安全转换为 float"""
        if value is None:
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None

    def _default_decision(self, reason: str) -> dict[str, Any]:
        """返回默认决策"""
        return {
            "action": "持有",
            "target_price": None,
            "confidence": 0.5,
            "risk_score": 0.5,
            "reasoning": reason,
        }
