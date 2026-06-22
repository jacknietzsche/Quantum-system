"""Super Workflow 构建器 + 运行入口 — 导入所有节点函数组装工作流"""

import os
import time
import uuid
from datetime import datetime
from typing import Any

from langgraph.graph import END, StateGraph

from skills import register_all_skills
from workflows.nodes._shared import (
    AShareSuperState,
    WorkflowCompilerCache,
    create_data_bus,
)
from workflows.nodes.node_ai_hedge_fund_vote import node_ai_hedge_fund_vote
from workflows.nodes.node_data_collector import node_data_collector
from workflows.nodes.node_debate_committee import node_debate_committee
from workflows.nodes.node_fetch_global_data import node_fetch_global_data
from workflows.nodes.node_fincept_master_verify import node_fincept_master_verify
from workflows.nodes.node_generate_final_report import node_generate_final_report
from workflows.nodes.node_generate_recommendations import node_generate_recommendations
from workflows.nodes.node_multi_model_vote import node_multi_model_vote
from workflows.nodes.node_portfolio_management import node_portfolio_management
from workflows.nodes.node_push_notification import node_push_notification
from workflows.nodes.node_risk_control_audit import node_risk_control_audit
from workflows.nodes.node_skill_analysis_parallel import node_skill_analysis_parallel


def router_risk_pass_or_not(state: AShareSuperState) -> str:
    if state.get("risk_pass", True):
        return "portfolio_management"
    return "generate_final_report_direct"


def build_super_workflow() -> StateGraph:
    register_all_skills()
    workflow = StateGraph(AShareSuperState)
    workflow.add_node("fetch_global_data", node_fetch_global_data)
    workflow.add_node("data_collector", node_data_collector)
    workflow.add_node("skill_analysis_parallel", node_skill_analysis_parallel)
    workflow.add_node("debate_committee", node_debate_committee)
    workflow.add_node("ai_hedge_fund_vote", node_ai_hedge_fund_vote)
    workflow.add_node("fincept_master_verify", node_fincept_master_verify)
    workflow.add_node("risk_control_audit", node_risk_control_audit)
    workflow.add_node("portfolio_management", node_portfolio_management)
    workflow.add_node("multi_model_vote", node_multi_model_vote)
    workflow.add_node("generate_recommendations", node_generate_recommendations)
    workflow.add_node("generate_final_report", node_generate_final_report)
    workflow.add_node("generate_final_report_direct", node_generate_final_report)
    workflow.add_node("push_notification", node_push_notification)

    workflow.set_entry_point("fetch_global_data")
    workflow.add_edge("fetch_global_data", "data_collector")
    workflow.add_edge("data_collector", "skill_analysis_parallel")
    workflow.add_edge("skill_analysis_parallel", "debate_committee")
    workflow.add_edge("debate_committee", "ai_hedge_fund_vote")
    workflow.add_edge("ai_hedge_fund_vote", "fincept_master_verify")
    workflow.add_edge("fincept_master_verify", "risk_control_audit")
    workflow.add_conditional_edges(
        "risk_control_audit",
        router_risk_pass_or_not,
        {
            "portfolio_management": "portfolio_management",
            "generate_final_report_direct": "generate_final_report_direct",
        },
    )
    workflow.add_edge("portfolio_management", "multi_model_vote")
    workflow.add_edge("multi_model_vote", "generate_recommendations")
    workflow.add_edge("generate_recommendations", "generate_final_report")
    workflow.add_edge("generate_final_report_direct", "push_notification")
    workflow.add_edge("generate_final_report", "push_notification")
    workflow.add_edge("push_notification", END)
    return workflow


