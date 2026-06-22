"""Node 5: Fincept Master Verify — Fincept大师验证"""

from datetime import datetime

from workflows.nodes._shared import run_fincept_master_verify
from workflows.state import AShareSuperState
from workflows.stubs import TieredVoter


def node_fincept_master_verify(state: AShareSuperState) -> dict:
    """
    第四层:Fincept 37位大师终极验证
    优化:仅在投委会出现严重分歧时激活,降低成本
    """
    logs = list(state.get("logs", []))
    hedge_decision = state.get("hedge_fund_decision", {})

    # 协同逻辑:检查是否需要激活大师验证
    tiered_voter = TieredVoter()
    should_activate = tiered_voter.should_activate_fincept(hedge_decision)

    if not should_activate:
        logs.append(
            f"[{datetime.now().strftime('%H:%M:%S')}] ⏭️ Fincept大师验证跳过(投委会一致性较高,无需二次验证)"
        )
        # 返回默认通过结果
        stock_decisions = hedge_decision.get("stock_decisions", {})
        verify_results = {}
        for code, decision in stock_decisions.items():
            verify_results[code] = {
                "stock_name": decision.get("stock_name", code),
                "committee_decision": decision.get("winner", "持有"),
                "approve_count": 0,
                "reject_count": 0,
                "abstain_count": 0,
                "approval_rate": 0.8,
                "master_verifications": [],
                "final_verdict": "通过(跳过验证)",
            }
        return {
            "fincept_verify": {
                "stock_verifications": verify_results,
                "global_approval_rate": 0.8,
                "master_count": 0,
                "activated": False,
                "reason": "投委会一致性较高,跳过大师验证以节省成本",
                "timestamp": datetime.now().isoformat(),
            },
            "logs": logs,
        }

    logs.append(
        f"[{datetime.now().strftime('%H:%M:%S')}] 🔍 Fincept大师验证层(投委会分歧,激活验证)..."
    )

    # 执行完整的大师验证
    state["logs"] = logs
    return run_fincept_master_verify(state)
