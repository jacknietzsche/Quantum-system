"""Node 9: Generate Recommendations — 生成交易建议"""

from workflows.nodes._shared import _log
from workflows.state import AShareSuperState


def node_generate_recommendations(state: AShareSuperState) -> dict:
    """生成投资建议(融合所有层级结果)"""
    logs = list(state.get("logs", []))
    logs.append(_log(state, "💡 生成投资建议..."))

    portfolio = state.get("portfolio", [])
    risk = state.get("risk_assessment", {})
    hedge = state.get("hedge_fund_decision", {})
    fincept = state.get("fincept_verify", {})
    state.get("rebalance_plan", {})
    vote_results = state.get("vote_results", {})

    recommendations = []

    for h in portfolio:
        code = h.get("stock_code", "")
        name = h.get("stock_name", "")
        pl_pct = h.get("profit_loss_pct", 0)

        # 综合各层信号
        stock_risk = risk.get("stock_risks", {}).get(code, {})
        risk_level = stock_risk.get("level", "UNKNOWN")

        committee = hedge.get("stock_decisions", {}).get(code, {})
        committee_rec = committee.get("winner", "持有")
        committee_consistency = committee.get("consistency", 0)

        verify = fincept.get("stock_verifications", {}).get(code, {})
        verify_verdict = verify.get("final_verdict", "通过")
        approval_rate = verify.get("approval_rate", 0.5)

        vote = vote_results.get(code, {})
        vote_winner = vote.get("winner", "持有")
        vote_consistency = vote.get("consistency", 0)

        # 综合决策逻辑
        signals = [committee_rec, vote_winner]
        approve_signals = signals.count("买入")
        reject_signals = signals.count("卖出")

        if verify_verdict == "否决" or risk_level == "HIGH":
            action = "减仓"
            reason = "风控否决/个股高风险"
        elif approve_signals >= 2 and committee_consistency > 0.6 and approval_rate > 0.6:
            action = "加仓"
            reason = (
                f"投委会+投票一致看多(一致性{committee_consistency:.0%}+{vote_consistency:.0%})"
            )
        elif reject_signals >= 2:
            action = "减仓"
            reason = "投委会+投票一致看空"
        elif pl_pct > 25:
            action = "考虑止盈"
            reason = f"盈利{pl_pct:.1f}%,已达目标区间"
        elif pl_pct < -15:
            action = "评估止损"
            reason = f"亏损{pl_pct:.1f}%,需重新评估"
        else:
            action = "持有观察"
            reason = "多空信号分歧,维持现状"

        recommendations.append(
            {
                "stock_code": code,
                "stock_name": name,
                "action": action,
                "reason": reason,
                "risk_level": risk_level,
                "profit_loss_pct": pl_pct,
                "committee_rec": committee_rec,
                "committee_consistency": committee_consistency,
                "verify_verdict": verify_verdict,
                "vote_winner": vote_winner,
                "vote_consistency": vote_consistency,
                "priority": "高"
                if action in ("减仓", "加仓")
                else "中"
                if action == "考虑止盈"
                else "低",
            }
        )

    # 系统级建议
    position_advice = risk.get("tail_risk", {}).get("position_advice", "维持当前仓位")
    market_decision = hedge.get("market_decision", "维持")
    recommendations.append(
        {
            "stock_code": "SYSTEM",
            "stock_name": "系统建议",
            "action": position_advice,
            "reason": f"投委会市场判断={market_decision},市场风险={risk.get('market_risk', {}).get('level', 'N/A')},周期={risk.get('cycle_risk', 'N/A')}",
            "priority": "高",
        }
    )

    # 按优先级排序
    recommendations.sort(
        key=lambda x: 0 if x.get("priority") == "高" else 1 if x.get("priority") == "中" else 2
    )

    logs.append(_log(state, f"✅ 生成{len(recommendations)}条建议"))

    return {"recommendations": recommendations, "logs": logs}
