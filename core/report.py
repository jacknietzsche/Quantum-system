"""
core.report — 统一报告输出
============================
整合报告生成功能（选股报告 + 持仓报告 + 回测报告）。

提供:
  1. SelectionReportGenerator — 每日选股报告（HTML+JSON）
  2. PortfolioReportGenerator — 持仓分析报告（HTML+Plotly）
  3. BacktestReportGenerator — 回测报告（HTML+Plotly）

设计原则:
  - 统一报告风格（配色/字体/布局）
  - 统一输出接口: generate(data, output_dir) → filepath
  - 所有报告均为自包含 HTML（CDN 引用 Bootstrap/Plotly）
"""

import os
import json
import logging
from datetime import datetime, date
from typing import Dict, List, Optional, Any
from pathlib import Path

import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from core.config import QuantConfig, ReportConfig, COLORS

logger = logging.getLogger(__name__)

__all__ = [
    "SelectionReportGenerator",
    "PortfolioReportGenerator",
    "BacktestReportGenerator",
    "SimulationReportGenerator",
]


# ================================================================
# SelectionReportGenerator — 每日选股报告
# ================================================================

class SelectionReportGenerator:
    """
    每日选股报告生成器

    输入: v15 评分结果 + 市场数据
    输出: JSON + HTML 报告
    """

    def __init__(self, config: Optional[QuantConfig] = None):
        self.cfg = config or QuantConfig()
        Path(self.cfg.report.selection_report_dir).mkdir(parents=True, exist_ok=True)

    def generate(
        self,
        results: List[dict],
        top_stocks: List[dict],
        market_data: dict,
        market_state: Optional[dict] = None,
        elapsed_sec: float = 0,
        scoring_weights: Optional[dict] = None,
    ) -> Dict[str, str]:
        """
        生成选股报告

        Args:
            results: 所有评分结果
            top_stocks: Top N 推荐
            market_data: 市场数据
            market_state: 市场状态
            elapsed_sec: 耗时
            scoring_weights: 评分权重

        Returns:
            {"json": path, "html": path}
        """
        today = datetime.now().strftime('%Y-%m-%d')
        report_dir = Path(self.cfg.report.selection_report_dir)

        # ── JSON 报告 ──
        weights = scoring_weights or {
            'base_weight': self.cfg.selection.weight_base,
            'enhanced_weight': self.cfg.selection.weight_enhanced,
            'market_weight': self.cfg.selection.weight_market,
            'factor_v2_weight': self.cfg.selection.weight_factor_v2,
        }

        json_report = {
            'date': today,
            'generated_at': datetime.now().isoformat(),
            'system': 'v15',
            'scoring_model': weights,
            'market_data': {k: v for k, v in market_data.items() if k != 'sector_strength'},
            'market_state': market_state or 'unavailable',
            'total_analyzed': len(results),
            'top_stocks': top_stocks,
            'avg_score': float(sum(r['total_score'] for r in top_stocks) / max(len(top_stocks), 1)),
            'elapsed_sec': round(elapsed_sec, 1),
        }

        json_path = report_dir / f"v15_report_{today}.json"
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(json_report, f, ensure_ascii=False, indent=2)

        # ── HTML 报告 ──
        html_path = report_dir / f"v15_report_{today}.html"
        html = self._render_html(top_stocks, market_state, today, len(results), elapsed_sec)
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(html)

        return {"json": str(json_path), "html": str(html_path)}

    def _render_html(self, top_stocks, market_state, today, total_count, elapsed) -> str:
        """渲染 HTML 报告"""
        ms_label = "数据不可用"
        ms_color = "#999"
        if market_state and isinstance(market_state, dict):
            ms = market_state.get('market_state', 'unknown')
            labels = {'bull': '多头市场', 'bear': '空头市场', 'neutral': '震荡市场'}
            colors = {'bull': '#c62828', 'bear': '#2e7d32', 'neutral': '#1565c0'}
            ms_label = labels.get(ms, ms)
            ms_color = colors.get(ms, '#999')

        rows = ''
        for i, s in enumerate(top_stocks, 1):
            reasons_html = ''.join(f'<li>{r}</li>' for r in s.get('reasons', [])[:4])
            chg_color = '#c62828' if s.get('change_pct', 0) >= 0 else '#2e7d32'
            at_triggered = s.get('anti_top_triggered', 0)
            at_bg = '#e8f5e9' if at_triggered == 0 else ('#fff3e0' if at_triggered == 1 else '#fce4ec')
            at_fg = '#2e7d32' if at_triggered == 0 else ('#e65100' if at_triggered == 1 else '#c62828')

            fv2 = s.get('factor_v2_coef', 1.0)
            fv2_bg = '#e8f5e9' if fv2 >= 1.01 else ('#fffde7' if fv2 >= 0.96 else '#fce4ec')
            fv2_fg = '#2e7d32' if fv2 >= 1.01 else ('#f57f17' if fv2 >= 0.96 else '#c62828')

            rows += f"""<tr>
                <td>{i}</td>
                <td><strong>{s['symbol']}</strong><br/><small>{s.get('name', '')}</small></td>
                <td style="color:{chg_color};font-weight:bold;font-size:16px">{s['total_score']:.4f}</td>
                <td style="color:{chg_color}">{s.get('price', 0):.2f}</td>
                <td style="color:{chg_color}">{s.get('change_pct', 0):+.2f}%</td>
                <td style="background:{at_bg};color:{at_fg};font-weight:bold;padding:6px;border-radius:6px">
                    {at_triggered}项</td>
                <td style="background:{fv2_bg};color:{fv2_fg};font-weight:bold;padding:6px;border-radius:6px">
                    {fv2:.3f}</td>
                <td style="text-align:left"><ul style="margin:0;padding-left:16px;font-size:11px">{reasons_html}</ul></td>
            </tr>"""

        return f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8">
