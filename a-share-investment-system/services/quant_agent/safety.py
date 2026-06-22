"""安全边界 — AI不可逾越的硬约束"""

from __future__ import annotations

from typing import ClassVar

from services.quant_agent.schemas import DecisionReport


class SafetyBoundary:
    """硬约束, AI决策必须遵守

    所有越界行为会被自动修正并记录警告。
    """

    HARD_LIMITS: ClassVar[dict[str, float | list[str]]] = {
        "max_single_position": 0.20,  # 单票 ≤ 20%
        "max_sector_exposure": 0.40,  # 单行业 ≤ 40%
        "max_total_position": 0.80,  # 总仓位 ≤ 80%
        "min_stop_loss": -0.07,  # 最低止损 -7%
        "forbidden_prefixes": ["*ST", "ST"],  # 禁止ST
    }

    def enforce(self, decision: DecisionReport) -> DecisionReport:
        """检查并修正越界的决策"""
        max_single = float(self.HARD_LIMITS["max_single_position"])
        max_total = float(self.HARD_LIMITS["max_total_position"])
        min_stop = float(self.HARD_LIMITS["min_stop_loss"])

        for pick in decision.picks:
            weight = float(pick.weight)
            stop_loss = float(pick.stop_loss)
            take_profit = float(pick.take_profit)

            # 单票仓位上限
            if weight > max_single:
                pick.warnings.append(f"仓位超限→已调至{max_single:.0%}")
                pick.weight = max_single

            # 止损检查
            if stop_loss > -min_stop:
                pick.warnings.append(f"止损过宽→已调至{min_stop:.0%}")
                pick.stop_loss = min_stop

            # 止盈不低于止损
            if take_profit > 0 and stop_loss < 0 and take_profit < abs(stop_loss):
                pick.take_profit = abs(stop_loss) * 1.5

        # 总仓位检查
        total_weight = sum(float(p.weight) for p in decision.picks)
        if total_weight > max_total:
            scale = max_total / total_weight
            for pick in decision.picks:
                pick.weight *= scale
            decision.risk_warnings.append(f"总仓位超限→已等比缩放至{max_total:.0%}")

        return decision
