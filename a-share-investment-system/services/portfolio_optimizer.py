"""组合优化器 - 约束预计算+信号聚合+成本感知再平衡 - 来源: ai-hedge-fund"""

from services.base import BaseService, ServiceResult
from shared.logging import emit_log


class ConstraintPrecomputer:
    """确定性约束预计算 - 纯Python,无LLM调用"""

    def compute(
        self,
        positions: list[dict],
        signals: list[dict],
        cash: float,
        risk_limits: dict | None = None,
    ) -> dict:
        """预计算每只股票允许的操作"""
        limits = risk_limits or {}
        max_single_pct = limits.get("max_single_stock_pct", 20.0) / 100
        limits.get("max_total_position_pct", 80.0) / 100

        total_value = cash + sum(p.get("market_value", p.get("cost_value", 0)) for p in positions)
        constraints = {}

        for sig in signals:
            code = sig.get("stock_code", "")
            pos = next((p for p in positions if p.get("stock_code") == code), None)
            current_value = pos.get("market_value", pos.get("cost_value", 0)) if pos else 0
            current_weight = current_value / total_value if total_value > 0 else 0
            price = sig.get("target_price", 10) or 10

            max_buy_shares = int(cash * max_single_pct / price)
            max_sell_shares = pos.get("quantity", 0) if pos else 0

            allowed = ["持有"]
            if max_buy_shares >= 100:
                allowed.append("买入")
            if max_sell_shares >= 100:
                allowed.append("卖出")

            constraints[code] = {
                "current_weight": round(current_weight * 100, 1),
                "max_buy_shares": max_buy_shares,
                "max_sell_shares": max_sell_shares,
                "allowed_actions": allowed,
                "needs_llm": len([a for a in allowed if a != "持有"]) > 0,  # >1种选择才需LLM
            }

        return {
            "constraints": constraints,
            "total_value": round(total_value, 0),
            "cash": cash,
            "skip_llm_count": sum(1 for c in constraints.values() if not c["needs_llm"]),
        }


class SignalAggregator:
    """多源信号聚合器 - LLM仅在多选时调用"""

    def aggregate(
        self,
        signals: list[dict],
        constraints: dict,
        debate_results: dict | None = None,
        factor_scores: dict | None = None,
    ) -> list[dict]:
        """聚合多源信号,生成综合决策"""
        aggregated = []

        for sig in signals:
            code = sig.get("stock_code", "")
            cons = constraints.get("constraints", {}).get(code, {})
            allowed = cons.get("allowed_actions", ["持有"])

            # 预填充优化:只有1种选择→跳过LLM直接确定
            if len(allowed) == 1:
                aggregated.append(
                    {
                        "stock_code": code,
                        "stock_name": sig.get("stock_name", ""),
                        "action": allowed[0],
                        "confidence": 1.0,
                        "reason": "预填充: 约束条件下唯一可行操作",
                        "source": "constraint_prefill",
                    }
                )
                continue

            # 多源信号加权融合
            scores = {"买入": 0.0, "持有": 0.0, "卖出": 0.0}
            total_weight = 0.0

            # 辩论结果权重 40%
            if debate_results:
                dr = debate_results.get(code, {})
                verdict = dr.get("verdict", "持有")
                conf = dr.get("confidence", 0.5)
                scores[verdict] += conf * 0.40
                total_weight += 0.40

            # 原始信号权重 30%
            action = sig.get("action", sig.get("verdict", "持有"))
            conf = sig.get("confidence", 0.5)
            scores[action] += conf * 0.30
            total_weight += 0.30

            # 因子评分权重 30%
            if factor_scores:
                fs = factor_scores.get(code, {})
                fs_signal = fs.get("signal", "neutral")
                fs_score = fs.get("composite_score", 50) / 100
                mapped = (
                    "买入"
                    if fs_signal == "bullish"
                    else ("卖出" if fs_signal == "bearish" else "持有")
                )
                scores[mapped] += fs_score * 0.30
                total_weight += 0.30

            # 归一化
            if total_weight > 0:
                for k in scores:
                    scores[k] /= total_weight

            winner = max(scores, key=lambda k: scores[k])
            winner_conf = scores[winner]

            # 过滤不允许的操作
            if winner not in allowed:
                winner = "持有"
                winner_conf = scores["持有"]

            aggregated.append(
                {
                    "stock_code": code,
                    "stock_name": sig.get("stock_name", ""),
                    "action": winner,
                    "confidence": round(winner_conf, 3),
                    "reason": f"信号融合: { {k: round(v, 2) for k, v in scores.items()} }",
                    "source": "signal_aggregation",
                    "scores": {k: round(v, 3) for k, v in scores.items()},
                }
            )

        return aggregated


