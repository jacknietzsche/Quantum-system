"""日频分析命令 — 选股 + 持仓分析 + 报告生成

从 main.py 提取,保持完全相同的逻辑。
"""

import json as _json
import logging
import os
from datetime import datetime as _dt
from typing import Any

from services.trading_calendar import TradingCalendar

_trading_cal = TradingCalendar()


def is_trading_day(date=None):
    return _trading_cal.is_trading_day(date)


def cmd_daily(args):
    """日频分析 — 选股 + 持仓分析 + 报告生成"""
    if not is_trading_day():
        print("⏸️  今日非交易日,跳过分析(使用 --force 强制执行)")
        if not args.force:
            return 0

    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table

    console = Console()
    console.print(Panel("[bold blue]📡 日频分析启动[/bold blue]", border_style="blue"))

    # ── 0. Kline数据刷新 ──
    from services.data_initializer import DataInitializer

    console.print("\n📊 [bold]Kline数据刷新[/bold]")
    di = DataInitializer()
    kline_result = di.refresh_klines_batch(max_stocks=500, days=90)
    kr = kline_result
    console.print(
        f"   刷新: {kr.get('success', 0)} 成功 / {kr.get('failed', 0)} 失败 / {kr.get('total', 0)} 总计"
    )

    # ── 1. 市场感知 ──
    from services.market_perception import MarketPerception

    mp = MarketPerception()
    regime = mp.perceive(
        {
            "breadth": {"up": 2000, "down": 2000, "total": 5000, "limit_up": 30, "limit_down": 25},
            "indices": {},
        }
    )
    regime_data = regime.data
    console.print(
        f"📊 市场状态: {regime_data['regime']} | "
        f"仓位建议: {regime_data['adaptive_params']['target_position_pct']:.0%}"
    )

    # ── 2. 全市场选股 (Top 50) ──
    from services.stock_screener import StockScreener

    console.print("\n🔍 [bold]Stage 1-3: 全市场选股[/bold]")
    screener = StockScreener(style="hybrid")
    screen_result = screener.run(
        market_regime=regime_data.get("regime", "NEUTRAL"),
        top_n=getattr(args, "top", 50),
    )
    recs = screen_result.data.get("recommendations", [])
    console.print(
        f"   推荐: {len(recs)} 只 | "
        f"筛选: {screen_result.data.get('total_screened', 0)} → "
        f"{screen_result.data.get('stage1_passed', 0)} → "
        f"{screen_result.data.get('stage2_passed', 0)} → "
        f"{len(recs)}"
    )

    if recs:
        table = Table(title="选股推荐 Top")
        table.add_column("排名", style="dim")
        table.add_column("代码", style="cyan")
        table.add_column("名称")
        table.add_column("得分", style="magenta")
        table.add_column("信号")
        table.add_column("PE")
        table.add_column("ROE")
        for r in recs[:15]:
            sig = r.get("signal", "")
            sig_style = (
                "green"
                if sig in ("买入", "bullish")
                else ("red" if sig in ("卖出", "bearish") else "yellow")
            )
            table.add_row(
                str(r.get("rank", "")),
                r.get("stock_code", ""),
                r.get("stock_name", ""),
                str(r.get("score", "")),
                f"[{sig_style}]{sig}[/{sig_style}]",
                f"{r.get('pe', 0):.1f}" if r.get("pe") else "-",
                f"{r.get('roe', 0):.1f}" if r.get("roe") else "-",
            )
        console.print(table)

    # ── 3. 持仓分析 ──
    console.print("\n💼 [bold]持仓分析[/bold]")
    try:
        from services.portfolio import PortfolioService
        from shared.models import get_session

        ps = PortfolioService(get_session)
        holdings = ps.get_all_stock_info()
        if holdings.get("stocks"):
            hold_table = Table(title="持仓监控")
            hold_table.add_column("代码", style="cyan")
            hold_table.add_column("名称")
            hold_table.add_column("盈亏%")
            hold_table.add_column("信号")
            for code, info in holdings["stocks"].items():
                pnl = info.get("profit_loss_pct", 0)
                pnl_style = "green" if pnl > 0 else "red"
                matched = next((r for r in recs if r.get("stock_code") == code), None)
                signal = matched.get("signal", "持有") if matched else "持有"
                if pnl < -10 and signal != "买入":
                    signal = "[red]止损[/red]"
                hold_table.add_row(
                    code,
                    info.get("name", ""),
                    f"[{pnl_style}]{pnl:+.1f}%[/{pnl_style}]",
                    signal,
                )
            console.print(hold_table)
        else:
            console.print("   暂无持仓")
    except Exception as e:
        console.print(f"   持仓加载失败: {e}")

    # ── 4. 因子概览 ──
    from services.factor_farm import FactorFarm

    ff = FactorFarm()
    factors = ff.get_top_factors(5)
    console.print(f"\n📈 活跃因子: {factors.data.get('count', 0)}个")

    # ── 5. 风控 ──
    from services.risk_engine import RiskEngine

    re_eng = RiskEngine()
    risk = re_eng.full_audit([])
    pass_str = "✅ 通过" if risk.data.get("pass") else "❌ 未通过"
    console.print(f"🛡️ 风控: {pass_str}")

    report_data: dict[str, Any] = {}
    # ── 5.5. 生成交易计划 ──
    from services.trading_plan import TradingPlanGenerator, extract_master_factors

    tpg = TradingPlanGenerator()
    positions_list: list[dict[str, Any]] = []
    try:
        holdings_data = ps.get_holdings("value")
        positions_list = holdings_data.get("positions", []) if holdings_data else []
    except Exception as e:
        logging.debug("Handled: %s", e)
    _factors = extract_master_factors(screen_result.data)
    _mpf = _factors["master_position_factor"]
    console.print(
        f"   Master因子: weight={_factors['master_weight_factor']:.2f}, position={_mpf:.2f}"
    )
    plan_result = tpg.generate(
        recommendations=recs,
        current_positions=positions_list,
        risk_report=risk.data if hasattr(risk, "data") else {},
        cash=positions_list[0].get("cash", 0) if positions_list else 0,
        total_capital=sum(p.get("current_value", p.get("cost_value", 0)) for p in positions_list)
        if positions_list
        else 0,
        master_position_factor=_mpf,
        master_weight_factor=_factors["master_weight_factor"],
    )
    if plan_result.data:
        plan = plan_result.data
        orders = plan.get("execution_plan", {}).get("orders", [])
        buy_orders = [o for o in orders if o.get("action") == "买入"]
        sell_orders = [o for o in orders if o.get("action") in ("卖出", "减仓")]
        console.print(
            f"\n📋 交易计划: {len(buy_orders)}买入 / {len(sell_orders)}卖出 / 风险{plan.get('market_assessment', {}).get('risk_level', '?')}"
        )
        if buy_orders:
            buy_table = Table(title="买入计划")
            buy_table.add_column("代码", style="cyan")
            buy_table.add_column("名称")
            buy_table.add_column("数量")
            buy_table.add_column("限价")
            buy_table.add_column("止损")
            buy_table.add_column("止盈")
            buy_table.add_column("置信度")
            for o in buy_orders[:10]:
                buy_table.add_row(
                    o.get("code", ""),
                    o.get("name", ""),
                    str(o.get("quantity", "")),
                    o.get("limit_price", "-"),
                    o.get("stop_loss", "-"),
                    o.get("take_profit", "-"),
                    o.get("confidence", ""),
                )
            console.print(buy_table)
        if sell_orders:
            sell_table = Table(title="卖出/减仓计划")
            sell_table.add_column("代码", style="cyan")
            sell_table.add_column("名称")
            sell_table.add_column("动作")
            sell_table.add_column("数量")
            sell_table.add_column("原因")
            for o in sell_orders[:10]:
                sell_table.add_row(
                    o.get("code", ""),
                    o.get("name", ""),
                    o.get("action", ""),
                    str(o.get("quantity", "")),
                    o.get("reasoning", "")[:30],
                )
            console.print(sell_table)
        report_data["trading_plan"] = plan
    else:
        console.print("⚠️ 交易计划生成失败")

    # ── 6. 保存报告 ──

    # Build enhanced report
    from services.master_agents import get_master_agents
    from skills import register_all_skills, skill_registry

    masters = get_master_agents()
    register_all_skills()
    top_master_results = []
    skill_summary = []
    try:
        for r in recs[:5]:
            code = r.get("stock_code", "")
            if not code:
                continue
            sample = masters.analyze_all(
                code,
                {
                    "pe_ratio": r.get("pe"),
                    "roe": r.get("roe"),
                    "change_pct": r.get("change_pct"),
                },
            )
            top_master_results.append(
                {
                    "stock_code": code,
                    "stock_name": r.get("stock_name", ""),
                    "masters": sample[:3],
                }
            )
        for name in ["buffett", "munger", "taleb", "china_stock_research", "trading_agents_ashare"]:
            try:
                out = skill_registry.execute(
                    name,
                    {
                        "stock_code": recs[0].get("stock_code", "") if recs else "",
                        "financials": {},
                        "market_data": {"breadth": {"up": 0, "down": 0, "total": 0}, "indices": {}},
                    },
                )
                skill_summary.append(out)
            except Exception as e:
                skill_summary.append({"skill": name, "status": "error", "error": str(e)[:120]})
    except Exception as e:
        console.print(f"[yellow]⚠ Skill/Master enrichment failed: {e}[/yellow]")

    report_data = {
        "date": _dt.now().strftime("%Y-%m-%d"),
        "regime": regime_data.get("regime", ""),
        "market_overview": {
            "regime": regime_data.get("regime", "NEUTRAL"),
            "target_position": regime_data.get("adaptive_params", {}).get(
                "target_position_pct", 0.5
            ),
            "description": regime_data.get("description", ""),
        },
        "recommendations": recs[:50],
        "total_screened": screen_result.data.get("total_screened", 0),
        "stage1_passed": screen_result.data.get("stage1_passed", 0),
        "stage2_passed": screen_result.data.get("stage2_passed", 0),
        "factor_count": factors.data.get("count", 0),
        "top_factors": factors.data.get("factors", [])[:5] if hasattr(factors, "data") else [],
        "risk_pass": risk.data.get("pass", False),
        "risk_details": risk.data if hasattr(risk, "data") else {},
        "skill_summary": skill_summary[:10],
        "top_master_results": top_master_results[:5],
        "summary": {
            "buy_count": sum(1 for r in recs if r.get("signal") == "买入"),
            "hold_count": sum(1 for r in recs if r.get("signal") == "持有"),
            "sell_count": sum(1 for r in recs if r.get("signal") in ("卖出", "止损")),
            "watch_count": sum(1 for r in recs if r.get("signal") == "观望"),
        },
    }
    os.makedirs("reports", exist_ok=True)
    report_path = os.path.join("reports", f"daily_{_dt.now().strftime('%Y%m%d')}.json")
    with open(report_path, "w", encoding="utf-8") as f:
        _json.dump(report_data, f, ensure_ascii=False, indent=2, default=str)
    console.print(f"\n💾 报告已保存: {report_path}")

    # ── 7. V2 多Agent深度分析 (参考 TradingAgents) ──
    v2_analysis_results = []
    if recs:
        try:
            from graph_v2 import AShareTradingGraph
            from graph_v2.default_config import get_default_config

            v2_config = get_default_config()
            top_picks = [r for r in recs[:5] if r.get("stock_code")]

            if top_picks:
                console.print(f"\n🤖 [bold]V2 多Agent深度分析 (Top {len(top_picks)})[/bold]")
                graph = AShareTradingGraph(
                    selected_analysts=["market", "sentiment", "news", "fundamentals"],
                    config=v2_config,
                )
                for pick in top_picks:
                    code = pick["stock_code"]
                    try:
                        with console.status(f"  分析 {code}..."):
                            _decision, signal = graph.propagate(
                                stock_code=code,
                                trade_date=_dt.now().strftime("%Y-%m-%d"),
                                validate=True,
                            )
                        action = signal.get("action", "hold")
                        confidence = signal.get("confidence", 0)
                        action_color = (
                            "green"
                            if "buy" in action
                            else ("red" if "sell" in action else "yellow")
                        )
                        console.print(
                            f"  [{action_color}]{code}: {action} (confidence {confidence:.0%})[/{action_color}]"
                        )
                        v2_analysis_results.append(
                            {
                                "stock_code": code,
                                "stock_name": pick.get("stock_name", ""),
                                "action": action,
                                "confidence": confidence,
                                "reasoning": signal.get("reasoning", "")[:300],
                            }
                        )
                    except Exception as e:
                        console.print(f"  [yellow]⚠ {code} analysis failed: {e}[/yellow]")
                        v2_analysis_results.append({"stock_code": code, "error": str(e)})

                report_data["v2_analysis"] = v2_analysis_results
        except Exception as e:
            console.print(f"  [yellow]⚠ V2 module load failed: {e}[/yellow]")

    # ── 8. 邮件通知 (参考 daily_stock_analysis) ──
    try:
        from shared.config import Config

        cfg = Config()
        email_cfg = cfg.get("notification.email", {})
        if email_cfg and email_cfg.get("sender") and email_cfg.get("auth_code"):
            from services_v2.email_sender import EmailSender

            receivers = email_cfg.get("receiver", [])
            if isinstance(receivers, str):
                receivers = [r.strip() for r in receivers.split(",") if r.strip()]
            sender = EmailSender(
                {
                    "smtp_host": email_cfg.get("smtp_server", "smtp.qq.com"),
                    "smtp_port": email_cfg.get("smtp_port", 465),
                    "sender": email_cfg["sender"],
                    "password": email_cfg["auth_code"],
                    "receivers": receivers,
                    "sender_name": email_cfg.get("sender_name", "A-share Research"),
                }
            )
            buy_count = report_data.get("summary", {}).get("buy_count", 0)
            sell_count = report_data.get("summary", {}).get("sell_count", 0)
            regime = report_data.get("regime", "NEUTRAL")
            subject = f"Daily Analysis {report_data.get('date', '')} | {regime} | {buy_count}B {sell_count}S"
            md_lines = [
                f"# A-Share Daily Report {report_data.get('date', '')}",
                "",
                f"## Market: {regime}",
                f"- Target Position: {report_data.get('market_overview', {}).get('target_position', 0):.0%}",
                f"- Screened: {report_data.get('total_screened', 0)} -> {len(recs)}",
                "",
                "## Summary",
                f"- Buy: {buy_count}",
                f"- Hold: {report_data.get('summary', {}).get('hold_count', 0)}",
                f"- Sell: {sell_count}",
                "",
            ]
            if report_data.get("skill_summary"):
                md_lines.append("## Skill Insights")
                for item in report_data["skill_summary"][:5]:
                    md_lines.append(f"- {item.get('skill', '?')}: {item.get('status', 'ok')}")
            if report_data.get("top_master_results"):
                md_lines.append("## Master Agent Views")
                for item in report_data["top_master_results"][:3]:
                    master_names = ", ".join(
                        m.get("name", "?") for m in item.get("masters", [])[:2]
                    )
                    md_lines.append(
                        f"- {item.get('stock_name', '')}({item.get('stock_code', '')}): {master_names}"
                    )
                md_lines.append("")
            if v2_analysis_results:
                md_lines.append("## Multi-Agent Deep Analysis")
                for r in v2_analysis_results:
                    if r.get("error"):
                        md_lines.append(f"- {r['stock_code']}: error - {r['error'][:50]}")
                    else:
                        md_lines.append(
                            f"- {r.get('stock_name', '')}({r['stock_code']}): {r['action']} conf={r.get('confidence', 0):.0%}"
                        )
                        if r.get("reasoning"):
                            md_lines.append(f"  > {r['reasoning'][:150]}")
                md_lines.append("")
            md_lines.append("---")
            md_lines.append("*Generated by AShare-X Multi-Agent System*")
            email_ok = sender.send(subject, "\n".join(md_lines))
            if email_ok:
                console.print("\n📧 [green]Email notification sent[/green]")
            else:
                console.print("\n📧 [yellow]Email skipped (not configured or failed)[/yellow]")
        else:
            console.print("\n📧 [dim]Email not configured[/dim]")
    except Exception as e:
        console.print(f"\n📧 [yellow]Email notification failed: {e}[/yellow]")

    # Step 7: Compute derived fields + enrich financial data
    try:
        from services.data_initializer import DataInitializer

        di = DataInitializer()
        _derived_result = di.compute_derived_fields()
        enrich_result = di.enrich_financial_data(max_stocks=50)
        console.print(f"\n? ???: {enrich_result.get('success', 0)}????")
    except Exception as e:
        console.print(f"\n? ??????: {e}")

    console.print(Panel("[bold green]✅ 日频分析完成[/bold green]", border_style="green"))
    return 0
