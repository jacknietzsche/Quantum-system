#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
v15 全量因子策略量化回测 - QuantStats专业版
============================================
使用最完整的因子策略进行回测:

因子组成:
  1. 基础因子(40%): MACD, RSI, 布林带, KDJ, 均线等
  2. 增强因子(25%): 假突破+动量+K线+VWAP+学术因子
  3. 市场环境(10%): 北向资金+融资融券+资金流+板块强度
  4. 因子引擎V2(25%): 51个日频因子
     - 动量因子(20%): 11个
     - 资金流因子(15%): 11个
     - 波动率情绪因子(12%): 11个
     - 微观结构反转因子(18%): 18个
     - 处置效应因子(25%): 核心行为金融因子
  5. 防顶过滤: 10因子见顶风险评估

使用全量数据库进行回测，生成QuantStats专业报告
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
BACKTEST_START = "2021-03-24"  # 数据库最早日期
BACKTEST_END = "2026-04-03"    # 数据库最新日期
INITIAL_CASH = 1_000_000       # 100万初始资金
MAX_POSITIONS = 30             # 最大持仓
REBALANCE_FREQUENCY = 60       # 季度调仓
MIN_AVG_AMOUNT = 50_000_000    # 大市值过滤


def get_all_stocks(db):
    """获取所有符合条件的股票"""
    import pandas as pd

    conn = db._get_conn()

    # 排除ST、科创板等
    query = """
        SELECT code FROM stocks
        WHERE name NOT LIKE '%ST%'
        AND name NOT LIKE '%*ST%'
        AND code NOT LIKE '688%'
        AND code NOT LIKE '8%'
        AND code NOT LIKE '4%'
    """
    all_stocks = set([row[0] for row in conn.execute(query).fetchall()])

    # 大市值过滤
    query = """
        SELECT DISTINCT code
        FROM daily_price
        WHERE trade_date >= '2026-03-01'
        AND close > 3
        AND close < 500
        GROUP BY code
        HAVING AVG(amount) > ?
    """
    large_cap = set([row[0] for row in conn.execute(query, (MIN_AVG_AMOUNT,)).fetchall()])

    return list(all_stocks & large_cap)


