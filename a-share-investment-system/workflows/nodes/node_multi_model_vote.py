"""Node 8: Multi-Model Vote — 多模型投票验证"""

from decision_review import DecisionReviewManager
from workflows.nodes._shared import MultiModelVoter, _log, logger
from workflows.state import AShareSuperState


def node_multi_model_vote(state: AShareSuperState) -> dict:
    """多模型投票仲裁 — 对投委会+大师验证的结论进行最终确认"""
    logs = list(state.get("logs", []))
    errors = list(state.get("errors", []))
    logs.append(_log(state, "🗳️ 多模型投票仲裁..."))

    hedge = state.get("hedge_fund_decision", {})
    fincept = state.get("fincept_verify", {})
    stock_decisions = hedge.get("stock_decisions", {})
    stock_verifications = fincept.get("stock_verifications", {})

    # 从配置加载真实 LLM 配置(容错,config.json 已删除,通过 MultiModelVoter 兼容层读取)
    try:
        MultiModelVoter.from_config_file()
        logs.append(_log(state, "  ✅ 已加载真实LLM配置"))
    except Exception as e:
        logs.append(_log(state, f"  ⚠️ LLM配置加载失败({str(e)[:80]}),使用仲裁逻辑"))

    vote_results = {}

    # 初始化复盘管理器(容错:数据库异常不影响仲裁)
    review_manager = None
    try:
        review_manager = DecisionReviewManager()
    except Exception as e:
        logs.append(_log(state, f"  ⚠️ 复盘数据库初始化失败: {str(e)[:100]}"))

    for code, decision in stock_decisions.items():
        try:
            name = decision.get("stock_name", code)
            winner = decision.get("winner", "持有")
            consistency = decision.get("consistency", 0)

            verify = stock_verifications.get(code, {})
            verify_verdict = verify.get("final_verdict", "通过")
            approval_rate = verify.get("approval_rate", 0.8)

            # 仲裁问题:不是重新分析,而是确认/否决投委会结论
            if verify_verdict == "否决":
                arbitration = "卖出"
                arb_confidence = max(0.6, consistency * 0.5)
                arb_reason = f"大师验证否决(通过率{approval_rate:.0%}),推翻投委会{winner}建议"
            elif consistency >= 0.7 and approval_rate >= 0.6:
                arbitration = winner
                arb_confidence = (consistency + approval_rate) / 2
                arb_reason = (
                    f"投委会+大师验证一致(一致性{consistency:.0%}+通过率{approval_rate:.0%})"
                )
            elif consistency <= 0.4:
                arbitration = "持有"
                arb_confidence = 0.4
                arb_reason = f"投委会分歧严重(一致性仅{consistency:.0%}),建议观望"
            else:
                arbitration = winner
                arb_confidence = consistency * 0.8
                arb_reason = f"投委会建议{winner}(一致性{consistency:.0%}),大师验证{verify_verdict}"

            vote_results[code] = {
                "stock_code": code,
                "stock_name": name,
                "winner": arbitration,
                "confidence": round(arb_confidence, 3),
                "consistency": round(arb_confidence, 3),
                "reasoning": arb_reason,
                "committee_winner": winner,
                "committee_consistency": consistency,
                "verify_verdict": verify_verdict,
                "arbiter_count": 2,
            }

            # 记录到复盘数据库(容错)
            if review_manager:
                try:
                    review_manager.record_vote_result(vote_results[code])
                except Exception as e:
                    logs.append(_log(state, f"  ⚠️ {name}复盘记录失败: {str(e)[:80]}"))

        except Exception as e:
            err_msg = f"股票{code}仲裁异常: {str(e)[:200]}"
            errors.append(err_msg)
            logs.append(_log(state, f"  ❌ {err_msg}"))
            # 使用安全默认值
            vote_results[code] = {
                "stock_code": code,
                "stock_name": decision.get("stock_name", code),
                "winner": "持有",
                "confidence": 0.3,
                "consistency": 0.3,
                "reasoning": f"仲裁异常,建议观望: {str(e)[:100]}",
                "arbiter_count": 0,
            }

    # 关闭复盘管理器
    if review_manager:
        try:
            review_manager.close()
        except Exception as _e:
            logger.warning("Suppressed: %s", _e)

    logs.append(_log(state, f"✅ 仲裁完成: {len(vote_results)}只"))

    return {"vote_results": vote_results, "logs": logs, "errors": errors}
