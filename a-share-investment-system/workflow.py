"""
A股智能投资系统 - LangGraph 编排层(第二阶段增强版)
统一投资决策工作流:数据获取 → 并行分析 → 多模型投票 → 风控审计 → 动态仓位 → 决策生成 → 报告输出
"""

import contextlib
import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

from decision_review import DecisionReviewManager, PositionManager
from multi_model_voter import MultiModelVoter
from services.data_bus import DatabaseBackedDataBus as DataBus
from shared.models import DailyReport, Portfolio, RiskLevel, TradeStatus, get_session
from skills import RiskFirewall, register_all_skills, skill_registry
from workflows.stubs import StrategyMonitor

#  工作流状态定义


class InvestmentState(TypedDict):
    """投资决策工作流的全局状态"""

    date: str
    timestamp: str
    # 数据层
    market_data: dict[str, Any]
    portfolio: list[dict[str, Any]]
    # 分析层(并行产出)
    analysis_results: dict[str, Any]
    # 多模型投票
    vote_results: dict[str, Any]
    # 风控层
    risk_assessment: dict[str, Any]
    risk_pass: bool
    # 动态仓位
    position_plan: dict[str, Any]
    # 决策层
    recommendations: list[dict[str, Any]]
    # 报告
    report: str
    # 元信息
    errors: list[str]
    logs: list[str]


#  工作流节点实现


def create_data_bus() -> DataBus:
    return DataBus(db_path="data/investment.db")


def node_fetch_data(state: InvestmentState) -> InvestmentState:
    """节点1:数据获取"""
    logs = state.get("logs", [])
    errors = state.get("errors", [])
    logs.append(f"[{datetime.now().strftime('%H:%M:%S')}] 📡 开始获取市场数据...")

    data_bus = create_data_bus()
    try:
        indices = data_bus.get_market_indices()
        breadth = data_bus.get_market_breadth()
        sectors = data_bus.get_sector_ranking(10)
        north_flow = data_bus.get_north_flow()

        # 更新持仓行情
        session = get_session()
        holdings = session.query(Portfolio).filter_by(status=TradeStatus.HOLDING).all()
        portfolio = []
        for h in holdings:
            quote = data_bus.get_stock_quote(h.stock_code)
            if quote and quote["price"] > 0:
                h.current_price = quote["price"]
            portfolio.append(
                {
                    "stock_code": h.stock_code,
                    "stock_name": h.stock_name,
                    "buy_price": h.buy_price,
                    "quantity": h.quantity,
                    "current_price": h.current_price or 0,
                    "cost_value": h.cost_value,
                    "current_value": h.current_value,
                    "profit_loss": h.profit_loss,
                    "profit_loss_pct": h.profit_loss_pct,
                }
            )
        session.commit()
        session.close()

        market_data = {
            "indices": indices,
            "breadth": breadth,
            "sectors": (
                sectors
                if isinstance(sectors, list)
                else sectors.to_dict("records")
                if not sectors.empty
                else []
            ),
            "north_flow": north_flow,
        }
        logs.append(
            f"[{datetime.now().strftime('%H:%M:%S')}] ✅ 数据获取完成,持仓{len(portfolio)}只"
        )
        return {**state, "market_data": market_data, "portfolio": portfolio, "logs": logs}
    except Exception as e:
        errors.append(f"数据获取失败: {e}")
        logs.append(f"[{datetime.now().strftime('%H:%M:%S')}] ❌ 数据获取失败: {e}")
        return {**state, "market_data": {}, "portfolio": [], "errors": errors, "logs": logs}


