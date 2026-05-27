#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
v15 大市值股票量化回测 - QuantStats专业版
============================================
使用QuantStats生成专业回测报告

回测设置:
- 时间范围: 2021-03-24 ~ 2026-04-03（数据库完整日期）
- 选股池: 100亿市值以上
- 持仓: 最多 30 只，等权重
- 调仓频率: 季度（60个交易日）
- 初始资金: 100 万
"""

import logging
from pathlib import Path

from core.logging_config import setup_logging, get_logger

setup_logging()
logger = get_logger(__name__)

# 静音子模块
for mod in ["httpx", "openai", "urllib3", "matplotlib", "seaborn"]:
    logging.getLogger(mod).setLevel(logging.WARNING)

ROOT = Path(__file__).resolve().parent

# 回测参数
BACKTEST_START = "2021-03-24"
BACKTEST_END = "2026-04-03"
INITIAL_CASH = 1_000_000
MAX_POSITIONS = 30
REBALANCE_FREQUENCY = 60

# 大市值过滤条件
MIN_AVG_AMOUNT = 50_000_000
MIN_PRICE = 3
MAX_PRICE = 500


def get_large_cap_pool(db):
    """从本地数据库获取大市值股票池"""
    import pandas as pd

    conn = db._get_conn()

    query = """
        SELECT code, AVG(amount) as avg_amount, AVG(close) as avg_close
        FROM daily_price
        WHERE trade_date >= '2026-03-01'
        AND close > ?
        AND close < ?
        GROUP BY code
        HAVING avg_amount > ?
    """
    df = pd.read_sql_query(query, conn, params=(MIN_PRICE, MAX_PRICE, MIN_AVG_AMOUNT))

    query_st = "SELECT code FROM stocks WHERE name LIKE '%ST%' OR name LIKE '%*ST%'"
    st_codes = set([row[0] for row in conn.execute(query_st).fetchall()])

    df = df[~df['code'].isin(st_codes)]
    print(f"大市值股票池: {len(df)} 只")
    return df['code'].tolist()


def simple_score(df):
    """简单技术指标评分"""
    import numpy as np

    if df is None or len(df) < 60:
        return {'total_score': 0, 'price': 0}

    close = df['close']
    volume = df['volume']

    returns_20 = (close.iloc[-1] / close.iloc[-20] - 1) if len(df) >= 20 else 0
    momentum_score = np.clip((returns_20 + 0.2) / 0.4, 0, 1) if returns_20 else 0.5

    ma5 = close.tail(5).mean()
    ma20 = close.tail(20).mean() if len(df) >= 20 else close.mean()
    trend_score = 1.0 if ma5 > ma20 else 0.5

    vol_ma5 = volume.tail(5).mean()
    vol_ma20 = volume.tail(20).mean() if len(df) >= 20 else volume.mean()
    volume_score = np.clip(vol_ma5 / vol_ma20 if vol_ma20 > 0 else 1, 0.5, 1.5)

    returns = close.pct_change().dropna()
    vol = returns.tail(20).std() if len(returns) >= 20 else 0.02
    volatility_score = np.clip(1 - vol * 10, 0.3, 1.0)

    total_score = (momentum_score * 0.3 + trend_score * 0.3 +
                   volume_score * 0.2 + volatility_score * 0.2)
    total_score = float(np.clip(total_score, 0, 1))

    return {'total_score': total_score, 'price': close.iloc[-1]}


def run_backtest():
    """运行回测并返回每日收益率序列"""
    from core.local_db_adapter import LocalDBAdapter
    import pandas as pd
    import numpy as np
    import backtrader as bt

    print("=" * 60)
    print("v15 大市值股票量化回测 - QuantStats版")
    print("=" * 60)

    # 1. 初始化本地数据库
    print("初始化本地数据库...")
    db = LocalDBAdapter()
    stats = db.get_stats()
    print(f"数据库: {stats['stock_count']}只股票, {stats['price_count']//10000}万条行情")

    # 2. 获取大市值股票池
    print("获取大市值股票池...")
    large_cap_pool = get_large_cap_pool(db)

    # 3. 获取交易日
    conn = db._get_conn()
    trade_days = pd.read_sql_query(
        f"SELECT DISTINCT trade_date FROM daily_price WHERE trade_date >= ? AND trade_date <= ? ORDER BY trade_date",
        conn, params=(BACKTEST_START, BACKTEST_END)
    )['trade_date'].tolist()

    print(f"交易日: {len(trade_days)} 天")
    rebalance_days = trade_days[::REBALANCE_FREQUENCY]
    print(f"调仓日: {len(rebalance_days)} 次")

    # 4. 准备 Backtrader
    cerebro = bt.Cerebro()
    cerebro.broker.setcash(INITIAL_CASH)
    cerebro.broker.setcommission(commission=0.0002)

    # 5. 自定义策略 - 记录每日组合价值
    class MonthlyRebalance(bt.Strategy):
        params = (
            ('max_positions', MAX_POSITIONS),
            ('db', None),
            ('scorer', None),
            ('trade_days', []),
            ('rebalance_idx', 0),
            ('portfolio_values', []),
            ('dates', []),
        )

        def __init__(self):
            self.orders = {}

        def next(self):
            # 记录每日组合价值
            self.params.portfolio_values.append(self.broker.getvalue())
            self.params.dates.append(self.datas[0].datetime.date(0))

            current_date = self.datas[0].datetime.date(0)
            date_str = current_date.strftime('%Y-%m-%d')

            if self.params.rebalance_idx < len(self.params.trade_days):
                next_rebalance = self.params.trade_days[self.params.rebalance_idx]
                if date_str >= next_rebalance:
                    self.rebalance(current_date)
                    self.params.rebalance_idx += 1

        def rebalance(self, current_date):
            db = self.params.db
            scorer = self.params.scorer
            all_codes = [d._name for d in self.datas]

            stock_scores = []
            for code in all_codes:
                try:
                    df = db.get_price(code, "2024-01-01", current_date.strftime('%Y-%m-%d'))
                    if len(df) < 60:
                        continue
                    result = scorer(df)
                    if result and result.get('total_score', 0) > 0.3:
                        stock_scores.append({
                            'code': code,
                            'score': result['total_score'],
                            'price': result.get('price', 0),
                        })
                except Exception as e:
                    logger.debug("scoring failed for %s: %s", code, e)
                    continue

            stock_scores.sort(key=lambda x: x['score'], reverse=True)
            target_stocks = [s['code'] for s in stock_scores[:self.params.max_positions]]

            current_positions = set()
            for d in self.datas:
                pos = self.getposition(d)
                if pos.size > 0:
                    current_positions.add(d._name)

            for d in self.datas:
                if d._name not in target_stocks:
                    pos = self.getposition(d)
                    if pos.size > 0:
                        self.close(d)

            if target_stocks:
                weight = 1.0 / len(target_stocks)
                for code in target_stocks:
                    for d in self.datas:
                        if d._name == code:
                            pos = self.getposition(d)
                            if pos.size == 0:
                                target_value = self.broker.getvalue() * weight
                                size = int(target_value / d.close[0] / 100) * 100
                                if size > 0:
                                    self.buy(d, size=size)
                            break

    # 6. 添加数据
    print("添加回测数据...")
    import random
    random.seed(42)
    selected_stocks = large_cap_pool[:200]

    success_count = 0
    for code in selected_stocks:
        df = db.get_price_for_backtest(code, BACKTEST_START, BACKTEST_END)
        if len(df) < 100:
            continue
        df = df.rename(columns={'date': 'datetime'})
        df['datetime'] = pd.to_datetime(df['datetime'])
        df = df.set_index('datetime')
        try:
            data = bt.feeds.PandasData(dataname=df)
            cerebro.adddata(data, name=code)
            success_count += 1
        except Exception as e:
            logger.debug("data add failed for %s: %s", code, e)
            continue

    print("添加 %s 只股票数据" % success_count)

    # 7. 添加策略
    cerebro.addstrategy(
        MonthlyRebalance,
        db=db,
        scorer=simple_score,
        trade_days=rebalance_days,
    )

    # 8. 添加分析器
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name='sharpe')
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name='drawdown')
    cerebro.addanalyzer(bt.analyzers.Returns, _name='returns')
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name='trades')

    # 9. 运行回测
    print("开始回测...")
    results = cerebro.run()

    # 10. 获取结果
    strat = results[0]
    portfolio_values = strat.params.portfolio_values
    dates = strat.params.dates

    # 计算每日收益率
    df_portfolio = pd.DataFrame({
        'date': dates,
        'value': portfolio_values
    })
    df_portfolio['date'] = pd.to_datetime(df_portfolio['date'])
    df_portfolio.set_index('date', inplace=True)

    # 计算日收益率
    df_portfolio['returns'] = df_portfolio['value'].pct_change()

    # 补充初始日期的收益率（从1开始）
    full_dates = pd.date_range(start=BACKTEST_START, end=BACKTEST_END, freq='B')
    df_full = pd.DataFrame(index=full_dates)
    df_full = df_full.join(df_portfolio['returns'])
    df_full['returns'] = df_full['returns'].fillna(0)

    print(f"生成 {len(df_full)} 个交易日的收益率数据")

    return df_full['returns'], cerebro.broker.getvalue()


def main():
    """主函数 - 生成QuantStats报告"""
    import quantstats as qs

    print("运行回测...")
    returns, final_value = run_backtest()

    # 输出结果摘要
    print("%s" % "\n" + "=" * 60)
    print("回测完成!")
    print("%s" % "=" * 60)

    # 生成QuantStats完整报告
    output_path = ROOT / "backtest_reports"
    output_path.mkdir(exist_ok=True)

    report_file = output_path / "quantstats_report_large_cap_20260407.html"

    print("生成QuantStats报告: %s" % report_file)

    # 生成完整HTML报告
    qs.reports.html(
        returns=returns,
        benchmark=None,  # 无基准收益
        title="v15 大市值量化策略回测报告",
        output=str(report_file),
        periods_per_year=252,
        initial_cash=INITIAL_CASH,
    )
    print("报告已生成: %s" % report_file)

    # 同时打印关键指标到控制台
    print("\n" + "=" * 60)
    print("QuantStats 关键指标摘要")
    print("=" * 60)

    print("\n策略收益率:")
    print("  总收益率: %.2f%%" % (qs.stats.comp(returns) * 100))
    print("  年化收益率: %.2f%%" % (qs.stats.cagr(returns) * 100))

    print("\n风险指标:")
    print("  夏普比率: %.2f" % qs.stats.sharpe(returns))
    print("  最大回撤: %.2f%%" % (qs.stats.max_drawdown(returns) * 100))
    print("  波动率: %.2f%%" % (qs.stats.volatility(returns) * 100))
    print("  VaR(95%): %.2f%%" % (qs.stats.var(returns) * 100))
    print("  CVaR(95%): %.2f%%" % (qs.stats.cvar(returns) * 100))

    print("\n风险调整收益:")
    print("  卡尔玛比率: %.2f" % qs.stats.calmar(returns))
    print("  索提诺比率: %.2f" % qs.stats.sortino(returns))

    print("\n盈利统计:")
    print("\n盈利统计:")
    print("  胜率: %.2f%%" % (qs.stats.win_rate(returns) * 100))
    print("  平均盈利: %.2f" % qs.stats.avg_win(returns))
    print("  平均亏损: %.2f" % qs.stats.avg_loss(returns))
    print("  盈亏比: %.2f" % qs.stats.win_loss_ratio(returns))

    print("\n其他指标:")
    print("  收益波动率: %.2f%%" % (qs.stats.volatility(returns) * 100))
    print("  下行波动率: %.2f%%" % (qs.stats.downsidevol(returns) * 100))
    print("  最长亏损期: %d 天" % qs.stats.longest_win_streak(returns))
    print("  最长盈利期: %d 天" % qs.stats.longest_loss_streak(returns))

    print("\n" + "=" * 60)
    print("完整报告: %s" % report_file)
    print("=" * 60)

    return str(report_file)


if __name__ == '__main__':
    main()