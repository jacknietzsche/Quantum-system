"""Node 4: AI Hedge Fund vote — AI对冲基金投委会 (含结构化多空辩论)"""

import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

from shared.models import get_session
from workflows.nodes._shared import HEDGE_FUND_ANALYSTS, logger
from workflows.state import AShareSuperState
from workflows.stubs import LLMCaller, TieredVoter, TokenBudget
from workflows.utils import AbortWorkflowException, check_abort

# ── 阵营划分 ──
_BULL_CAMP = {
    "warren_buffett",
    "charlie_munger",
    "peter_lynch",
    "phil_fisher",
    "mohnish_pabrai",
    "seth_klarman",
    "aswath_damodaran",
    "li_lu",
    "rakesh_jhunjhunwala",
}
_BEAR_CAMP = {
    "michael_burry",
    "nassim_taleb",
    "david_tepper",
    "george_soros",
    "jim_simons",
}
# 其余分析师为中立/灵活阵营


def _extract_camp_args(signals: dict, camp_keys: set, max_count: int = 3) -> list:
    """从某阵营分析师的信号中提取最有力的 top-N 论点"""
    args = []
    for k in camp_keys:
        sig = signals.get(k)
        if sig and sig.get("reasoning"):
            args.append(
                {
                    "analyst": sig["name"],
                    "style": sig.get("style", ""),
                    "recommendation": sig.get("recommendation", "持有"),
                    "confidence": sig.get("confidence", 0),
                    "reasoning": sig["reasoning"][:150],
                }
            )
    args.sort(key=lambda x: abs(x["confidence"]), reverse=True)
    return args[:max_count]


def _run_debate_judge(
    code: str, name: str, stock_signals: dict, stock_context: dict, llm_caller
) -> dict:
    """结构化多空辩论 — LLM 作为研究经理裁决

    流程:
      1. 提取多空阵营的 top 论点
      2. 构造辩论 prompt, LLM 一次性评估
      3. 输出裁决: 多空焦点 + 收敛/分歧 + 最终倾向
    """
    bull_args = _extract_camp_args(stock_signals, _BULL_CAMP)
    bear_args = _extract_camp_args(stock_signals, _BEAR_CAMP)

    def _fmt(args: list) -> str:
        lines = []
        for a in args:
            lines.append(
                f"  - [{a['style']}] {a['analyst']}: {a['recommendation']} "
                f"(置信度:{a['confidence']:.0%}) — {a['reasoning']}"
            )
        return "\n".join(lines) if lines else "  (无明确论点)"

    debate_prompt = (
        f"你是一位中立的投资研究经理, 需要裁决以下针对 {name}({code}) 的多空辩论。\n\n"
        f"## 看多方论点 (Bull Camp)\n{_fmt(bull_args)}\n\n"
        f"## 看空方论点 (Bear Camp)\n{_fmt(bear_args)}\n\n"
        f"请输出结构化裁决 (严格遵循以下格式, 不要额外内容):\n"
        f"<!-- DEBATE_JUDGE: {{\n"
        f'  "bull_strength": <0-100整数>,  /* 看多方论据充分程度 */\n'
        f'  "bear_strength": <0-100整数>,  /* 看空方论据充分程度 */\n'
        f'  "key_agreements": ["共识1", "共识2"],\n'
        f'  "key_disagreements": ["分歧1", "分歧2"],\n'
        f'  "unresolved_risks": ["未解决风险1"],\n'
        f'  "judge_tendency": "bullish|bearish|neutral",  /* 裁决者倾向 */\n'
        f'  "judge_confidence": <0-100整数>,\n'
        f'  "summary": "<一句话最终判断>"\n'
        f"}} -->"
    )
    try:
        raw = llm_caller.call(debate_prompt, temperature=0.3, max_tokens=1000)
        payload = _extract_tagged_json(raw, "DEBATE_JUDGE")
        if not payload:
            return {"debate_status": "parse_failed", "raw": raw[:300]}
        return {
            "debate_status": "success",
            "bull_strength": int(payload.get("bull_strength", 50)),
            "bear_strength": int(payload.get("bear_strength", 50)),
            "key_agreements": payload.get("key_agreements", []),
            "key_disagreements": payload.get("key_disagreements", []),
            "unresolved_risks": payload.get("unresolved_risks", []),
            "judge_tendency": payload.get("judge_tendency", "neutral"),
            "judge_confidence": int(payload.get("judge_confidence", 0)),
            "summary": payload.get("summary", ""),
        }
    except Exception as e:
        return {"debate_status": "error", "error": str(e)[:100]}


def _extract_tagged_json(text: str, tag: str) -> dict:
    """从 LLM 回复中提取 <!-- TAG: {...} --> 格式的 JSON"""
    pattern = rf"<!--\s*{re.escape(tag)}:\s*(\{{.*?\}})\s*-->"
    match = re.search(pattern, text, flags=re.DOTALL)
    if not match:
        return {}
    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError:
        return {}


