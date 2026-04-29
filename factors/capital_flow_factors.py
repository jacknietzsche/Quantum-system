#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
资金流细分维度 & 流动性精细化日频因子库 v1.0
=============================================
研报/顶刊依据:
  Frazzini & Lamont(2008) 《Dumb Money: Mutual Fund Flows》JFE
  中信金工《A股资金行为全景分析》2023
  广发金工《细分资金流因子的选股有效性》2024
  Amihud(2002) 《Illiquidity and Stock Returns》JFM
  Pastor & Stambaugh(2003) 《Liquidity Risk and Expected Stock Returns》JPE
  国君金工《流动性因子的A股短期应用》2023

大类三：资金流细分维度日频因子（6个）
  1. 北向资金净流入强度 (north_flow_intensity)
  2. 融资资金健康度 (margin_fund_health)
  3. 主力资金净流入持续性 (main_flow_persistence)
  4. 散户接盘预警 (retail_takeover_warning)
  5. 价资背离预警 (price_capital_divergence)
  6. 资金流多空强度综合 (flow_strength_score)

大类四：流动性精细化日频因子（5个）
  7. Amihud非流动性边际变化 (amihud_chg)
  8. 换手率边际变化 (turnover_chg)
  9. 日内价差因子 (intraday_spread)
  10. 行业成交额占比变化 (sector_amt_ratio_chg)
  11. 流动性综合评分 (liquidity_score)

注意：部分因子（北向、融资、主力资金）需要外部市场数据传入；
      纯K线可算因子（Amihud、换手、价差）可独立运行。
