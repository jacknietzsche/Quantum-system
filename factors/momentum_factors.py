#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
动量类 & 量价结构精细化日频因子库 v1.0
==========================================
研报/顶刊依据:
  Jegadeesh & Titman(1993) 《Returns to Buying Winners and Selling Losers》JF
  国君金工《日内动量因子的A股本土化实证》2023
  广发金工《日内交易行为与短期收益》2024
  Gervais et al.(2001) 《The High Volume Return Premium》JF
  Blume et al.(1994)《Market Statistics and Technical Analysis》JF
  海通金工《量价结构因子全解析》2023
  国盛金工《量价背离的精细化识别》2024

大类一：日内降频日频动量类因子（5个）
  1. 隔夜动量因子 (overnight_mom)
  2. 日内动量因子 (intraday_mom)
  3. 动量一致性因子 (mom_consistency)
  4. 动量反转预警因子 (mom_reversal_warning)
  5. 尾盘动量因子 (tail_end_mom)

大类二：量价结构精细化日频因子（6个）
  6. 涨跌量比因子 (up_down_vol_ratio)
  7. 量能领先滞后因子 (vol_lead_lag)
  8. 缩量上涨预警因子 (shrink_rise_warning)
  9. 放量滞涨预警因子 (surge_vol_stall_warning)
  10. 量价背离强度因子 (price_vol_divergence)
  11. 换手率平稳度因子 (turnover_stability)