class RebalanceEngine:
    """再平衡引擎 - 成本感知 + 杠铃结构维护"""

    def plan(
        self,
        current_positions: list[dict],
        target_signals: list[dict],
        total_value: float,
        barbell_ratio: float = 0.70,
    ) -> dict:
        """生成再平衡计划"""
        actions = []
        signal_map = {s["stock_code"]: s for s in target_signals}

        for pos in current_positions:
            code = pos.get("stock_code", "")
            current_weight = (
                pos.get("market_value", pos.get("cost_value", 0)) / total_value
                if total_value > 0
                else 0
            )
            sig = signal_map.get(code, {})

            action = sig.get("action", "持有")
            if action == "卖出":
                priority = "高"
                action_text = "建议全仓卖出"
            elif action == "买入":
                priority = "中"
                action_text = "建议加仓至目标权重"
            elif current_weight > 0.25:
                priority = "高"
                action_text = "仓位过重,建议减仓至20%以下"
            elif current_weight > 0.20:
                priority = "中"
                action_text = "仓位偏重,考虑小幅减仓"
            else:
                priority = "低"
                action_text = "维持当前仓位"

            actions.append(
                {
                    "stock_code": code,
                    "stock_name": pos.get("stock_name", ""),
                    "current_weight_pct": round(current_weight * 100, 1),
                    "action": action_text,
                    "priority": priority,
                }
            )

        # 杠铃结构检查
        core_pct = (
            sum(
                p.get("market_value", p.get("cost_value", 0))
                for p in current_positions
                if p.get("industry") not in ("科技", "成长", "概念")
            )
            / total_value
            if total_value > 0
            else 0
        )

        actions.sort(
            key=lambda a: 0 if a["priority"] == "高" else (1 if a["priority"] == "中" else 2)
        )

        return {
            "actions": actions,
            "high_priority_count": sum(1 for a in actions if a["priority"] == "高"),
            "barbell_status": {
                "core_pct": round(core_pct * 100, 1),
                "satellite_pct": round((1 - core_pct) * 100, 1),
                "target_core": round(barbell_ratio * 100, 0),
                "drift": round((core_pct - barbell_ratio) * 100, 1),
            },
        }


