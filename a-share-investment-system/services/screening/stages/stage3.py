"""Stage3: 深度分析 — 从 stock_screener.py 拆分

包含:
- stage3_deep_analyze: 标准深度分析 (QuantAnalyzers)
- stage3_master_analyze: Master Agent 增强分析
- compute_master_factors: 从 Master Agent 结果提取因子
"""

from __future__ import annotations

from typing import Any

from shared.logging import emit_log


def stage3_deep_analyze(
    candidates: list[dict],
    config: Any,
    market_regime: str = "NEUTRAL",
) -> list[dict]:
    """标准 Stage3: QuantAnalyzers (Buffett/Graham/Lynch/Taleb) 打分

    Args:
        candidates: Stage2 通过的候选股
        config: Stage3Config 数据类
        market_regime: 市场状态
    """
    from services.quant_analyzers import QuantAnalyzers

    qa = QuantAnalyzers()
    results = []

    for stock in candidates[: config.deep_top]:
        code = stock.get("stock_code", "")
        financials = _extract_financials(stock)

        try:
            buffett = qa.buffett_analyze(code, financials)
            graham = qa.graham_analyze(code, financials)
            lynch = qa.lynch_analyze(code, financials)
            taleb = qa.taleb_analyze(code, financials)

            w = config.weights
            composite = (
                buffett["score"] * w.get("buffett", 0.35)
                + graham["score"] * w.get("graham", 0.20)
                + lynch["score"] * w.get("lynch", 0.25)
                + taleb["score"] * w.get("taleb", 0.20)
            )
        except Exception as e:
            emit_log("WARNING", "screening", f"Stage3 异常 {code}: {e}")
            composite = 50

        signal = "买入" if composite >= 60 else ("持有" if composite >= 40 else "观望")
        results.append(
            {
                "rank": 0,
                "stock_code": code,
                "stock_name": stock.get("stock_name", ""),
                "score": round(composite, 0),
                "industry": stock.get("industry", ""),
                "pe": stock.get("pe", 0),
                "roe": stock.get("roe", 0),
                "signal": signal,
                "price": stock.get("price", stock.get("latest_price", 0)),
                "change_pct": stock.get("change_pct", 0),
                "turnover_rate": stock.get("turnover_rate", 0),
                "volume_ratio": stock.get("volume_ratio", 0),
            }
        )

    results.sort(key=lambda x: x.get("score", 0), reverse=True)
    for i, r in enumerate(results):
        r["rank"] = i + 1

    emit_log("INFO", "screening", f"Stage3: {len(candidates)} -> {len(results)}")
    return results


def stage3_master_analyze(
    candidates: list[dict],
    config: Any,
    market_regime: str = "NEUTRAL",
) -> list[dict]:
    """增强 Stage3: Master Agent 打分 (limit_up/momentum 风格)

    使用配置中指定的 master_agents 列表进行分析。
    """
    from services.master_agents import get_master_agents

    if not config.master_agents:
        return stage3_deep_analyze(candidates, config, market_regime)

    agents = get_master_agents()
    weights = _get_agent_weights(config.master_agents)
    results = []

    for stock in candidates[: config.deep_top]:
        code = stock.get("stock_code", "")
        financials = _extract_financials(stock)

        try:
            master_results = agents.analyze_selected(
                stock_code=code,
                financials=financials,
                agent_names=config.master_agents,
            )
            total_score = 0
            for i, mr in enumerate(master_results):
                if mr and "score" in mr:
                    total_score += mr.get("score", 50) * weights[i]
        except Exception as e:
            emit_log("WARNING", "screening", f"Stage3 master 异常 {code}: {e}")
            total_score = 50
            master_results = []

        _signal = "买入" if total_score >= 70 else ("持有" if total_score >= 50 else "观望")
        stock["_stage3_master_score"] = total_score
        stock["_stage3_masters"] = master_results
        results.append(stock)

    results.sort(key=lambda x: x.get("_stage3_master_score", 0), reverse=True)
    emit_log("INFO", "screening", f"Stage3 master: {len(candidates)} -> {len(results)}")
    return results[: config.deep_top]


def compute_master_factors(candidates: list[dict]) -> dict[str, float]:
    """从 Stage3 候选股的 Master Agent 结果中提取权重/仓位因子。"""
    if not candidates:
        return {"master_weight_factor": 1.0, "master_position_factor": 1.0}

    all_signals = []
    all_scores = []

    for c in candidates:
        masters = c.get("_stage3_masters", [])
        for m in masters:
            if isinstance(m, dict) and "score" in m:
                all_scores.append(m["score"])
                all_signals.append(m.get("signal", "neutral"))

        if not masters:
            all_scores.append(c.get("score", 50))
            sig = c.get("signal", "")
            all_signals.append(
                "bullish" if sig in ("买入",) else ("bearish" if sig in ("卖出",) else "neutral")
            )

    n = len(all_signals) or 1
    bull = sum(1 for s in all_signals if s in ("bullish", "看多"))
    bear = sum(1 for s in all_signals if s in ("bearish", "看空"))
    avg_score = sum(all_scores) / len(all_scores) if all_scores else 50
    direction_ratio = (bull - bear) / n

    weight_factor = max(
        0.70, min(1.30, 1.0 + 0.30 * direction_ratio + 0.15 * ((avg_score - 50) / 50))
    )
    position_factor = max(
        0.80, min(1.20, 1.0 + 0.25 * direction_ratio + 0.10 * ((avg_score - 50) / 50))
    )

    return {
        "master_weight_factor": round(weight_factor, 4),
        "master_position_factor": round(position_factor, 4),
    }


def _extract_financials(stock: dict) -> dict:
    """从股票数据中提取财务指标"""
    return {
        "roe": stock.get("roe", 0),
        "pe_ratio": stock.get("pe", 0),
        "pb_ratio": stock.get("pb", 0),
        "price": stock.get("price", stock.get("latest_price", 1)),
        "gross_margin": stock.get("gross_margin", 30),
        "debt_to_equity": stock.get("debt_to_equity", 50),
        "eps": stock.get("eps", 1),
        "bvps": stock.get("bvps", 10),
        "earnings_growth_3y": stock.get("earnings_growth_3y", 0),
        "revenue_growth_3y": stock.get("revenue_growth_3y", 0),
        "cash_to_assets": stock.get("cash_ratio", 0),
        "current_assets": stock.get("current_assets", 0),
        "total_liabilities": stock.get("total_liabilities", 0),
        "turnover_rate": stock.get("turnover_rate", 0),
        "daily_volume_ratio": stock.get("volume_ratio", stock.get("daily_volume_ratio", 0)),
        "change_pct": stock.get("change_pct", 0),
    }


def _get_agent_weights(agent_names: list[str]) -> list[float]:
    """获取 Master Agent 权重 (等权分配)"""
    n = len(agent_names)
    if n == 0:
        return []
    return [1.0 / n] * n
