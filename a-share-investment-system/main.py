#!/usr/bin/env python
"""
AShare-X 智能投研系统 — 统一入口

用法:
  python main.py analyze 600519     # 单股深度分析
  python main.py daily              # 日频分析 + 报告
  python main.py screen             # 全市场选股
  python main.py serve              # 仅启动API后端
  python main.py schedule           # 定时任务模式(每日15:30)
  python main.py backtest           # 回测验证
  python main.py skills             # 列出技能和大师Agent

参考: ai-hedge-fund (CLI模式) + daily_stock_analysis (多模式)
"""

import argparse
import io
import os
import sys
import warnings
from datetime import datetime, timedelta
from typing import Any

# 全局抑制第三方库噪音
warnings.filterwarnings("ignore", category=ResourceWarning)
os.environ.setdefault("TQDM_DISABLE", "1")

# SOCKS proxy 清理: 如果未安装 socksio, 清除 PROXY 环境变量防止网络请求阻塞
try:
    import socksio  # noqa: F401
except ImportError:
    for _key in (
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "http_proxy",
        "https_proxy",
        "PROXY_URL",
        "ALL_PROXY",
    ):
        os.environ.pop(_key, None)

# Force IPv4 for outbound connections (Chinese financial APIs reject IPv6)
import socket as _socket

_old_gai = _socket.getaddrinfo


def _prefer_ipv4(host, port, family=0, type=0, proto=0, flags=0):
    results = _old_gai(host, port, _socket.AF_INET, type, proto, flags)
    if not results:
        results = _old_gai(host, port, family, type, proto, flags)
    return results


_socket.getaddrinfo = _prefer_ipv4

# Windows GBK编码兼容
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)


from services.trading_calendar import TradingCalendar

_trading_cal = TradingCalendar()


def is_trading_day(date=None):
    return _trading_cal.is_trading_day(date)


def cmd_analyze(args):
    """单股深度分析 — rich终端UI + 大师Agent技能"""
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table

    from services.factor_farm import FactorFarm
    from services.market_perception import MarketPerception
    from services.quant_analyzers import QuantAnalyzers

    console = Console()
    code = args.code
    qa = QuantAnalyzers()
    ff = FactorFarm()

    with console.status(f"[cyan]分析 {code}..."):
        regime = MarketPerception().perceive(
            {
                "breadth": {
                    "up": 2000,
                    "down": 2000,
                    "total": 5000,
                    "limit_up": 30,
                    "limit_down": 25,
                },
                "indices": {},
            }
        )
        f = {
            "roe": 18,
            "debt_to_equity": 35,
            "gross_margin": 55,
            "eps": 5.2,
            "bvps": 28,
            "price": 120,
            "pe_ratio": 23,
            "earnings_growth_3y": 12,
            "cash_to_assets": 15,
        }
        buffett = qa.buffett_analyze(code, f)
        graham = qa.graham_analyze(code, f)
        lynch = qa.lynch_analyze(code, f)
        factors = ff.get_top_factors(5)

        from services.master_agents import get_master_agents

        masters = get_master_agents()
        master_results = masters.analyze_all(code, f)

    reg = regime.data
    console.print(
        Panel(
            f"[bold blue]市场: {reg['regime']} | 仓位建议: {reg['adaptive_params']['target_position_pct']:.0%} | {reg.get('trading_phase', '')}",
            border_style="blue",
        )
    )

    table = Table(title=f"[bold]{code} 估值分析")
    table.add_column("分析师", style="cyan")
    table.add_column("得分", style="magenta")
    table.add_column("信号")
    for name, r in [("巴菲特", buffett), ("格雷厄姆", graham), ("林奇", lynch)]:
        s = r["signal"]
        sig_style = "green" if s == "bullish" else ("red" if s == "bearish" else "yellow")
        table.add_row(name, str(r["score"]), f"[{sig_style}]{s}[/{sig_style}]")
    if master_results:
        for r in master_results[:5]:
            s = r.get("signal", "neutral")
            sig_style = "green" if s == "bullish" else ("red" if s == "bearish" else "yellow")
            table.add_row(
                r.get("display_name", r.get("name", "?")),
                str(r.get("score", 0)),
                f"[{sig_style}]{s}[/{sig_style}]",
            )
    console.print(table)

    ft = Table(title="Top 5 有效因子")
    ft.add_column("因子", style="cyan")
    ft.add_column("IC", style="magenta")
    ft.add_column("类别")
    for f_item in factors.data.get("factors", [])[:5]:
        ft.add_row(f_item["name"], f"{f_item.get('ic_mean', 0):.3f}", f_item.get("category", ""))
    console.print(ft)
    return 0


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
        console.print(f"[yellow]⚠ 加载持仓失败: {e}[/yellow]")
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
    import json as _json
    import os
    from datetime import datetime as _dt

    # Build enhanced report
    from services.master_agents import get_master_agents

    try:
        from services.skill_engine import get_skill_engine

        _skill_engine = get_skill_engine()
    except Exception:
        _skill_engine = None

    masters = get_master_agents()
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
        if _skill_engine:
            for name in [
                "buffett",
                "munger",
                "taleb",
                "china_stock_research",
                "trading_agents_ashare",
            ]:
                try:
                    knowledge = _skill_engine.inject_knowledge(
                        name,
                        context=recs[0].get("stock_code", "") if recs else "",
                        max_refs=2,
                    )
                    skill_summary.append(
                        {"skill": name, "status": "ok", "knowledge": knowledge[:200]}
                    )
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


