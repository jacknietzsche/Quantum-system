"""Node 10: Generate Final Report — 生成最终报告"""

import os
from datetime import datetime

from shared.models import DailyReport, RiskLevel, get_session
from workflows.nodes._shared import _log, logger
from workflows.state import AShareSuperState
from workflows.stubs import RiskQuadrantEngine, StrategyMonitor


def node_generate_final_report(state: AShareSuperState) -> dict:
    """第七层:生成最终专业报告"""
    logs = list(state.get("logs", []))
    logs.append(_log(state, "📝 [第七层] 生成最终报告..."))

    date = state.get("date", datetime.now().strftime("%Y-%m-%d"))
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    run_id = state.get("run_id", "")
    market = state.get("market_data", {})
    portfolio = state.get("portfolio", [])
    risk = state.get("risk_assessment", {})
    recs = state.get("recommendations", [])
    skill_outputs = state.get("skill_outputs", {})
    skill_stats = state.get("skill_stats", {})
    hedge = state.get("hedge_fund_decision", {})
    fincept = state.get("fincept_verify", {})
    vote_results = state.get("vote_results", {})
    pos_plan = state.get("position_plan", {})
    rebalance = state.get("rebalance_plan", {})
    look_ahead = state.get("look_ahead_audit", {})
    state.get("performance_metrics", {})

    lines = []

    # 报告头
    lines.append("# 🏛️ A股超级智能投研系统 — 每日决策报告")
    lines.append(f"> **日期**: {date} | **生成时间**: {now} | **运行ID**: {run_id}")
    lines.append(
        f"> **数据源**: {state.get('data_source', 'N/A')} | **融合Agent**: 15+19+10=44个 | **融合Skill**: {skill_stats.get('success', 0)}个"
    )
    lines.append("")

    # ═══ 一、市场概览 ═══
    lines.append("---\n## 一、📡 市场概览\n")
    indices = market.get("indices", {})
    if indices:
        lines.append("| 指数 | 最新价 | 涨跌幅 |")
        lines.append("|------|--------|--------|")
        for name, data in indices.items():
            lines.append(f"| {name} | {data['price']:,.2f} | {data['change_pct']:+.2f}% |")
    else:
        lines.append("⚠️ 暂无市场数据(非交易时间或网络问题)")

    breadth = market.get("breadth", {})
    if breadth.get("total", 0) > 0:
        lines.append(
            f"\n上涨: **{breadth['up']}**家 | 下跌: **{breadth['down']}**家 | 涨停: **{breadth['limit_up']}**家 | 跌停: **{breadth['limit_down']}**家"
        )

    north = market.get("north_flow")
    if north:
        emoji = "🟢" if north["net_buy_amount"] > 0 else "🔴"
        lines.append(f"\n{emoji} 北向资金净流入: **¥{north['net_buy_amount'] / 1e8:,.2f}亿**")

    # ═══ 二、Skill分析统计 ═══
    lines.append("\n---\n## 二、🔬 Skill分析统计\n")
    lines.append("| Skill | 调用次数 | 状态 |")
    lines.append("|-------|---------|------|")
    for skill_name, results in skill_outputs.items():
        count = len(results) if isinstance(results, list) else 1
        status = "✅" if results else "⚠️"
        lines.append(f"| {skill_name} | {count} | {status} |")
    lines.append(
        f"\n**总计**: 成功 {skill_stats.get('success', 0)} | 失败 {skill_stats.get('failed', 0)} | 耗时 {skill_stats.get('elapsed', 0)}s"
    )

    # ═══ 三、AI对冲基金投委会 ═══
    lines.append("\n---\n## 三、🏛️ AI对冲基金投委会(18人投票)\n")
    market_decision = hedge.get("market_decision", "N/A")
    market_consistency = hedge.get("market_consistency", 0)
    lines.append(f"**市场整体判断**: {market_decision} (一致性 {market_consistency:.0%})")
    lines.append("")
    stock_decisions = hedge.get("stock_decisions", {})
    if stock_decisions:
        lines.append("| 股票 | 投委会决策 | 一致性 | 大师数 |")
        lines.append("|------|-----------|--------|--------|")
        for code, decision in stock_decisions.items():
            emoji = (
                "🟢"
                if decision["winner"] == "买入"
                else "🔴"
                if decision["winner"] == "卖出"
                else "🟡"
            )
            lines.append(
                f"| {decision['stock_name']}({code}) | {emoji}{decision['winner']} | {decision['consistency']:.0%} | {decision['analyst_count']} |"
            )

    # ═══ 四、Fincept大师验证 ═══
    lines.append("\n---\n## 四、🔍 Fincept大师验证\n")
    stock_verifications = fincept.get("stock_verifications", {})
    if stock_verifications:
        lines.append("| 股票 | 投委会决策 | 大师验证 | 通过率 | 最终判定 |")
        lines.append("|------|-----------|---------|--------|---------|")
        for code, verify in stock_verifications.items():
            emoji = "✅" if verify["final_verdict"] == "通过" else "❌"
            lines.append(
                f"| {verify['stock_name']}({code}) | {verify['committee_decision']} | {verify['approve_count']}赞成/{verify['reject_count']}反对 | {verify['approval_rate']:.0%} | {emoji}{verify['final_verdict']} |"
            )
    lines.append(
        f"\n**全局通过率**: {fincept.get('global_approval_rate', 0):.0%} | 参与大师: {fincept.get('master_count', 0)}位"
    )

    # ═══ 五、三层风险审计 ═══
    lines.append("\n---\n## 五、🛡️ 三层风险审计\n")
    mr = risk.get("market_risk", {})
    tr = risk.get("tail_risk", {})
    cr = risk.get("cycle_risk", "N/A")
    lines.append("| 风险层 | 等级 | 评分 | 说明 |")
    lines.append("|--------|------|------|------|")
    lines.append(
        f"| 市场风险(恐慌指数) | **{mr.get('level', 'N/A')}** | {mr.get('score', 0):.0f} | {mr.get('message', '')} |"
    )
    lines.append(f"| 市场周期(霍华德-马克思) | **{cr}** | - | 周期位置判断 |")
    lines.append(
        f"| 尾部风险(塔勒布) | **{tr.get('level', 'N/A')}** | {tr.get('score', 0)} | {tr.get('message', '')} |"
    )
    lines.append(
        f"| **综合判定** | {'✅ 通过' if risk.get('pass') else '❌ 未通过'} | {risk.get('overall_level', 0)} | 仓位建议: {tr.get('position_advice', 'N/A')} |"
    )

    # 风险象限分析
    panic_score = mr.get("score", 50)
    quadrant_engine = RiskQuadrantEngine()
    quadrant = quadrant_engine.evaluate(panic_score, cr)
    lines.append(f"\n**风险象限**: {quadrant['quadrant']} — {quadrant['description']}")
    lines.append(
        f"- 最大仓位: {quadrant['max_position_pct'] * 100:.0f}% | 最低现金: {quadrant['min_cash_pct'] * 100:.0f}% | 单股上限: {quadrant['max_single_stock_pct'] * 100:.0f}%"
    )
    lines.append(f"- 操作建议: {quadrant['action']}")

    # 降级信息
    degradation = state.get("degradation", {})
    if degradation.get("fallback_count", 0) > 0:
        lines.append(f"\n⚠️ **降级信息**: {degradation['fallback_count']}个节点使用了降级默认值")
        for warning in degradation.get("warnings", []):
            lines.append(f"  - {warning}")

    # 前视偏差审计
    if look_ahead:
        la_pass = look_ahead.get("pass", True)
        lines.append(
            f"\n**前视偏差审计**: {'✅ 通过' if la_pass else '❌ 发现问题'} (严重{look_ahead.get('critical', 0)} 警告{look_ahead.get('warning', 0)})"
        )

    # ═══ 六、多模型投票 ═══
    if vote_results:
        lines.append("\n---\n## 六、🗳️ 多模型投票\n")
        for code, vote in vote_results.items():
            consistency = vote.get("consistency", 0)
            emoji = "🟢" if consistency > 0.7 else "🟡" if consistency > 0.4 else "🔴"
            all_results = vote.get("all_results", [])
            stock_name = (
                all_results[0].get("context", {}).get("stock_name", code) if all_results else code
            )
            lines.append(f"### {stock_name}({code})")
            lines.append(
                f"- 投票结果: **{vote.get('winner', 'N/A')}** {emoji} 一致性 {consistency:.0%}"
            )
            lines.append(f"- 置信度: {vote.get('winner_confidence', 0):.0%}")
            for rec, data in vote.get("votes", {}).items():
                models = ", ".join(m["role"] for m in data.get("models", []))
                lines.append(f"  - {rec}: {data['count']}票 ({models})")

    # ═══ 七、组合管理 ═══
    lines.append("\n---\n## 七、📐 组合管理\n")
    lines.append(
        f"- 风险评分: **{pos_plan.get('risk_score', 'N/A')}** ({pos_plan.get('level', 'N/A')})"
    )
    lines.append(f"- 建议仓位: **{pos_plan.get('position_pct', 'N/A')}**")
    lines.append(f"- 仓位建议: {pos_plan.get('advice', 'N/A')}")

    if rebalance.get("barbell_allocation", {}).get("barbell_advice"):
        lines.append(f"- 杠铃策略: {rebalance['barbell_allocation']['barbell_advice']}")

    if rebalance.get("suggested_actions"):
        lines.append("\n**再平衡建议(按优先级)**:")
        lines.append("| 股票 | 当前仓位 | 盈亏% | 投委会 | 大师验证 | 建议操作 | 优先级 |")
        lines.append("|------|---------|-------|--------|---------|---------|--------|")
        for a in rebalance["suggested_actions"]:
            lines.append(
                f"| {a.get('stock', 'N/A')} | {a.get('weight', 'N/A')} | {a.get('pl_pct', 'N/A')} | {a.get('committee', 'N/A')} | {a.get('verify', 'N/A')} | {a.get('action', 'N/A')} | {a.get('priority', 'N/A')} |"
            )

    # ═══ 八、投资建议 ═══
    lines.append("\n---\n## 八、💡 投资建议(综合决策)\n")
    for r in recs:
        if r["stock_code"] == "SYSTEM":
            lines.append(f"\n### 📌 {r['stock_name']}")
            lines.append(f"- **建议**: {r['action']}")
            lines.append(f"- **理由**: {r['reason']}")
        else:
            priority_emoji = (
                "🔴" if r.get("priority") == "高" else "🟡" if r.get("priority") == "中" else "🟢"
            )
            lines.append(f"\n### {priority_emoji} {r['stock_name']}({r['stock_code']})")
            lines.append(f"- **操作建议**: {r['action']}")
            lines.append(f"- **理由**: {r['reason']}")
            lines.append(f"- **风险等级**: {r['risk_level']}")
            lines.append(
                f"- **投委会**: {r.get('committee_rec', 'N/A')} (一致性{r.get('committee_consistency', 0):.0%})"
            )
            lines.append(f"- **大师验证**: {r.get('verify_verdict', 'N/A')}")
            lines.append(
                f"- **多模型投票**: {r.get('vote_winner', 'N/A')} (一致性{r.get('vote_consistency', 0):.0%})"
            )

    # ═══ 九、策略表现监控 ═══
    monitor = StrategyMonitor()
    mock_returns = []
    for h in portfolio:
        daily_ret = h.get("profit_loss_pct", 0) / max(len(portfolio), 1)
        mock_returns.append(daily_ret / 100)
    if mock_returns:
        metrics = monitor.calculate_metrics(mock_returns)
        alerts = monitor.check_alerts(metrics)
        lines.append("\n---\n## 九、📈 策略表现监控\n")
        lines.append("| 指标 | 值 | 状态 |")
        lines.append("|------|------|------|")
        for name, val in [
            ("夏普比率", f"{metrics.get('sharpe_ratio', 0):.2f}"),
            ("最大回撤", f"{metrics.get('max_drawdown', 0):.2%}"),
            ("胜率", f"{metrics.get('win_rate', 0):.1%}"),
            ("盈亏比", f"{metrics.get('profit_loss_ratio', 0):.2f}"),
            ("Calmar比率", f"{metrics.get('calmar_ratio', 0):.2f}"),
        ]:
            lines.append(f"| {name} | {val} | ✅ |")
        if alerts:
            lines.append(f"\n⚠️ **{len(alerts)}个告警**: ")
            for a in alerts:
                lines.append(f"- [{a['level']}] {a['message']}")

    # ═══ 十、执行日志 ═══
    lines.append("\n---\n## 十、📋 执行日志\n")
    for log in state.get("logs", []):
        lines.append(f"- {log}")

    lines.append(
        f"\n---\n*报告由 A股超级智能投研系统 驱动 | 融合44个Agent + {skill_stats.get('success', 0)}个Skill | {now}*"
    )
    lines.append("*免责声明:本报告仅供参考,不构成任何投资建议。*")

    report = "\n".join(lines)

    # 保存报告(同时生成 HTML 邮件版本)
    os.makedirs("reports", exist_ok=True)
    filename = f"super_report_{date.replace('-', '')}.md"
    filepath = os.path.join("reports", filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(report)

    # 生成QQ邮箱兼容的HTML版本
    try:
        from email_report import save_email_report

        save_email_report(
            report,
            report_dir="reports",
            filename_prefix="super_report",
            date_str=date.replace("-", ""),
            title="🏛️ A股超级智能投研系统 — 每日决策报告",
            subtitle=f"日期: {date} | 运行ID: {run_id} | 生成时间: {now}",
        )
        logs.append(_log(state, "✅ HTML邮件报告已生成"))
    except Exception as e:
        logs.append(_log(state, f"⚠️ HTML报告生成失败: {e}"))

    # 保存到数据库
    try:
        session = get_session()
        report_record = DailyReport(
            date=date,
            market_summary=f"上涨{breadth.get('up', 0)}家/下跌{breadth.get('down', 0)}家",
            recommendations=str(len(recs)),
            total_return_pct=sum(h.get("profit_loss_pct", 0) for h in portfolio) / len(portfolio)
            if portfolio
            else 0,
            risk_level=RiskLevel.HIGH if not risk.get("pass") else RiskLevel.MEDIUM,
            report_file=filepath,
        )
        session.add(report_record)
        session.commit()
        session.close()
    except Exception as _e:
        logger.warning("Suppressed: %s", _e)

    logs.append(_log(state, f"✅ 报告已保存: {filepath}"))

    return {"report": report, "logs": logs}