def run_super_workflow(
    target_stocks: list[str] | None = None, progress_callback=None, abort_check=None
) -> dict:
    run_id = str(uuid.uuid4())[:8]
    t_start = time.time()

    def report(step, status, message, detail=None):
        elapsed = time.time() - t_start
        ts = datetime.now().strftime("%H:%M:%S")
        line = f"[{ts}] {message}"
        print(line)
        if progress_callback:
            progress_callback(
                step, status, message, {"elapsed": round(elapsed, 1), **(detail or {})}
            )

    report("init", "start", f"运行超级工作流 (RunID: {run_id})")
    cache = WorkflowCompilerCache()
    source_files = [os.path.join(os.path.dirname(__file__), "super_workflow.py")]
    # 工作流图仍被编译并提供 build_super_workflow() 给其他调用方使用，但
    # 这里的执行路径已改为顺序调用节点函数, 避免 LangGraph 重复跑完整张图。
    _app = cache.get(source_files, build_super_workflow)
    del _app
    report("compile", "done", "工作流编译完成")

    initial_state: dict[str, Any] = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "timestamp": datetime.now().isoformat(),
        "run_id": run_id,
        "market_data": {},
        "portfolio": [],
        "watchlist": [],
        "data_source": "",
        "prefetched_data": {},
        "skill_outputs": {},
        "skill_stats": {},
        "hedge_fund_decision": {},
        "hedge_fund_signals": {},
        "fincept_verify": {},
        "risk_assessment": {},
        "risk_pass": True,
        "look_ahead_audit": {},
        "position_plan": {},
        "rebalance_plan": {},
        "vote_results": {},
        "recommendations": [],
        "report": "",
        "errors": [],
        "logs": [f"[{datetime.now().strftime('%H:%M:%S')}] 超级工作流启动 (RunID: {run_id})"],
        "performance_metrics": {},
        "degradation": {},
        "aborted": False,
    }

    nodes_list = [
        ("fetch_global_data", node_fetch_global_data, "获取全局市场数据"),
        ("data_collector", node_data_collector, "批量预取持仓+自选股数据"),
        ("skill_analysis_parallel", node_skill_analysis_parallel, "Skill 并行分析"),
        ("debate_committee", node_debate_committee, "多空辩论委员会"),
        ("ai_hedge_fund_vote", node_ai_hedge_fund_vote, "AI 对冲基金投委会"),
        ("fincept_master_verify", node_fincept_master_verify, "Fincept 大师验证"),
        ("risk_control_audit", node_risk_control_audit, "三层风险控制审计"),
        ("portfolio_management", node_portfolio_management, "组合管理与再平衡"),
        ("multi_model_vote", node_multi_model_vote, "多模型投票验证"),
        ("generate_recommendations", node_generate_recommendations, "生成交易建议"),
        ("generate_final_report", node_generate_final_report, "生成最终报告"),
    ]

    current_state: dict[str, Any] = dict(initial_state)
    for i, (node_name, node_fn, node_desc) in enumerate(nodes_list):
        if abort_check and abort_check():
            report("abort", "error", "用户中止工作流")
            current_state["aborted"] = True
            return {
                "report": "",
                "total_elapsed": round(time.time() - t_start, 1),
                "errors": ["用户手动中止"],
                "aborted": True,
            }
        current_state["aborted"] = False
        report("node", "start", f"  [{i + 1}/{len(nodes_list)}] {node_desc}")
        # 条件路由：风险未通过时跳过 portfolio_management/multi_model_vote/
        # generate_recommendations,直接进入最终报告与推送
        if node_name == "portfolio_management" and not current_state.get("risk_pass", True):
            report("node", "skip", "  [风险未通过] 跳过组合管理,直接生成最终报告")
            current_state["position_plan"] = current_state.get("position_plan", {})
            current_state["vote_results"] = current_state.get("vote_results", {})
            try:
                final_part = node_generate_final_report(current_state)
                current_state.update(final_part)
                report("node", "done", f"  [{node_desc}] 完成（直接）")
            except Exception as e:
                msg = f"  [最终报告（直接）] 失败: {str(e)[:200]}"
                report("node", "error", msg)
                current_state["errors"] = [*current_state.get("errors", []), msg]
            try:
                push_part = node_push_notification(current_state)
                current_state.update(push_part)
            except Exception as e:
                msg = f"  [推送] 失败: {str(e)[:200]}"
                report("node", "error", msg)
                current_state["errors"] = [*current_state.get("errors", []), msg]
            break
        try:
            partial = node_fn(current_state)
            current_state.update(partial)
            report("node", "done", f"  [{node_desc}] 完成")
        except Exception as e:
            msg = f"  [{node_desc}] 失败: {str(e)[:200]}"
            report("node", "error", msg)
            current_state["errors"] = [*current_state.get("errors", []), msg]

    total_elapsed = time.time() - t_start
    recs = current_state.get("recommendations", [])
    return {
        "report": current_state.get("report", ""),
        "total_elapsed": round(total_elapsed, 1),
        "run_id": run_id,
        "errors": current_state.get("errors", []),
        "market_summary": {
            "data_source": current_state.get("data_source", ""),
            "index_count": len(current_state.get("market_data", {}).get("indices", {})),
            "breadth": current_state.get("market_data", {}).get("breadth", {}),
        },
        "vote_stats": _extract_vote_stats(current_state),
        "risk_summary": {
            "level": current_state.get("risk_assessment", {}).get("risk_level", "未知"),
            "pass": current_state.get("risk_pass", False),
            "score": current_state.get("risk_assessment", {}).get("overall_score", 0),
        },
        "recommendations": recs,
        "high_priority_count": len(
            [r for r in recs if r.get("priority") == "高" and r.get("stock_code") != "SYSTEM"]
        ),
        "skill_stats": current_state.get("skill_stats", {}),
        "bias_audit": current_state.get("look_ahead_audit", {}),
    }


def run_super_workflow_single_stock(
    stock_code: str, progress_callback=None, abort_check=None
) -> dict:
    data_bus = create_data_bus()
    quote = data_bus.get_stock_quote(stock_code)
    stock_name = quote.get("stock_name", stock_code) if quote else stock_code
    if progress_callback:
        progress_callback("init", "start", f"分析目标: {stock_name}({stock_code})")
    from shared.models import Watchlist, get_session

    session = get_session()
    existing = session.query(Watchlist).filter_by(stock_code=stock_code).first()
    if not existing:
        wl = Watchlist(stock_code=stock_code, stock_name=stock_name, category="临时分析")
        session.add(wl)
        session.commit()
    session.close()
    return run_super_workflow(
        [stock_code], progress_callback=progress_callback, abort_check=abort_check
    )


def _extract_vote_stats(final_state: dict) -> dict:
    stats: dict[str, Any] = {
        "buy": 0,
        "hold": 0,
        "sell": 0,
        "disagree": 0,
        "total": 0,
        "details": [],
    }
    decision = final_state.get("hedge_fund_decision", {})
    if isinstance(decision, dict):
        for code, vote in decision.items():
            if not isinstance(vote, dict):
                continue
            action = vote.get("action", "")
            stats["total"] += 1
            if "买入" in str(action):
                stats["buy"] += 1
            elif "卖出" in str(action):
                stats["sell"] += 1
            elif "分歧" in str(action):
                stats["disagree"] += 1
            else:
                stats["hold"] += 1
            if len(stats["details"]) < 20:
                stats["details"].append(
                    {
                        "code": code,
                        "name": vote.get("stock_name", ""),
                        "action": action,
                        "confidence": vote.get("confidence", 0),
                    }
                )
    return stats