def node_parallel_analysis(state: InvestmentState) -> InvestmentState:
    """节点2:并行调用多个Skill分析(基本面+价值+多Agent)"""
    logs = state.get("logs", [])
    state.get("errors", [])
    portfolio = state.get("portfolio", [])
    analysis_results = state.get("analysis_results", {})

    logs.append(f"[{datetime.now().strftime('%H:%M:%S')}] 🔍 开始并行分析...")

    def run_skill(skill_name: str, context: dict) -> tuple:
        try:
            result = skill_registry.execute(skill_name, context)
            return skill_name, result
        except Exception as e:
            return skill_name, {"error": str(e)}

    # 对每只持仓股并行调用多个Skill
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = []
        for h in portfolio:
            context = {
                "stock_code": h["stock_code"],
                "stock_name": h["stock_name"],
                "market_data": state.get("market_data", {}),
                "portfolio": portfolio,
            }
            for skill_name in ["china_stock_research", "buffett", "taleb", "trading_agents_ashare"]:
                futures.append(executor.submit(run_skill, skill_name, context))

        for future in as_completed(futures):
            skill_name, result = future.result()
            if result and "error" not in result:
                key = f"{skill_name}"
                if key not in analysis_results:
                    analysis_results[key] = []
                analysis_results[key].append(result)

    # 芒格逆向思维单独调用(全局视角)
    munger_result = skill_registry.execute(
        "munger",
        {
            "portfolio": portfolio,
            "market_data": state.get("market_data", {}),
        },
    )
    if munger_result and "error" not in munger_result:
        analysis_results["munger"] = munger_result

    logs.append(
        f"[{datetime.now().strftime('%H:%M:%S')}] ✅ 并行分析完成,产出{len(analysis_results)}类结果"
    )
    return {**state, "analysis_results": analysis_results, "logs": logs}


def node_multi_model_vote(state: InvestmentState) -> InvestmentState:
    """节点2.5:多模型投票决策"""
    logs = state.get("logs", [])
    errors = list(state.get("errors", []))
    logs.append(f"[{datetime.now().strftime('%H:%M:%S')}] 🗳️ 开始多模型投票...")

    portfolio = state.get("portfolio", [])
    market_data = state.get("market_data", {})

    # 优先从 config.json 加载真实 LLM 配置
    voter = None
    try:
        voter = MultiModelVoter.from_config_file()
        logs.append(f"[{datetime.now().strftime('%H:%M:%S')}]   ✅ 已加载真实LLM配置")
    except Exception as e:
        logs.append(
            f"[{datetime.now().strftime('%H:%M:%S')}]   ⚠️ LLM配置加载失败({str(e)[:80]}),使用mock"
        )
        voter = MultiModelVoter(
            models={
                "主力": "mock:deepseek-chat",
                "辅助": "mock:qwen-plus",
                "验证": "mock:gpt-4o",
            }
        )

    vote_results = {}

    # 初始化复盘管理器(容错)
    review_manager = None
    try:
        review_manager = DecisionReviewManager()
    except Exception as e:
        logs.append(
            f"[{datetime.now().strftime('%H:%M:%S')}]   ⚠️ 复盘数据库初始化失败: {str(e)[:100]}"
        )

    for h in portfolio:
        try:
            vote = voter.analyze_stock(
                h["stock_code"], h["stock_name"], market_data=market_data, portfolio=portfolio
            )
            vote_results[h["stock_code"]] = vote
            # 记录决策到复盘数据库(容错)
            if review_manager:
                try:
                    review_manager.record_vote_result(vote)
                except Exception as e:
                    logs.append(
                        f"[{datetime.now().strftime('%H:%M:%S')}]   ⚠️ {h['stock_name']}复盘记录失败: {str(e)[:80]}"
                    )
        except Exception as e:
            err_msg = f"股票{h.get('stock_code', '?')}投票异常: {str(e)[:200]}"
            errors.append(err_msg)
            logs.append(f"[{datetime.now().strftime('%H:%M:%S')}]   ❌ {err_msg}")
            vote_results[h["stock_code"]] = {
                "winner": "持有",
                "consistency": 0.3,
                "winner_confidence": 0.3,
                "votes": {},
                "error": str(e)[:200],
            }

    if review_manager:
        with contextlib.suppress(Exception):
            review_manager.close()

    # 投票统计
    all_consistencies = [v.get("consistency", 0) for v in vote_results.values()]
    avg_consistency = sum(all_consistencies) / len(all_consistencies) if all_consistencies else 0

    logs.append(
        f"[{datetime.now().strftime('%H:%M:%S')}] "
        f"✅ 多模型投票完成,{len(vote_results)}只股票,平均一致性{avg_consistency:.0%}"
    )
    return {**state, "vote_results": vote_results, "logs": logs, "errors": errors}


