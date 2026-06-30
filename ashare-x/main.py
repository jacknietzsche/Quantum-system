"""CLI入口。

命令:
  serve    — 启动API服务器
  analyze  — 单股分析（调用LangGraph工作流）
  daily    — 每日数据更新
  screen   — 全市场选股
  backtest — 策略回测
  plan     — 生成每日交易计划
  schedule — 启动每日定时任务调度
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime

import schedule


def cmd_serve(port: int = 8765):
    import uvicorn

    uvicorn.run("server:app", host="127.0.0.1", port=port, reload=True)


def cmd_analyze(ticker: str, fast: bool = False, enable_masters: bool = False):
    """单股分析：调用真实LangGraph工作流。"""
    from core.config import Config
    from core.llm_client import LLMClient
    from core.state import make_initial_state
    from graph.trading_graph import build_trading_graph

    config = Config()
    api_key = config.get("llm.deepseek.api_key", "")
    if not api_key:
        import os

        api_key = os.getenv("DEEPSEEK_API_KEY", "")
    if not api_key:
        print("❌ 未配置DEEPSEEK_API_KEY，请在.env或config.yaml中设置")
        sys.exit(1)

    print(f"📊 开始分析 {ticker} (模式: {'快速' if fast else '完整'})")

    llm_client = LLMClient(config)
    graph = build_trading_graph(llm_client)

    state = make_initial_state(ticker=ticker, mode="fast" if fast else "full")
    state["config"] = {
        "debate": {
            "investment": {"max_rounds": 1 if fast else 2},
            "risk": {"max_rounds": 1 if fast else 2},
        },
        "features": {"enable_masters": enable_masters},
    }

    print("⚙ 构建工作流完成，开始执行Agent...\n")

    thread_config = {"configurable": {"thread_id": "cli-analysis"}}
    final_state = graph.invoke(state, config=thread_config)

    # 解析结果
    pm_report = final_state.get("portfolio_manager_report", "")
    action = "Hold"
    confidence = 70

    if pm_report:
        import re

        json_match = re.search(r"\{[^{}]*\}", pm_report.replace("\n", " "))
        if json_match:
            try:
                decision = json.loads(json_match.group())
                action = decision.get("rating", "Hold")
                confidence = decision.get("confidence", 70)
            except json.JSONDecodeError:
                pass

    # 输出摘要
    print("=" * 60)
    print(f"📈 分析结果: {ticker}")
    print(f"   决策: {action}  置信度: {confidence}%")
    print("-" * 60)

    # 各Agent报告摘要
    report_keys = [
        ("market_analyst_report", "市场分析师"),
        ("fundamentals_analyst_report", "基本面分析师"),
        ("news_analyst_report", "新闻分析师"),
        ("sentiment_analyst_report", "情绪分析师"),
        ("research_manager_report", "研究经理"),
        ("trader_report", "交易员"),
        ("portfolio_manager_report", "组合经理"),
    ]

    for key, label in report_keys:
        report = final_state.get(key, "")
        if report:
            preview = report[:200].replace("\n", " ")
            print(f"\n📋 {label}:")
            print(f"   {preview}{'...' if len(report) > 200 else ''}")

    # 大师信号
    master_signals = final_state.get("master_signals", {})
    if master_signals:
        print(f"\n👑 大师评审 ({len(master_signals)}位):")
        for name, signal in master_signals.items():
            print(f"   {name}: {signal.get('signal', 'N/A')} ({signal.get('confidence', 0):.0f}%)")

    # 预算
    budget = llm_client.get_budget_snapshot()
    print(f"\n💰 Token消耗: {budget.get('total_tokens', 0)} / {budget.get('daily_budget', 0)} ({budget.get('usage_pct', 0):.1f}%)")
    print(f"   月成本: ¥{budget.get('monthly_used_rmb', 0):.2f} / ¥{budget.get('monthly_budget_rmb', 0):.2f}")
    print("=" * 60)


def cmd_daily():
    """每日数据更新。"""
    from services.updater import DailyUpdater

    print("🔄 开始每日数据更新...")
    updater = DailyUpdater()
    stats = updater.run_daily_update()

    print("\n" + "=" * 60)
    print("📊 每日更新完成")
    print("-" * 60)
    print(f"  K线更新: {stats.get('kline_updated', 0)} 只")
    print(f"  股票信息: {stats.get('stock_info_updated', 0)} 只")
    print(f"  基本面: {stats.get('fundamentals_updated', 0)} 只")
    print(f"  新闻: {stats.get('news_updated', 0)} 只")
    print(f"  情绪: {stats.get('sentiment_updated', 0)} 只")
    print(f"  市场广度: {'✅' if stats.get('market_breadth_updated') else '❌'}")
    errors = stats.get("errors", [])
    if errors:
        print(f"\n  ⚠ 错误 ({len(errors)}):")
        for err in errors[:5]:
            print(f"    - {err}")
    print("=" * 60)


def cmd_screen(style: str = "balanced", limit: int = 20):
    """全市场选股。"""
    from providers.data_bus import DatabaseFirstDataBus
    from services.screening import rank_stocks

    print(f"🔍 选股 (风格: {style}, 数量: {limit})")

    bus = DatabaseFirstDataBus()
    stocks = bus.get_market_snapshot()

    if not stocks:
        print("⚠ 数据库无快照数据，尝试获取...")
        stocks = bus.get_market_snapshot()
    if not stocks:
        print("❌ 无可用股票数据，请先运行 'python main.py daily' 更新数据")
        return

    ranked = rank_stocks(stocks, top_n=limit, style=style)

    if not ranked:
        print("⚠ 筛选后无符合条件的股票")
        return

    print(f"\n📊 选股结果 ({len(ranked)}只):")
    print("-" * 80)
    print(f"{'排名':<5} {'代码':<8} {'名称':<10} {'评分':<8} {'PE':<8} {'行业':<10}")
    print("-" * 80)
    for i, s in enumerate(ranked, 1):
        print(
            f"{i:<5} {s.get('stock_code', ''):<8} "
            f"{s.get('stock_name', '-'):<10} "
            f"{s.get('score', 0):<8.1f} "
            f"{s.get('pe_ratio', '-'):<8} "
            f"{s.get('industry', '-'):<10}"
        )
    print("-" * 80)


def cmd_backtest(codes: str, strategy: str = "ma_cross", days: int = 250, capital: float = 1_000_000):
    """策略回测。"""
    stock_codes = [c.strip() for c in codes.split(",") if c.strip()]
    if not stock_codes:
        print("❌ 请提供股票代码（逗号分隔）")
        return

    print(f"📈 回测: {', '.join(stock_codes)} | 策略: {strategy} | 天数: {days}")

    from services.backtest import VectorbtBacktest

    engine = VectorbtBacktest(initial_capital=capital)
    result = engine.run(stock_codes=stock_codes, strategy=strategy, days=days)

    print("\n" + "=" * 60)
    print("📊 回测结果")
    print("-" * 60)
    print(f"  总收益: {result.get('total_return', 'N/A')}")
    print(f"  基准收益: {result.get('benchmark_return', 'N/A')}")
    print(f"  超额收益: {result.get('excess_return', 'N/A')}")
    print(f"  夏普比率: {result.get('sharpe', 'N/A')}")
    print(f"  最大回撤: {result.get('max_drawdown', 'N/A')}")

    per_stock = result.get("per_stock", {})
    if per_stock:
        print(f"\n  逐股明细 ({len(per_stock)}只):")
        for code, metrics in per_stock.items():
            print(f"    {code}: 收益={metrics.get('total_return', 'N/A')} "
                  f"夏普={metrics.get('sharpe', 'N/A')} "
                  f"回撤={metrics.get('max_drawdown', 'N/A')} "
                  f"交易={metrics.get('total_trades', 'N/A')}")
    print("=" * 60)


def cmd_plan(fast: bool = True, show_only: bool = False):
    """每日交易计划生成。"""
    from services.daily_plan import DailyPlanGenerator

    gen = DailyPlanGenerator()

    if show_only:
        plan = gen.get_today_plan()
        if not plan:
            print("❌ 今日尚未生成交易计划，请运行 'python main.py plan' 生成")
            return
    else:
        print("⚙ 开始生成每日交易计划...")
        plan = gen.generate(fast_mode=fast)

    if not plan:
        print("❌ 计划生成失败")
        return

    # 打印格式化交易计划
    print("\n" + "=" * 60)
    print(f"  📊 每日交易计划 — {plan.get('date', 'N/A')}")
    print(f"  市场状态: {plan.get('market_state', 'N/A')}")
    print("=" * 60)

    # 账户概览
    account = plan.get("account", {})
    if account:
        print("\n💰 账户概览:")
        print(f"   总资产: ¥{account.get('total_assets', 0):,.2f}")
        print(f"   现金: ¥{account.get('cash', 0):,.2f}")
        print(f"   持仓市值: ¥{account.get('holdings_value', 0):,.2f}")
        print(f"   盈亏: ¥{account.get('pnl', 0):,.2f} ({account.get('pnl_pct', 0):+.1f}%)")

    # 今日操作建议
    actions = plan.get("actions", [])
    if actions:
        print(f"\n── 今日操作建议 ({len(actions)}项) ──")
        action_emojis = {
            "INITIAL_BUY": "📈", "ADD": "⬆", "REDUCE": "⬇",
            "CLEAR": "🔴", "HOLD": "⚪", "WATCH": "👀",
        }
        for a in actions:
            emoji = action_emojis.get(a["action"], "•")
            print(f"\n{emoji} {a['action']} {a.get('stock_code', '')} {a.get('stock_name', '')}")
            if a.get("target_shares"):
                print(f"   建议股数: {a['target_shares']}股")
            if a.get("target_price"):
                print(f"   建议价格: ¥{a['target_price']:.2f}")
            if a.get("stop_loss"):
                print(f"   止损: ¥{a['stop_loss']:.2f}")
            if a.get("take_profit"):
                print(f"   止盈: ¥{a['take_profit']:.2f}")
            print(f"   置信度: {a.get('confidence', 0)}%")
            reasoning = a.get("reasoning", "")
            if reasoning:
                print(f"   理由: {reasoning[:200]}")
    else:
        print("\n── 今日无操作建议 ──")

    # 当前持仓
    holdings = plan.get("holdings_status", [])
    if holdings:
        print(f"\n── 当前持仓 ({len(holdings)}只) ──")
        print(f"  {'代码':<8} {'名称':<10} {'持仓':<8} {'成本':<10} {'现价':<10} {'盈亏%':<8}")
        print("-" * 60)
        for h in holdings:
            print(
                f"  {h['stock_code']:<8} {h['stock_name']:<10} "
                f"{h['shares']:<8} ¥{h['avg_cost']:<9.2f} "
                f"¥{h.get('current_price', 0):<9.2f} "
                f"{h.get('pnl_pct', 0):+.1f}%"
            )

    # 观察名单
    watchlist = plan.get("watchlist", [])
    if watchlist:
        print(f"\n── 观察名单 ({len(watchlist)}只) ──")
        for w in watchlist:
            last = w.get("last_analysis_date") or "未分析"
            print(f"  {w['stock_code']:<8} {w.get('stock_name', '-'):<10} 评分: {w.get('score', 0):.1f}  上次: {last}")

    # 摘要
    print(f"\n{'─' * 60}")
    print(f"📋 {plan.get('summary', '')}")

    errors = plan.get("errors", [])
    if errors:
        print(f"\n⚠ 错误 ({len(errors)}):")
        for err in errors[:5]:
            print(f"  - {err}")

    print("=" * 60)


def _is_trading_day(date: datetime | None = None) -> bool:
    """判断是否为交易日（仅排除周末，简单版）。"""
    if date is None:
        date = datetime.now()
    return date.weekday() < 5


def cmd_schedule(
    update_time: str = "09:00",
    screen_time: str = "09:30",
    plan_time: str = "15:10",
    once: bool = False,
    skip_weekend: bool = True,
):
    """启动每日定时任务调度器。

    默认时间安排（A股交易日）:
      - 09:00  数据更新 (daily)
      - 09:30  全市场扫描 (screen)
      - 15:10  收盘后生成交易计划 (plan)
    """
    def _wrap_job(name: str, fn, *, check_trading_day: bool = True):
        def job():
            if skip_weekend and check_trading_day and not _is_trading_day():
                print(f"⏭ {name} 跳过（非交易日）")
                return
            print(f"\n🔔 定时任务触发: {name} — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            try:
                fn()
            except Exception as e:
                print(f"❌ {name} 执行失败: {e}")
        return job

    schedule.every().day.at(update_time).do(
        _wrap_job("每日数据更新", cmd_daily)
    )
    schedule.every().day.at(screen_time).do(
        _wrap_job("全市场扫描", lambda: cmd_screen(style="balanced", limit=50))
    )
    schedule.every().day.at(plan_time).do(
        _wrap_job("交易计划生成", lambda: cmd_plan(fast=True))
    )

    print("=" * 60)
    print("📅 AShare-X 定时调度器已启动")
    print(f"  数据更新:  每日 {update_time}")
    print(f"  全市场扫描: 每日 {screen_time}")
    print(f"  交易计划:  每日 {plan_time}")
    print(f"  跳过周末:  {'是' if skip_weekend else '否'}")
    if once:
        print("  模式:      立即执行一次后退出")
    else:
        print("  模式:      常驻调度（按 Ctrl+C 停止）")
    print("=" * 60)

    if once:
        schedule.run_all()
        return

    try:
        while True:
            schedule.run_pending()
            time.sleep(60)
    except KeyboardInterrupt:
        print("\n🛑 调度器已停止")


def main():
    parser = argparse.ArgumentParser(description="AShare-X CLI — A股智能投研系统")
    subparsers = parser.add_subparsers(dest="command")

    # serve
    serve_parser = subparsers.add_parser("serve", help="启动API服务器")
    serve_parser.add_argument("--port", type=int, default=8766, help="端口号")

    # analyze
    analyze_parser = subparsers.add_parser("analyze", help="单股分析")
    analyze_parser.add_argument("ticker", help="股票代码 (如 600519)")
    analyze_parser.add_argument("--fast", action="store_true", help="快速模式")
    analyze_parser.add_argument("--masters", action="store_true", help="启用大师评审")

    # daily
    subparsers.add_parser("daily", help="每日数据更新")

    # screen
    screen_parser = subparsers.add_parser("screen", help="全市场选股")
    screen_parser.add_argument("--style", default="balanced", help="选股风格 (value/growth/momentum/balanced)")
    screen_parser.add_argument("--limit", type=int, default=20, help="返回数量")

    # backtest
    bt_parser = subparsers.add_parser("backtest", help="策略回测")
    bt_parser.add_argument("codes", help="股票代码（逗号分隔，如 600519,000858）")
    bt_parser.add_argument("--strategy", default="ma_cross", help="策略 (ma_cross/rsi/bollinger)")
    bt_parser.add_argument("--days", type=int, default=250, help="回测天数")
    bt_parser.add_argument("--capital", type=float, default=1_000_000, help="初始资金")

    # plan
    plan_parser = subparsers.add_parser("plan", help="生成每日交易计划")
    plan_parser.add_argument("--full", action="store_true", help="完整模式（更多Agent轮次）")
    plan_parser.add_argument("--show", action="store_true", help="仅显示今日计划（不重新生成）")

    # schedule
    sched_parser = subparsers.add_parser("schedule", help="启动每日定时任务调度")
    sched_parser.add_argument("--update-time", default="09:00", help="数据更新时间 (HH:MM)")
    sched_parser.add_argument("--screen-time", default="09:30", help="全市场扫描时间 (HH:MM)")
    sched_parser.add_argument("--plan-time", default="15:10", help="交易计划生成时间 (HH:MM)")
    sched_parser.add_argument("--once", action="store_true", help="立即执行一次后退出")
    sched_parser.add_argument("--no-skip-weekend", action="store_true", help="周末也执行")

    args = parser.parse_args()

    if args.command == "serve":
        cmd_serve(args.port)
    elif args.command == "analyze":
        cmd_analyze(args.ticker, fast=args.fast, enable_masters=args.masters)
    elif args.command == "daily":
        cmd_daily()
    elif args.command == "screen":
        cmd_screen(style=args.style, limit=args.limit)
    elif args.command == "backtest":
        cmd_backtest(args.codes, strategy=args.strategy, days=args.days, capital=args.capital)
    elif args.command == "plan":
        cmd_plan(fast=not args.full, show_only=args.show)
    elif args.command == "schedule":
        cmd_schedule(
            update_time=args.update_time,
            screen_time=args.screen_time,
            plan_time=args.plan_time,
            once=args.once,
            skip_weekend=not args.no_skip_weekend,
        )
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