"""

import warnings
warnings.filterwarnings('ignore')

import pandas as pd
import numpy as np
from typing import Dict, Optional, List
import logging

logger = logging.getLogger("capital_flow_factors")


# ===================================================================
# 工具函数
# ===================================================================

def _safe_get_col(data: pd.DataFrame, *names) -> Optional[pd.Series]:
    for name in names:
        if name in data.columns:
            return data[name]
    return None


# ===================================================================
# 大类三：资金流细分维度日频因子
# ===================================================================

def calc_north_flow_intensity(
    north_flow_5d: float = 0.0,
    market_cap: float = 1e10,
    threshold: float = 0.002
) -> Dict:
    """
    因子1：北向资金净流入强度
    NorthFlow = 过去5日北向资金累计净流入 / 流通市值

    正向选股：值越大越好，外资持续买入代表定价权认可
    数据来源：外部传入（market_data_fetcher 获取）

    参数：
        north_flow_5d: 过去5日北向资金净流入额（元）
        market_cap: 流通市值（元）
        threshold: 强流入阈值（比例）
    """
    result = {'north_flow_intensity': 0.0, 'signal': '中性'}
    try:
        if market_cap <= 0:
            return result
        intensity = float(north_flow_5d / market_cap)
        signal = '北向强买' if intensity > threshold else (
            '北向净卖' if intensity < -threshold else '中性'
        )
        result.update({'north_flow_intensity': intensity, 'signal': signal})
    except Exception as e:
        logger.debug("calc_north_flow_intensity error: %s", e)
    return result


def calc_margin_fund_health(
    margin_balance_5d_growth: float = 0.0,  # 融资余额5日增速
    price_5d_return: float = 0.0,           # 个股5日涨幅
) -> Dict:
    """
    因子2：融资资金健康度
    FinHealth = 融资余额5日增速 / 股价5日涨幅

    正向选股：1.0~1.5 区间最优，杠杆与涨幅匹配
    反向避顶：>2.0 代表杠杆过热，直接剔除
    """
    result = {'margin_health': 1.0, 'signal': '中性'}
    try:
        if abs(price_5d_return) < 1e-6:
            health = 1.0 if abs(margin_balance_5d_growth) < 0.02 else 2.0
        else:
            health = float(margin_balance_5d_growth / price_5d_return)

        if 1.0 <= health <= 1.5:
            signal = '杠杆健康'
        elif health > 2.0:
            signal = '杠杆过热⚠'
        elif health < 0:
            signal = '减杠杆'
        else:
            signal = '中性'

        result.update({'margin_health': health, 'signal': signal})
    except Exception as e:
        logger.debug("calc_margin_fund_health error: %s", e)
    return result


def calc_main_flow_persistence(
    main_flow_days_positive: int = 0,
    total_days: int = 10
) -> Dict:
    """
    因子3：主力资金净流入持续性
    过去N日主力资金净流入的天数占比

    正向选股：>70% 优先，主力持续建仓
    反向避顶：<30% 代表主力持续出货，直接剔除

    参数：
        main_flow_days_positive: 净流入正的天数
        total_days: 总天数
    """
    result = {'main_flow_persistence': 0.5, 'signal': '中性'}
    try:
        if total_days <= 0:
            return result
        ratio = float(main_flow_days_positive / total_days)
        if ratio > 0.7:
            signal = '主力持续建仓'
        elif ratio < 0.3:
            signal = '主力持续出货⚠'
        else:
            signal = '中性'
        result.update({'main_flow_persistence': ratio, 'signal': signal})
    except Exception as e:
        logger.debug("calc_main_flow_persistence error: %s", e)
    return result


def calc_retail_takeover_warning(
    retail_net_inflow: float = 0.0,
    total_amount: float = 1.0
) -> Dict:
    """
    因子4：散户接盘预警
    RetailRatio = 小单净流入额 / 当日成交额

    反向避顶：>30% 代表散户高位接盘，主力出货，直接剔除
    """
    result = {'retail_ratio': 0.0, 'signal': '正常'}
    try:
        if total_amount <= 0:
            return result
        ratio = float(retail_net_inflow / total_amount)
        ratio = max(0.0, ratio)
        signal = '散户接盘⚠' if ratio > 0.30 else ('散户轻度接盘' if ratio > 0.20 else '正常')
        result.update({'retail_ratio': ratio, 'signal': signal})
    except Exception as e:
        logger.debug("calc_retail_takeover_warning error: %s", e)
    return result


def calc_price_capital_divergence(
    price_5d_return: float = 0.0,
    main_net_flow_5d: float = 0.0
) -> Dict:
    """
    因子5：价资背离预警
    过去5日股价累计上涨，但主力资金累计净流出

    反向避顶：价涨资出，主力诱多，直接剔除
    """
    result = {'price_capital_diverge': False, 'signal': '正常'}
    try:
        diverge = bool(price_5d_return > 0.02 and main_net_flow_5d < 0)
        signal = '价涨资出-主力诱多⚠' if diverge else '正常'
        result.update({'price_capital_diverge': diverge, 'signal': signal})
    except Exception as e:
        logger.debug("calc_price_capital_divergence error: %s", e)
    return result


def calc_flow_strength_from_data(data: pd.DataFrame, window: int = 10) -> Dict:
    """
    因子6：基于纯日K数据的资金流多空强度评估
    （无需外部资金流数据，用价量合成近似主力资金）

    核心逻辑：
    - 大涨大量 = 主力买入
    - 大跌大量 = 主力卖出
    - 以20%分位成交量为小单，其余为大单（简化估算）

    返回：
        flow_strength: -1~1，>0代表主力买入，<0代表主力卖出
        flow_score: 0~1
    """
    result = {'flow_strength': 0.0, 'flow_score': 0.5, 'signal': '中性'}
    try:
        close = data['close']
        volume = data['volume']
        if len(data) < window:
            return result

        returns = close.pct_change(fill_method=None).fillna(0)

        # 用涨跌幅加权成交量作为资金流方向代理
        # 正收益 * 成交量 = 买盘力量
        # 负收益 * 成交量 = 卖盘力量
        signed_vol = returns * volume
        recent = signed_vol.iloc[-window:].values
        flow_strength = float(np.sum(recent) / (np.sum(np.abs(recent)) + 1e-8))

        # 持续性：最近N日净流入天数
        n_positive = int(np.sum(recent > 0))
        persistence = n_positive / window

        flow_score = 0.5 + flow_strength * 0.3 + (persistence - 0.5) * 0.2
        flow_score = float(np.clip(flow_score, 0, 1))

        signal = '主力净买入' if flow_strength > 0.2 else (
            '主力净卖出⚠' if flow_strength < -0.2 else '中性'
        )
        result.update({
            'flow_strength': flow_strength,
            'flow_persistence': persistence,
            'flow_score': flow_score,
            'signal': signal,
        })
    except Exception as e:
        logger.debug("calc_flow_strength_from_data error: %s", e)
    return result


# ===================================================================
# 大类四：流动性精细化日频因子
# ===================================================================

def calc_amihud_change(data: pd.DataFrame, short_w: int = 10, long_w: int = 60) -> Dict:
    """
    因子7：Amihud非流动性边际变化
    AmihudChg = MA(Amihud, short_w) / MA(Amihud, long_w)
    其中 Amihud_t = |R_t| / AMT_t（成交额的绝对收益冲击）

    正向选股：<0.8，流动性显著改善
    反向避顶：>1.5，流动性恶化，直接剔除
    """
    result = {'amihud_chg': 1.0, 'signal': '中性'}
    try:
        close = data['close']
        amount = _safe_get_col(data, 'amount', 'turnover_money', 'money')
        volume = data['volume']
        if len(data) < long_w:
            return result

        returns = close.pct_change(fill_method=None).abs()
        if amount is not None:
            amt = amount
        else:
            # 近似：成交量 × 收盘价
            amt = volume * close

        amihud = returns / (amt + 1e-8) * 1e8  # 放大便于比较

        ma_short = amihud.rolling(short_w).mean()
        ma_long = amihud.rolling(long_w).mean()
        chg = float(ma_short.iloc[-1] / (ma_long.iloc[-1] + 1e-8))

        signal = '流动性改善' if chg < 0.8 else ('流动性恶化⚠' if chg > 1.5 else '中性')
        result.update({'amihud_chg': chg, 'signal': signal})
    except Exception as e:
        logger.debug("calc_amihud_change error: %s", e)
    return result


def calc_turnover_change(data: pd.DataFrame, short_w: int = 5, long_w: int = 20) -> Dict:
    """
    因子8：换手率边际变化
    TurnChg = MA(Turn, short_w) / MA(Turn, long_w)

    正向选股：1.2~2.0 区间最优，温和放量
    反向避顶：>2.5 代表脉冲放量过热，直接剔除
    """
    result = {'turnover_chg': 1.0, 'signal': '中性'}
    try:
        turn = _safe_get_col(data, 'turnover', 'turn_over', 'turnoverrate', 'pct_turn')
        if turn is None:
            # 用成交量代替
            vol = data['volume']
            if len(vol) < long_w:
                return result
            ma_s = vol.rolling(short_w).mean()
            ma_l = vol.rolling(long_w).mean()
        else:
            if len(turn) < long_w:
                return result
            ma_s = turn.rolling(short_w).mean()
            ma_l = turn.rolling(long_w).mean()

        chg = float(ma_s.iloc[-1] / (ma_l.iloc[-1] + 1e-8))
        if 1.2 <= chg <= 2.0:
            signal = '温和放量'
        elif chg > 2.5:
            signal = '脉冲放量⚠'
        elif chg < 0.6:
            signal = '明显缩量'
        else:
            signal = '中性'

        result.update({'turnover_chg': chg, 'signal': signal})
    except Exception as e:
        logger.debug("calc_turnover_change error: %s", e)
    return result


def calc_intraday_spread(data: pd.DataFrame, window: int = 10) -> Dict:
    """
    因子9：日内价差因子（流动性代理）
    Spread = MA((High - Low) / Close, window)

    正向选股：值越小越好，流动性越好，冲击成本越低
    反向避顶：单日值放大3倍以上，多空分歧加剧，直接剔除
    """
    result = {'intraday_spread': 0.02, 'spread_chg': 1.0, 'signal': '中性'}
    try:
        high = data['high']
        low = data['low']
        close = data['close']
        if len(data) < window + 5:
            return result

        spread = (high - low) / (close + 1e-8)
        ma_spread = spread.rolling(window).mean()

        last_spread = float(spread.iloc[-1])
        ma_val = float(ma_spread.iloc[-1])
        chg = last_spread / (ma_val + 1e-8)

        signal = '流动性良好' if ma_val < 0.02 else ('波动过大⚠' if chg > 3.0 else '中性')
        result.update({
            'intraday_spread': ma_val,
            'spread_chg': chg,
            'signal': signal,
        })
    except Exception as e:
        logger.debug("calc_intraday_spread error: %s", e)
    return result


def calc_sector_amt_ratio_change(
    stock_5d_avg_amt: float = 0.0,
    stock_20d_avg_amt: float = 0.0,
    sector_5d_avg_amt: float = 1.0,
    sector_20d_avg_amt: float = 1.0
) -> Dict:
    """
    因子10：行业成交额占比变化
    AmtRatioChg = (个股/行业 近5日均值) / (个股/行业 近20日均值)

    正向选股：值越大越好，个股在行业内关注度持续提升
    """
    result = {'sector_amt_ratio_chg': 1.0, 'signal': '中性'}
    try:
        if sector_5d_avg_amt <= 0 or sector_20d_avg_amt <= 0:
            return result
        ratio_5d = stock_5d_avg_amt / sector_5d_avg_amt
        ratio_20d = stock_20d_avg_amt / sector_20d_avg_amt
        chg = float(ratio_5d / (ratio_20d + 1e-8))
        signal = '行业内关注度提升' if chg > 1.2 else ('关注度下降' if chg < 0.8 else '中性')
        result.update({'sector_amt_ratio_chg': chg, 'signal': signal})
    except Exception as e:
        logger.debug("calc_sector_amt_ratio_change error: %s", e)
    return result


# ===================================================================
# 综合调用接口
# ===================================================================

class CapitalFlowFactorCalculator:
    """
    资金流细分 & 流动性精细化因子计算器
    整合11个日频因子，可传入外部市场数据增强信号质量
    """

    def __init__(self):
        self.name = "capital_flow_factors_v1"

    def calculate(self, data: pd.DataFrame,
                  market_extra: Optional[Dict] = None) -> Dict:
        """
        计算资金流 & 流动性因子

        参数：
            data: 日频K线 DataFrame
            market_extra: 外部市场数据（可选），格式：
              {
                'north_flow_5d': float,         # 北向5日净流入（元）
                'market_cap': float,             # 流通市值
                'margin_5d_growth': float,       # 融资余额5日增速
                'price_5d_return': float,        # 个股5日收益
                'main_flow_positive_days': int,  # 主力净流入天数
                'main_flow_total_days': int,     # 总天数
                'retail_net_inflow': float,      # 小单净流入
                'total_amount_1d': float,        # 当日成交额
                'main_net_flow_5d': float,       # 主力5日净流入
              }

        返回：
            dict 包含 flow_liquidity_score, warning_signals, positive_signals, details
        """
        if data is None or len(data) < 15:
            return {
                'flow_liquidity_score': 0.5,
                'warning_signals': [],
                'positive_signals': [],
                'details': {}
            }

        warnings_list = []
        positives = []
        details = {}
        market_extra = market_extra or {}

        # ── 大类三：资金流（需外部数据时优雅退化） ──
        north_flow_5d = market_extra.get('north_flow_5d', 0.0)
        market_cap = market_extra.get('market_cap', 1e10)
        r1 = calc_north_flow_intensity(north_flow_5d, market_cap)
        details['north_flow_intensity'] = r1['north_flow_intensity']
        if r1['signal'] == '北向强买':
            positives.append(f"北向资金持续买入")
        elif r1['signal'] == '北向净卖':
            warnings_list.append("北向资金持续流出⚠")

        margin_5d_growth = market_extra.get('margin_5d_growth', 0.0)
        price_5d_return = market_extra.get('price_5d_return', 0.0)
        r2 = calc_margin_fund_health(margin_5d_growth, price_5d_return)
        details['margin_health'] = r2['margin_health']
        if r2['signal'] == '杠杆健康':
            positives.append("融资资金健康匹配")
        elif r2['signal'] == '杠杆过热⚠':
            warnings_list.append("融资杠杆过热⚠")

        main_pos_days = market_extra.get('main_flow_positive_days', 0)
        main_total = market_extra.get('main_flow_total_days', 10)
        r3 = calc_main_flow_persistence(main_pos_days, main_total)
        details['main_flow_persistence'] = r3['main_flow_persistence']
        if '建仓' in r3['signal']:
            positives.append("主力持续建仓")
        elif '出货' in r3['signal']:
            warnings_list.append("主力持续出货⚠")

        retail_net = market_extra.get('retail_net_inflow', 0.0)
        total_amt = market_extra.get('total_amount_1d', 1.0)
        r4 = calc_retail_takeover_warning(retail_net, total_amt)
        details['retail_ratio'] = r4['retail_ratio']
        if '接盘' in r4['signal'] and '轻度' not in r4['signal']:
            warnings_list.append("散户高位接盘⚠")

        main_net_5d = market_extra.get('main_net_flow_5d', 0.0)
        r5 = calc_price_capital_divergence(price_5d_return, main_net_5d)
        details['price_capital_diverge'] = int(r5['price_capital_diverge'])
        if r5['price_capital_diverge']:
            warnings_list.append("价涨资出-诱多⚠")

        # ── 纯K线资金流强度（无需外部数据） ──
        r6 = calc_flow_strength_from_data(data)
        details['flow_strength'] = r6['flow_strength']
        details['flow_persistence'] = r6.get('flow_persistence', 0.5)
        if '净买入' in r6['signal']:
            positives.append(f"量价合成主力净买入({r6['flow_strength']:+.2f})")
        elif '净卖出' in r6['signal']:
            warnings_list.append(f"量价合成主力净卖出⚠")

        # ── 大类四：流动性因子 ──
        r7 = calc_amihud_change(data)
        details['amihud_chg'] = r7['amihud_chg']
        if '改善' in r7['signal']:
            positives.append("流动性持续改善")
        elif '恶化' in r7['signal']:
            warnings_list.append("流动性急剧恶化⚠")

        r8 = calc_turnover_change(data)
        details['turnover_chg'] = r8['turnover_chg']
        if r8['signal'] == '温和放量':
            positives.append(f"温和放量({r8['turnover_chg']:.2f})")
        elif r8['signal'] == '脉冲放量⚠':
            warnings_list.append("脉冲放量⚠")

        r9 = calc_intraday_spread(data)
        details['intraday_spread'] = r9['intraday_spread']
        details['spread_chg'] = r9['spread_chg']
        if '波动过大' in r9['signal']:
            warnings_list.append("日内价差突扩⚠")
        elif '良好' in r9['signal']:
            positives.append("流动性好")

        # 行业占比（外部数据，退化为中性）
        s5d = market_extra.get('stock_5d_avg_amt', 0.0)
        s20d = market_extra.get('stock_20d_avg_amt', 1.0)
        sec5d = market_extra.get('sector_5d_avg_amt', 1.0)
        sec20d = market_extra.get('sector_20d_avg_amt', 1.0)
        r10 = calc_sector_amt_ratio_change(s5d, s20d, sec5d, sec20d)
        details['sector_amt_ratio_chg'] = r10['sector_amt_ratio_chg']
        if '提升' in r10['signal']:
            positives.append("行业内关注度提升")

        # ── 综合评分 ──
        n_warn = len(warnings_list)
        n_pos = len(positives)

        base = 0.5
        # 资金流强度贡献
        flow_s = details.get('flow_strength', 0.0)
        flow_contrib = np.tanh(flow_s * 3) * 0.15

        # 流动性贡献（amihud_chg 下降 = 流动性改善 = 正向）
        amihud_chg = details.get('amihud_chg', 1.0)
        liquidity_contrib = (1.0 - min(amihud_chg, 2.0)) * 0.1

        # 换手率（温和放量加分）
        turn_chg = details.get('turnover_chg', 1.0)
        turn_contrib = 0.05 if (1.2 <= turn_chg <= 2.0) else (-0.05 if turn_chg > 2.5 else 0.0)

        score = base + flow_contrib + liquidity_contrib + turn_contrib
        score += n_pos * 0.03
        score -= n_warn * 0.06

        # 严重预警强制扣分
        if details.get('price_capital_diverge', 0):
            score -= 0.10
        if details.get('retail_ratio', 0) > 0.30:
            score -= 0.08

        flow_liquidity_score = float(np.clip(score, 0.0, 1.0))

        return {
            'flow_liquidity_score': flow_liquidity_score,
            'warning_signals': warnings_list,
            'positive_signals': positives,
            'details': details,
        }


_capital_calc = None


def get_capital_flow_calculator() -> CapitalFlowFactorCalculator:
    global _capital_calc
    if _capital_calc is None:
        _capital_calc = CapitalFlowFactorCalculator()
    return _capital_calc