def node_risk_audit(state: InvestmentState) -> InvestmentState:
    """节点3:三层风险防火墙"""
    logs = state.get("logs", [])
    state.get("errors", [])
    logs.append(f"[{datetime.now().strftime('%H:%M:%S')}] 🛡️ 开始风险审计...")

    data_bus = create_data_bus()
    firewall = RiskFirewall(data_bus)
    portfolio = state.get("portfolio", [])

    risk_assessment = firewall.full_check(portfolio)

    # 对每只持仓股做个股风险检查
    stock_risks = {}
    for h in portfolio:
        stock_risks[h["stock_code"]] = firewall.check_stock_risk(h["stock_code"])
    risk_assessment["stock_risks"] = stock_risks

    risk_pass = risk_assessment["pass"]
    logs.append(
        f"[{datetime.now().strftime('%H:%M:%S')}] "
        f"{'✅' if risk_pass else '❌'} 风险审计完成: "
        f"市场={risk_assessment['market_risk']['level']} "
        f"尾部={risk_assessment['tail_risk']['level']} "
        f"通过={'是' if risk_pass else '否'}"
    )
    return {**state, "risk_assessment": risk_assessment, "risk_pass": risk_pass, "logs": logs}


def node_position_plan(state: InvestmentState) -> InvestmentState:
    """节点3.5:动态仓位规划"""
    logs = state.get("logs", [])
    logs.append(f"[{datetime.now().strftime('%H:%M:%S')}] 📐 计算动态仓位...")

    risk = state.get("risk_assessment", {})
    risk_score = risk.get("tail_risk", {}).get("score", 50)
    portfolio = state.get("portfolio", [])

    pm = PositionManager()
    position_plan = pm.calculate_position_ratio(risk_score)

    # 如果有持仓,计算每只股票的权重建议
    total_cost = sum(h.get("cost_value", 0) for h in portfolio)
    if total_cost > 0 and portfolio:
        position_plan["allocations"] = []
        for h in portfolio:
            current_weight = h.get("cost_value", 0) / total_cost * 100
            position_plan["allocations"].append(
                {
                    "stock": f"{h['stock_name']}({h['stock_code']})",
                    "current_weight": f"{current_weight:.1f}%",
                    "pl_pct": f"{h.get('profit_loss_pct', 0):+.1f}%",
                }
            )

    logs.append(
        f"[{datetime.now().strftime('%H:%M:%S')}] "
        f"✅ 仓位规划完成: {position_plan['level']} → {position_plan['position_pct']}"
    )
    return {**state, "position_plan": position_plan, "logs": logs}


def node_generate_recommendations(state: InvestmentState) -> InvestmentState:
    """节点4:生成投资建议"""
    logs = state.get("logs", [])
    logs.append(f"[{datetime.now().strftime('%H:%M:%S')}] 💡 生成投资建议...")

    portfolio = state.get("portfolio", [])
    risk = state.get("risk_assessment", {})
    recommendations = []

    for h in portfolio:
        pl = h.get("profit_loss_pct", 0)
        stock_risk = risk.get("stock_risks", {}).get(h["stock_code"], {})
        risk_level = stock_risk.get("level", "UNKNOWN")

        # 基于盈亏和风险的简单建议逻辑
        if risk_level == "HIGH":
            action = "减仓"
            reason = f"个股风险偏高: {stock_risk.get('message', '')}"
        elif pl > 20:
            action = "考虑止盈"
            reason = f"盈利{pl:.1f}%,已达目标收益区间"
        elif pl < -15:
            action = "评估止损"
            reason = f"亏损{pl:.1f}%,需重新评估基本面"
        else:
            action = "持有观察"
            reason = f"盈亏{pl:.1f}%,在正常波动范围内"

        # 查找对应的分析结果
        related_skills = []
        for skill_name, results in state.get("analysis_results", {}).items():
            items = results if isinstance(results, list) else [results]
            for r in items:
                if isinstance(r, dict) and r.get("stock_code") == h["stock_code"]:
                    related_skills.append(skill_name)

        recommendations.append(
            {
                "stock_code": h["stock_code"],
                "stock_name": h["stock_name"],
                "action": action,
                "reason": reason,
                "risk_level": risk_level,
                "profit_loss_pct": pl,
                "related_skills": related_skills,
                "skill_prompts": [f"调用 {s} 深度分析 {h['stock_name']}" for s in related_skills],
            }
        )

    # 仓位建议
    position_advice = risk.get("tail_risk", {}).get("position_advice", "维持当前仓位")
    recommendations.append(
        {
            "stock_code": "SYSTEM",
            "stock_name": "仓位建议",
            "action": position_advice,
            "reason": f"市场风险={risk.get('market_risk', {}).get('level', 'UNKNOWN')},尾部风险评分={risk.get('tail_risk', {}).get('score', 0)}",
        }
    )

    logs.append(f"[{datetime.now().strftime('%H:%M:%S')}] ✅ 生成{len(recommendations)}条建议")
    return {**state, "recommendations": recommendations, "logs": logs}