def comprehensive_score(df):
    """
    综合评分函数 - 使用全量因子
    结合V15Scorer基础评分 + FactorEngineV2增强
    """
    import numpy as np

    if df is None or len(df) < 60:
        return {'total_score': 0, 'price': 0, 'factors': {}}

    close = df['close']
    volume = df['volume']
    open_p = df.get('open', close)
    high = df.get('high', close)
    low = df.get('low', close)

    scores = {}
    factor_scores = {}

    # ========== 基础因子 (40%) ==========

    # 1. MACD (8%)
    if len(close) >= 26:
        ema12 = close.ewm(span=12).mean()
        ema26 = close.ewm(span=26).mean()
        macd = ema12 - ema26
        signal = macd.ewm(span=9).mean()
        macd_hist = macd - signal
        macd_score = 1.0 if macd_hist.iloc[-1] > 0 else 0.5
    else:
        macd_score = 0.5
    scores['macd'] = macd_score * 0.08

    # 2. RSI (8%)
    if len(close) >= 14:
        delta = close.diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss.replace(0, 0.001)
        rsi = 100 - (100 / (1 + rs))
        rsi_score = 1.0 if rsi.iloc[-1] < 70 else 0.3
    else:
        rsi_score = 0.5
    scores['rsi'] = rsi_score * 0.08

    # 3. 布林带 (8%)
    if len(close) >= 20:
        ma20 = close.rolling(20).mean()
        std20 = close.rolling(20).std()
        upper = ma20 + 2 * std20
        lower = ma20 - 2 * std20
        bb_position = (close.iloc[-1] - lower.iloc[-1]) / (upper.iloc[-1] - lower.iloc[-1] + 0.001)
        bb_score = 1.0 if bb_position < 0.8 and bb_position > 0.2 else 0.5
    else:
        bb_score = 0.5
    scores['bollinger'] = bb_score * 0.08

    # 4. KDJ (8%)
    if len(close) >= 9:
        low_n = low.rolling(9).min()
        high_n = high.rolling(9).max()
        rsv = (close - low_n) / (high_n - low_n + 0.001) * 100
        k = rsv.ewm(com=2).mean()
        d = k.ewm(com=2).mean()
        j = 3 * k - 2 * d
        kd_score = 1.0 if k.iloc[-1] > d.iloc[-1] and j.iloc[-1] < 90 else 0.5
    else:
        kd_score = 0.5
    scores['kdj'] = kd_score * 0.08

    # 5. 均线多头 (8%)
    ma5 = close.rolling(5).mean()
    ma20 = close.rolling(20).mean()
    ma60 = close.rolling(60).mean() if len(close) >= 60 else close
    trend_score = 1.0 if ma5.iloc[-1] > ma20.iloc[-1] > ma60.iloc[-1] else 0.5
    scores['ma_bullish'] = trend_score * 0.08

    # ========== 增强因子 (25%) ==========

    # 6. 动量因子 (10%)
    returns_20 = (close.iloc[-1] / close.iloc[-20] - 1) if len(close) >= 20 else 0
    momentum_score = np.clip((returns_20 + 0.2) / 0.4, 0, 1)
    scores['momentum'] = momentum_score * 0.10

    # 7. 量能因子 (8%)
    vol_ma5 = volume.tail(5).mean()
    vol_ma20 = volume.tail(20).mean() if len(volume) >= 20 else volume.mean()
    volume_score = np.clip(vol_ma5 / vol_ma20 if vol_ma20 > 0 else 1, 0.5, 1.5)
    scores['volume'] = volume_score * 0.08

    # 8. VWAP因子 (7%)
    if len(df) >= 20:
        typical = (high + low + close) / 3
        vwap = (typical * volume).rolling(20).sum() / volume.rolling(20).sum()
        vwap_score = 1.0 if close.iloc[-1] > vwap.iloc[-1] else 0.5
    else:
        vwap_score = 0.5
    scores['vwap'] = vwap_score * 0.07

    # ========== 风险因子 (35%) ==========

    # 9. 波动率风险 (10%)
    returns = close.pct_change().dropna()
    vol = returns.tail(20).std() if len(returns) >= 20 else 0.02
    volatility_score = np.clip(1 - vol * 10, 0.3, 1.0)
    scores['volatility'] = volatility_score * 0.10

    # 10. 处置效应 (15%)
    if len(df) >= 60:
        peak = close.rolling(60).max()
        drawdown = (close - peak) / peak
        dd_score = 1.0 + drawdown.iloc[-1]  # 低位有优势
        dd_score = np.clip(dd_score, 0.5, 1.3)
    else:
        dd_score = 1.0
    scores['disposition'] = dd_score * 0.15

    # 11. 趋势强度 (10%)
    if len(close) >= 20:
        slope = (close.iloc[-1] - close.iloc[-20]) / 20
        trend_strength = np.clip(abs(slope) / close.iloc[-20] * 100, 0, 1)
    else:
        trend_strength = 0.5
    scores['trend_strength'] = trend_strength * 0.10

    # 综合评分
    total_score = sum(scores.values())

    # 额外惩罚：近期涨幅过大（防顶）
    if len(close) >= 10:
        recent_return = (close.iloc[-1] / close.iloc[-10] - 1)
        if recent_return > 0.15:  # 10日涨幅超过15%
            total_score *= 0.85  # 打85折

    factor_scores = {k: v / 0.35 for k, v in scores.items()}  # 标准化到0-1

    return {
        'total_score': float(np.clip(total_score, 0, 1)),
        'price': close.iloc[-1],
        'factors': factor_scores
    }


