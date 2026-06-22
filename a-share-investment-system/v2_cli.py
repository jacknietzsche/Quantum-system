#!/usr/bin/env python
"""
AShare-X v2 — 多 Agent 交易决策系统 CLI

参考 TradingAgents CLI 设计,提供:
  python v2_cli.py analyze 600519           # 单股深度分析
  python v2_cli.py analyze 600519 --date 2026-05-30  # 指定日期
  python v2_cli.py analyze 600519 --checkpoint        # 启用检查点
  python v2_cli.py clear-checkpoints                  # 清除所有检查点
  python v2_cli.py memory                             # 查看记忆日志
"""

import argparse
import io
import os
import sys
from datetime import datetime

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)

# Windows 编码兼容
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


def cmd_analyze(args):
    """单股深度分析"""
    from rich.console import Console
    from rich.panel import Panel

    from graph_v2 import AShareTradingGraph
    from graph_v2.default_config import get_default_config

    console = Console()
    stock_code = args.code
    trade_date = args.date or datetime.now().strftime("%Y-%m-%d")

    config = get_default_config()
    if args.checkpoint:
        config["checkpoint_enabled"] = True
    if args.provider:
        config["llm_provider"] = args.provider
    if args.deep_model:
        config["deep_think_llm"] = args.deep_model
    if args.quick_model:
        config["quick_think_llm"] = args.quick_model
    if args.rounds:
        config["max_debate_rounds"] = args.rounds
        config["max_risk_discuss_rounds"] = args.rounds

    # A 股特色分析师
    analysts = ["market", "sentiment", "news", "fundamentals"]
    if args.northbound:
        analysts.append("northbound")
    if args.sector:
        analysts.append("sector")

    console.print(
        Panel(
            f"[bold blue]🚀 A 股多 Agent 决策分析[/bold blue]\n"
            f"股票: {stock_code} | 日期: {trade_date}\n"
            f"LLM: {config['llm_provider']} / {config['quick_think_llm']}\n"
            f"分析师: {', '.join(analysts)}\n"
            f"辩论轮次: {config['max_debate_rounds']}",
            border_style="blue",
        )
    )

    try:
        graph = AShareTradingGraph(
            selected_analysts=analysts,
            debug=args.debug,
            config=config,
        )

        with console.status(f"[cyan]正在分析 {stock_code}..."):
            _, signal = graph.propagate(
                stock_code=stock_code,
                trade_date=trade_date,
            )

        # 输出结果
        action = signal.get("action", "neutral")
        action_color = {
            "strong_buy": "bold green",
            "buy": "green",
            "hold": "yellow",
            "sell": "red",
            "strong_sell": "bold red",
        }.get(action, "white")

        console.print(
            Panel(
                f"[{action_color}]决策: {action.upper()}[/{action_color}]\n"
                f"置信度: {signal.get('confidence', 0):.0%}\n\n"
                f"{signal.get('reasoning', '')[:500]}",
                title="📊 最终决策",
                border_style="green"
                if "buy" in action
                else ("red" if "sell" in action else "yellow"),
            )
        )

        # 输出各分析师报告摘要
        if args.verbose and graph.curr_state:
            state = graph.curr_state
            for report_key, title in [
                ("market_report", "📈 技术分析"),
                ("sentiment_report", "💭 情绪分析"),
                ("news_report", "📰 新闻分析"),
                ("fundamentals_report", "📊 基本面"),
                ("northbound_report", "🌏 北向资金"),
                ("sector_report", "🏭 板块分析"),
            ]:
                report = state.get(report_key, "")
                if report:
                    console.print(
                        Panel(
                            report[:800] + ("..." if len(report) > 800 else ""),
                            title=title,
                            border_style="cyan",
                        )
                    )

        # 决策日志路径
        results_dir = config.get("results_dir", "results")
        log_path = os.path.join(
            results_dir, stock_code, "logs", f"full_states_log_{trade_date}.json"
        )
        if os.path.exists(log_path):
            console.print(f"\n[dim]📄 完整日志: {log_path}[/dim]")

    except Exception as e:
        console.print(f"[red]❌ 分析失败: {e}[/red]")
        if args.debug:
            import traceback

            traceback.print_exc()
        return 1

    return 0


def cmd_clear_checkpoints(args):
    """清除所有检查点"""
    from graph_v2 import clear_all_checkpoints
    from graph_v2.default_config import get_default_config

    config = get_default_config()
    data_dir = config.get("data_cache_dir", "data/cache")
    count = clear_all_checkpoints(data_dir)
    print(f"✅ 已清除 {count} 个检查点数据库")
    return 0


def cmd_memory(args):
    """查看记忆日志"""
    from agents_v2.memory import TradingMemory
    from graph_v2.default_config import get_default_config

    config = get_default_config()
    memory = TradingMemory(
        {
            "memory_log_path": config.get("memory_log_path"),
        }
    )

    entries = memory.load_entries()
    if not entries:
        print("📭 记忆日志为空")
        return 0

    print(f"📚 记忆日志: {len(entries)} 条目\n")
    for i, entry in enumerate(entries[-10:], 1):  # 显示最近 10 条
        status = (
            "⏳ pending"
            if entry.get("pending")
            else f"收益{entry.get('raw_return', '?')} 超额{entry.get('alpha_return', '?')}"
        )
        print(f"  {i}. [{entry['date']} | {entry['stock_code']} | {entry['rating']} | {status}]")
        if entry.get("reflection"):
            print(f"     反思: {entry['reflection'][:100]}...")

    return 0


def main():
    parser = argparse.ArgumentParser(
        description="AShare-X v2 多 Agent 交易决策系统",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    sub = parser.add_subparsers(dest="command")

    # analyze
    p = sub.add_parser("analyze", help="单股深度分析")
    p.add_argument("code", help="股票代码 (如 600519)")
    p.add_argument("--date", help="分析日期 (YYYY-MM-DD)")
    p.add_argument("--checkpoint", action="store_true", help="启用检查点恢复")
    p.add_argument("--provider", help="LLM 提供商 (siliconflow/deepseek/openai/...)")
    p.add_argument("--deep-model", help="深度思考模型")
    p.add_argument("--quick-model", help="快速思考模型")
    p.add_argument("--rounds", type=int, help="辩论轮次")
    p.add_argument("--northbound", action="store_true", help="启用北向资金分析")
    p.add_argument("--sector", action="store_true", help="启用板块分析")
    p.add_argument("--verbose", "-v", action="store_true", help="显示详细报告")
    p.add_argument("--debug", action="store_true", help="调试模式")

    # clear-checkpoints
    sub.add_parser("clear-checkpoints", help="清除所有检查点")

    # memory
    sub.add_parser("memory", help="查看记忆日志")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 0

    cmds = {
        "analyze": cmd_analyze,
        "clear-checkpoints": cmd_clear_checkpoints,
        "memory": cmd_memory,
    }

    return cmds[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