def cmd_screen(args):
    """全市场选股 — rich进度条+表格"""
    from rich.console import Console
    from rich.progress import Progress
    from rich.table import Table

    from services.stock_screener import StockScreener

    console = Console()
    ss = StockScreener()

    with Progress() as progress:
        task = progress.add_task("[cyan]三级漏斗选股...", total=3)
        progress.update(task, description="[yellow]Hard filter: 硬过滤...")
        result = ss.run(top_n=args.top or 8)
        d = result.data
        progress.update(
            task,
            advance=1,
            description=f"[yellow]Hard filter: {d.get('filter_passed', 0)}只通过...",
        )
        progress.update(
            task,
            advance=1,
            description=f"[yellow]Stage 3: 深度分析({d.get('stage3_recommended', 0)}只)...",
        )
        progress.update(task, advance=1, description="[green]完成!")

    console.print(
        f"\n全市场 [bold]{d['total_screened']}[/bold] → 推荐 [bold green]{d['stage3_recommended']}[/bold green] 只\n"
    )

    table = Table(title="选股结果 Top " + str(len(d.get("recommendations", []))))
    table.add_column("#", style="dim")
    table.add_column("股票", style="cyan")
    table.add_column("得分", style="magenta")
    table.add_column("信号")
    table.add_column("逻辑", style="dim")

    for r in d.get("recommendations", []):
        sig = r["signal"]
        sig_style = "green" if sig == "买入" else ("yellow" if sig == "持有" else "dim")
        table.add_row(
            str(r["rank"]),
            f"{r['stock_name']}({r['stock_code']})",
            str(r["score"]),
            f"[{sig_style}]{sig}[/{sig_style}]",
            r.get("reasoning", "")[:50],
        )
    console.print(table)
    return 0


def cmd_serve(args):
    """API后端"""
    import uvicorn

    print(f"\nAPI后端启动: http://127.0.0.1:{args.port}")
    print(f"   API文档: http://127.0.0.1:{args.port}/docs\n")
    uvicorn.run("server:app", host="127.0.0.1", port=args.port, log_level="info")


def cmd_desktop(args=None):
    """启动后端 + 打开浏览器 → 委托 launch.py"""
    from launch import start

    start(open_browser=True)