def node_ai_hedge_fund_vote(state: AShareSuperState) -> dict:
    """第三层:AI对冲基金投票 + 结构化多空辩论"""
    logs = list(state.get("logs", []))
    list(state.get("errors", []))
    logs.append(f"[{datetime.now().strftime('%H:%M:%S')}] [投委会] 开始投票+辩论...")

    portfolio = state.get("portfolio", [])
    watchlist = state.get("watchlist", [])
    skill_outputs = state.get("skill_outputs", {})
    market_data = state.get("market_data", {})

    TokenBudget(max_tokens=50000)
    TieredVoter()
    selected_analysts = list(HEDGE_FUND_ANALYSTS.items())
    llm_caller = LLMCaller()

    context = {
        "market_data": market_data,
        "skill_outputs": {k: str(v)[:500] for k, v in skill_outputs.items()},
        "portfolio_summary": f"持仓{len(portfolio)}只" if portfolio else "空仓",
    }

    # 从 StockInfo 加载股票信息
    stock_info_map = {}
    try:
        from shared.models import StockInfo as _StockInfo

        _session = get_session()
        for info in _session.query(_StockInfo).all():
            stock_info_map[info.stock_code] = {
                "industry": info.industry,
                "pe": round(info.pe_ratio, 1) if info.pe_ratio else 0,
                "pb": round(info.pb_ratio, 2) if info.pb_ratio else 0,
                "roe": round(info.roe, 1) if info.roe else 0,
                "gross_margin": round(info.gross_margin, 1) if info.gross_margin else 0,
                "market_cap": round(info.total_market_cap, 0) if info.total_market_cap else 0,
                "ma5": info.ma5,
                "ma10": info.ma10,
                "ma20": info.ma20,
                "ma60": info.ma60,
                "rsi": round(info.rsi_14, 1) if info.rsi_14 else 50,
                "macd": round(info.macd, 4) if info.macd else 0,
                "volatility": round(info.volatility_20d, 1) if info.volatility_20d else 0,
                "max_dd": round(info.max_drawdown_60d, 1) if info.max_drawdown_60d else 0,
                "trend": info.trend or "未知",
                "alignment": info.ma_alignment or "未知",
            }
        _session.close()
    except Exception as _e:
        logger.warning("Stock info query failed: %s", _e)

    all_signals = {}
    all_decisions = {}

    all_targets = []
    seen = set()
    for h in portfolio:
        code = h.get("stock_code", "")
        if code and code not in seen:
            all_targets.append({"stock_code": code, "stock_name": h.get("stock_name", code)})
            seen.add(code)
    for w in watchlist:
        code = w.get("stock_code", "")
        if code and code not in seen:
            all_targets.append({"stock_code": code, "stock_name": w.get("stock_name", code)})
            seen.add(code)

    # ── 分析 + 辩论循环 ──
    debate_count = 0
    for stock in all_targets:
        code = stock.get("stock_code", "")
        name = stock.get("stock_name", "")
        if not code:
            continue

        try:
            check_abort(state)
        except AbortWorkflowException:
            logs.append(f"[{datetime.now().strftime('%H:%M:%S')}] [投委会] 用户中止")
            break

        si = stock_info_map.get(code, {})
        stock_context = {**context, "stock_code": code, "stock_name": name}
        if si:
            si_info = (
                f"行业:{si.get('industry', '')} PE:{si.get('pe', 0)} "
                f"PB:{si.get('pb', 0)} ROE:{si.get('roe', 0)}% "
                f"毛利率:{si.get('gross_margin', 0)}% "
                f"市值:{si.get('market_cap', 0)}亿 "
                f"MA5:{si.get('ma5', 0):.2f} MA20:{si.get('ma20', 0):.2f} "
                f"MA60:{si.get('ma60', 0):.2f} "
                f"RSI:{si.get('rsi', 50):.1f} MACD:{si.get('macd', 0):.4f} "
                f"波动率:{si.get('volatility', 0):.1f}% "
                f"回撤:{si.get('max_dd', 0):.1f}% "
                f"趋势:{si.get('trend', '未知')} "
                f"均线:{si.get('alignment', '未知')}"
            )
            stock_context["stock_info"] = si_info

        # 1. 并行分析师投票 (ThreadPoolExecutor + TieredVoter)
        stock_signals = _vote_analysts(code, name, stock_context, selected_analysts, state)

        # 2. 汇总投票
        votes = {}
        for sig in stock_signals.values():
            rec = sig["recommendation"]
            votes[rec] = votes.get(rec, 0) + 1
        winner = max(votes, key=votes.get) if votes else "持有"
        total = sum(votes.values())
        consistency = votes.get(winner, 0) / total if total > 0 else 0

        # 3. 结构化辩论 (仅在存在有意义分歧时触发)
        debate_record = {}
        if consistency < 0.80 and total >= 5:
            debate_record = _run_debate_judge(code, name, stock_signals, stock_context, llm_caller)
            if debate_record.get("debate_status") == "success":
                debate_count += 1
                # 根据辩论裁决调整一致性 — 法官高置信度时权重更高
                jc = debate_record.get("judge_confidence", 0)
                if debate_record.get("judge_tendency") in ("bullish", "bearish"):
                    adj = jc / 100.0 * 0.2  # 最多调整 20%
                    adj = adj if debate_record["judge_tendency"] == "bullish" else -adj
                    consistency = min(max(consistency + adj, 0), 1)

        all_signals[code] = stock_signals
        all_decisions[code] = {
            "stock_name": name,
            "winner": winner,
            "consistency": round(consistency, 2),
            "votes": votes,
            "analyst_count": len(stock_signals),
            "debate": debate_record if debate_record else None,
        }

    # 市场级判断
    market_vote = _market_judge(context, llm_caller)

    hedge_fund_decision = {
        "market_decision": market_vote.get("winner", "维持"),
        "market_consistency": market_vote.get("consistency", 0),
        "stock_decisions": all_decisions,
        "analyst_count": len(selected_analysts),
        "analyzed_targets": len(all_targets),
        "debate_count": debate_count,
        "timestamp": datetime.now().isoformat(),
    }

    logs.append(
        f"[{datetime.now().strftime('%H:%M:%S')}] "
        f"[投委会] 投票完成: 市场={hedge_fund_decision['market_decision']}, "
        f"辩论={debate_count}/{len(all_decisions)}只股票, "
        f"分析={len(all_decisions)}只"
    )

    return {
        "hedge_fund_decision": hedge_fund_decision,
        "hedge_fund_signals": all_signals,
        "logs": logs,
    }