<title>v15 量化选股报告 {today}</title>
<style>
body{{font-family:'Microsoft YaHei',sans-serif;background:#f5f5f5;padding:20px}}
.container{{max-width:1400px;margin:auto;background:white;border-radius:12px;padding:30px;box-shadow:0 2px 16px rgba(0,0,0,.1)}}
h1{{color:#b71c1c;margin-bottom:4px}}
.meta{{display:flex;gap:16px;margin-bottom:20px;flex-wrap:wrap}}
.badge{{background:#fce4ec;color:#b71c1c;padding:6px 16px;border-radius:20px;font-size:13px}}
table{{width:100%;border-collapse:collapse;font-size:14px}}
th{{background:#b71c1c;color:white;padding:10px 8px;text-align:center;position:sticky;top:0;font-size:12px}}
td{{padding:8px;border-bottom:1px solid #eee;text-align:center;vertical-align:middle}}
tr:hover td{{background:#fafafa}}
.footer{{margin-top:20px;color:#999;font-size:12px;text-align:center}}
</style></head><body>
<div class="container">
<h1>v15 量化选股日报</h1>
<div class="meta">
    <span class="badge">日期: {today}</span>
    <span class="badge">分析: {total_count} 只</span>
    <span class="badge">推荐: Top {len(top_stocks)}</span>
    <span class="badge">耗时: {elapsed:.1f}s</span>
</div>
<table><tr><th>#</th><th>Stock</th><th>Score</th><th>Price</th><th>Chg%</th>
<th>AntiTop</th><th>V2 Engine</th><th>Reasons</th></tr>
{rows}
</table>
<div class="footer">生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | v15 System</div>
</div></body></html>"""


# ================================================================
# PortfolioReportGenerator — 持仓分析报告
# ================================================================

class PortfolioReportGenerator:
    """
    持仓分析报告生成器

    输入: 调仓结果 + 持仓快照
    输出: HTML 报告（Bootstrap 5 + Plotly）
    """

    def __init__(self, config: Optional[QuantConfig] = None):
        self.cfg = config or QuantConfig()
        Path(self.cfg.report.portfolio_report_dir).mkdir(parents=True, exist_ok=True)

    def generate(
        self,
        rebalance_result: dict,
        position_manager=None,
        output_dir: Optional[str] = None,
    ) -> str:
        """生成持仓报告"""
        out_dir = Path(output_dir or self.cfg.report.portfolio_report_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        today = datetime.now().strftime('%Y-%m-%d')
        html_path = out_dir / f"portfolio_report_{today}.html"

        # 获取持仓数据
        holdings = pd.DataFrame()
        trades_hist = pd.DataFrame()
        if position_manager:
            holdings = position_manager.get_current_holdings()
            trades_hist = position_manager.get_trade_history()

        initial = self.cfg.portfolio.initial_cash
        total_value = position_manager.get_portfolio_value() if position_manager else initial
        cum_return = (total_value / initial - 1) * 100 if initial > 0 else 0
        stock_value = holdings['market_value'].sum() if not holdings.empty else 0
        position_ratio = stock_value / total_value * 100 if total_value > 0 else 0

        # 生成图表
        fig_json = self._make_equity_curve(trades_hist, initial)
        pie_json = self._make_pie_chart(holdings) if not holdings.empty else "{}"

        html = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8">
<title>持仓分析报告 {today}</title>
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
<script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
<style>
body{{font-family:'Microsoft YaHei',sans-serif;background:#f5f5f5;padding:20px}}
.main-card{{max-width:1200px;margin:auto;background:white;border-radius:12px;padding:30px;box-shadow:0 2px 16px rgba(0,0,0,.1)}}
h1{{color:#b71c1c}}h2{{color:#b71c1c;border-bottom:2px solid #b71c1c;padding-bottom:8px;margin-top:30px}}
.summary-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:16px;margin:20px 0}}
.summary-item{{background:#fafafa;border-radius:8px;padding:16px;text-align:center;border-left:4px solid #ccc}}
.summary-item .label{{font-size:12px;color:#888}}.summary-item .value{{font-size:22px;font-weight:bold}}
.profit-pos{{color:#c62828;font-weight:bold}}.profit-neg{{color:#2e7d32;font-weight:bold}}
</style></head><body>
<div class="main-card">
<h1>模拟持仓分析报告</h1>
<p style="color:#888">报告日期: {today}</p>
<div class="summary-grid">
  <div class="summary-item" style="border-left-color:#b71c1c"><div class="label">初始资金</div><div class="value">¥{initial:,.0f}</div></div>
  <div class="summary-item" style="border-left-color:#1565c0"><div class="label">当前总资产</div><div class="value">¥{total_value:,.0f}</div></div>
  <div class="summary-item" style="border-left-color:#2e7d32"><div class="label">累计收益率</div><div class="value {'profit-pos' if cum_return >= 0 else 'profit-neg'}">{cum_return:+.2f}%</div></div>
  <div class="summary-item" style="border-left-color:#e65100"><div class="label">当前仓位</div><div class="value">{position_ratio:.1f}%</div></div>
  <div class="summary-item" style="border-left-color:#6a1b9a"><div class="label">持仓数量</div><div class="value">{len(holdings)}</div></div>
</div>
<div id="equity-chart" style="height:400px;margin:20px 0"></div>
<div id="pie-chart" style="height:400px;margin:20px 0"></div>
<div class="text-center" style="color:#999;font-size:12px;margin-top:30px">v15 Quant System</div>
</div>
<script>
var eqData = {fig_json};
Plotly.newPlot('equity-chart', eqData.data, eqData.layout);
var pieData = {pie_json};
if (pieData.data) Plotly.newPlot('pie-chart', pieData.data, pieData.layout);
</script></body></html>"""

        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(html)

        logger.info("持仓报告已生成: %s", html_path)
        return str(html_path)

    def _make_equity_curve(self, trades_hist: pd.DataFrame, initial: float) -> str:
        """生成净值曲线"""
        if trades_hist.empty:
            return json.dumps({"data": [], "layout": {"title": "净值曲线"}})

        dates = sorted(trades_hist['date'].unique())
        values = [initial]
        cash = initial
        holdings = {}

        for d in dates:
            day_trades = trades_hist[trades_hist['date'] == d]
            for _, t in day_trades.iterrows():
                code = t['code']
                if t['action'] == 'buy':
                    cash -= t['amount']
                    holdings[code] = holdings.get(code, 0) + t['shares']
                elif t['action'] == 'sell':
                    cash += t['amount']
                    holdings[code] = max(0, holdings.get(code, 0) - t['shares'])
                    if holdings[code] == 0:
                        holdings.pop(code, None)
            values.append(cash)

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=dates, y=values[1:], mode='lines+markers',
            line=dict(color='#b71c1c', width=2), name='总资产'
        ))
        fig.update_layout(title="资金曲线", template="plotly_white",
                         xaxis_title="日期", yaxis_title="金额（元）")
        return json.dumps(fig.to_dict(), default=str)

    def _make_pie_chart(self, holdings: pd.DataFrame) -> str:
        """生成持仓饼图"""
        if holdings.empty:
            return "{}"
        fig = go.Figure(go.Pie(
            labels=[f"{r['code']} {r['name']}" for _, r in holdings.iterrows()],
            values=holdings['market_value'].tolist(),
            textinfo='label+percent',
        ))
        fig.update_layout(title="持仓分布")
        return json.dumps(fig.to_dict(), default=str)


# ================================================================
# BacktestReportGenerator — 回测报告
# ================================================================

class BacktestReportGenerator:
    """
    回测报告生成器

    输入: BacktestEngine.run_backtest() 的结果
    输出: HTML 报告（Plotly 交互式图表）
    """

    def __init__(self, config: Optional[QuantConfig] = None):
        self.cfg = config or QuantConfig()
        Path(self.cfg.report.backtest_report_dir).mkdir(parents=True, exist_ok=True)

    def generate(
        self,
        backtest_result: dict,
        title: str = "回测报告",
        output_dir: Optional[str] = None,
    ) -> str:
        """生成回测报告"""
        out_dir = Path(output_dir or self.cfg.report.backtest_report_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        stats = backtest_result.get('stats', {})
        trades = backtest_result.get('trades', [])
        daily = backtest_result.get('daily_value', pd.Series())

        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        html_path = out_dir / f"backtest_report_{ts}.html"

        # 净值曲线
        equity_json = self._make_equity(daily)
        # 回撤曲线
        dd_json = self._make_drawdown(daily)
        # 月度收益
        monthly_json = self._make_monthly(daily)

        # 交易表
        trade_rows = ''
        for t in trades[:50]:
            pnl_cls = 'profit-pos' if t.get('pnl', 0) > 0 else 'profit-neg'
            trade_rows += f"""<tr>
                <td>{t.get('code','')}</td>
                <td>{t.get('buy_date','')}</td><td>{t.get('sell_date','')}</td>
                <td>{t.get('buy_price',0):.2f}</td><td>{t.get('sell_price',0):.2f}</td>
                <td class="{pnl_cls}">{t.get('pnl',0):.2f}</td>
                <td class="{pnl_cls}">{t.get('pnl_pct',0):.2f}%</td>
            </tr>"""

        html = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8">
<title>{title}</title>
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
<script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
<style>
body{{font-family:'Microsoft YaHei',sans-serif;background:#f5f5f5;padding:20px}}
.card{{max-width:1200px;margin:auto;background:white;border-radius:12px;padding:30px;box-shadow:0 2px 16px rgba(0,0,0,.1)}}
h1{{color:#b71c1c}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px;margin:20px 0}}
.metric{{background:#fafafa;border-radius:8px;padding:14px;text-align:center;border-left:4px solid #ccc}}
.metric .label{{font-size:11px;color:#888}}.metric .val{{font-size:20px;font-weight:bold}}
.profit-pos{{color:#c62828;font-weight:bold}}.profit-neg{{color:#2e7d32;font-weight:bold}}
table{{width:100%;border-collapse:collapse;font-size:13px}}
th{{background:#b71c1c;color:white;padding:8px;text-align:center}}
td{{padding:6px;border-bottom:1px solid #eee;text-align:center}}
</style></head><body>
<div class="card">
<h1>{title}</h1>
<div class="grid">
  <div class="metric" style="border-left-color:#b71c1c"><div class="label">总收益率</div><div class="val {'profit-pos' if stats.get('total_return',0)>=0 else 'profit-neg'}">{stats.get('total_return',0):.2f}%</div></div>
  <div class="metric" style="border-left-color:#1565c0"><div class="label">年化收益</div><div class="val">{stats.get('annual_return',0):.2f}%</div></div>
  <div class="metric" style="border-left-color:#2e7d32"><div class="label">夏普比率</div><div class="val">{stats.get('sharpe_ratio',0):.4f}</div></div>
  <div class="metric" style="border-left-color:#e65100"><div class="label">最大回撤</div><div class="val">{stats.get('max_drawdown',0):.2f}%</div></div>
  <div class="metric" style="border-left-color:#6a1b9a"><div class="label">胜率</div><div class="val">{stats.get('win_rate',0):.1f}%</div></div>
  <div class="metric" style="border-left-color:#333"><div class="label">盈亏比</div><div class="val">{stats.get('profit_factor',0):.2f}</div></div>
  <div class="metric" style="border-left-color:#333"><div class="label">交易次数</div><div class="val">{stats.get('total_trades',0)}</div></div>
  <div class="metric" style="border-left-color:#333"><div class="label">Calmar</div><div class="val">{stats.get('calmar_ratio',0):.4f}</div></div>
</div>
<div id="eq-chart" style="height:400px"></div>
<div id="dd-chart" style="height:300px"></div>
<div id="mon-chart" style="height:300px"></div>
<h2 style="color:#b71c1c;margin-top:30px">交易记录</h2>
<table><tr><th>代码</th><th>买入日</th><th>卖出日</th><th>买入价</th><th>卖出价</th><th>盈亏</th><th>收益率</th></tr>
{trade_rows}
</table>
<div style="text-align:center;color:#999;font-size:12px;margin-top:30px">v15 Backtest System</div>
</div>
<script>
Plotly.newPlot('eq-chart', {equity_json}.data, {equity_json}.layout);
Plotly.newPlot('dd-chart', {dd_json}.data, {dd_json}.layout);
Plotly.newPlot('mon-chart', {monthly_json}.data, {monthly_json}.layout);
</script></body></html>"""

        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(html)

        logger.info("回测报告已生成: %s", html_path)
        return str(html_path)

    def _make_equity(self, daily: pd.Series) -> str:
        if daily.empty:
            return json.dumps({"data": [], "layout": {"title": "净值曲线"}})
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=daily.index, y=daily.values, mode='lines',
                                  line=dict(color='#b71c1c', width=2), name='策略净值'))
        fig.update_layout(title="净值曲线", template="plotly_white",
                         xaxis_title="日期", yaxis_title="净值")
        return json.dumps(fig.to_dict(), default=str)

    def _make_drawdown(self, daily: pd.Series) -> str:
        if daily.empty:
            return json.dumps({"data": [], "layout": {"title": "回撤曲线"}})
        cummax = daily.cummax()
        dd = (daily - cummax) / cummax * 100
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=dd.index, y=dd.values, mode='lines',
                                  line=dict(color='#2e7d32', width=1), fill='tozeroy',
                                  fillcolor='rgba(46,125,50,0.1)', name='回撤'))
        fig.update_layout(title="回撤曲线", template="plotly_white")
        return json.dumps(fig.to_dict(), default=str)

    def _make_monthly(self, daily: pd.Series) -> str:
        if daily.empty:
            return json.dumps({"data": [], "layout": {"title": "月度收益"}})
        monthly = daily.resample('M').last().pct_change().dropna() * 100
        colors = ['#c62828' if v > 0 else '#2e7d32' for v in monthly.values]
        fig = go.Figure()
        fig.add_trace(go.Bar(x=[d.strftime('%Y-%m') for d in monthly.index],
                             y=monthly.values, marker_color=colors, name='月度收益'))
        fig.update_layout(title="月度收益", template="plotly_white")
        return json.dumps(fig.to_dict(), default=str)


# ================================================================
# SimulationReportGenerator — 模拟交易报告
# ================================================================

class SimulationReportGenerator:
    """
    模拟交易报告生成器

    参考顶尖量化公司实践，提供完整的模拟交易报告：
    1. 交易信号：买入/卖出信号、评级、信心度
    2. 仓位计划：持仓建议、目标仓位、风险预算
    3. 持仓状态：当前持仓、盈亏、止损止盈
    4. 绩效追踪：净值曲线、回撤、胜率

    报告包含：
    - 买卖信号列表（含评级 A/B/C/D/E）
    - 建议持仓明细（买入价、目标价、止损价）
    - 当前持仓状态（含浮动盈亏）
    - 绩效统计图表
    """

    def __init__(self, config: Optional[QuantConfig] = None):
        self.cfg = config or QuantConfig()
        out_dir = getattr(self.cfg.report, 'simulation_report_dir', 'simulation_portfolio/reports')
        Path(out_dir).mkdir(parents=True, exist_ok=True)

    def generate(
        self,
        buy_signals: List[dict],
        sell_signals: List[dict],
        holdings: pd.DataFrame,
        snapshots: List[dict],
        stats: dict,
        date: Optional[str] = None,
        output_dir: Optional[str] = None,
    ) -> Dict[str, str]:
        """
        生成模拟交易报告

        Args:
            buy_signals: 买入信号列表
            sell_signals: 卖出信号列表
            holdings: 当前持仓 DataFrame
            snapshots: 每日快照列表
            stats: 绩效统计
            date: 报告日期
            output_dir: 输出目录

        Returns:
            {"html": path, "json": path}
        """
        date = date or datetime.now().strftime('%Y-%m-%d')
        out_dir = Path(output_dir or getattr(self.cfg.report, 'simulation_report_dir', 'simulation_portfolio/reports'))
        out_dir.mkdir(parents=True, exist_ok=True)

        # JSON 报告
        json_data = {
            'date': date,
            'generated_at': datetime.now().isoformat(),
            'system': 'v15_simulation',
            'buy_signals': buy_signals,
            'sell_signals': sell_signals,
            'holdings': holdings.to_dict('records') if not holdings.empty else [],
            'snapshots': snapshots,
            'stats': stats,
        }
        json_path = out_dir / f"sim_report_{date}.json"
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(json_data, f, ensure_ascii=False, indent=2)

        # HTML 报告
        html_path = out_dir / f"sim_report_{date}.html"
        html = self._render_html(buy_signals, sell_signals, holdings, snapshots, stats, date)
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(html)

        return {"html": str(html_path), "json": str(json_path)}

    def _render_html(
        self,
        buy_signals: List[dict],
        sell_signals: List[dict],
        holdings: pd.DataFrame,
        snapshots: List[dict],
        stats: dict,
        date: str
    ) -> str:
        """渲染 HTML 报告"""
        # 信号表格
        buy_rows = self._render_signal_rows(buy_signals, 'buy')
        sell_rows = self._render_signal_rows(sell_signals, 'sell')

        # 持仓表格
        hold_rows = self._render_holding_rows(holdings)

        # 净值曲线数据
        equity_data = self._make_equity_curve(snapshots)
        drawdown_data = self._make_drawdown_curve(snapshots)

        # 统计卡片
        total_return = stats.get('total_return', 0)
        max_drawdown = stats.get('max_drawdown', 0)
        win_rate = stats.get('win_rate', 0)
        cum_return = total_return

        return f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8">
<title>模拟交易报告 {date}</title>
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
<script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
<style>
body{{font-family:'Microsoft YaHei',sans-serif;background:#f5f5f5;padding:20px}}
.card{{max-width:1400px;margin:auto;background:white;border-radius:12px;padding:24px;box-shadow:0 2px 16px rgba(0,0,0,.1);margin-bottom:20px}}
h1{{color:#b71c1c;margin-bottom:4px}}h2{{color:#b71c1c;border-bottom:2px solid #b71c1c;padding-bottom:8px;margin-top:24px;font-size:18px}}
.badge-a{{background:#c62828}} .badge-b{{background:#e53935}} .badge-c{{background:#fb8c00}}
.badge-d{{background:#fbc02d;color:#333}} .badge-e{{background:#9e9e9e}}
.stat-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin:16px 0}}
.stat-box{{background:#fafafa;border-radius:8px;padding:14px;text-align:center;border-left:4px solid #ccc}}
.stat-box .label{{font-size:11px;color:#888}} .stat-box .value{{font-size:20px;font-weight:bold}}
.profit-pos{{color:#c62828}} .profit-neg{{color:#2e7d32}}
table{{width:100%;border-collapse:collapse;font-size:13px;margin-top:12px}}
th{{background:#b71c1c;color:white;padding:8px;text-align:center;position:sticky;top:0}}
td{{padding:6px 8px;border-bottom:1px solid #eee;text-align:center}}
td.left{{text-align:left}} td.right{{text-align:right}}
tr:hover td{{background:#fafafa}}
.buy-signal td{{background:#fff3e0}} .sell-signal td{{background:#ffebee}}
.grade{{padding:3px 8px;border-radius:4px;color:white;font-weight:bold;font-size:12px}}
.footer{{text-align:center;color:#999;font-size:12px;margin-top:30px}}
</style></head><body>
<div class="card">
<h1>模拟交易报告</h1>
<p style="color:#888">报告日期: {date} | 系统: v15 量化系统</p>

<!-- 绩效统计 -->
<div class="stat-grid">
  <div class="stat-box" style="border-left-color:#b71c1c">
    <div class="label">累计收益率</div>
    <div class="value {'profit-pos' if cum_return >= 0 else 'profit-neg'}">{cum_return:+.2f}%</div>
  </div>
  <div class="stat-box" style="border-left-color:#2e7d32">
    <div class="label">最大回撤</div>
    <div class="value profit-neg">{max_drawdown:.2f}%</div>
  </div>
  <div class="stat-box" style="border-left-color:#1565c0">
    <div class="label">胜率</div>
    <div class="value">{win_rate:.1f}%</div>
  </div>
  <div class="stat-box" style="border-left-color:#6a1b9a">
    <div class="label">交易次数</div>
    <div class="value">{stats.get('total_trades', 0)}</div>
  </div>
  <div class="stat-box" style="border-left-color:#e65100">
    <div class="label">持仓数量</div>
    <div class="value">{len(holdings)}</div>
  </div>
  <div class="stat-box" style="border-left-color:#00897b">
    <div class="label">可用现金</div>
    <div class="value">¥{stats.get('current_cash', 0):,.0f}</div>
  </div>
</div>
</div>

<!-- 买入信号 -->
<div class="card">
<h2>建议买入信号</h2>
<table><thead><tr>
  <th>#</th><th>股票</th><th>评级</th><th>信心度</th><th>评分</th>
  <th>当前价</th><th>建议买入价</th><th>止损价</th><th>止盈价</th>
  <th>目标仓位</th><th>持仓周期</th><th>风险</th>
  <th>买入理由</th>
</tr></thead><tbody>
{buy_rows if buy_rows else '<tr><td colspan="13" style="text-align:center;color:#999">暂无买入信号</td></tr>'}
</tbody></table>
</div>

<!-- 卖出信号 -->
<div class="card">
<h2>建议卖出信号</h2>
<table><thead><tr>
  <th>#</th><th>股票</th><th>评级</th><th>信心度</th><th>评分</th>
  <th>当前价</th><th>成本价</th><th>持仓天数</th>
  <th>浮动盈亏</th><th>卖出理由</th>
</tr></thead><tbody>
{sell_rows if sell_rows else '<tr><td colspan="10" style="text-align:center;color:#999">暂无卖出信号</td></tr>'}
</tbody></table>
</div>

<!-- 当前持仓 -->
<div class="card">
<h2>当前持仓状态</h2>
<table><thead><tr>
  <th>#</th><th>股票</th><th>持仓数量</th><th>成本价</th><th>当前价</th>
  <th>浮动盈亏</th><th>盈亏%</th><th>止损价</th><th>止盈价</th>
  <th>持仓天数</th><th>调仓次数</th>
</tr></thead><tbody>
{hold_rows if hold_rows else '<tr><td colspan="11" style="text-align:center;color:#999">暂无持仓</td></tr>'}
</tbody></table>
</div>

<!-- 图表 -->
<div class="card">
<h2>净值曲线 & 回撤</h2>
<div id="equity-chart" style="height:350px"></div>
<div id="drawdown-chart" style="height:250px;margin-top:16px"></div>
</div>

<div class="footer">v15 量化系统 | 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</div>
</div>
<script>
var eqData = {equity_data};
Plotly.newPlot('equity-chart', eqData.data, eqData.layout);
var ddData = {drawdown_data};
Plotly.newPlot('drawdown-chart', ddData.data, ddData.layout);
</script></body></html>"""

    def _render_signal_rows(self, signals: List[dict], signal_type: str) -> str:
        """渲染信号行"""
        rows = []
        for i, sig in enumerate(signals, 1):
            grade_cls = f"badge-{sig.get('grade', 'c').lower()}"
            risk_color = {'LOW': '#2e7d32', 'MEDIUM': '#fb8c00', 'HIGH': '#c62828'}.get(sig.get('risk_level', 'MEDIUM'), '#999')
            reasons = '<br>'.join(sig.get('reasons', [])[:2])
            conf = sig.get('confidence', 0) * 100

            if signal_type == 'buy':
                rows.append(f"""<tr class="buy-signal">
  <td>{i}</td>
  <td class="left"><strong>{sig.get('symbol', '')}</strong><br><small>{sig.get('name', '')}</small></td>
  <td><span class="grade {grade_cls}">{sig.get('grade', 'C')}</span></td>
  <td>{conf:.0f}%</td>
  <td>{sig.get('score', 0):.3f}</td>
  <td class="right">{sig.get('current_price', sig.get('entry_price', 0)):.2f}</td>
  <td class="right"><strong style="color:#c62828">{sig.get('entry_price', 0):.2f}</strong></td>
  <td class="right" style="color:#2e7d32">{sig.get('stop_loss', 0):.2f}</td>
  <td class="right" style="color:#c62828">{sig.get('take_profit', 0):.2f}</td>
  <td>{sig.get('target_position', 0)*100:.1f}%</td>
  <td>{sig.get('holding_period_days', 5)}天</td>
  <td><span style="color:{risk_color};font-weight:bold">{sig.get('risk_level', 'MEDIUM')}</span></td>
  <td class="left"><small>{reasons}</small></td>
</tr>""")
            else:  # sell
                pnl = sig.get('pnl', 0)
                pnl_pct = sig.get('pnl_pct', 0)
                pnl_cls = 'profit-pos' if pnl >= 0 else 'profit-neg'
                rows.append(f"""<tr class="sell-signal">
  <td>{i}</td>
  <td class="left"><strong>{sig.get('symbol', '')}</strong><br><small>{sig.get('name', '')}</small></td>
  <td><span class="grade {grade_cls}">{sig.get('grade', 'C')}</span></td>
  <td>{conf:.0f}%</td>
  <td>{sig.get('score', 0):.3f}</td>
  <td class="right">{sig.get('current_price', 0):.2f}</td>
  <td class="right">{sig.get('cost', 0):.2f}</td>
  <td>{sig.get('hold_days', 0)}天</td>
  <td class="right {pnl_cls}" style="font-weight:bold">¥{pnl:+.0f}<br>({pnl_pct:+.1f}%)</td>
  <td class="left"><small>{reasons}</small></td>
</tr>""")
        return ''.join(rows)

    def _render_holding_rows(self, holdings: pd.DataFrame) -> str:
        """渲染持仓行"""
        if holdings.empty:
            return ''
        rows = []
        for i, (_, row) in enumerate(holdings.iterrows(), 1):
            pnl = (row.get('current_price', row.get('cost', 0)) - row.get('cost', 0)) * row.get('shares', 0)
            pnl_pct = (row.get('current_price', row.get('cost', 0)) / row.get('cost', 0) - 1) * 100 if row.get('cost', 0) > 0 else 0
            pnl_cls = 'profit-pos' if pnl >= 0 else 'profit-neg'
            stop_loss = row.get('cost', 0) * 0.92
            take_profit = row.get('cost', 0) * 1.15

            rows.append(f"""<tr>
  <td>{i}</td>
  <td class="left"><strong>{row.get('symbol', '')}</strong><br><small>{row.get('name', '')}</small></td>
  <td>{row.get('shares', 0)}</td>
  <td class="right">{row.get('cost', 0):.2f}</td>
  <td class="right">{row.get('current_price', row.get('cost', 0)):.2f}</td>
  <td class="right {pnl_cls}" style="font-weight:bold">¥{pnl:+.0f}</td>
  <td class="right {pnl_cls}">{pnl_pct:+.1f}%</td>
  <td class="right" style="color:#2e7d32">{stop_loss:.2f}</td>
  <td class="right" style="color:#c62828">{take_profit:.2f}</td>
  <td>{row.get('hold_days', 0)}天</td>
  <td>{row.get('adjustments', 0)}</td>
</tr>""")
        return ''.join(rows)

    def _make_equity_curve(self, snapshots: List[dict]) -> str:
        """生成净值曲线"""
        if not snapshots:
            return json.dumps({"data": [], "layout": {"title": "净值曲线"}})

        dates = [s['date'] for s in snapshots]
        values = [s['total_value'] for s in snapshots]

        fig = go.Figure()
        fig.add_trace(go.Scatter(x=dates, y=values, mode='lines+markers',
            line=dict(color='#b71c1c', width=2), name='总资产',
            hovertemplate='%{x}<br>¥%{y:,.0f}<extra></extra>'))
        fig.update_layout(title="资产净值曲线", template="plotly_white",
                         xaxis_title="日期", yaxis_title="金额（元）",
                         hovermode='x unified')
        return json.dumps(fig.to_dict(), default=str)

    def _make_drawdown_curve(self, snapshots: List[dict]) -> str:
        """生成回撤曲线"""
        if not snapshots:
            return json.dumps({"data": [], "layout": {"title": "回撤曲线"}})

        dates = [s['date'] for s in snapshots]
        values = [s['max_drawdown'] for s in snapshots]

        fig = go.Figure()
        fig.add_trace(go.Scatter(x=dates, y=values, mode='lines',
            line=dict(color='#2e7d32', width=1.5), fill='tozeroy',
            fillcolor='rgba(46,125,50,0.15)', name='回撤',
            hovertemplate='%{x}<br>%{y:.2f}%<extra></extra>'))
        fig.update_layout(title="回撤曲线", template="plotly_white",
                         xaxis_title="日期", yaxis_title="回撤（%）",
                         hovermode='x unified')
        return json.dumps(fig.to_dict(), default=str)