def cmd_schedule(args):
    """定时任务模式"""
    import time as _time

    print(f"\n⏰ 定时任务模式 — 每日 {args.time or '15:30'} 执行")

    while True:
        now = datetime.now()
        target_parts = (args.time or "15:30").split(":")
        target = now.replace(
            hour=int(target_parts[0]),
            minute=int(target_parts[1]),
            second=0,
        )

        if now > target:
            target += timedelta(days=1)

        wait_seconds = (target - now).total_seconds()
        print(f"   下次执行: {target.strftime('%Y-%m-%d %H:%M')} ({wait_seconds / 60:.0f}分钟后)")

        if wait_seconds > 0:
            _time.sleep(min(wait_seconds, 3600))  # 每小时检查一次
            continue

        if is_trading_day():
            print(f"\n{'=' * 50}")
            print(f"  执行日频分析: {now.strftime('%Y-%m-%d %H:%M')}")
            print(f"{'=' * 50}")
            cmd_daily(args)
        else:
            print(f"  跳过: {now.strftime('%Y-%m-%d')} 非交易日")

        _time.sleep(60)  # 避免同一天重复执行


def cmd_skills(args):
    """列出所有已注册的技能和大师Agent"""
    from rich.console import Console
    from rich.table import Table

    console = Console()

    # 技能引擎
    try:
        from services.skill_engine import get_skill_engine

        se = get_skill_engine()
        console.print(f"\n[bold cyan]技能引擎: {len(se.skills)} 个技能[/bold cyan]")
        if se.skills:
            st = Table(title="已注册技能")
            st.add_column("名称", style="green")
            st.add_column("分类", style="yellow")
            st.add_column("描述", style="dim")
            for name, meta in sorted(se.skills.items()):
                st.add_row(name, meta.category, meta.description[:60])
            console.print(st)
    except Exception as e:
        console.print(f"[red]技能引擎错误: {e}[/red]")

    # 大师Agent
    try:
        from services.master_agents import get_master_agents

        ma = get_master_agents()
        console.print(f"\n[bold cyan]大师Agent: {len(ma.get_all_names())} 个[/bold cyan]")
        mt = Table(title="投资大师")
        mt.add_column("名称", style="green")
        mt.add_column("风格", style="yellow")
        for name in ma.get_all_names():
            agent = ma.get_agent(name)
            style = agent.style if agent else "?"
            mt.add_row(name, style)
        console.print(mt)
    except Exception as e:
        console.print(f"[red]大师Agent错误: {e}[/red]")

    return 0


