"""Node 3: Debate committee — 多空辩论委员会"""

from workflows.nodes._shared import _log
from workflows.state import AShareSuperState
from workflows.stubs import get_services


def node_debate_committee(state: AShareSuperState) -> dict:
    """节点:多空辩论委员会"""
    logs = list(state.get("logs", []))
    logs.append(_log(state, "⚔️ [辩论] 多空辩论委员会启动..."))

    services = get_services()
    if not services.is_ready("debate_engine"):
        logs.append(_log(state, "⏭️ DebateEngine未就绪,跳过辩论"))
        return {"logs": logs}

    portfolio = state.get("portfolio", [])
    market_data = state.get("market_data", {})
    perception = market_data.get("_perception", {})
    skill_outputs = state.get("skill_outputs", {})

    debate_results = {}
    debate_stats = {"bull_wins": 0, "bear_wins": 0, "hold": 0, "low_info_count": 0}

    for h in portfolio:
        code = h.get("stock_code", "")
        name = h.get("stock_name", "")

        stock_reports = []
        for _skill_name, results in skill_outputs.items():
            items = results if isinstance(results, list) else [results]
            for r in items:
                if isinstance(r, dict) and r.get("stock_code") == code:
                    stock_reports.append(r)

        result = services.debate_engine.run_debate(
            stock_code=code,
            analyst_reports=stock_reports,
            market_context={
                "stock_name": name,
                "regime": perception.get("regime", "NEUTRAL"),
                "pe": 0,
                "roe": 0,
                "industry": "",
                "pl_pct": h.get("profit_loss_pct", 0),
            },
            max_rounds=2,
        )

        debate_results[code] = result.data
        verdict = result.data.get("verdict", "持有")
        if verdict == "买入":
            debate_stats["bull_wins"] += 1
        elif verdict == "卖出":
            debate_stats["bear_wins"] += 1
        else:
            debate_stats["hold"] += 1
        if result.data.get("low_information_debate"):
            debate_stats["low_info_count"] += 1

        logs.append(
            _log(
                state,
                f"  {name}({code}): {verdict} "
                f"(置信度{result.data.get('confidence', 0):.0%}, "
                f"声明{len(result.data.get('claims', []))}个, "
                f"来源重合{result.data.get('source_overlap_ratio', 0):.0%})",
            )
        )

    logs.append(
        _log(
            state,
            f"✅ 辩论完成: 买入{debate_stats['bull_wins']} 卖出{debate_stats['bear_wins']} "
            f"持有{debate_stats['hold']} 低信息增量{debate_stats['low_info_count']}",
        )
    )

    return {"logs": logs, "debate_results": debate_results}