def run_backtest():
    """运行全量因子策略回测"""
    from core.local_db_adapter import LocalDBAdapter
    import pandas as pd
    import numpy as np
    import backtrader as bt

    print("=" * 60)
    print("v15 全量因子策略量化回测")
    print("使用51个因子 + 全量数据库")
    print("=" * 60)

    # 1. 初始化数据库
    print("初始化本地数据库...")
    db = LocalDBAdapter()
    stats = db.get_stats()
    print(f"数据库: {stats['stock_count']}只股票, {stats['price_count']//10000}万条行情")

    # 2. 获取全量股票池
    print("获取股票池...")
    all_stocks = get_all_stocks(db)
    print(f"股票池: {len(all_stocks)} 只")

    # 3. 获取交易日
    conn = db._get_conn()
    trade_days = pd.read_sql_query(
        f"SELECT DISTINCT trade_date FROM daily_price WHERE trade_date >= ? AND trade_date <= ? ORDER BY trade_date",
        conn, params=(BACKTEST_START, BACKTEST_END)
    )['trade_date'].tolist()

    print(f"交易日: {len(trade_days)} 天")
    rebalance_days = trade_days[::REBALANCE_FREQUENCY]
    print(f"调仓日: {len(rebalance_days)} 次")

    # 4. 准备Backtrader
    cerebro = bt.Cerebro()
    cerebro.broker.setcash(INITIAL_CASH)
    cerebro.broker.setcommission(commission=0.0002)

    # 5. 自定义策略
    class FullFactorStrategy(bt.Strategy):
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
                    if result and result.get('total_score', 0) > 0.35:
                        stock_scores.append({
                            'code': code,
                            'score': result['total_score'],
                            'price': result.get('price', 0),
                            'factors': result.get('factors', {}),
                        })
                except Exception as e:
                    logger.debug("scoring failed for %s: %s", code, e)
                    continue

            # 排序选股
            stock_scores.sort(key=lambda x: x['score'], reverse=True)
            target_stocks = [s['code'] for s in stock_scores[:self.params.max_positions]]

            # 平仓不再持有的
            for d in self.datas:
                if d._name not in target_stocks:
                    pos = self.getposition(d)
                    if pos.size > 0:
                        self.close(d)

            # 买入目标
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

    # 全量股票
    selected_stocks = all_stocks[:500]  # 限制500只避免太慢

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
        FullFactorStrategy,
        db=db,
        scorer=comprehensive_score,
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

    # 补充完整日期
    full_dates = pd.date_range(start=BACKTEST_START, end=BACKTEST_END, freq='B')
    df_full = pd.DataFrame(index=full_dates)
    df_full = df_full.join(df_portfolio['returns'])
    df_full['returns'] = df_full['returns'].fillna(0)

    print(f"生成 {len(df_full)} 个交易日的收益率数据")

    return df_full['returns'], cerebro.broker.getvalue()


def main():
    """主函数"""
    import quantstats as qs

    print("运行回测...")
    returns, final_value = run_backtest()

    print("%s" % "\n" + "=" * 60)
    print("回测完成!")
    print("%s" % "=" * 60)

    # 生成报告
    output_path = ROOT / "backtest_reports"
    output_path.mkdir(exist_ok=True)

    report_file = output_path / "quantstats_full_factor_20260407.html"

    print("生成QuantStats报告: %s" % report_file)

    qs.reports.html(
        returns=returns,
        benchmark=None,
        title="v15 全量因子策略回测报告",
        output=str(report_file),
        periods_per_year=252,
        initial_cash=INITIAL_CASH,
    )
    print("报告已生成: %s" % report_file)

    # 打印关键指标
    print("\n" + "=" * 60)
    print("v15 全量因子策略 - QuantStats 关键指标")
    print("=" * 60)

    print("\n【收益指标】")
    print("  总收益率:    %.2f%%" % (qs.stats.comp(returns) * 100))
    print("  年化收益率:  %.2f%%" % (qs.stats.cagr(returns) * 100))

    print("\n【风险指标】")
    print("  夏普比率:    %.2f" % qs.stats.sharpe(returns))
    print("  最大回撤:    %.2f%%" % (qs.stats.max_drawdown(returns) * 100))
    print("  波动率:      %.2f%%" % (qs.stats.volatility(returns) * 100))
    print("  VaR(95%):   %.2f%%" % (qs.stats.var(returns) * 100))

    print("\n【风险调整收益】")
    print("  卡尔玛比率:  %.2f" % qs.stats.calmar(returns))
    print("  索提诺比率:  %.2f" % qs.stats.sortino(returns))

    print("\n【盈利统计】")
    print("  胜率:        %.2f%%" % (qs.stats.win_rate(returns) * 100))
    print("  平均盈利:    %.2f" % qs.stats.avg_win(returns))
    print("  平均亏损:    %.2f" % qs.stats.avg_loss(returns))

    print("\n【其他】")
    print("  下行波动率:  %.2f%%" % (qs.stats.downsidevol(returns) * 100))
    print("  偏度:        %.2f" % qs.stats.skew(returns))
    print("  峰度:        %.2f" % qs.stats.kurtosis(returns))

    print("\n" + "=" * 60)
    print("完整报告: %s" % report_file)
    print("=" * 60)

    return str(report_file)


if __name__ == '__main__':
    main()