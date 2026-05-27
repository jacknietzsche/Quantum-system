#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
run_portfolio_v2.py — v2 模拟持仓调仓入口
============================================
基于 core 统一架构的持仓管理入口。

用法:
    python run_portfolio_v2.py                    # 使用今日
    python run_portfolio_v2.py --date 20260327    # 指定日期
"""

import os as _boot_os
_boot_os.environ['DISABLE_TQDM'] = 'true'
del _boot_os

import argparse
import logging
from datetime import datetime

from core.logging_config import setup_logging, get_logger

setup_logging()
logger = get_logger(__name__)

# 静音子模块（防止 openai/httpx 日志格式冲突）
for mod in ["httpx", "openai", "urllib3"]:
    logging.getLogger(mod).setLevel(logging.WARNING)


def main():
    parser = argparse.ArgumentParser(description='v2 模拟持仓调仓')
    parser.add_argument('--date', type=str, default=None, help='调仓日期 YYYYMMDD')
    parser.add_argument('--capital', type=float, default=100000, help='初始资金')
    parser.add_argument('--top', type=int, default=10, help='持仓股票数量')
    args = parser.parse_args()

    from core.config import QuantConfig
    from core.data import UnifiedDataFetcher
    from core.risk import PositionManager
    from core.report import PortfolioReportGenerator

    # 使用旧版 DefaultStrategy（从 v14 报告读取）
    from portfolio_manager import DefaultStrategy

    date_str = args.date or datetime.now().strftime('%Y%m%d')

    logger.info(f"模拟持仓调仓 — 日期: {date_str}")

    # 配置
    cfg = QuantConfig()
    cfg.portfolio.initial_cash = args.capital
    cfg.selection.top_n = args.top
    cfg.ensure_dirs()

    # 初始化
    fetcher = UnifiedDataFetcher(cfg.data)
    strategy = DefaultStrategy(
        report_dir=cfg.report.selection_report_dir,
        top_n=args.top,
    )

    pm = PositionManager(config=cfg, data_fetcher=fetcher, strategy=strategy)

    # 执行调仓
    result = pm.run_daily_rebalance(date_str)

    if result['status'] == 'no_signals':
        logger.warning(f"无选股信号 ({date_str})")
        return

    logger.info(f"调仓完成: 买入 {result['bought']} 只, 卖出 {result['sold']} 只")

    # 生成报告
    reporter = PortfolioReportGenerator(cfg)
    report_path = reporter.generate(result, position_manager=pm)
    logger.info(f"报告: {report_path}")

    # 打印持仓
    holdings = pm.get_current_holdings()
    if not holdings.empty:
        logger.info("当前持仓:")
        for _, h in holdings.iterrows():
            pnl_cls = '+' if h.get('pnl', 0) >= 0 else ''
            logger.info(f"  {h['code']} {h['name']:10s} "
                        f"{h['shares']}股 @ {h['cost_price']:.2f} "
                        f"→ {h['current_price']:.2f}  {pnl_cls}{h.get('pnl', 0):.0f} ({h.get('pnl_pct', 0):+.1f}%)")

    return report_path


if __name__ == '__main__':
    main()
