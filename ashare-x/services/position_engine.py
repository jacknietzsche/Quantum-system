r"""仓位决策引擎 — 根据分析结果 + 当前持仓 → 具体操作建议。

决策矩阵:
  分析\持仓   无持仓    有持仓     满仓
  Buy(高置信) INITIAL  ADD       HOLD
  Buy(低置信) WATCH    HOLD      HOLD
  Hold       WATCH    HOLD      HOLD
  Sell       WATCH    CLEAR     CLEAR
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from core.config import Config

logger = logging.getLogger("ashare-x.services.position_engine")


@dataclass
class PositionDecision:
    """单个股票的仓位决策。"""

    action: str  # INITIAL_BUY / ADD / REDUCE / CLEAR / HOLD / WATCH
    stock_code: str
    stock_name: str
    target_shares: int = 0
    target_price: float = 0.0
    current_price: float = 0.0
    current_shares: int = 0
    reasoning: str = ""
    risk_factors: list[str] = field(default_factory=list)
    confidence: float = 0.0
    entry_price: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    position_pct: float = 0.0

    def to_dict(self) -> dict:
        return {
            "action": self.action,
            "stock_code": self.stock_code,
            "stock_name": self.stock_name,
            "target_shares": self.target_shares,
            "target_price": self.target_price,
            "current_price": self.current_price,
            "current_shares": self.current_shares,
            "reasoning": self.reasoning,
            "risk_factors": self.risk_factors,
            "confidence": self.confidence,
            "entry_price": self.entry_price,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "position_pct": self.position_pct,
        }


class PositionEngine:
    """仓位决策引擎。"""

    def __init__(self, config: Config | None = None):
        self.config = config or Config()
        self.initial_capital = self.config.get("portfolio.initial_capital", 100000)
        self.max_holdings = self.config.get("portfolio.max_holdings", 5)
        self.max_single_pct = self.config.get("portfolio.max_single_pct", 0.30)
        self.min_cash_pct = self.config.get("portfolio.min_cash_pct", 0.20)
        self.max_industry_pct = self.config.get("portfolio.max_industry_pct", 0.40)
        self.lot_size = self.config.get("portfolio.lot_size", 100)

    def decide(
        self,
        analysis_result: dict[str, Any],
        current_holding: dict | None,
        account: dict | None = None,
        market_state: str = "NEUTRAL",
        holding_count: int = 0,
    ) -> PositionDecision:
        """
        核心决策逻辑。

        Args:
            analysis_result: LangGraph输出的 {action, confidence, entry_price, ...}
            current_holding: 当前持仓dict（None=未持仓）
            account: 账户信息 {cash, total_assets, ...}
            market_state: 市场状态 BULL/NEUTRAL/BEAR/PANIC
            holding_count: 当前持仓数量
        """
        action = analysis_result.get("action", "Hold")
        confidence = analysis_result.get("confidence", 50)
        ticker = analysis_result.get("ticker", "")
        stock_name = analysis_result.get("stock_name", "")
        entry_price = analysis_result.get("entry_price")
        stop_loss = analysis_result.get("stop_loss")
        take_profit = analysis_result.get("take_profit")
        thesis = analysis_result.get("thesis", analysis_result.get("executive_summary", ""))

        current_price = entry_price or analysis_result.get("current_price", 0.0)
        current_shares = current_holding.get("shares", 0) if current_holding else 0

        decision = PositionDecision(
            action="HOLD",
            stock_code=ticker,
            stock_name=stock_name,
            current_price=current_price,
            current_shares=current_shares,
            reasoning=thesis,
            confidence=confidence,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
        )

        # 决策矩阵
        is_buy = action in ("Buy", "Strong Buy", "买入")
        is_sell = action in ("Sell", "Strong Sell", "卖出")
        is_high_confidence = confidence >= 70

        if current_holding is None:
            # 无持仓
            if is_buy and is_high_confidence:
                if holding_count >= self.max_holdings:
                    decision.action = "HOLD"
                    decision.reasoning = f"已达最大持仓数{self.max_holdings}，暂不新增。{thesis}"
                else:
                    decision.action = "INITIAL_BUY"
                    decision.target_shares = self._compute_position_size(
                        current_price, confidence, account, market_state
                    )
                    decision.position_pct = self._compute_position_pct(
                        decision.target_shares, current_price, account
                    )
                    decision.reasoning = self._build_buy_reasoning(
                        thesis, confidence, decision.target_shares, current_price, "初次买入"
                    )
            else:
                decision.action = "WATCH"
                decision.reasoning = f"观察等待。置信度{confidence}%未达买入标准。{thesis}"
        # 有持仓
        elif is_sell:
            decision.action = "CLEAR"
            decision.target_shares = current_shares
            decision.target_price = current_price
            decision.reasoning = self._build_sell_reasoning(
                thesis, confidence, "分析信号转空，清仓"
            )
        elif is_buy and is_high_confidence:
            # 检查是否可加仓
            current_pct = self._compute_holding_pct(current_holding, account)
            if current_pct >= self.max_single_pct:
                decision.action = "HOLD"
                decision.reasoning = (
                    f"已达单只上限{self.max_single_pct*100:.0f}%，不加仓。{thesis}"
                )
            else:
                decision.action = "ADD"
                decision.target_shares = self._compute_add_size(
                    current_price, confidence, account, current_pct
                )
                decision.position_pct = self._compute_position_pct(
                    decision.target_shares, current_price, account
                )
                decision.reasoning = self._build_buy_reasoning(
                    thesis, confidence, decision.target_shares, current_price, "加仓"
                )
        else:
            # Hold或低置信度
            decision.action = "HOLD"
            # 检查止损
            if stop_loss and current_price and current_price <= stop_loss:
                decision.action = "REDUCE"
                decision.target_shares = self._round_lot(current_shares // 2)
                decision.target_price = current_price
                decision.reasoning = f"价格跌破止损线¥{stop_loss}，减半仓位。{thesis}"
                decision.risk_factors.append("触发止损")
            elif confidence < 40:
                decision.action = "REDUCE"
                decision.target_shares = self._round_lot(current_shares // 2)
                decision.target_price = current_price
                decision.reasoning = f"置信度低({confidence}%)，减半仓位降低风险。{thesis}"
                decision.risk_factors.append("置信度过低")
            else:
                decision.reasoning = f"维持持仓。置信度{confidence}%。{thesis}"

        return decision

    def _compute_position_size(
        self, price: float, confidence: float,
        account: dict | None, market_state: str
    ) -> int:
        """
        计算买入仓位大小。
        - 小资金: 单只15-30%
        - 高置信度(>80): 30%
        - 中置信度(70-80): 20%
        - 低置信度(<70): 15%
        - 市场状态调整: BEAR→减半, PANIC→不买
        """
        if market_state == "PANIC":
            return 0

        if price <= 0:
            return 0

        # 基础仓位比例
        if confidence >= 80:
            base_pct = 0.30
        elif confidence >= 70:
            base_pct = 0.20
        else:
            base_pct = 0.15

        # 市场状态调整
        market_adj = {
            "BULL": 1.0,
            "NEUTRAL": 1.0,
            "BEAR": 0.5,
            "PANIC": 0.0,
        }
        base_pct *= market_adj.get(market_state, 1.0)

        # 上限约束
        base_pct = min(base_pct, self.max_single_pct)

        # 可用资金
        if account:
            total_assets = account.get("total_assets", self.initial_capital)
            cash = account.get("cash", total_assets)
            min_cash = total_assets * self.min_cash_pct
            available = max(0, cash - min_cash)
        else:
            available = self.initial_capital * base_pct

        target_amount = total_assets * base_pct if account else self.initial_capital * base_pct
        # 不超过可用资金
        target_amount = min(target_amount, available)

        shares = int(target_amount / price)
        return self._round_lot(shares)

    def _compute_add_size(
        self, price: float, confidence: float,
        account: dict | None, current_pct: float
    ) -> int:
        """计算加仓大小。加到max_single_pct为止。"""
        if price <= 0:
            return 0

        if account:
            total_assets = account.get("total_assets", self.initial_capital)
            cash = account.get("cash", total_assets)
            min_cash = total_assets * self.min_cash_pct
            available = max(0, cash - min_cash)
        else:
            total_assets = self.initial_capital
            available = self.initial_capital * 0.3

        # 目标加到max_single_pct
        target_pct = min(self.max_single_pct, current_pct + 0.15)
        add_pct = target_pct - current_pct
        target_amount = min(total_assets * add_pct, available)

        shares = int(target_amount / price)
        return self._round_lot(shares)

    def _compute_position_pct(self, shares: int, price: float,
                               account: dict | None) -> float:
        """计算仓位占比。"""
        if not account or price <= 0:
            return 0.0
        total_assets_raw = account.get("total_assets", self.initial_capital)
        total_assets = float(total_assets_raw) if total_assets_raw else 0.0
        if total_assets <= 0:
            return 0.0
        return round(shares * price / total_assets * 100, 1)

    @staticmethod
    def _compute_holding_pct(holding: dict, account: dict | None) -> float:
        """计算现有持仓占比。"""
        if not account:
            return 0.0
        total_assets_raw = account.get("total_assets", 0)
        total_assets = float(total_assets_raw) if total_assets_raw else 0.0
        if total_assets <= 0:
            return 0.0
        market_value_raw = holding.get(
            "market_value", holding.get("shares", 0) * holding.get("avg_cost", 0)
        )
        market_value = float(market_value_raw) if market_value_raw else 0.0
        return market_value / total_assets

    def _round_lot(self, shares: int) -> int:
        """取100股整数倍。"""
        return int((shares // self.lot_size) * self.lot_size)

    @staticmethod
    def _build_buy_reasoning(thesis: str, confidence: float,
                             shares: int, price: float, action_label: str) -> str:
        """构建买入理由。"""
        amount = shares * price
        return (
            f"{action_label}: {shares}股 @¥{price:.2f} (约¥{amount:,.0f})。"
            f"置信度{confidence}%。{thesis}"
        )

    @staticmethod
    def _build_sell_reasoning(thesis: str, confidence: float,
                              action_label: str) -> str:
        """构建卖出理由。"""
        return f"{action_label}。置信度{confidence}%。{thesis}"
