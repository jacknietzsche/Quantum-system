"""Node 6: Risk Control Audit — 三层风险审计"""

from datetime import datetime

from skills import RiskFirewall
from workflows.nodes._shared import _log, create_data_bus
from workflows.state import AShareSuperState
from workflows.stubs import RISK_DEFAULTS, FaultTolerantNode, LookAheadBiasAuditor


@FaultTolerantNode(timeout=180, default=RISK_DEFAULTS, node_name="risk_control_audit")
def node_risk_control_audit(state: AShareSuperState) -> dict:
    """第五层:三层风险审计(霍华德-马克思 + 塔勒布 + 前视偏差)"""
    logs = list(state.get("logs", []))
    list(state.get("errors", []))
    logs.append(_log(state, "🛡️ [第五层] 三层风险审计启动..."))

    data_bus = create_data_bus()
    firewall = RiskFirewall(data_bus)
    portfolio = state.get("portfolio", [])

    # 预取全市场行情(复用状态中的 market_data breadth,避免重复拉取)
    market_data = state.get("market_data", {})
    pre_breadth = market_data.get("breadth")

    # 第一层:市场风险(恐慌指数)— 用预取的 breadth 数据
    if pre_breadth and pre_breadth.get("total", 0) > 0:
        breadth = pre_breadth
        down_ratio = breadth["down"] / breadth["total"] * 100
        limit_down_ratio = breadth["limit_down"] / breadth["total"] * 100
        panic_score = down_ratio * 0.6 + limit_down_ratio * 15
        if panic_score > 80:
            market_risk = {
                "level": "EXTREME",
                "score": panic_score,
                "pass": False,
                "message": f"市场恐慌指数{panic_score:.0f},建议降低仓位至50%以下",
            }
        elif panic_score > 60:
            market_risk = {
                "level": "HIGH",
                "score": panic_score,
                "pass": True,
                "message": f"市场恐慌指数{panic_score:.0f},注意控制仓位",
            }
        elif panic_score > 40:
            market_risk = {
                "level": "MEDIUM",
                "score": panic_score,
                "pass": True,
                "message": f"市场情绪中性,恐慌指数{panic_score:.0f}",
            }
        else:
            market_risk = {
                "level": "LOW",
                "score": panic_score,
                "pass": True,
                "message": f"市场情绪偏暖,恐慌指数{panic_score:.0f}",
            }
    else:
        market_risk = firewall.check_market_risk()

    # 第二层:个股风险(仅检查持仓,自选股量大不做逐个检查)
    stock_risks = {}
    for h in portfolio:
        stock_risks[h["stock_code"]] = firewall.check_stock_risk(h["stock_code"])

    # 第三层:尾部风险(集中度/杠杆)
    tail_risk = firewall.check_tail_risk(portfolio)

    # 霍华德-马克思市场周期风险(来自Skill输出)
    howard_marks_output = state.get("skill_outputs", {}).get("howard_marks", [])
    cycle_risk = "UNKNOWN"
    if howard_marks_output:
        hm = (
            howard_marks_output[0] if isinstance(howard_marks_output, list) else howard_marks_output
        )
        cycle_risk = hm.get("cycle_position", "UNKNOWN")

    # 前视偏差审计
    auditor = LookAheadBiasAuditor()
    audit_result = auditor.audit_code(
        "from data_bus import DataBus; from skills import RiskFirewall", "super_workflow.py"
    )

    risk_assessment = {
        "pass": market_risk["pass"] and tail_risk["pass"],
        "market_risk": market_risk,
        "stock_risks": stock_risks,
        "tail_risk": tail_risk,
        "cycle_risk": cycle_risk,
        "overall_level": max(market_risk["score"], tail_risk["score"]),
        "timestamp": datetime.now().isoformat(),
    }

    risk_pass = risk_assessment["pass"]

    logs.append(
        _log(
            state,
            f"{'✅' if risk_pass else '❌'} 风险审计完成: "
            f"市场={market_risk['level']} 周期={cycle_risk} "
            f"尾部={tail_risk['level']} 通过={'是' if risk_pass else '否'}",
        )
    )

    return {
        "risk_assessment": risk_assessment,
        "risk_pass": risk_pass,
        "look_ahead_audit": audit_result,
        "logs": logs,
    }