def _vote_analysts(code, name, stock_context, selected_analysts, state):
    """并行执行所有分析师投票"""
    stock_signals = {}
    max_workers = min(10, len(selected_analysts))

    def _vote_one(analyst_key, analyst_info):
        question = (
            f"作为{analyst_info['name']}({analyst_info['style']}),"
            f"请分析 {name}({code})。{analyst_info['prompt']}"
        )
        try:
            caller = LLMCaller()
            raw = caller.call(
                question,
                system_prompt=(
                    '请以 JSON 格式输出: {"recommendation": "买入|卖出|持有|分歧", '
                    '"confidence": 0.0-1.0, "reasoning": "<理由>"}'
                ),
                temperature=0.7,
                max_tokens=800,
            )
            result = _parse_vote_result(raw)
            return analyst_key, {
                "name": analyst_info["name"],
                "style": analyst_info["style"],
                "recommendation": result.get("recommendation", "持有"),
                "confidence": result.get("confidence", 0.5),
                "reasoning": result.get("reasoning", "")[:200],
            }
        except Exception as e:
            return analyst_key, {
                "name": analyst_info["name"],
                "style": analyst_info["style"],
                "recommendation": "持有",
                "confidence": 0.3,
                "reasoning": f"分析失败: {str(e)[:100]}",
            }

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_vote_one, k, v): k for k, v in selected_analysts}
        for future in as_completed(futures):
            key, signal = future.result()
            stock_signals[key] = signal
    return stock_signals


def _parse_vote_result(raw: str) -> dict:
    """从 LLM 回复中解析 JSON 投票结果"""
    # 尝试提取 JSON 块
    m = re.search(r'\{[^{}]*"recommendation"[^{}]*\}', raw, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    # 退化为关键词匹配
    rec = "持有"
    if "买入" in raw or "看多" in raw or "建议买" in raw:
        rec = "买入"
    elif "卖出" in raw or "看空" in raw or "建议卖" in raw:
        rec = "卖出"
    elif "分歧" in raw or "观望" in raw or "中性" in raw:
        rec = "分歧"
    return {"recommendation": rec, "confidence": 0.6, "reasoning": raw[:150]}


def _market_judge(context: dict, llm_caller) -> dict:
    """市场级整体判断"""
    prompt = (
        f"基于当前A股市场环境:\n"
        f"指数数据: {str(context.get('market_data', {}).get('indices', {}))[:300]}\n"
        f"持仓概况: {context.get('portfolio_summary', '空仓')}\n\n"
        f"请给出整体仓位建议(加仓/维持/减仓/空仓),"
        f'JSON格式: {{"winner": "...", "consistency": 0-100}}'
    )
    try:
        raw = llm_caller.call(prompt, temperature=0.3, max_tokens=500)
        m = re.search(r'\{[^{}]*"winner"[^{}]*\}', raw, re.DOTALL)
        if m:
            result = json.loads(m.group(0))
            return {
                "winner": result.get("winner", "维持"),
                "consistency": int(result.get("consistency", 50)),
            }
    except Exception as _e:
        logger.warning("Vote result failed: %s", _e)
    return {"winner": "维持", "consistency": 50}
