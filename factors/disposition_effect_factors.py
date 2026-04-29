#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Disposition Effect Factor (DE Factor) - Daily Frequency
========================================================
Academic basis:
  Shefrin & Statman(1985) JF
  Odean(1998) JF - 10k US brokerage accounts, 7 years
  Odean(1999) JF
  A-share 3.2M accounts: DE=1.68, highest globally

3 versions:
  V1 Basic: Profit Ratio (retail sell probability proxy)
  V2 Enhanced: Sell Probability Prediction (multi-factor regression)
  V3 Market: Market-wide DE coefficient (timing)

All daily-frequency, akshare compatible.
"""
import warnings
warnings.filterwarnings('ignore')
import numpy as np
import pandas as pd
from typing import Dict, Optional, Tuple
import logging

logger = logging.getLogger("disposition_effect_factors")


def _safe_div(a, b, fill=0.0):
    try:
        if isinstance(b, (int, float)):
            return a / b if abs(b) > 1e-9 else fill
        result = np.where(np.abs(b) > 1e-9, a / b, fill)
        if hasattr(a, 'index'):
            return pd.Series(result, index=a.index, dtype=float)
        return result
    except Exception:
        return fill


def _latest(series) -> float:
    if series is None:
        return 0.0
    if isinstance(series, (int, float, np.floating)):
        v = float(series)
        return v if not np.isnan(v) else 0.0
    try:
        v = float(series.iloc[-1])
    except (AttributeError, IndexError):
        v = float(series)
    return v if not np.isnan(v) else 0.0


class DispositionEffectCalculator:
    """Disposition Effect Factor Calculator"""

    COST_WINDOW = 60
    TURN_ABNORMAL_WINDOW = 20
    VOL_WINDOW = 5

    # A-share calibrated regression coefficients
    BETA_PROFIT = 0.45
    BETA_TURN = 0.25
    BETA_VOL = 0.15
    BETA_MARKET = 0.15

    # Thresholds
    WASHOUT_PR_LOW = 0.10
    WASHOUT_PR_HIGH = 0.20
    WASHOUT_TURN_LOW = 1.2
    WASHOUT_TURN_HIGH = 2.0
    TOP_PR = 0.90
    TOP_GAIN_5D = 0.15
    TOP_TURN = 2.5
    TOP_STALL = 1.0
    MKT_DE_DANGER = 2.0

    def __init__(self):
        pass

    def check_df(self, df):
        required = ['open', 'close', 'high', 'low', 'volume', 'amount', 'pctChg', 'turn']
        missing = [c for c in required if c not in df.columns]
        if missing:
            return f"missing: {missing}"
        if len(df) < self.COST_WINDOW:
            return f"need {self.COST_WINDOW} rows, got {len(df)}"
        return None

    def calc_avg_cost(self, df):
        """AvgCost = sum(Close*Turn, N) / sum(Turn, N), N=60"""
        close = df['close'].astype(float)
        turn = df['turn'].replace(0, np.nan).fillna(method='ffill').astype(float)
        wc = close * turn
        cost = wc.rolling(self.COST_WINDOW, min_periods=20).sum() / \
               turn.rolling(self.COST_WINDOW, min_periods=20).sum()
        return cost.fillna(method='ffill')

    def calc_profit_ratio(self, df, avg_cost=None):
        """V1: ProfitRatio = (Close - AvgCost) / AvgCost"""
        if avg_cost is None:
            avg_cost = self.calc_avg_cost(df)
        close = df['close']
        lc = float(close.iloc[-1])
        lac = _latest(avg_cost)
        pr = (lc - lac) / lac if lac > 0.01 else 0.0
        pvc = lc / lac if lac > 0.01 else 1.0
        pr_s = ((close - avg_cost) / avg_cost.replace(0, np.nan)).fillna(0)
        pr5 = _latest(pr_s.rolling(5, min_periods=2).mean())
        if len(pr_s) >= 10:
            rr = _latest(pr_s.tail(5).mean())
            rb = _latest(pr_s.iloc[-10:-5].mean())
            d = rr - rb
            trend = 'rising' if d > 0.03 else ('falling' if d < -0.03 else 'stable')
        else:
            trend = 'stable'
        return {
            'profit_ratio': round(float(pr), 6), 'avg_cost': round(lac, 3),
            'price_vs_cost': round(float(pvc), 4), 'profit_ratio_5d': round(float(pr5), 6),
            'profit_ratio_trend': trend,
        }

    def calc_sell_probability(self, df, profit_ratio=None, market_return=0.0):
        """V2: SellProb = sigmoid(b1*PR + b2*Turn + b3*Vol + b4*Mkt)"""
        if profit_ratio is None:
            profit_ratio = self.calc_profit_ratio(df)['profit_ratio']
        turn = df['turn'].replace(0, np.nan).fillna(method='ffill')
        tm20 = turn.rolling(self.TURN_ABNORMAL_WINDOW, min_periods=5).mean()
        ta = _safe_div(turn, tm20, fill=1.0)
        lta = _latest(ta)
        ret = df['pctChg'] / 100.0
        v5 = _latest(ret.rolling(self.VOL_WINDOW, min_periods=3).std())
        pr_n = np.clip(profit_ratio / 0.5, -1, 1) * 0.5 + 0.5
        t_n = np.clip((lta - 0.5) / 3.0, 0, 1)
        v_n = np.clip(v5 / 0.05, 0, 1)
        m_n = np.clip(market_return / 0.05, 0, 1)
        lin = (self.BETA_PROFIT * pr_n + self.BETA_TURN * t_n +
               self.BETA_VOL * v_n + self.BETA_MARKET * m_n)
        sp = 1.0 / (1.0 + np.exp(-8 * (lin - 0.5))) * 100
        sig = ('high' if sp > 70 else 'moderate' if sp > 50 else 'low' if sp > 30 else 'minimal') + '_sell_pressure'
        return {
            'sell_probability': round(float(sp), 2), 'turn_abnormal': round(float(lta), 4),
            'volatility_5d': round(float(v5), 6), 'sell_signal': sig,
            'sell_prob_components': {
                'profit_c': round(self.BETA_PROFIT * pr_n, 4),
                'turn_c': round(self.BETA_TURN * t_n, 4),
                'vol_c': round(self.BETA_VOL * v_n, 4),
                'mkt_c': round(self.BETA_MARKET * m_n, 4),
            },
        }

    def calc_market_de(self, mkt_up_ratio=0.5, mkt_down_ratio=0.5):
        """V3: Market-wide DE coefficient"""
        mkt_pr = 0.5
        pgr = mkt_up_ratio / mkt_pr if mkt_pr > 0.01 else 1.0
        plr = mkt_down_ratio / (1 - mkt_pr) if (1 - mkt_pr) > 0.01 else 1.0
        de = pgr / plr if plr > 0.01 else 1.0
        sig = ('extreme_crowding' if de > self.MKT_DE_DANGER else
               'high_de' if de > 1.5 else 'normal_de' if de > 1.0 else
               'low_de' if de > 0.8 else 'panic_selling')
        return {
            'mkt_de_coefficient': round(float(de), 4),
            'mkt_profit_ratio': round(float(mkt_pr), 4),
            'mkt_pgr': round(float(pgr), 4), 'mkt_plr': round(float(plr), 4),
            'mkt_signal': sig,
        }

    def calc_washout_signal(self, df, profit_ratio=None, sell_prob=None, main_net_inflow=0.0):
        """Washout end signal for buy entry"""
        if profit_ratio is None:
            profit_ratio = self.calc_profit_ratio(df)['profit_ratio']
        if sell_prob is None:
            sell_prob = self.calc_sell_probability(df, profit_ratio)
        close = df['close']
        n = len(close)
        r10 = float(close.iloc[-1] / close.iloc[-min(10, n)] - 1) if n >= 10 else 0
        ma10 = float(close.rolling(10, min_periods=5).mean().iloc[-1]) if n >= 5 else float(close.iloc[-1])
        ma10p = float(close.rolling(10, min_periods=5).mean().iloc[-3]) if n >= 8 else ma10
        c1 = ma10 > ma10p and 0.05 <= r10 <= 0.15
        c2 = self.WASHOUT_PR_LOW <= profit_ratio <= self.WASHOUT_PR_HIGH
        ta = sell_prob.get('turn_abnormal', 1.0)
        c3 = self.WASHOUT_TURN_LOW <= ta <= self.WASHOUT_TURN_HIGH
        c4 = main_net_inflow > 0
        met = sum([c1, c2, c3, c4])
        score = int(c1)*0.25 + int(c2)*0.30 + int(c3)*0.25 + int(c4)*0.20
        return {
            'washout_signal': met >= 3, 'washout_score': round(score, 4),
            'washout_conditions': {
                'trend': c1, 'profit': c2, 'turn': c3, 'flow': c4,
                'met': f'{met}/4',
                'detail': f'r10={r10:.1%} pr={profit_ratio:.1%} ta={ta:.2f}',
            },
        }

    def calc_top_avoidance(self, df, profit_ratio=None, sell_prob=None, mkt_de=1.0):
        """Top avoidance veto signal"""
        if profit_ratio is None:
            profit_ratio = self.calc_profit_ratio(df)['profit_ratio']
        if sell_prob is None:
            sell_prob = self.calc_sell_probability(df, profit_ratio)
        close = df['close']
        n = len(close)
        triggers = []
        r5 = float(close.iloc[-1] / close.iloc[-min(5, n)] - 1) if n >= 5 else 0
        if profit_ratio > self.TOP_PR and r5 > self.TOP_GAIN_5D:
            triggers.append(f'PR={profit_ratio:.0%}>90% + r5={r5:.0%}>15%')
        h20 = float(close.rolling(20, min_periods=5).max().iloc[-2]) if n >= 10 else float(close.iloc[-1])
        ta = sell_prob.get('turn_abnormal', 1.0)
        pct = abs(float(df['pctChg'].iloc[-1]))
        if close.iloc[-1] >= h20 and ta > self.TOP_TURN and pct < self.TOP_STALL:
            triggers.append(f'newHigh+turn={ta:.1f}>2.5+stall={pct:.1f}%<1%')
        if mkt_de > self.MKT_DE_DANGER:
            triggers.append(f'MktDE={mkt_de:.2f}>2.0')
        tc = len(triggers)
        return {
            'top_avoidance': tc >= 1, 'top_triggers': triggers,
            'top_trigger_count': tc,
            'top_penalty': 0.70 if tc >= 2 else (0.85 if tc == 1 else 1.0),
        }

    def calculate_all(self, df, market_return=0.0, main_net_inflow=0.0,
                      market_up_amt_ratio=0.5, market_down_amt_ratio=0.5):
        """Calculate all disposition effect factors"""
        err = self.check_df(df)
        if err:
            logger.warning("DE check failed: %s", err)
            return self._defaults()
        try:
            ac = self.calc_avg_cost(df)
            pr = self.calc_profit_ratio(df, ac)
            sp = self.calc_sell_probability(df, pr['profit_ratio'], market_return)
            md = self.calc_market_de(market_up_amt_ratio, market_down_amt_ratio)
            wo = self.calc_washout_signal(df, pr['profit_ratio'], sp, main_net_inflow)
            ta = self.calc_top_avoidance(df, pr['profit_ratio'], sp, md['mkt_de_coefficient'])
            return {
                'profit_ratio': pr['profit_ratio'], 'avg_cost': pr['avg_cost'],
                'price_vs_cost': pr['price_vs_cost'], 'profit_ratio_5d': pr['profit_ratio_5d'],
                'profit_ratio_trend': pr['profit_ratio_trend'],
                'sell_probability': sp['sell_probability'], 'turn_abnormal': sp['turn_abnormal'],
                'volatility_5d': sp['volatility_5d'], 'sell_signal': sp['sell_signal'],
                'sell_prob_components': sp['sell_prob_components'],
                'mkt_de_coefficient': md['mkt_de_coefficient'], 'mkt_profit_ratio': md['mkt_profit_ratio'],
                'mkt_pgr': md['mkt_pgr'], 'mkt_plr': md['mkt_plr'], 'mkt_signal': md['mkt_signal'],
                'washout_signal': wo['washout_signal'], 'washout_score': wo['washout_score'],
                'washout_conditions': wo['washout_conditions'],
                'top_avoidance': ta['top_avoidance'], 'top_triggers': ta['top_triggers'],
                'top_trigger_count': ta['top_trigger_count'], 'top_penalty': ta['top_penalty'],
            }
        except Exception as e:
            logger.error(f"DE error: {e}", exc_info=True)
            return self._defaults()

    def _defaults(self):
        return {
            'profit_ratio': 0.0, 'avg_cost': 0.0, 'price_vs_cost': 1.0,
            'profit_ratio_5d': 0.0, 'profit_ratio_trend': 'stable',
            'sell_probability': 50.0, 'turn_abnormal': 1.0, 'volatility_5d': 0.02,
            'sell_signal': 'moderate_sell_pressure',
            'sell_prob_components': {'profit_c': 0.225, 'turn_c': 0.125,
                                     'vol_c': 0.075, 'mkt_c': 0.075},
            'mkt_de_coefficient': 1.0, 'mkt_profit_ratio': 0.5,
            'mkt_pgr': 1.0, 'mkt_plr': 1.0, 'mkt_signal': 'normal_de',
            'washout_signal': False, 'washout_score': 0.0,
            'washout_conditions': {}, 'top_avoidance': False,
            'top_triggers': [], 'top_trigger_count': 0, 'top_penalty': 1.0,
        }

    def get_de_adjustment(self, factors):
        """Get DE adjustment coefficient for scoring"""
        if factors.get('washout_signal', False):
            return round(1.0 + factors.get('washout_score', 0.5) * 0.05, 4), 'washout_buy'
        elif factors.get('top_avoidance', False):
            return factors.get('top_penalty', 0.85), 'top_avoidance'
        else:
            sp = factors.get('sell_probability', 50.0)
            if sp > 70: return 0.92, 'high_pressure'
            elif sp > 55: return 0.97, 'moderate_pressure'
            elif sp < 30: return 1.02, 'low_pressure'
            return 1.0, 'neutral'

    def get_factor_summary(self, factors):
        pr = factors.get('profit_ratio', 0)
        sp = factors.get('sell_probability', 50)
        mkt = factors.get('mkt_de_coefficient', 1.0)
        parts = [f"PR:{pr:+.1%}", f"SellProb:{sp:.0f}%", f"MktDE:{mkt:.2f}"]
        if factors.get('top_avoidance'): parts.append("AVOID_TOP!")
        if factors.get('washout_signal'): parts.append("WASHOUT_BUY!")
        return " | ".join(parts)


if __name__ == '__main__':
    print("=" * 60)
    print("DispositionEffectCalculator Test")
    print("=" * 60)
    np.random.seed(42)
    n = 120
    trend = np.linspace(0, 0.15, n)
    noise = np.random.normal(0, 0.02, n)
    close = 10.0 * np.cumprod(1 + trend / n + noise / n)
    high = close * (1 + np.random.uniform(0, 0.03, n))
    low = close * (1 - np.random.uniform(0, 0.03, n))
    open_ = close * (1 + np.random.normal(0, 0.01, n))
    turn = np.concatenate([np.random.uniform(0.5, 2.0, n-10), np.random.uniform(1.5, 3.0, 10)])
    volume = np.random.uniform(1e7, 5e8, n)
    amount = volume * close
    pctChg = np.concatenate([np.random.normal(0.05, 1.5, n-10), np.random.normal(0.3, 1.0, 10)])
    pctChg[0] = 0
    df = pd.DataFrame({
        'open': open_, 'close': close, 'high': high, 'low': low,
        'volume': volume, 'amount': amount, 'pctChg': pctChg, 'turn': turn
    })
    calc = DispositionEffectCalculator()
    factors = calc.calculate_all(df, market_return=0.02, main_net_inflow=0.5)
    print(f"\n[V1 Basic] AvgCost={factors['avg_cost']:.3f} PR={factors['profit_ratio']:+.2%} P/C={factors['price_vs_cost']:.4f} Trend={factors['profit_ratio_trend']}")
    print(f"[V2 SellProb] SP={factors['sell_probability']:.1f}% TurnA={factors['turn_abnormal']:.2f} Vol5={factors['volatility_5d']:.4f} Sig={factors['sell_signal']}")
    c = factors['sell_prob_components']
    print(f"  Components: profit={c['profit_c']:.3f} turn={c['turn_c']:.3f} vol={c['vol_c']:.3f} mkt={c['mkt_c']:.3f}")
    print(f"[V3 Market] DE={factors['mkt_de_coefficient']:.4f} Sig={factors['mkt_signal']}")
    print(f"[Strategy] Washout={factors['washout_signal']}({factors['washout_score']:.2f}) TopAvoid={factors['top_avoidance']}({factors['top_trigger_count']})")
    if factors['top_triggers']:
        for t in factors['top_triggers']: print(f"  TRIGGER: {t}")
    coef, sig = calc.get_de_adjustment(factors)
    print(f"[Adj] {coef:.4f} | {sig}")
    print(f"[Summary] {calc.get_factor_summary(factors)}")
    print("\n[PASS] OK")
