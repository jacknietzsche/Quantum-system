"""Node 2: Skill parallel analysis — 25+ Skill并行分析"""

import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from skills import skill_registry
from workflows.nodes._shared import _log
from workflows.state import AShareSuperState
from workflows.utils import AbortWorkflowException, check_abort


def node_skill_analysis_parallel(state: AShareSuperState) -> dict:
    """第二层:25+ Skill并行分析"""
    logs = list(state.get("logs", []))
    list(state.get("errors", []))
    logs.append(_log(state, "🔬 [第二层] 25+ Skill并行分析启动..."))

    portfolio = state.get("portfolio", [])
    watchlist = state.get("watchlist", [])
    market_data = state.get("market_data", {})

    # 确定分析目标(持仓 + 自选)
    targets = []
    seen = set()
    for h in portfolio:
        if h["stock_code"] not in seen:
            targets.append(h)
            seen.add(h["stock_code"])
    for w in watchlist:
        if w["stock_code"] not in seen:
            targets.append(w)
            seen.add(w["stock_code"])

    skill_outputs = {}
    skill_stats = {"success": 0, "failed": 0, "skipped": 0, "elapsed": 0}
    start_time = time.time()

    def run_single_skill(skill_name: str, context: dict) -> tuple:
        try:
            result = skill_registry.execute(skill_name, context)
            return skill_name, result
        except Exception as e:
            return skill_name, {"error": str(e)}

    # 每批执行完后,结果注入下一批的 context(peer_outputs)
    data_skills = ["a_share_data", "fund_flow", "risk_alert", "technical_analysis"]
    analysis_skills = [
        "buffett",
        "munger",
        "taleb",
        "graham",
        "howard_marks",
        "financial_health",
        "news_sentiment",
        "quant_factor",
        "china_stock_research",
        "trading_agents_ashare",
    ]
    global_skills = ["zhou_jintao", "convertible_bond", "etf_rotation", "strategy_evaluation"]

    batches = [
        ("数据型Skill", data_skills),
        ("分析型Skill", analysis_skills),
        ("全局Skill", global_skills),
    ]

    peer_outputs = {}

    for _batch_name, batch_skills in batches:
        check_abort(state)  # 每批开始前检查中止

        batch_futures = []
        with ThreadPoolExecutor(max_workers=6) as executor:
            for target in targets:
                context = {
                    "stock_code": target.get("stock_code", ""),
                    "stock_name": target.get("stock_name", ""),
                    "market_data": market_data,
                    "portfolio": portfolio,
                    "peer_outputs": peer_outputs,  # 注入前批结果
                }
                for skill_name in batch_skills:
                    batch_futures.append(executor.submit(run_single_skill, skill_name, context))

            for future in as_completed(batch_futures):
                # 每个Future完成后检查中止
                try:
                    check_abort(state)
                except AbortWorkflowException:
                    # 取消剩余未完成的 futures
                    for f in batch_futures:
                        f.cancel()
                    executor.shutdown(wait=False)
                    raise

                skill_name, result = future.result()
                if result and "error" not in result:
                    skill_stats["success"] += 1
                    if skill_name not in skill_outputs:
                        skill_outputs[skill_name] = []
                    skill_outputs[skill_name].append(result)
                    # 将结构化结果注入下一批
                    if isinstance(result, dict) and result.get("status") == "analyzed":
                        peer_outputs[skill_name] = result
                else:
                    skill_stats["failed"] += 1

    skill_stats["elapsed"] = round(time.time() - start_time, 2)

    logs.append(
        _log(
            state,
            f"✅ Skill分析完成: 成功{skill_stats['success']}, "
            f"失败{skill_stats['failed']}, 耗时{skill_stats['elapsed']}s",
        )
    )

    return {"skill_outputs": skill_outputs, "skill_stats": skill_stats, "logs": logs}