def cmd_backtest(args):
    """回测验证"""
    import numpy as np
    import pandas as pd

    from services.backtest_loop import BacktestLoop

    print(f"\n📈 回测验证 ({args.days or 60}天)...\n")
    np.random.seed(42)
    dates = pd.date_range("2024-01-01", periods=args.days or 60, freq="B")
    df = pd.DataFrame(
        {
            "close": 100 * (1 + np.random.randn(args.days or 60).cumsum() * 0.012),
            "high": None,
            "low": None,
            "volume": None,
            "amount": None,
        },
        index=dates,
    )
    df["high"] = df["close"] * 1.02
    df["low"] = df["close"] * 0.98
    df["volume"] = np.random.randint(1_000_000, 10_000_000, args.days or 60)
    df["amount"] = df["close"] * df["volume"]

    bl = BacktestLoop()
    result = bl.run(df, window_size=min(30, (args.days or 60) // 2))

    s = result.data["summary"]
    print(f"   夏普: {s.get('mean_abs_ic', 0):.3f}  |  IC稳定性: {s.get('ic_stability', 0):.1f}")
    print(
        f"   窗口数: {s.get('total_windows', 0)}  |  有效因子率: {s.get('significant_pct', 0):.1%}"
    )
    print(f"   Bandit状态: {result.data.get('bandit_status', {})}")
    return 0


def cmd_review(args):
    """执行日频复盘 — 对比昨日推荐 vs 今日实际表现"""
    from rich.console import Console
    from rich.table import Table

    from services.screening.daily_review import DailyReview

    console = Console()

    # 尝试加载 LLM
    llm = None
    try:
        from llm_clients.factory import get_client_for_role

        llm = get_client_for_role("secondary")
    except Exception as e:
        console.print(f"[yellow]⚠ LLM 客户端加载失败,使用默认: {e}[/yellow]")

    with console.status("[cyan]执行日频复盘..."):
        review = DailyReview(llm_client=llm)
        result = review.review_yesterday()

    if not result.get("ok"):
        console.print(f"[red]复盘失败: {result.get('error', '未知错误')}[/red]")
        return 1

    stats = result.get("stats", {})
    console.print(f"\n[bold]复盘日期: {result.get('trade_date', '?')}[/bold]")
    console.print(f"  推荐: {stats.get('total', 0)} 只")
    console.print(f"  有数据: {stats.get('with_data', 0)} 只")
    console.print(f"  命中: [green]{stats.get('hits', 0)}[/green] / {stats.get('with_data', 0)}")
    console.print(f"  命中率: [bold]{stats.get('hit_rate', 0):.0%}[/bold]")
    console.print(f"  平均收益: {stats.get('avg_return', 0):+.1f}%")
    console.print(f"  最大收益: {stats.get('max_return', 0):+.1f}%")
    console.print(f"  最小收益: {stats.get('min_return', 0):+.1f}%")

    agent_hits = result.get("agent_hits", [])
    if agent_hits:
        at = Table(title="Agent 表现")
        at.add_column("Agent", style="cyan")
        at.add_column("推荐", style="dim")
        at.add_column("正确", style="green")
        at.add_column("准确率")
        for ah in sorted(
            agent_hits,
            key=lambda x: x.get("correct_count", 0) / max(x.get("picks_count", 1), 1),
            reverse=True,
        ):
            count = ah.get("picks_count", 0)
            correct = ah.get("correct_count", 0)
            acc = correct / max(count, 1)
            at.add_row(
                ah.get("agent_name", "?"),
                str(count),
                str(correct),
                f"{acc:.0%}",
            )
        console.print(at)

    reflection = result.get("reflection", "")
    if reflection:
        console.print(f"\n[bold]反思:[/bold] {reflection}")

    return 0


def main():
    parser = argparse.ArgumentParser(
        description="AShare-X 智能投研系统",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python main.py                        # 默认: 打开桌面应用
  python main.py analyze 600519         # 单股深度分析
  python main.py daily                  # 日频分析
  python main.py daily --force          # 强制执行(跳过交易日检查)
  python main.py screen                 # 全市场选股
  python main.py screen --top 10        # 选股Top10
  python main.py serve                  # 仅API后端
  python main.py serve --port 8080      # 指定端口
  python main.py schedule               # 定时任务(每日15:30)
  python main.py backtest               # 回测
  python main.py backtest --days 120    # 回测120天
  python main.py skills                 # 列出技能和大师Agent
        """,
    )

    sub = parser.add_subparsers(dest="command", help="命令")

    # analyze
    p = sub.add_parser("analyze", help="单股深度分析")
    p.add_argument("code", help="股票代码 (如 600519)")

    # daily
    p = sub.add_parser("daily", help="日频分析")
    p.add_argument("--force", action="store_true", help="跳过交易日检查")
    p.add_argument("--top", type=int, default=50, help="推荐数量(最多50)")

    # screen
    p = sub.add_parser("screen", help="全市场选股")
    p.add_argument("--top", type=int, default=8, help="推荐数量")

    # serve
    p = sub.add_parser("serve", help="API后端")
    p.add_argument("--port", type=int, default=8765, help="端口")

    # schedule
    p = sub.add_parser("schedule", help="定时任务")
    p.add_argument("--time", default="15:30", help="执行时间")
    p.add_argument("--force", action="store_true", help="跳过交易日检查")

    # backtest
    p = sub.add_parser("backtest", help="回测")
    p.add_argument("--days", type=int, default=60, help="回测天数")

    # review
    sub.add_parser("review", help="日频复盘—对比昨日推荐vs今日表现")

    # skills
    sub.add_parser("skills", help="列出技能和大师Agent")

    args = parser.parse_args()

    if not args.command:
        return cmd_desktop(args)

    cmds = {
        "analyze": cmd_analyze,
        "daily": cmd_daily,
        "screen": cmd_screen,
        "serve": cmd_serve,
        "schedule": cmd_schedule,
        "backtest": cmd_backtest,
        "review": cmd_review,
        "skills": cmd_skills,
    }
    return cmds[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
