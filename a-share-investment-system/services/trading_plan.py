"""交易计划生成器 - 选股模块的最终输出，生成可执行的交易计划

基于选股结果 + 风险评估 + 持仓状态，生成:
1. 即时订单（买入/卖出/加仓/减仓）
2. 条件订单（止盈止损/突破买入）
3. 仓位建议（Kelly公式 / 等权分配）
4. 监控信号
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import ClassVar

from services.base import BaseService, ServiceResult
from shared.logging import emit_log


def extract_master_factors(screening_result: dict) -> dict[str, float]:
    """从选股结果中提取 Master 因子（优先使用 screener 计算的因子）。

    如果选股结果中包含 master_factors（由 StockScreener._compute_master_factors 计算），
    直接使用；否则降级为从推荐列表统计推导。
    """
    # 优先: 使用 screener 直接计算的因子
    factors = screening_result.get("master_factors")
    if isinstance(factors, dict) and "master_weight_factor" in factors:
        return {
            "master_weight_factor": float(factors.get("master_weight_factor", 1.0)),
            "master_position_factor": float(factors.get("master_position_factor", 1.0)),
        }

    # 降级: 从推荐列表推导  # noqa: ERA001
    recommendations = screening_result.get("recommendations", [])
    return compute_factor_from_recommendations(recommendations)


def compute_factor_from_recommendations(recommendations: list[dict]) -> dict[str, float]:
    """从选股推荐列表中计算 Master 风格的权重/仓位因子。

    基于推荐的整体方向性(多/空比例)和平均得分来调整:
    - 多头主导 → 因子 > 1.0 (放大仓位)
    - 空头主导 → 因子 < 1.0 (缩减仓位)

    Returns:
        {"master_weight_factor": float, "master_position_factor": float}
    """
    if not recommendations:
        return {"master_weight_factor": 1.0, "master_position_factor": 1.0}

    n = len(recommendations)
    avg_score = sum(r.get("score", 50) for r in recommendations) / n

    buy_count = sum(1 for r in recommendations if r.get("signal") in ("买入", "bullish"))
    sell_count = sum(1 for r in recommendations if r.get("signal") in ("卖出", "bearish"))
    direction_ratio = (buy_count - sell_count) / n

    weight_center = 1.0 + 0.30 * direction_ratio + 0.15 * ((avg_score - 50) / 50)
    weight_factor = max(0.70, min(1.30, weight_center))

    position_center = 1.0 + 0.25 * direction_ratio + 0.10 * ((avg_score - 50) / 50)
    position_factor = max(0.80, min(1.20, position_center))

    return {
        "master_weight_factor": round(weight_factor, 4),
        "master_position_factor": round(position_factor, 4),
    }


@dataclass
class OrderItem:
    """单笔交易指令"""

    code: str
    name: str
    action: str  # 买入/卖出/加仓/减仓/持有
    quantity: int | None = None
    weight: str | None = None
    limit_price: str | None = None
    stop_loss: str | None = None
    take_profit: str | None = None
    reasoning: str = ""
    confidence: str = "中"  # 高/中/低


@dataclass
class ConditionalOrder:
    """条件单"""

    stock_code: str
    stock_name: str
    condition: str
    action: str
    trigger_price: float | None = None
    timing: str = ""


@dataclass
class MonitoringSignal:
    """监控信号"""

    stock_code: str
    signal_type: str  # STOP_LOSS / TAKE_PROFIT / BREAKOUT / VOLUME
    description: str
    threshold: float | None = None


@dataclass
class ExecutionPlan:
    """执行计划"""

    immediate_summary: str = ""
    immediate_orders: list = field(default_factory=list)
    conditional_orders: list = field(default_factory=list)
    monitoring_signals: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "immediate_summary": self.immediate_summary,
            "orders": [o.__dict__ if hasattr(o, "__dict__") else o for o in self.immediate_orders],
            "conditional_orders": [
                o.__dict__ if hasattr(o, "__dict__") else o for o in self.conditional_orders
            ],
            "monitoring_signals": [
                s.__dict__ if hasattr(s, "__dict__") else s for s in self.monitoring_signals
            ],
        }


@dataclass
class RiskManagement:
    """风控规则"""

    circuit_breaker: str = ""
    portfolio_stop: str = ""
    key_risks: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "circuit_breaker": self.circuit_breaker,
            "portfolio_stop": self.portfolio_stop,
            "key_risks": self.key_risks,
        }


@dataclass
class TradingPlan:
    """完整的交易计划"""

    market_regime: str = ""
    risk_level: str = "中等"
    max_position: float = 0.7
    execution: ExecutionPlan = field(default_factory=ExecutionPlan)
    risk: RiskManagement = field(default_factory=RiskManagement)
    position_sizing: dict = field(default_factory=dict)
    summary: str = ""
    generated_at: str = ""

    def to_dict(self) -> dict:
        return {
            "market_assessment": {
                "regime": self.market_regime,
                "risk_level": self.risk_level,
                "max_position": self.max_position,
            },
            "execution_plan": self.execution.to_dict(),
            "risk_management": self.risk.to_dict(),
            "position_sizing": self.position_sizing,
            "summary": self.summary,
            "generated_at": self.generated_at,
        }


class TradingPlanGenerator(BaseService):
    """交易计划生成器 - 从选股结果生成可执行的交易计划"""

    # 风险等级 -> 最大仓位映射
    RISK_POSITION_MAP: ClassVar[dict[str, float]] = {
        "LOW": 0.85,
        "MEDIUM": 0.70,
        "HIGH": 0.50,
        "EXTREME": 0.30,
    }

    # 止损止盈默认参数
    DEFAULT_STOP_LOSS_PCT = -8.0
    DEFAULT_TAKE_PROFIT_PCT = 20.0
    TRAILING_STOP_PCT = 5.0

    def generate(
        self,
        recommendations: list[dict],
        current_positions: list[dict] | None = None,
        risk_report: dict | None = None,
        cash: float = 0,
        total_capital: float = 0,
        master_position_factor: float = 1.0,
        master_weight_factor: float = 1.0,
    ) -> ServiceResult:
        """生成完整交易计划

        Args:
            recommendations: 选股推荐列表 (stock_code, stock_name, price, score, signal, confidence)
            current_positions: 当前持仓列表
            risk_report: 风险引擎审计结果
            cash: 可用现金
            total_capital: 总资金
        """
        try:
            emit_log(
                "INFO",
                "trading_plan",
                f"generate_start: {len(recommendations)} recs, {len(current_positions or [])} positions",
            )

            positions = current_positions or []
            risk_level = (risk_report or {}).get("risk_level", "MEDIUM")
            market_regime = (risk_report or {}).get("market_risk", {}).get("message", "")

            # 确定最大仓位
            max_position = self.RISK_POSITION_MAP.get(risk_level, 0.70)
            if total_capital <= 0:
                total_capital = cash + sum(
                    p.get("current_value", p.get("cost_value", 0)) for p in positions
                )
            if total_capital <= 0:
                return ServiceResult.error(errors=["total_capital is zero, cannot generate plan"])

            # 1. 生成即时订单
            immediate_orders = self._generate_immediate_orders(
                recommendations, positions, cash, total_capital, max_position
            )

            # 2. 生成条件单
            conditional_orders = self._generate_conditional_orders(recommendations, positions)

            # 3. 生成监控信号
            monitoring_signals = self._generate_monitoring_signals(recommendations, positions)

            # 4. 仓位规划
            position_sizing = self._calculate_position_sizing(
                recommendations,
                cash,
                total_capital,
                max_position,
                master_position_factor,
                master_weight_factor,
            )

            # 5. 风控规则
            risk_mgmt = self._generate_risk_management(risk_level, risk_report, positions)

            # 6. 摘要
            buy_count = sum(1 for o in immediate_orders if o.action == "买入")
            sell_count = sum(1 for o in immediate_orders if o.action in ("卖出", "减仓"))
            hold_count = sum(1 for o in immediate_orders if o.action == "持有")
            summary = f"交易计划: {buy_count}买入/{sell_count}卖出/{hold_count}持有, 风险等级{risk_level}, 最大仓位{max_position:.0%}"

            # 构建执行计划
            exec_plan = ExecutionPlan(
                immediate_summary=summary,
                immediate_orders=immediate_orders,
                conditional_orders=conditional_orders,
                monitoring_signals=monitoring_signals,
            )

            plan = TradingPlan(
                market_regime=market_regime,
                risk_level=risk_level,
                max_position=max_position,
                execution=exec_plan,
                risk=risk_mgmt,
                position_sizing=position_sizing,
                summary=summary,
                generated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            )

            emit_log(
                "INFO",
                "trading_plan",
                f"generate_done: {len(immediate_orders)} orders, {len(conditional_orders)} conditions",
            )

            return ServiceResult.ok(data=plan.to_dict())

        except Exception as e:
            return ServiceResult.error(errors=[f"TradingPlanGenerator failed: {e}"])

    def _generate_immediate_orders(
        self,
        recommendations: list[dict],
        positions: list[dict],
        cash: float,
        total_capital: float,
        max_position: float,
    ) -> list[OrderItem]:
        """生成即时交易订单"""
        orders = []
        position_map = {p.get("stock_code", ""): p for p in positions}
        _current_total = sum(p.get("current_value", p.get("cost_value", 0)) for p in positions)

        for rec in recommendations:
            code = rec.get("stock_code", "")
            name = rec.get("stock_name", code)
            price = rec.get("price", 0)
            signal = rec.get("signal", "观望")
            confidence = rec.get("confidence", "中")
            score = rec.get("score", 50)
            pe = rec.get("pe", 0)

            if not code or not price:
                continue

            pos = position_map.get(code)
            reasoning_parts = []

            if signal == "买入" and confidence in ("高", "中"):
                # 新建仓或加仓
                if pos:
                    # 已持仓，判断是否加仓
                    current_weight = (
                        pos.get("current_value", 0) / total_capital if total_capital > 0 else 0
                    )
                    if current_weight < max_position * 0.6:
                        target_value = total_capital * max_position * 0.3
                        add_value = target_value - pos.get("current_value", 0)
                        qty = (
                            max(100, int(add_value / price / 100) * 100)
                            if add_value > 0 and price > 0
                            else 0
                        )
                        if qty >= 100:
                            reasoning_parts.append(f"已持仓{current_weight:.1%},建议加仓")
                            orders.append(
                                OrderItem(
                                    code=code,
                                    name=name,
                                    action="加仓",
                                    quantity=qty,
                                    limit_price=str(round(price, 2)),
                                    stop_loss=str(
                                        round(price * (1 + self.DEFAULT_STOP_LOSS_PCT / 100), 2)
                                    ),
                                    take_profit=str(
                                        round(price * (1 + self.DEFAULT_TAKE_PROFIT_PCT / 100), 2)
                                    ),
                                    reasoning="; ".join(reasoning_parts),
                                    confidence=confidence,
                                )
                            )
                    else:
                        orders.append(
                            OrderItem(
                                code=code,
                                name=name,
                                action="持有",
                                reasoning=f"已持仓{current_weight:.1%},仓位充足",
                                confidence=confidence,
                            )
                        )
                else:
                    # 新建仓
                    alloc_pct = min(max_position * 0.2, 0.15)
                    alloc_value = total_capital * alloc_pct
                    qty = max(100, int(alloc_value / price / 100) * 100) if price > 0 else 0
                    if qty >= 100 and cash >= qty * price:
                        reasoning_parts.append(f"新建仓位,目标占比{alloc_pct:.0%}")
                        if score >= 80:
                            reasoning_parts.append(f"高评分{score}")
                        if pe and 0 < pe < 30:
                            reasoning_parts.append(f"估值合理PE={pe:.1f}")
                        orders.append(
                            OrderItem(
                                code=code,
                                name=name,
                                action="买入",
                                quantity=qty,
                                weight=f"{alloc_pct:.0%}",
                                limit_price=str(round(price, 2)),
                                stop_loss=str(
                                    round(price * (1 + self.DEFAULT_STOP_LOSS_PCT / 100), 2)
                                ),
                                take_profit=str(
                                    round(price * (1 + self.DEFAULT_TAKE_PROFIT_PCT / 100), 2)
                                ),
                                reasoning="; ".join(reasoning_parts),
                                confidence=confidence,
                            )
                        )

            elif signal == "卖出" or (signal == "观望" and score < 30):
                # 卖出或减仓
                if pos:
                    qty = pos.get("quantity", 0)
                    pnl = pos.get("profit_loss_pct", 0)
                    if pnl < -10:
                        reasoning_parts.append(f"浮亏{pnl:.1f}%,建议止损")
                        action = "卖出"
                    elif pnl > 20:
                        reasoning_parts.append(f"浮盈{pnl:.1f}%,建议止盈")
                        action = "减仓"
                        qty = max(100, qty // 2 // 100 * 100)
                    else:
                        reasoning_parts.append("信号转弱,建议减仓")
                        action = "减仓"
                        qty = max(100, qty // 3 // 100 * 100)
                    if qty >= 100:
                        orders.append(
                            OrderItem(
                                code=code,
                                name=name,
                                action=action,
                                quantity=qty,
                                limit_price=str(round(price, 2)),
                                reasoning="; ".join(reasoning_parts),
                                confidence=confidence,
                            )
                        )
                # 不在持仓中的卖出信号忽略
            # 观望
            elif pos:
                orders.append(
                    OrderItem(
                        code=code,
                        name=name,
                        action="持有",
                        reasoning=f"信号: {signal}, 维持持仓",
                        confidence=confidence,
                    )
                )

        # 检查持仓中不在推荐列表的股票
        rec_codes = {r.get("stock_code") for r in recommendations}
        for p in positions:
            code = p.get("stock_code", "")
            if code and code not in rec_codes:
                pnl = p.get("profit_loss_pct", 0)
                if pnl < -15:
                    orders.append(
                        OrderItem(
                            code=code,
                            name=p.get("stock_name", code),
                            action="卖出",
                            quantity=p.get("quantity", 0),
                            reasoning=f"不在推荐列表且浮亏{pnl:.1f}%,建议清理",
                            confidence="中",
                        )
                    )

        return orders

    def _generate_conditional_orders(
        self, recommendations: list[dict], positions: list[dict]
    ) -> list[ConditionalOrder]:
        """生成条件订单"""
        conditionals = []
        position_map = {p.get("stock_code", ""): p for p in positions}

        for rec in recommendations:
            code = rec.get("stock_code", "")
            name = rec.get("stock_name", code)
            price = rec.get("price", 0)
            signal = rec.get("signal", "观望")

            if not code or not price:
                continue

            # 止损条件单
            pos = position_map.get(code)
            if pos:
                cost = pos.get("cost_price", price)
                stop_price = round(cost * 0.92, 2)  # 成本价-8%
                take_price = round(cost * 1.20, 2)  # 成本价+20%
                conditionals.append(
                    ConditionalOrder(
                        stock_code=code,
                        stock_name=name,
                        condition=f"价格跌破止损价 {stop_price}",
                        action="全部卖出止损",
                        trigger_price=stop_price,
                        timing="即时",
                    )
                )
                conditionals.append(
                    ConditionalOrder(
                        stock_code=code,
                        stock_name=name,
                        condition=f"价格涨至止盈价 {take_price}",
                        action="分批止盈(先卖50%)",
                        trigger_price=take_price,
                        timing="盘中监控",
                    )
                )

            # 突破买入条件单
            if signal in ("买入", "观望") and code not in position_map:
                breakout_price = round(price * 1.03, 2)  # 突破当前价3%
                conditionals.append(
                    ConditionalOrder(
                        stock_code=code,
                        stock_name=name,
                        condition=f"放量突破 {breakout_price} 元",
                        action="限价买入",
                        trigger_price=breakout_price,
                        timing="盘中",
                    )
                )

        return conditionals

    def _generate_monitoring_signals(
        self, recommendations: list[dict], positions: list[dict]
    ) -> list[MonitoringSignal]:
        """生成监控信号"""
        signals = []

        for pos in positions:
            code = pos.get("stock_code", "")
            cost = pos.get("cost_price", 0)
            pnl = pos.get("profit_loss_pct", 0)

            if cost > 0:
                signals.append(
                    MonitoringSignal(
                        stock_code=code,
                        signal_type="STOP_LOSS",
                        description=f"止损线: 成本价{round(cost, 2)} x 92% = {round(cost * 0.92, 2)}",
                        threshold=round(cost * 0.92, 2),
                    )
                )
                signals.append(
                    MonitoringSignal(
                        stock_code=code,
                        signal_type="TAKE_PROFIT",
                        description=f"止盈线: 成本价{round(cost, 2)} x 120% = {round(cost * 1.20, 2)}",
                        threshold=round(cost * 1.20, 2),
                    )
                )

            if pnl > 15:
                signals.append(
                    MonitoringSignal(
                        stock_code=code,
                        signal_type="TRAILING_STOP",
                        description=f"浮盈{pnl:.1f}%,启用移动止损(回撤5%卖出)",
                        threshold=round(pos.get("current_price", cost) * 0.95, 2),
                    )
                )

        for rec in recommendations:
            code = rec.get("stock_code", "")
            price = rec.get("price", 0)
            if code and price and code not in {p.get("stock_code") for p in positions}:
                signals.append(
                    MonitoringSignal(
                        stock_code=code,
                        signal_type="VOLUME",
                        description=f"关注放量突破信号,目标价{round(price * 1.03, 2)}",
                        threshold=round(price * 1.03, 2),
                    )
                )

        return signals

    def _calculate_position_sizing(
        self,
        recommendations: list[dict],
        cash: float,
        total_capital: float,
        max_position: float,
        master_position_factor: float = 1.0,
        master_weight_factor: float = 1.0,
    ) -> dict:
        """计算仓位分配 - Kelly公式 + 等权分配"""
        if not recommendations:
            return {"method": "none", "allocations": []}

        allocs = []
        total_score = sum(max(r.get("score", 50), 1) for r in recommendations)

        for rec in recommendations:
            code = rec.get("stock_code", "")
            name = rec.get("stock_name", code)
            price = rec.get("price", 0)
            score = rec.get("score", 50)
            # Master weight factor adjusts score: bullish consensus raises score
            score = max(0, min(100, score * master_weight_factor))
            _confidence = rec.get("confidence", "中")

            if not code or not price:
                continue

            # b = 盈亏比 (默认2), p = 胜率, q = 1-p
            win_rate = 0.5 + (score - 50) / 200  # score 50 -> 50%, score 100 -> 75%
            win_rate = max(0.3, min(0.8, win_rate))
            payoff_ratio = 2.0  # 盈亏比
            kelly_fraction = (payoff_ratio * win_rate - (1 - win_rate)) / payoff_ratio
            kelly_fraction = max(0, min(0.25, kelly_fraction))  # 上限25%

            # 等权分配
            equal_weight = 1.0 / len(recommendations)

            # 混合分配: 60% score加权 + 40% Kelly  # noqa: ERA001
            score_weight = score / total_score if total_score > 0 else equal_weight
            blended = 0.6 * score_weight + 0.4 * kelly_fraction

            # 应用最大仓位限制
            final_weight = min(
                blended * master_position_factor, max_position * 0.3
            )  # 单股不超过最大仓位的30%
            alloc_value = total_capital * final_weight
            shares = max(0, int(alloc_value / price / 100) * 100) if price > 0 else 0

            allocs.append(
                {
                    "stock_code": code,
                    "stock_name": name,
                    "score": score,
                    "win_rate": round(win_rate * 100, 1),
                    "kelly_fraction": round(kelly_fraction * 100, 2),
                    "target_weight": round(final_weight * 100, 2),
                    "target_value": round(alloc_value, 0),
                    "target_shares": shares,
                    "price": price,
                }
            )

        return {
            "method": "blended_kelly_equal",
            "max_position_pct": round(max_position * 100, 1),
            "allocations": allocs,
        }

    def _generate_risk_management(
        self, risk_level: str, risk_report: dict | None, positions: list[dict]
    ) -> RiskManagement:
        """生成风控规则"""
        # 熔断规则
        if risk_level == "EXTREME":
            breaker = "当日组合亏损>5%立即清仓, 单股亏损>8%立即止损"
            port_stop = "总仓位降至30%以下"
        elif risk_level == "HIGH":
            breaker = "当日组合亏损>7%暂停交易, 单股亏损>10%止损"
            port_stop = "总仓位降至50%以下"
        else:
            breaker = "当日组合亏损>10%暂停交易, 单股亏损>15%止损"
            port_stop = "总仓位不超过70%"

        # 关键风险
        key_risks = []
        if risk_report:
            portfolio_risk = risk_report.get("portfolio_risk", {})
            for issue in portfolio_risk.get("issues", []):
                key_risks.append(issue)
            stress = portfolio_risk.get("stress_test", {})
            if stress.get("estimated_loss_pct", 0) < -30:
                key_risks.append(
                    "压力测试显示极端场景可能亏损{p}%".format(p=stress.get("estimated_loss_pct", 0))
                )

        if not key_risks:
            key_risks = ["当前无重大风险预警"]

        return RiskManagement(
            circuit_breaker=breaker,
            portfolio_stop=port_stop,
            key_risks=key_risks,
        )