class PortfolioOptimizer(BaseService):
    """组合优化器 - 整合约束预计算+信号聚合+再平衡"""

    def __init__(self, risk_engine=None):
        super().__init__()
        self.constraint_precomputer = ConstraintPrecomputer()
        self.signal_aggregator = SignalAggregator()
        self.rebalance_engine = RebalanceEngine()
        self._risk_engine = risk_engine

    @property
    def risk_engine(self):
        if self._risk_engine is None:
            from services.risk_engine import RiskEngine

            self._risk_engine = RiskEngine()
        return self._risk_engine

    def optimize(
        self,
        current_positions: list[dict],
        signals: list[dict],
        risk_report: dict | None = None,
        cash: float = 0,
        debate_results: dict | None = None,
        factor_scores: dict | None = None,
    ) -> ServiceResult:
        """运行完整组合优化"""
        try:
            risk_limits = (risk_report or {}).get("position_limits", {})

            # Step 1: 约束预计算(纯Python)
            constraints = self.constraint_precomputer.compute(
                current_positions, signals, cash, risk_limits
            )

            # Step 2: 信号聚合(LLM仅在多选时调用)
            aggregated = self.signal_aggregator.aggregate(
                signals, constraints, debate_results, factor_scores
            )

            # Step 3: 再平衡计划
            total_value = constraints["total_value"]
            rebalance = self.rebalance_engine.plan(current_positions, aggregated, total_value)

            # 统计
            prefill_count = constraints.get("skip_llm_count", 0)

            return ServiceResult.ok(
                data={
                    "target_signals": aggregated,
                    "constraints": constraints,
                    "rebalance_plan": rebalance,
                    "prefill_count": prefill_count,
                    "total_positions": len(current_positions),
                    "total_signals": len(signals),
                }
            )
        except Exception as e:
            return ServiceResult.error(errors=[f"PortfolioOptimizer failed: {e}"])

    def kelly_position_sizing(
        self,
        candidates: list[dict],
        total_capital: float,
        cash: float,
        max_single_pct: float = 25.0,
        half_kelly: bool = True,
    ) -> ServiceResult:
        """Kelly公式仓位计算

        Args:
            candidates: 候选股票列表，需含 stock_code, score, price, volatility
            total_capital: 总资金
            cash: 可用现金
            max_single_pct: 单股最大仓位占比
            half_kelly: 是否使用半Kelly(更保守)
        """
        try:
            emit_log("INFO", "portfolio_optimizer", f"kelly_start: {len(candidates)} candidates")

            if not candidates:
                return ServiceResult.ok(data={"allocations": [], "method": "kelly"})

            allocations = []
            for c in candidates:
                code = c.get("stock_code", "")
                name = c.get("stock_name", code)
                price = c.get("price", 0)
                score = c.get("score", 50)
                vol = c.get("volatility", 0.3)

                if not code or not price or price <= 0:
                    continue

                # Kelly参数估计
                # 胜率: 基于score映射 (50->50%, 80->65%, 100->75%)
                win_rate = 0.50 + (score - 50) / 200
                win_rate = max(0.30, min(0.80, win_rate))

                # 盈亏比: 基于波动率反推 (低波动 -> 高盈亏比)
                payoff_ratio = max(1.0, 3.0 - vol * 4)
                payoff_ratio = min(4.0, payoff_ratio)

                # Kelly公式: f* = (bp - q) / b
                loss_rate = 1 - win_rate
                kelly_f = (payoff_ratio * win_rate - loss_rate) / payoff_ratio
                kelly_f = max(0, kelly_f)

                # 半Kelly (更保守，实际更常用)
                if half_kelly:
                    kelly_f = kelly_f / 2

                # 应用上限
                max_f = max_single_pct / 100
                kelly_f = min(kelly_f, max_f)

                # 计算具体股数
                alloc_value = total_capital * kelly_f
                shares = int(alloc_value / price / 100) * 100  # 向下取整到100股

                allocations.append(
                    {
                        "stock_code": code,
                        "stock_name": name,
                        "win_rate": round(win_rate * 100, 1),
                        "payoff_ratio": round(payoff_ratio, 2),
                        "kelly_fraction": round(kelly_f * 100, 2),
                        "half_kelly": half_kelly,
                        "target_weight_pct": round(kelly_f * 100, 2),
                        "target_value": round(shares * price, 0),
                        "target_shares": shares,
                        "price": price,
                    }
                )

            # 按kelly比例排序
            allocations.sort(key=lambda a: a["kelly_fraction"], reverse=True)

            # 检查总仓位是否超限
            total_alloc = sum(a["target_value"] for a in allocations)
            if total_alloc > cash * 1.05:
                # 按比例缩减
                scale = cash / total_alloc if total_alloc > 0 else 1
                for a in allocations:
                    a["target_shares"] = int(a["target_shares"] * scale / 100) * 100
                    a["target_value"] = round(a["target_shares"] * a["price"], 0)
                    a["target_weight_pct"] = round(a["target_value"] / total_capital * 100, 2)

            emit_log("INFO", "portfolio_optimizer", f"kelly_done: {len(allocations)} allocations")

            return ServiceResult.ok(
                data={
                    "method": "half_kelly" if half_kelly else "full_kelly",
                    "total_capital": round(total_capital, 0),
                    "available_cash": round(cash, 0),
                    "total_allocated": round(sum(a["target_value"] for a in allocations), 0),
                    "allocations": allocations,
                }
            )
        except Exception as e:
            return ServiceResult.error(errors=[f"kelly_position_sizing failed: {e}"])

    def risk_budget_allocation(
        self,
        candidates: list[dict],
        total_capital: float,
        risk_budget_pct: float = 2.0,
    ) -> ServiceResult:
        """风险预算分配 - 按风险贡献均等化分配仓位

        Args:
            candidates: 候选股票，需含 stock_code, price, volatility
            total_capital: 总资金
            risk_budget_pct: 组合日风险预算占比
        """
        try:
            if not candidates:
                return ServiceResult.ok(data={"allocations": []})

            # 计算每只股票的风险贡献
            inv_vols = []
            for c in candidates:
                vol = c.get("volatility", 0.3)
                inv_vol = 1.0 / max(vol, 0.01)
                inv_vols.append(inv_vol)

            total_inv_vol = sum(inv_vols)
            if total_inv_vol <= 0:
                return ServiceResult.ok(data={"allocations": []})

            allocations = []
            for i, c in enumerate(candidates):
                code = c.get("stock_code", "")
                name = c.get("stock_name", code)
                price = c.get("price", 0)
                vol = c.get("volatility", 0.3)

                if not code or not price or price <= 0:
                    continue

                # 风险平价权重
                weight = inv_vols[i] / total_inv_vol
                alloc_value = total_capital * weight
                shares = int(alloc_value / price / 100) * 100

                allocations.append(
                    {
                        "stock_code": code,
                        "stock_name": name,
                        "volatility": round(vol * 100, 1),
                        "weight_pct": round(weight * 100, 2),
                        "target_value": round(shares * price, 0),
                        "target_shares": shares,
                        "price": price,
                    }
                )

            return ServiceResult.ok(
                data={
                    "method": "risk_parity",
                    "risk_budget_pct": risk_budget_pct,
                    "allocations": allocations,
                }
            )
        except Exception as e:
            return ServiceResult.error(errors=[f"risk_budget_allocation failed: {e}"])