def node_generate_report(state: InvestmentState) -> InvestmentState:
    """节点5:生成最终报告"""
    logs = state.get("logs", [])
    logs.append(f"[{datetime.now().strftime('%H:%M:%S')}] 📝 生成报告...")

    date = state.get("date", datetime.now().strftime("%Y-%m-%d"))
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    market = state.get("market_data", {})
    portfolio = state.get("portfolio", [])
    risk = state.get("risk_assessment", {})
    recs = state.get("recommendations", [])
    analysis = state.get("analysis_results", {})

    lines = []
    lines.append("# 📊 A股每日投资决策报告(LangGraph v2 增强版)")
    lines.append(f"> **日期**: {date} | **生成时间**: {now}")
    lines.append("")

    # 市场概览
    lines.append("---\n## 一、市场概览\n")
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

    # 风控审计
    lines.append("\n---\n## 二、🛡️ 风控审计\n")
    mr = risk.get("market_risk", {})
    tr = risk.get("tail_risk", {})
    lines.append(
        f"- 市场风险: **{mr.get('level', 'N/A')}** (恐慌指数 {mr.get('score', 0):.0f}) — {mr.get('message', '')}"
    )
    lines.append(
        f"- 尾部风险: **{tr.get('level', 'N/A')}** (评分 {tr.get('score', 0)}) — {tr.get('message', '')}"
    )
    lines.append(f"- 仓位建议: **{tr.get('position_advice', 'N/A')}**")
    lines.append(f"- 风控通过: {'✅ 是' if risk.get('pass') else '❌ 否'}")

    # 持仓概览
    lines.append("\n---\n## 三、持仓概览\n")
    if portfolio:
        total_cost = sum(h["cost_value"] for h in portfolio)
        total_value = sum(h["current_value"] for h in portfolio)
        total_pl = total_value - total_cost
        pl_e = "🟢" if total_pl >= 0 else "🔴"
        lines.append(
            f"持仓 **{len(portfolio)}** 只 | 成本 ¥{total_cost:,.0f} | 市值 ¥{total_value:,.0f} | 盈亏 {pl_e}¥{total_pl:,.0f} ({total_pl / total_cost * 100 if total_cost else 0:+.2f}%)"
        )
        lines.append("")
        lines.append("| 股票 | 买入价 | 现价 | 盈亏% | 风险 | 建议 |")
        lines.append("|------|--------|------|-------|------|------|")
        for h in portfolio:
            pl_e = "🟢" if h["profit_loss"] >= 0 else "🔴"
            sr = risk.get("stock_risks", {}).get(h["stock_code"], {})
            lines.append(
                f"| {h['stock_name']}({h['stock_code']}) | ¥{h['buy_price']:.2f} | ¥{h['current_price']:.2f} | {pl_e}{h['profit_loss_pct']:+.1f}% | {sr.get('level', 'N/A')} | 见下方 |"
            )

    # 投资建议
    lines.append("\n---\n## 四、💡 投资建议\n")
    for r in recs:
        if r["stock_code"] == "SYSTEM":
            lines.append(f"\n### 📌 {r['stock_name']}")
            lines.append(f"- **建议**: {r['action']}")
            lines.append(f"- **理由**: {r['reason']}")
        else:
            lines.append(f"\n### {r['stock_name']}({r['stock_code']})")
            lines.append(f"- **操作建议**: {r['action']}")
            lines.append(f"- **理由**: {r['reason']}")
            lines.append(f"- **风险等级**: {r['risk_level']}")
            if r.get("skill_prompts"):
                lines.append("- **深度分析**:")
                for sp in r["skill_prompts"]:
                    lines.append(f"  - {sp}")

    # Skill调用统计
    lines.append("\n---\n## 五、🤖 Skill 调用统计\n")
    lines.append("| Skill | 调用次数 | 状态 |")
    lines.append("|-------|---------|------|")
    for skill_name, results in analysis.items():
        count = len(results) if isinstance(results, list) else 1
        status = "✅ 成功" if results else "⚠️ 无结果"
        lines.append(f"| {skill_name} | {count} | {status} |")

    # 多模型投票结果
    vote_results = state.get("vote_results", {})
    if vote_results:
        lines.append("\n---\n## 六、🗳️ 多模型投票结果\n")
        for code, vote in vote_results.items():
            consistency = vote.get("consistency", 0)
            emoji = "🟢" if consistency > 0.7 else "🟡" if consistency > 0.4 else "🔴"
            name0 = vote.get("all_results", [{}])[0].get("context", {}).get("stock_name", code)
            lines.append(f"### {name0}({code})")
            lines.append(
                f"- 投票结果: **{vote.get('winner', 'N/A')}** {emoji} 一致性 {consistency:.0%}"
            )
            lines.append(f"- 置信度: {vote.get('winner_confidence', 0):.0%}")
            for rec, data in vote.get("votes", {}).items():
                models = ", ".join(m["role"] for m in data.get("models", []))
                lines.append(f"  - {rec}: {data['count']}票 ({models})")
            if vote.get("disagreements"):
                lines.append(
                    f"- ⚠️ 分歧: {json.dumps(vote['disagreements'], ensure_ascii=False)[:200]}"
                )

    # 动态仓位规划
    pos_plan = state.get("position_plan", {})
    if pos_plan:
        lines.append("\n---\n## 七、📐 动态仓位规划\n")
        lines.append(
            f"- 风险评分: **{pos_plan.get('risk_score', 'N/A')}** ({pos_plan.get('level', 'N/A')})"
        )
        lines.append(f"- 建议仓位: **{pos_plan.get('position_pct', 'N/A')}**")
        lines.append(f"- 仓位建议: {pos_plan.get('advice', 'N/A')}")
        if pos_plan.get("allocations"):
            lines.append("\n| 股票 | 当前权重 | 盈亏% |")
            lines.append("|------|---------|-------|")
            for a in pos_plan["allocations"]:
                s = a.get("stock", "N/A")
                w = a.get("current_weight", "N/A")
                p = a.get("pl_pct", "N/A")
                lines.append(f"| {s} | {w} | {p} |")

    # 执行日志
    section_num = 8 if vote_results else (7 if pos_plan else 6)

    # 策略表现监控
    monitor = StrategyMonitor()
    # 模拟收益率序列(基于持仓盈亏)
    mock_returns = []
    for h in portfolio:
        daily_ret = h.get("profit_loss_pct", 0) / max(len(portfolio), 1)
        mock_returns.append(daily_ret / 100)
    if mock_returns:
        metrics = monitor.calculate_metrics(mock_returns)
        alerts = monitor.check_alerts(metrics)
        section_num += 1
        lines.append(f"\n---\n## {section_num}. 📈 策略表现监控\n")
        lines.append("| 指标 | 值 | 状态 |")
        lines.append("|------|------|------|")
        items = [
            ("夏普比率", f"{metrics.get('sharpe_ratio', 0):.2f}"),
            ("最大回撤", f"{metrics.get('max_drawdown', 0):.2%}"),
            ("胜率", f"{metrics.get('win_rate', 0):.1%}"),
            ("盈亏比", f"{metrics.get('profit_loss_ratio', 0):.2f}"),
            ("Calmar比率", f"{metrics.get('calmar_ratio', 0):.2f}"),
        ]
        for name, val in items:
            lines.append(f"| {name} | {val} | ✅ |")
        if alerts:
            lines.append(f"\n⚠️ **{len(alerts)}个告警**: ")
            for a in alerts:
                lines.append(f"- [{a['level']}] {a['message']}")

    # 前视偏差审计提醒
    section_num += 1
    lines.append(f"\n---\n## {section_num}. 🔍 前视偏差审计\n")
    lines.append("> ⚠️ 每次修改策略代码后,请运行 `python main.py audit` 进行前视偏差自动审计。")
    lines.append(
        "> 常见问题:shift(-N)使用未来数据、rolling(center=True)、全样本标准化、信号未对齐T+1。"
    )

    section_num += 1
    lines.append(f"\n---\n## {section_num}. 📋 执行日志\n")
    for log in state.get("logs", []):
        lines.append(f"- {log}")

    lines.append(f"\n---\n*报告由 LangGraph 工作流引擎驱动 | {now}*")
    lines.append("*免责声明:本报告仅供参考,不构成任何投资建议。*")

    report = "\n".join(lines)

    # 保存报告
    os.makedirs("reports", exist_ok=True)
    filename = f"report_{date.replace('-', '')}.md"
    filepath = os.path.join("reports", filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(report)

    # 保存到数据库
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

    logs.append(f"[{datetime.now().strftime('%H:%M:%S')}] ✅ 报告已保存: {filepath}")
    return {**state, "report": report, "logs": logs}


#  构建工作流图


def build_workflow() -> StateGraph[InvestmentState, Any, Any, Any]:
    """构建LangGraph投资决策工作流(v2 增强版)"""
    register_all_skills()

    workflow = StateGraph(state_schema=InvestmentState)

    # 添加节点(7个)
    workflow.add_node("fetch_data", node_fetch_data)
    workflow.add_node("parallel_analysis", node_parallel_analysis)
    workflow.add_node("multi_model_vote", node_multi_model_vote)
    workflow.add_node("risk_audit", node_risk_audit)
    workflow.add_node("position_plan", node_position_plan)
    workflow.add_node("generate_recommendations", node_generate_recommendations)
    workflow.add_node("generate_report", node_generate_report)

    # 定义边
    workflow.set_entry_point("fetch_data")
    workflow.add_edge("fetch_data", "parallel_analysis")
    workflow.add_edge("parallel_analysis", "multi_model_vote")
    workflow.add_edge("multi_model_vote", "risk_audit")
    workflow.add_edge("risk_audit", "position_plan")

    # 条件分支:风控不通过则跳过建议生成,直接输出报告
    workflow.add_conditional_edges(
        "position_plan",
        lambda state: (
            "generate_recommendations" if state.get("risk_pass", True) else "generate_report"
        ),
        {
            "generate_recommendations": "generate_recommendations",
            "generate_report": "generate_report",
        },
    )

    workflow.add_edge("generate_recommendations", "generate_report")
    workflow.add_edge("generate_report", END)

    return workflow


def run_daily_workflow() -> str:
    """运行完整的每日投资决策工作流"""
    workflow = build_workflow()
    app = workflow.compile()

    initial_state = InvestmentState(
        date=datetime.now().strftime("%Y-%m-%d"),
        timestamp=datetime.now().isoformat(),
        market_data={},
        portfolio=[],
        analysis_results={},
        vote_results={},
        risk_assessment={},
        risk_pass=True,
        position_plan={},
        recommendations=[],
        report="",
        errors=[],
        logs=[],
    )

    print("🚀 启动 LangGraph 投资决策工作流...")
    final_state = app.invoke(initial_state)

    print("\n" + "=" * 60)
    print("📋 执行日志:")
    for log in final_state.get("logs", []):
        print(f"  {log}")

    if final_state.get("errors"):
        print("\n⚠️ 错误:")
        for err in final_state["errors"]:
            print(f"  {err}")

    report = final_state.get("report", "")
    return report if isinstance(report, str) else ""
