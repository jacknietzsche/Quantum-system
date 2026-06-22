"""Node 7: Portfolio Management — 组合管理与再平衡"""

from decision_review import PositionManager
from workflows.nodes._shared import _log
from workflows.state import AShareSuperState


def node_portfolio_management(state: AShareSuperState) -> dict:
    """第六层:组合管理(动态仓位 + 再平衡方案)"""
    logs = list(state.get("logs", []))
    logs.append(_log(state, "📐 [第六层] 组合管理启动..."))

    risk = state.get("risk_assessment", {})
    risk_score = risk.get("overall_level", risk.get("tail_risk", {}).get("score", 50))
    portfolio = state.get("portfolio", [])
    hedge_decision = state.get("hedge_fund_decision", {})
    fincept_verify = state.get("fincept_verify", {})

    # 动态仓位
    pm = PositionManager()
    position_plan = pm.calculate_position_ratio(risk_score)

    # 再平衡方案
    rebalance_plan = {
        "current_positions": [],
        "suggested_actions": [],
        "barbell_allocation": {},
    }

    if portfolio:
        total_cost = sum(h.get("cost_value", 0) for h in portfolio)
        sum(h.get("current_value", 0) for h in portfolio)

        for h in portfolio:
            current_weight = h.get("cost_value", 0) / total_cost * 100 if total_cost > 0 else 0
            pl_pct = h.get("profit_loss_pct", 0)

            # 综合投委会+大师验证给出再平衡建议
            stock_decision = hedge_decision.get("stock_decisions", {}).get(h["stock_code"], {})
            verify = fincept_verify.get("stock_verifications", {}).get(h["stock_code"], {})

            committee_rec = stock_decision.get("winner", "持有")
            verify_verdict = verify.get("final_verdict", "通过")

            # 再平衡逻辑
            if verify_verdict == "否决" or committee_rec == "卖出":
                action = "建议减仓/卖出"
                priority = "高"
            elif pl_pct > 30 and committee_rec != "买入":
                action = "考虑止盈减仓"
                priority = "中"
            elif pl_pct < -20:
                action = "评估止损"
                priority = "高"
            elif current_weight > 25:
                action = "仓位过重,建议减仓"
                priority = "中"
            else:
                action = "维持当前仓位"
                priority = "低"

            rebalance_plan["current_positions"].append(
                {
                    "stock": f"{h['stock_name']}({h['stock_code']})",
                    "weight": f"{current_weight:.1f}%",
                    "pl_pct": f"{pl_pct:+.1f}%",
                    "committee": committee_rec,
                    "verify": verify_verdict,
                    "action": action,
                    "priority": priority,
                }
            )

        # 杠铃策略分配
        stock_count = len(portfolio)
        if total_cost > 0:
            barbell = pm.calculate_stock_weight(total_cost, risk_score, stock_count)
            rebalance_plan["barbell_allocation"] = barbell

    # 按优先级排序
    rebalance_plan["suggested_actions"] = sorted(
        [p for p in rebalance_plan["current_positions"] if p["priority"] in ("高", "中")],
        key=lambda x: 0 if x["priority"] == "高" else 1,
    )

    logs.append(
        _log(
            state,
            f"✅ 组合管理完成: {position_plan['level']} → {position_plan['position_pct']}, "
            f"再平衡建议{len(rebalance_plan['suggested_actions'])}条",
        )
    )

    return {"position_plan": position_plan, "rebalance_plan": rebalance_plan, "logs": logs}