全部为日频滚动因子，回溯5/10/20日，数据源：akshare日频K线
"""

import warnings
warnings.filterwarnings('ignore')

import pandas as pd
import numpy as np
from typing import Dict, Optional, Tuple
import logging

logger = logging.getLogger("momentum_factors")


# ===================================================================
# 工具函数
# ===================================================================

def _safe_get_col(data: pd.DataFrame, *names) -> Optional[pd.Series]:
    """安全获取列（支持多个备用列名）"""
    for name in names:
        if name in data.columns:
            return data[name]
    return None


def _is_high_position(close: pd.Series, window: int = 20, pct: float = 0.8) -> bool:
    """判断是否处于高位（收盘价高于近N日的pct分位）"""
    if len(close) < window:
        return False
    return float(close.iloc[-1]) >= float(close.iloc[-window:].quantile(pct))


# ===================================================================
# 大类一：日内降频日频动量类因子
# ===================================================================

def calc_overnight_momentum(data: pd.DataFrame, window: int = 5) -> Dict:
    """
    因子1：隔夜动量因子
    OvernightMOM_t = sum(ln(Open_τ / Close_{τ-1}), τ=t-4..t)
    过去N日隔夜收益累计值

    正向选股：值越大越好，隔夜持续上涨代表资金抢筹，短期上涨动力足

    参数：
        data: 含 open、close 列的 DataFrame
    返回：
        dict {
          'overnight_mom': float,         # 隔夜动量累计值
          'overnight_win_rate': float,    # 近N日隔夜上涨胜率
          'signal': str,                  # '做多'/'做空'/'中性'
        }
    """
    result = {'overnight_mom': 0.0, 'overnight_win_rate': 0.5, 'signal': '中性'}
    try:
        close = data['close']
        open_ = data['open']
        if len(data) < window + 2:
            return result

        # 计算每日隔夜收益 ln(Open / Close_{prev})
        overnight_rets = np.log(open_.values[1:] / close.values[:-1])

        # 取最近N日
        recent = overnight_rets[-window:]
        overnight_mom = float(np.sum(recent))
        win_rate = float(np.mean(recent > 0))

        signal = '做多' if overnight_mom > 0.02 else ('做空' if overnight_mom < -0.02 else '中性')
        result.update({
            'overnight_mom': overnight_mom,
            'overnight_win_rate': win_rate,
            'signal': signal,
        })
    except Exception as e:
        logger.debug("calc_overnight_momentum error: %s", e)
    return result


def calc_intraday_momentum(data: pd.DataFrame, window: int = 10) -> Dict:
    """
    因子2：日内动量因子
    IntradayMOM_t = sum(ln(Close_τ / Open_τ), τ=t-9..t)
    过去N日日内收益累计值

    正向选股：值越大越好，日内持续走强代表多头力量强劲
    """
    result = {'intraday_mom': 0.0, 'intraday_win_rate': 0.5, 'signal': '中性'}
    try:
        close = data['close']
        open_ = data['open']
        if len(data) < window:
            return result

        intraday_rets = np.log(close.values / open_.values)
        recent = intraday_rets[-window:]
        intraday_mom = float(np.sum(recent))
        win_rate = float(np.mean(recent > 0))

        signal = '做多' if intraday_mom > 0.03 else ('做空' if intraday_mom < -0.03 else '中性')
        result.update({
            'intraday_mom': intraday_mom,
            'intraday_win_rate': win_rate,
            'signal': signal,
        })
    except Exception as e:
        logger.debug("calc_intraday_momentum error: %s", e)
    return result


def calc_momentum_consistency(data: pd.DataFrame, window: int = 5) -> Dict:
    """
    因子3：动量一致性因子
    统计过去N日中，隔夜收益与日内收益同为正的天数占比

    正向选股：占比100%优先，上涨动能无分歧，持续性强
    """
    result = {'mom_consistency': 0.0, 'signal': '中性'}
    try:
        close = data['close']
        open_ = data['open']
        if len(data) < window + 2:
            return result

        # 隔夜收益（对齐到T日，使用T日开盘/T-1日收盘）
        overnight_rets = np.log(open_.values[1:] / close.values[:-1])  # shape: n-1
        # 日内收益
        intraday_rets = np.log(close.values[1:] / open_.values[1:])    # shape: n-1，对齐T日

        # 取最近 window 天（都对齐到同一个 T 日）
        on = overnight_rets[-window:]
        id_ = intraday_rets[-window:]

        both_positive = float(np.mean((on > 0) & (id_ > 0)))
        signal = '做多' if both_positive >= 0.8 else ('做空' if both_positive < 0.4 else '中性')
        result.update({
            'mom_consistency': both_positive,
            'signal': signal,
        })
    except Exception as e:
        logger.debug("calc_momentum_consistency error: %s", e)
    return result


def calc_momentum_reversal_warning(data: pd.DataFrame, window: int = 3) -> Dict:
    """
    因子4：动量反转预警因子（避顶）
    隔夜收益为正，但日内收益连续N日为负

    反向避顶：高开低走，主力诱多出货，直接剔除
    """
    result = {'mom_reversal_warning': False, 'risk_score': 0.0, 'signal': '正常'}
    try:
        close = data['close']
        open_ = data['open']
        if len(data) < window + 2:
            return result

        overnight_rets = np.log(open_.values[1:] / close.values[:-1])
        intraday_rets = np.log(close.values[1:] / open_.values[1:])

        # 最近 window 天
        on_recent = overnight_rets[-window:]
        id_recent = intraday_rets[-window:]

        # 判断：隔夜正 & 日内持续负
        overnight_positive = np.mean(on_recent > 0)
        intraday_all_neg = np.all(id_recent < 0)
        warning = bool(overnight_positive >= 0.67 and intraday_all_neg)
        risk = float(overnight_positive * (1 - np.mean(id_recent > 0)))

        result.update({
            'mom_reversal_warning': warning,
            'risk_score': min(risk, 1.0),
            'signal': '诱多出货' if warning else '正常',
        })
    except Exception as e:
        logger.debug("calc_momentum_reversal_warning error: %s", e)
    return result


def calc_tail_momentum(data: pd.DataFrame, window: int = 5) -> Dict:
    """
    因子5：尾盘动量因子
    用日K收盘/VWAP合成近似「尾盘强弱」：
      VWAP_approx = amount / volume
      TailRatio = (Close - VWAP_approx) / VWAP_approx

    正向选股：持续为正代表尾盘主力抢筹，次日上涨胜率>60%
    """
    result = {'tail_mom': 0.0, 'tail_win_rate': 0.5, 'signal': '中性'}
    try:
        close = data['close']
        # 尝试获取 amount（成交额）
        amount = _safe_get_col(data, 'amount', 'turnover_money', 'money')
        volume = data['volume']

        if amount is not None and len(close) >= window:
            # 计算 VWAP 近似
            vwap_approx = amount / (volume + 1e-8)
            # 尾盘强弱：收盘价与 VWAP 的偏差
            tail_ratio = (close - vwap_approx) / (vwap_approx + 1e-8)
            recent = tail_ratio.iloc[-window:].values
            tail_mom = float(np.sum(recent))
            win_rate = float(np.mean(recent > 0))
        else:
            # 退化：用收盘 vs 均价近似
            if len(close) < window + 1:
                return result
            ma = close.rolling(window).mean()
            tail_ratio = (close - ma) / (ma + 1e-8)
            recent = tail_ratio.iloc[-window:].values
            tail_mom = float(np.sum(recent))
            win_rate = float(np.mean(recent > 0))

        signal = '尾盘抢筹' if (tail_mom > 0 and win_rate >= 0.6) else (
            '尾盘出货' if (tail_mom < 0 and win_rate < 0.4) else '中性'
        )
        result.update({
            'tail_mom': tail_mom,
            'tail_win_rate': win_rate,
            'signal': signal,
        })
    except Exception as e:
        logger.debug("calc_tail_momentum error: %s", e)
    return result


# ===================================================================
# 大类二：量价结构精细化日频因子
# ===================================================================

def calc_up_down_vol_ratio(data: pd.DataFrame, window: int = 10) -> Dict:
    """
    因子6：涨跌量比因子
    UpDownVolRatio = MA(上涨日成交量, N) / MA(下跌日成交量, N)

    正向选股：>1.2 优先，代表上涨放量、下跌缩量，健康上涨
    反向避顶：<0.8 代表缩量上涨/放量下跌，见顶信号
    """
    result = {'up_down_vol_ratio': 1.0, 'signal': '中性'}
    try:
        close = data['close']
        volume = data['volume']
        if len(data) < window:
            return result

        returns = close.pct_change(fill_method=None)
        up_mask = returns > 0
        down_mask = returns < 0

        up_vol = volume.where(up_mask, 0.0).rolling(window).mean()
        down_vol = volume.where(down_mask, 0.0).rolling(window).mean()

        ratio = up_vol / (down_vol + 1e-8)
        last = float(ratio.iloc[-1])

        signal = '放量上涨' if last > 1.2 else ('缩量滞涨' if last < 0.8 else '中性')
        result.update({
            'up_down_vol_ratio': last,
            'signal': signal,
        })
    except Exception as e:
        logger.debug("calc_up_down_vol_ratio error: %s", e)
    return result


def calc_vol_lead_lag(data: pd.DataFrame, window: int = 20) -> Dict:
    """
    因子7：量能领先滞后因子
    计算过去N日中，成交量变化「领先于」价格变化的天数占比
    领先定义：T日量增加，T+1日价上涨（量提前价1天启动）

    正向选股：占比>60%优先，量能提前启动，上涨持续性强
    """
    result = {'vol_lead_ratio': 0.5, 'signal': '中性'}
    try:
        close = data['close']
        volume = data['volume']
        if len(data) < window + 2:
            return result

        vol_chg = volume.pct_change(fill_method=None)
        price_chg = close.pct_change(fill_method=None)

        # 量先于价：T日量增 & T+1日价涨
        vol_up = (vol_chg > 0).values[:-1]  # T日量增
        price_up_next = (price_chg > 0).values[1:]  # T+1日价涨

        recent_vol = vol_up[-window:]
        recent_price = price_up_next[-window:]
        lead_ratio = float(np.mean(recent_vol & recent_price))

        signal = '量领先价' if lead_ratio > 0.6 else ('价量同步' if lead_ratio > 0.4 else '量滞后')
        result.update({
            'vol_lead_ratio': lead_ratio,
            'signal': signal,
        })
    except Exception as e:
        logger.debug("calc_vol_lead_lag error: %s", e)
    return result


def calc_shrink_rise_warning(data: pd.DataFrame, window: int = 3) -> Dict:
    """
    因子8：缩量上涨预警因子（避顶）
    连续N日收盘价上涨，成交量连续N日下降

    反向避顶：买盘乏力，即将见顶，直接剔除
    """
    result = {'shrink_rise_warning': False, 'signal': '正常'}
    try:
        close = data['close']
        volume = data['volume']
        if len(data) < window + 1:
            return result

        # 检查最近 window 天
        close_rising = all(close.iloc[-(window):].diff().dropna() > 0)
        vol_falling = all(volume.iloc[-(window):].diff().dropna() < 0)
        warning = bool(close_rising and vol_falling)

        result.update({
            'shrink_rise_warning': warning,
            'signal': '缩量上涨⚠' if warning else '正常',
        })
    except Exception as e:
        logger.debug("calc_shrink_rise_warning error: %s", e)
    return result


def calc_surge_vol_stall_warning(data: pd.DataFrame, vol_window: int = 20, pct_threshold: float = 0.01) -> Dict:
    """
    因子9：放量滞涨预警因子（避顶）
    单日成交量 > N日均量的2倍，当日涨跌幅绝对值 < threshold

    反向避顶：高位放量滞涨，主力出货，直接剔除
    """
    result = {'surge_vol_stall': False, 'signal': '正常'}
    try:
        close = data['close']
        volume = data['volume']
        if len(data) < vol_window + 1:
            return result

        ma_vol = volume.rolling(vol_window).mean()
        last_vol_ratio = float(volume.iloc[-1] / (ma_vol.iloc[-1] + 1e-8))
        last_chg = abs(float(close.pct_change(fill_method=None).iloc[-1]))

        warning = bool(last_vol_ratio > 2.0 and last_chg < pct_threshold)
        result.update({
            'surge_vol_stall': warning,
            'surge_vol_ratio': last_vol_ratio,
            'signal': '放量滞涨⚠' if warning else '正常',
        })
    except Exception as e:
        logger.debug("calc_surge_vol_stall_warning error: %s", e)
    return result


def calc_price_vol_divergence(data: pd.DataFrame, price_window: int = 20) -> Dict:
    """
    因子10：量价背离强度因子（避顶）
    过去N日价格创新高，但成交量创新低的幅度

    反向避顶：幅度>20%直接剔除，背离越严重，见顶概率越高
    """
    result = {'pv_divergence': 0.0, 'price_new_high': False, 'vol_new_low': False, 'signal': '正常'}
    try:
        close = data['close']
        volume = data['volume']
        if len(data) < price_window + 1:
            return result

        window_close = close.iloc[-price_window:]
        window_vol = volume.iloc[-price_window:]
        last_close = float(close.iloc[-1])
        last_vol = float(volume.iloc[-1])
        max_close = float(window_close.max())
        min_vol = float(window_vol.min())
        mean_vol = float(window_vol.mean())

        price_at_high = bool(last_close >= max_close * 0.98)  # 价格在高位（近98%高位）
        vol_at_low = bool(last_vol <= min_vol * 1.05)          # 量在低位

        # 背离强度：量低于均量的偏离程度
        divergence = float((mean_vol - last_vol) / (mean_vol + 1e-8)) if price_at_high else 0.0
        divergence = max(0.0, divergence)

        signal = '量价背离严重⚠' if (price_at_high and vol_at_low and divergence > 0.2) else (
            '量价背离⚠' if (price_at_high and vol_at_low) else '正常'
        )
        result.update({
            'pv_divergence': divergence,
            'price_new_high': price_at_high,
            'vol_new_low': vol_at_low,
            'signal': signal,
        })
    except Exception as e:
        logger.debug("calc_price_vol_divergence error: %s", e)
    return result


def calc_turnover_stability(data: pd.DataFrame, window: int = 20) -> Dict:
    """
    因子11：换手率平稳度因子
    过去N日换手率的变异系数（标准差/均值）

    正向选股：值越小越好，量能平稳无脉冲，上涨持续性强
    反向避顶：>1.5，换手率脉冲式波动，主力进出频繁，直接剔除
    """
    result = {'turnover_cv': 0.5, 'signal': '中性'}
    try:
        turn = _safe_get_col(data, 'turnover', 'turn_over', 'turnoverrate', 'pct_turn')
        if turn is None or len(turn) < window:
            return result

        recent = turn.iloc[-window:].values
        mean_turn = np.mean(recent)
        std_turn = np.std(recent)
        cv = float(std_turn / (mean_turn + 1e-8))

        signal = '量能平稳' if cv < 0.4 else ('轻微脉冲' if cv < 1.0 else '脉冲过热⚠')
        result.update({
            'turnover_cv': cv,
            'signal': signal,
        })
    except Exception as e:
        logger.debug("calc_turnover_stability error: %s", e)
    return result


# ===================================================================
# 综合调用接口
# ===================================================================

class MomentumFactorCalculator:
    """
    动量 & 量价结构因子计算器
    整合11个日频因子，返回标准化评分
    """

    def __init__(self):
        self.name = "momentum_factors_v1"

    def calculate(self, data: pd.DataFrame) -> Dict:
        """
        计算所有动量&量价结构因子

        参数：
            data: 日频K线 DataFrame (open/high/low/close/volume/turnover/amount)

        返回：
            dict，包含所有因子值、综合评分
              'momentum_score': float 0~1，越高越有短期上涨潜力
              'warning_signals': list[str]，见顶预警信号
              'positive_signals': list[str]，正向信号
        """
        if data is None or len(data) < 25:
            return {
                'momentum_score': 0.5,
                'warning_signals': [],
                'positive_signals': [],
                'details': {}
            }

        warnings_list = []
        positives = []
        details = {}

        # ── 大类一：日内动量 ──
        r1 = calc_overnight_momentum(data)
        details['overnight_mom'] = r1['overnight_mom']
        details['overnight_win_rate'] = r1['overnight_win_rate']
        if r1['signal'] == '做多':
            positives.append(f"隔夜动量强劲({r1['overnight_mom']:+.3f})")
        elif r1['signal'] == '做空':
            warnings_list.append(f"隔夜持续走弱({r1['overnight_mom']:+.3f})")

        r2 = calc_intraday_momentum(data)
        details['intraday_mom'] = r2['intraday_mom']
        details['intraday_win_rate'] = r2['intraday_win_rate']
        if r2['signal'] == '做多':
            positives.append(f"日内动量强({r2['intraday_mom']:+.3f})")
        elif r2['signal'] == '做空':
            warnings_list.append(f"日内持续回落({r2['intraday_mom']:+.3f})")

        r3 = calc_momentum_consistency(data)
        details['mom_consistency'] = r3['mom_consistency']
        if r3['mom_consistency'] >= 0.8:
            positives.append(f"动量高度一致({r3['mom_consistency']:.0%})")
        elif r3['mom_consistency'] < 0.4:
            warnings_list.append(f"动量分歧({r3['mom_consistency']:.0%})")

        r4 = calc_momentum_reversal_warning(data)
        details['mom_reversal_warning'] = int(r4['mom_reversal_warning'])
        details['mom_reversal_risk'] = r4['risk_score']
        if r4['mom_reversal_warning']:
            warnings_list.append("高开低走-诱多出货⚠")

        r5 = calc_tail_momentum(data)
        details['tail_mom'] = r5['tail_mom']
        details['tail_win_rate'] = r5['tail_win_rate']
        if r5['signal'] == '尾盘抢筹':
            positives.append(f"尾盘持续抢筹({r5['tail_win_rate']:.0%})")
        elif r5['signal'] == '尾盘出货':
            warnings_list.append(f"尾盘持续出货⚠")

        # ── 大类二：量价结构 ──
        r6 = calc_up_down_vol_ratio(data)
        details['up_down_vol_ratio'] = r6['up_down_vol_ratio']
        if r6['signal'] == '放量上涨':
            positives.append(f"上涨放量健康({r6['up_down_vol_ratio']:.2f})")
        elif r6['signal'] == '缩量滞涨':
            warnings_list.append(f"缩量滞涨⚠({r6['up_down_vol_ratio']:.2f})")

        r7 = calc_vol_lead_lag(data)
        details['vol_lead_ratio'] = r7['vol_lead_ratio']
        if r7['signal'] == '量领先价':
            positives.append(f"量能领先价({r7['vol_lead_ratio']:.0%})")

        r8 = calc_shrink_rise_warning(data)
        details['shrink_rise_warning'] = int(r8['shrink_rise_warning'])
        if r8['shrink_rise_warning']:
            warnings_list.append("连续缩量上涨-买盘乏力⚠")

        r9 = calc_surge_vol_stall_warning(data)
        details['surge_vol_stall'] = int(r9['surge_vol_stall'])
        if r9['surge_vol_stall']:
            warnings_list.append("放量滞涨-主力出货⚠")

        r10 = calc_price_vol_divergence(data)
        details['pv_divergence'] = r10['pv_divergence']
        details['price_new_high'] = int(r10['price_new_high'])
        if '严重' in r10['signal']:
            warnings_list.append(f"量价背离严重({r10['pv_divergence']:.0%})⚠")
        elif '背离' in r10['signal']:
            warnings_list.append("量价轻度背离⚠")

        r11 = calc_turnover_stability(data)
        details['turnover_cv'] = r11['turnover_cv']
        if r11['signal'] == '量能平稳':
            positives.append(f"换手率平稳({r11['turnover_cv']:.2f})")
        elif r11['signal'] == '脉冲过热⚠':
            warnings_list.append("换手率脉冲过热⚠")

        # ── 综合评分计算 ──
        # 正向加分 vs 负向扣分
        n_pos = len(positives)
        n_warn = len(warnings_list)

        # 基础分：由动量方向决定
        base = 0.5
        # 隔夜+日内动量组合加权
        overnight_contrib = np.tanh(details.get('overnight_mom', 0) * 10) * 0.15
        intraday_contrib = np.tanh(details.get('intraday_mom', 0) * 8) * 0.15
        consistency_contrib = (details.get('mom_consistency', 0.5) - 0.5) * 0.2
        ud_ratio = details.get('up_down_vol_ratio', 1.0)
        vol_contrib = np.tanh((ud_ratio - 1.0) * 3) * 0.1

        score = base + overnight_contrib + intraday_contrib + consistency_contrib + vol_contrib

        # 预警惩罚
        score -= n_warn * 0.06
        # 正向加分
        score += n_pos * 0.03

        # 反转预警 & 放量滞涨 强制大扣分
        if details.get('mom_reversal_warning', 0):
            score -= 0.12
        if details.get('surge_vol_stall', 0):
            score -= 0.10
        if details.get('shrink_rise_warning', 0):
            score -= 0.08

        momentum_score = float(np.clip(score, 0.0, 1.0))

        return {
            'momentum_score': momentum_score,
            'warning_signals': warnings_list,
            'positive_signals': positives,
            'details': details,
        }


# 单例
_momentum_calc = None


def get_momentum_calculator() -> MomentumFactorCalculator:
    global _momentum_calc
    if _momentum_calc is None:
        _momentum_calc = MomentumFactorCalculator()
    return _momentum_calc
