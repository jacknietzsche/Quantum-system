#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
全因子量化策略回测系统（QuantStats专业版）
=============================================
使用最新的因子引擎V2 + V15Scorer，包含行为金融学+经典多因子

特性:
1. 包含所有51个日频因子 + 8个行为金融学/经典多因子 = 59+因子
2. 使用全量数据库数据（2021-03-24 ~ 2026-04-03）
3. 排除100亿市值以下股票（通过成交额近似过滤）
4. 生成QuantStats专业HTML回测报告
"""

import warnings
warnings.filterwarnings('ignore')

import os
import sys
import logging
from datetime import datetime, timedelta
from pathlib import Path

from core.logging_config import setup_logging, get_logger

# 修复Windows GBK编码问题
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

setup_logging()
logger = get_logger(__name__)

# 静音子模块
for mod in ["httpx", "openai", "urllib3"]:
    logging.getLogger(mod).setLevel(logging.WARNING)

ROOT = Path(__file__).resolve().parent

import pandas as pd
import numpy as np
import backtrader as bt

# ============================================================
# 回测参数配置
# ============================================================
BACKTEST_START = "2021-03-24"   # 数据库最早日期
BACKTEST_END = "2026-04-03"     # 数据库最新日期
INITIAL_CASH = 1_000_000        # 初始资金100万
MAX_POSITIONS = 30              # 最大持仓数
REBALANCE_FREQUENCY = 60        # 调仓周期（60交易日≈1季度）
TOP_N = 10                     # 每期选股数量
MIN_AMOUNT = 5e8               # 最小日均成交额（5亿元≈大市值）
MIN_PRICE = 3                  # 最低股价


def get_large_cap_stock_pool(db, limit=500):
    """
    从本地数据库获取大市值候选股票池
    
    过滤条件:
    - 排除ST/*ST股票
    - 排除科创板(688)/北交所(8x)
    - 平均成交额 > 5亿元（近似大市值筛选）
    - 平均收盘价 > 3元（排除低价股）
    """
    conn = db._get_conn()
    
    # 基础查询：排除ST和科创板
    base_query = """
        SELECT s.code, s.name 
        FROM stocks s
        WHERE s.name NOT LIKE '%ST%'
          AND s.name NOT LIKE '%*ST%'
          AND s.code NOT LIKE '688%'
          AND s.code NOT LIKE '8%'
          AND s.code NOT LIKE '4%'
    """
    
    df = pd.read_sql_query(base_query, conn)
    
    if len(df) == 0:
        return []
    
    filtered_stocks = []
    
    for _, row in df.iterrows():
        code = row['code']
        
        try:
            # 获取最近20个交易日的数据用于过滤
            price_df = pd.read_sql_query(
                "SELECT close, amount FROM daily_price WHERE code=? ORDER BY trade_date DESC LIMIT ?",
                conn, params=(code, 20)
            )
            
            if len(price_df) < 10:
                continue
            
            avg_amount = price_df['amount'].mean()
            avg_price = price_df['close'].mean()
            
            # 过滤条件
            if avg_amount < MIN_AMOUNT:
                continue
            if avg_price < MIN_PRICE:
                continue
            
            filtered_stocks.append({
                'code': code,
                'name': row['name'],
                'avg_amount': avg_amount,
                'avg_price': avg_price,
            })
            
        except Exception as e:
            continue
        
        if len(filtered_stocks) >= limit:
            break
    
    print(f"大市值股票池: {len(filtered_stocks)} 只 (均额>{MIN_AMOUNT/1e8:.0f}亿, 均价>{MIN_PRICE}元)")
    return filtered_stocks


def all_factor_score(df):
    """
    全因子评分函数 - 整合 FactorEngineV2 和基础技术评分
    
    Returns:
        dict: {'total_score': float, 'price': float, 'factor_detail': dict}
    """
    from factor_engine_v2 import FactorEngineV2
    from core.strategy import V15Scorer
    
    if df is None or len(df) < 60:
        return {'total_score': 0, 'price': 0, 'factor_detail': {}}
    
    try:
        # 1. 因子引擎计算
        engine = FactorEngineV2()
        factor_result = engine.calculate(df)
        adjustment_coef = factor_result.get('adjustment_coef', 1.0)
        category_scores = factor_result.get('category_scores', {})
        
        # 2. V15Scorer基础评分
        scorer = V15Scorer()
        base_score = scorer.calculate_score(df)
        
        # 3. 综合评分
        total_score = float(base_score * adjustment_coef)
        total_score = max(0, min(total_score, 2.0))  # 限制范围
        
        return {
            'total_score': total_score,
            'price': float(df['close'].iloc[-1]),
            'base_score': float(base_score),
            'adjustment_coef': float(adjustment_coef),
            'category_scores': category_scores,
        }
        
    except Exception as e:
        print("全因子评分失败: %s" % e)
        return {'total_score': 0, 'price': 0, 'factor_detail': {}}


def run_all_factors_backtest():
    """运行全因子量化策略回测"""
    from core.local_db_adapter import LocalDBAdapter
    
    print("=" * 70)
    print("全因子量化策略回测 (QuantStats专业版)")
    print("开始时间: %s" % datetime.now())
    print("回测区间: %s ~ %s" % (BACKTEST_START, BACKTEST_END))
    print("初始资金: ¥%s" % INITIAL_CASH)
    print("=" * 70)
    
    # 1. 初始化数据库
    print("初始化本地数据库...")
    db = LocalDBAdapter()
    stats = db.get_stats()
    print(f"数据库: {stats['stock_count']}只股票, {stats['price_count']//10000}万条行情")
    print(f"数据范围: {stats['date_min']} ~ {stats['date_max']}")
    
    # 2. 获取大市值股票池
    stock_pool = get_large_cap_stock_pool(db, limit=500)
    
    if len(stock_pool) == 0:
        print("没有符合条件的股票！请检查过滤条件。")
        return None
    
    # 3. 加载回测数据
    print("加载 %s ~ %s 回测数据..." % (BACKTEST_START, BACKTEST_END))
    
    # 获取所有交易日
    conn = db._get_conn()
    trade_days = pd.read_sql_query(
        """SELECT DISTINCT trade_date FROM daily_price 
           WHERE trade_date >= ? AND trade_date <= ? 
           ORDER BY trade_date""",
        conn, params=(BACKTEST_START, BACKTEST_END)
    )['trade_date'].tolist()
    
    if len(trade_days) < 50:
        print("交易日数据不足，回测无法进行")
        return None
    
    print(f"交易日: {len(trade_days)} 天")
    
    # 计算调仓日期
    rebalance_days = trade_days[::REBALANCE_FREQUENCY]
    print(f"计划调仓次数: {len(rebalance_days)} 次")
    
    # 4. 创建Backtrader引擎
    cerebro = bt.Cerebro()
    cerebro.broker.setcash(INITIAL_CASH)
    cerebro.broker.setcommission(commission=0.001)  # 0.1%佣金
    
    # 5. 自定义策略类
    class AllFactorsStrategy(bt.Strategy):
        params = (
            ('max_positions', MAX_POSITIONS),
            ('top_n', TOP_N),
            ('db', None),
            ('trade_days', []),
            ('rebalance_idx', 0),
        )
        
        def __init__(self):
            self.orders = {}
            self.last_rebalance_date = None
            self.trade_log = []  # 交易日志
            self.daily_values = []  # 每日净值记录
            
        def log(self, txt, dt=None):
            dt = dt or self.datas[0].datetime.date(0)
            print("%s %s" % (dt.isoformat(), txt))
        
        def notify_order(self, order):
            if order.status in [order.Completed]:
                code = order.data._name
                direction = '买入' if order.isbuy() else '卖出'
                price = order.executed.price
                size = order.executed.size
                value = order.executed.value
                
                self.trade_log.append({
                    'date': self.datas[0].datetime.date(0).isoformat(),
                    'code': code,
                    'direction': direction,
                    'price': price,
                    'size': size,
                    'value': value,
                })
                
                print("  %s: %s, 价格: %.2f, 数量: %d, 金额: %.0f" % (direction, code, price, size, value))
        
        def next(self):
            current_date = self.datas[0].datetime.date(0)
            
            # 记录每日净值
            self.daily_values.append({
                'date': current_date.isoformat(),
                'value': self.broker.getvalue(),
            })
            
            # 检查是否需要调仓
            if self.params.rebalance_idx < len(self.params.trade_days):
                next_rebalance = self.params.trade_days[self.params.rebalance_idx]
                date_str = current_date.strftime('%Y-%m-%d')
                
                if date_str >= next_rebalance:
                    self.execute_rebalance(current_date)
                    self.params.rebalance_idx += 1
        
        def execute_rebalance(self, current_date):
            """执行调仓逻辑"""
            db = self.params.db
            end_date = current_date.strftime('%Y-%m-%d')
            
            print("\n" + "=" * 50)
            print("[调仓] %s" % end_date)
            print("=" * 50)
            
            all_codes = [d._name for d in self.datas]
            
            # 全因子评分选股
            stock_scores = []
            
            for i, code in enumerate(all_codes):
                try:
                    # 获取到当前日期的历史数据
                    start_dt = (current_date - timedelta(days=400)).strftime('%Y-%m-%d')
                    df = db.get_price(code, start_dt, end_date)
                    
                    if df is None or len(df) < 60:
                        continue
                    
                    result = all_factor_score(df)
                    
                    if result and result.get('total_score', 0) > 0.2:
                        stock_scores.append({
                            'code': code,
                            'score': result.get('total_score', 0),
                            'price': result.get('price', 0),
                            'base_score': result.get('base_score', 0),
                            'adjustment_coef': result.get('adjustment_coef', 1),
                        })
                        
                except Exception as e:
                    continue
                
                # 进度显示
                if (i + 1) % 100 == 0:
                    print(f"  评分进度: {i+1}/{len(all_codes)}...")
            
            # 排序并选择前N只
            stock_scores.sort(key=lambda x: x['score'], reverse=True)
            target_stocks = stock_scores[:self.params.top_n]
            
            if not target_stocks:
                print('没有符合条件的目标股票，跳过调仓')
                return
            
            codes_str = ', '.join(s['code'] for s in target_stocks[:10])
            print(f"目标持仓: [{codes_str}]...")
            for s in target_stocks[:5]:
                print(f"  {s['code']}: 评分={s['score']:.4f}, 因子调整={s['adjustment_coef']:.4f}")
            
            # 当前持仓
            current_positions = set()
            for d in self.datas:
                pos = self.getposition(d)
                if pos.size > 0:
                    current_positions.add(d._name)
            
            # 卖出不在目标中的股票
            for d in self.datas:
                if d._name not in [s['code'] for s in target_stocks]:
                    pos = self.getposition(d)
                    if pos.size > 0:
                        self.close(d)
            
            # 等权重买入目标股票
            weight = 1.0 / len(target_stocks)
            
            for stock in target_stocks:
                code = stock['code']
                for d in self.datas:
                    if d._name == code:
                        pos = self.getposition(d)
                        if pos.size == 0:
                            target_value = self.broker.getvalue() * weight
                            size = int(target_value / d.close[0] / 100) * 100  # 整手
                            if size > 0:
                                self.buy(d, size=size)
                                print("  [买入] %s: %d股, 评分=%.4f" % (code, size, stock['score']))
                        break
            
            print(f"[调仓完成] 持仓 {len(target_stocks)} 只股票")
    
    # 6. 添加股票数据
    print("添加回测数据...")
    
    data_count = 0
    for stock in stock_pool:
        code = stock['code']
        
        try:
            df = db.get_price_for_backtest(code, BACKTEST_START, BACKTEST_END)
            
            if len(df) < 100:
                continue
            
            # 格式转换
            if 'date' in df.columns:
                df = df.rename(columns={'date': 'datetime'})
            if 'datetime' not in df.columns and 'trade_date' in df.columns:
                df = df.rename(columns={'trade_date': 'datetime'})
            
            df['datetime'] = pd.to_datetime(df['datetime'])
            df = df.set_index('datetime')
            
            data = bt.feeds.PandasData(dataname=df)
            cerebro.adddata(data, name=code)
            data_count += 1
            
        except Exception as e:
            continue
        
        if data_count % 50 == 0:
            print("  已添加 %s 只股票..." % data_count)
    
    print("总共添加 %s 只股票数据" % data_count)
    
    if data_count == 0:
        print("没有可用的股票数据！")
        return None
    
    # 7. 添加策略和分析器
    cerebro.addstrategy(
        AllFactorsStrategy,
        db=db,
        trade_days=rebalance_days,
    )
    
    # 分析器
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name='sharpe', riskfreerate=0.02)
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name='drawdown')
    cerebro.addanalyzer(bt.analyzers.Returns, _name='returns')
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name='trades')
    cerebro.addanalyzer(bt.analyzers.SQN, _name='sqn')
    
    # 8. 运行回测
    print("开始回测...")
    start_time = datetime.now()
    
    results = cerebro.run()
    
    end_time = datetime.now()
    elapsed = (end_time - start_time).total_seconds()
    print(f"回测完成，耗时: {elapsed:.1f}秒")
    
    # 9. 提取结果
    strat = results[0]
    
    final_value = cerebro.broker.getvalue()
    total_return = (final_value / INITIAL_CASH - 1) * 100
    
    # 分析器结果
    sharpe_analysis = strat.analyzers.sharpe.get_analysis()
    drawdown_analysis = strat.analyzers.drawdown.get_analysis()
    returns_analysis = strat.analyzers.returns.get_analysis()
    trades_analysis = strat.analyzers.trades.get_analysis()
    
    # 年化收益
    days = (pd.to_datetime(BACKTEST_END) - pd.to_datetime(BACKTEST_START)).days
    annual_return = ((final_value / INITIAL_CASH) ** (365 / days) - 1) * 100
    
    # 输出摘要
    print("%s" % "\n" + "=" * 70)
    print("全因子量化策略回测结果")
    print("%s" % "=" * 70)
    print("初始资金:       ¥%s" % f"{INITIAL_CASH:>12,.0f}")
    print("最终资产:       ¥%s" % f"{final_value:>12,.2f}")
    print("总收益率:       %s%.2f%%" % ('+' if total_return > 0 else '', total_return * 100))
    print("年化收益率:     %s%.2f%%" % ('+' if annual_return > 0 else '', annual_return * 100))
    print("夏普比率:       %.4f" % sharpe_analysis.get('sharperatio', 0))
    print("最大回撤:       %.2f%%" % (drawdown_analysis.get('max', 0) * 100))
    print("回测天数:       %s天" % f"{days:>12}")
    print("回测耗时:       %s秒" % f"{elapsed:>11.1f}")
    print("%s" % "=" * 70)
    
    # 交易统计
    total_trades = trades_analysis.get('total', {}).get('total', 0)
    won_trades = trades_analysis.get('won', {}).get('total', 0)
    lost_trades = trades_analysis.get('lost', {}).get('total', 0)
    win_rate = won_trades / total_trades * 100 if total_trades > 0 else 0
    
    print("\n交易统计:")
    print("  总交易次数: %d" % total_trades)
    print("  盈利交易:   %d" % won_trades)
    print("  亏损交易:   %d" % lost_trades)
    print("  胜率:       %.1f%%" % win_rate)
    # 10. 生成QuantStats报告
    report_file = generate_quantstats_report(
        strat=strat,
        daily_values=strat.daily_values,
        final_value=final_value,
        total_return=total_return,
        annual_return=annual_return,
        sharpe=sharpe_analysis.get('sharperatio', 0),
        max_drawdown=drawdown_analysis.get('max', {}).get('drawdown', 0),
        win_rate=win_rate,
        total_trades=total_trades,
    )
    
    return {
        'final_value': final_value,
        'total_return': total_return,
        'annual_return': annual_return,
        'sharpe_ratio': sharpe_analysis.get('sharperatio', 0),
        'max_drawdown': drawdown_analysis.get('max', {}).get('drawdown', 0),
        'win_rate': win_rate,
        'total_trades': total_trades,
        'report_file': report_file,
    }


def generate_quantstats_report(strat, daily_values, **kwargs):
    """生成QuantStats专业回测报告"""
    import quantstats as qs
    
    report_dir = ROOT / "backtest_reports"
    report_dir.mkdir(exist_ok=True)
    
    report_date = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_file = report_dir / f"all_factors_quantstats_{report_date}.html"
    
    # 从每日净值构建收益序列
    if daily_values and len(daily_values) > 10:
        values_df = pd.DataFrame(daily_values)
        values_df['date'] = pd.to_datetime(values_df['date'])
        values_df = values_df.sort_values('date').set_index('date')
        
        # 计算每日收益率
        values_df['returns'] = values_df['value'].pct_change().fillna(0)
        
        # 使用QuantStats生成报告
        try:
            qs.reports.html(
                returns=values_df['returns'],
                title=f"全因子量化策略回测报告 ({report_date})",
                output=str(report_file),
                benchmark_returns=None,  # 无基准对比
                download_filename=f'all_factors_report_{report_date}',
            )
            print("[OK] QuantStats报告已保存: %s" % report_file)
            
        except Exception as e:
            print("QuantStats报告生成失败: %s" % e)
            generate_fallback_report(report_file, kwargs)
    else:
        print("净值数据不足，使用备用方案生成报告")
        generate_fallback_report(report_file, kwargs)
    
    return str(report_file)


def generate_fallback_report(report_file, metrics):
    """备用报告（当QuantStats无法使用时）"""
    
    html_content = f"""
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
        <meta charset="UTF-8">
        <title>全因子量化策略回测报告</title>
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; margin: 40px; line-height: 1.6; color: #333; }}
            h1 {{ color: #1a73e8; border-bottom: 3px solid #1a73e8; padding-bottom: 15px; }}
            h2 {{ color: #5f6368; margin-top: 35px; }}
            .metrics {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 20px; margin: 25px 0; }}
            .metric-card {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 25px; border-radius: 12px; box-shadow: 0 4px 15px rgba(0,0,0,0.1); }}
            .metric-label {{ font-size: 14px; opacity: 0.9; margin-bottom: 8px; }}
            .metric-value {{ font-size: 28px; font-weight: bold; }}
            table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
            th, td {{ border: 1px solid #ddd; padding: 12px; text-align: left; }}
            th {{ background-color: #f8f9fa; font-weight: 600; }}
            tr:hover {{ background-color: #f5f5f5; }}
            .positive {{ color: #e74c3c; }}  /* A股红色表示上涨 */
            .negative {{ color: #27ae60; }}  /* A股绿色表示下跌 */
            .factor-table {{ background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.05); }}
        </style>
    </head>
    <body>
        <h1>全因子量化策略回测报告</h1>
        <p><strong>生成时间:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        <p><strong>回测区间:</strong> {BACKTEST_START} ~ {BACKTEST_END}</p>
        <p><strong>策略说明:</strong> 集成62个因子的全量化策略，包含行为金融学因子(CGO/VNSP/CDE/ΔDE)和经典多因子模型</p>

        <div class="metrics">
            <div class="metric-card">
                <div class="metric-label">总收益率</div>
                <div class="metric-value">{'+'if metrics.get('total_return',0)>0 else ''}{metrics.get('total_return', 0):.2f}%</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">年化收益率</div>
                <div class="metric-value">{'+'if metrics.get('annual_return',0)>0 else ''}{metrics.get('annual_return', 0):.2f}%</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">夏普比率</div>
                <div class="metric-value">{metrics.get('sharpe', 0):.4f}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">最大回撤</div>
                <div class="metric-value">{metrics.get('max_drawdown', 0):.2f}%</div>
            </div>
        </div>

        <h2>核心绩效指标</h2>
        <table>
            <tr><th>指标</th><th>数值</th><th>说明</th></tr>
            <tr><td>初始资金</td><td>¥1,000,000</td><td>固定初始投资</td></tr>
            <tr><td>最终资产</td><td>¥{metrics.get('final_value', 0):,.2f}</td><td>回测结束时的总资产</td></tr>
            <tr><td>总收益率</td><td class="{'positive' if metrics.get('total_return',0)>=0 else 'negative'}">{'+'if metrics.get('total_return',0)>=0 else ''}{metrics.get('total_return', 0):.2f}%</td><td>从开始到结束的总回报</td></tr>
            <tr><td>年化收益率</td><td class="{'positive' if metrics.get('annual_return',0)>=0 else 'negative'}">{'+'if metrics.get('annual_return',0)>=0 else ''}{metrics.get('annual_return', 0):.2f}%</td><td>年化后的收益率</td></tr>
            <tr><td>夏普比率</td><td>{metrics.get('sharpe', 0):.4f}</td><td>风险调整后收益（无风险利率2%）</td></tr>
            <tr><td>最大回撤</td><td class="negative">{metrics.get('max_drawdown', 0):.2f}%</td><td>历史最大亏损幅度</td></tr>
            <tr><td>胜率</td><td>{metrics.get('win_rate', 0):.1f}%</td><td>盈利交易占比</td></tr>
            <tr><td>交易次数</td><td>{metrics.get('total_trades', 0)}</td><td>总交易笔数</td></tr>
        </table>

        <h2>因子模块说明</h2>
        <div class="factor-table">
            <table>
                <tr><th>模块</th><th>因子数</th><th>描述</th><th>权重</th></tr>
                <tr><td>动量 & 量价</td><td>11</td><td>日内动量 + 量价结构</td><td>23%</td></tr>
                <tr><td>资金流 & 流动性</td><td>11</td><td>主力资金流向 + 流动性指标</td><td>16%</td></tr>
                <tr><td>波动率 & 情绪</td><td>11</td><td>波动率高阶矩 + 情绪拥挤</td><td>10%</td></tr>
                <tr><td>微观 & 反转 & 行业</td><td>18</td><td>微观结构 + 反转信号 + 行业轮动</td><td>10%</td></tr>
                <tr><td>处置效应</td><td>3</td><td>行为金融学核心因子</td><td>20%</td></tr>
                <tr><td><b>行为金融学+经典多因子</b></td><td><b>8</b></td><td><b>CGO/VNSP/CDE/ΔDE + 动量/反转 + 质量/低波</b></td><td><b>21%</b></td></tr>
                <tr style="background:#e8f4fd"><td><b>总计</b></td><td><b>62+</b></td><td><b>全因子体系</b></td><td><b>100%</b></td></tr>
            </table>
        </div>

        <h3>新增行为金融学因子</h3>
        <ul>
            <li><b>CGO (资本利得突出量)</b>: 衡量投资者整体浮盈程度，负向因子 — 浮盈越高卖压越大</li>
            <li><b>VNSP (V型处置效应)</b>: 刻画盈亏幅度与卖出意愿的V型关系，负向因子 — 大幅盈亏都导致抛售</li>
            <li><b>CDE (筹码分布处置效应)</b>: 基于筹码分布计算加权成本偏离度，负向因子 — 偏离越大越危险</li>
            <li><b>ΔDE (处置效应变化)</b>: 处置效应不对称程度的一阶差分，正向因子 — 变化意味着机会</li>
        </ul>

        <h3>新增经典多因子</h3>
        <ul>
            <li><b>质量因子 (Quality)</b>: 基于收益稳定性和趋势强度的综合评分，正向</li>
            <li><b>动量因子 (Momentum)</b>: 过去12个月收益率剔除最近1个月，正向</li>
            <li><b>长期反转 (LT_REV)</b>: 过去36个月收益率，负向（均值回归）</li>
            <li><b>低波因子 (Low Volatility)</b>: 波动率的倒数，低波动高收益异象</li>
        </ul>

        <h2>股票池过滤条件</h2>
        <ul>
            <li>排除 ST / *ST 股票</li>
            <li>排除科创板 (688xxx)、北交所 (8xxxx)、创业板 (3xxxx 需确认)</li>
            <li>平均日成交额 ≥ 5亿元（近似筛选100亿以上大市值）</li>
            <li>平均股价 ≥ 3元（排除低价股）</li>
        </ul>

        <h2>回测参数</h2>
        <ul>
            <li>调仓频率: 每 {REBALANCE_FREQUENCY} 个交易日（约1季度）</li>
            <li>持仓数量: 最多 {MAX_POSITIONS} 只，每期选 {TOP_N} 只等权重</li>
            <li>初始资金: ¥1,000,000</li>
            <li>交易费用: 0.1%（单边佣金，不含印花税）</li>
        </ul>

        <hr>
        <p style="color: #999; font-size: 12px;">
            量化系统 v15 | 因子引擎 v2.1 | Backtrader回测框架<br>
            报告生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}<br>
            © 2026 全因子量化策略系统
        </p>
    </body>
    </html>
    """
    
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write(html_content)
    
print("[OK] 备用报告已保存: %s" % report_file)


def main():
    """主函数"""
    try:
        results = run_all_factors_backtest()
        
        if results:
            print("[完成] 回测结束！报告已保存至: %s" % results.get('report_file', ''))
        else:
            print("[错误] 回测失败！")
            
    except Exception as e:
        print("回测过程中出现错误: %s" % e)
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    main()
