#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
防短期见顶因子库 v1.0
======================
研报依据：华泰《交易拥挤与反转》、海通量价择时、中信《去除共性后的动量》
         国君《微观结构拥挤度》、A股杠杆资金行为实证论文

因子定位：
  - 个股处于上升趋势中，识别"过热/虚强/资金撤退/即将短期见顶"
  - 全部日频，只用价+量+换手率+成交额+两融，不用财报滞后数据
  - 目标：尽量不买在短期最高点，减少追高回撤

10个因子：
  1. 异常换手率（拥挤度核心）
  2. 20日量价相关系数（量价健康度）
  3. 残差动量衰减（相对强弱动量衰减）
  4. 近10日波动率跳升（高位震荡出货）
  5. 缩量新高（最经典短线见顶）
  6. 超买强度（优化RSI）
  7. 成交额拥挤度（全市场占比）
  8. 融资买入占比（杠杆见顶）
  9. 上涨动能衰减（斜率拐头）
  10. 近5日收益离散度（内部分歧加大）
"""

import warnings
warnings.filterwarnings('ignore')

import pandas as pd
import numpy as np
from typing import Dict, Optional, Tuple
import logging

logger = logging.getLogger("anti_top_factors")


# ============================================================
# 因子1：异常换手率（拥挤度核心）
# 研报：华泰《交易拥挤与反转》、海通量价择时
# ============================================================

def calc_turnover_deviation(data: pd.DataFrame, window: int = 20) -> Dict:
    """
    异常换手率因子
    Turn_Dev = Turn_t / MA(Turn_20)
    避顶：Turn_Dev > 2.5 且股价处于高位 → 过热，不买

    参数:
        data: 包含 turnover（换手率%）、close 列的 DataFrame
    返回:
        dict {
          'turn_dev': float,         # 换手率偏离度
          'is_crowded': bool,        # 是否拥挤（Turn_Dev > 2.5）
          'risk_score': float,       # 风险分 0~1，越高越危险
        }
    """
    result = {'turn_dev': 1.0, 'is_crowded': False, 'risk_score': 0.0}

    # 兼容字段名：turnover / turn_over / turnoverrate
    col_candidates = ['turnover', 'turn_over', 'turnoverrate', 'turn']
    turn_col = None
    for c in col_candidates:
        if c in data.columns:
            turn_col = c
            break

    if turn_col is None or len(data) < window + 5:
        return result

    turn = data[turn_col].replace(0, np.nan)
    ma20 = turn.rolling(window).mean()
    turn_dev = (turn / ma20.replace(0, np.nan)).fillna(1.0)

    latest_dev = float(turn_dev.iloc[-1])
    result['turn_dev'] = latest_dev

    # 判断高位（收盘价处于近20日最高水平）
    close = data['close']
    is_high_price = float(close.iloc[-1]) >= float(close.rolling(20).max().iloc[-1]) * 0.92

    result['is_crowded'] = (latest_dev > 2.5) and is_high_price
    # 风险打分：超过2.5倍开始有风险，超过3.5倍满分
    risk = np.clip((latest_dev - 1.5) / 2.0, 0, 1)
    result['risk_score'] = float(risk) if is_high_price else float(risk) * 0.5
    return result


# ============================================================
# 因子2：20日量价相关系数（量价健康度）
# 依据：Price and Volume 行为金融经典
# ============================================================

def calc_volume_price_corr(data: pd.DataFrame, window: int = 20) -> Dict:
    """
    20日量价相关系数
    Corr20 = Corr(Return_t, VolChange_t),  window=20
    VolChange_t = ln(Vol_t / Vol_{t-1})
    避顶：Corr < 0 且股价高位 → 量价背离，见顶风险大
    """
    result = {'corr20': 0.0, 'is_diverging': False, 'risk_score': 0.0}

    if len(data) < window + 5:
        return result

    close  = data['close']
    volume = data['volume'].replace(0, np.nan)

    ret = close.pct_change(fill_method=None)
    vol_chg = np.log(volume / volume.shift(1))

    corr = ret.rolling(window).corr(vol_chg)
    latest_corr = float(corr.iloc[-1]) if not np.isnan(corr.iloc[-1]) else 0.0
    result['corr20'] = latest_corr

    is_high_price = float(close.iloc[-1]) >= float(close.rolling(20).max().iloc[-1]) * 0.90
    result['is_diverging'] = (latest_corr < 0) and is_high_price

    # 负相关越强，风险越高
    risk = np.clip(-latest_corr * 2, 0, 1) if is_high_price else 0.0
    result['risk_score'] = float(risk)
    return result


# ============================================================
# 因子3：残差动量衰减（相对强弱动量衰减）
# 研报：华泰《残差动量》、中信《去除共性后的动量》
# ============================================================

def calc_residual_momentum(data: pd.DataFrame,
                           market_data: Optional[pd.DataFrame] = None,
                           window: int = 10) -> Dict:
    """
    残差动量衰减
    先做 OLS 回归 r_t = α + β1*r_mkt + ε_t
    ResMOM10 = 近10日残差之和
    避顶：价格创新高但 ResMOM10 不创新高 → 虚强，即将见顶
    """
    result = {'res_mom10': 0.0, 'is_diverging': False, 'risk_score': 0.0}

    if len(data) < window + 20:
        return result

    close = data['close']
    ret   = close.pct_change(fill_method=None).dropna()

    # 若有大盘数据则做市值中性化，否则用自身MA做基准
    if market_data is not None and len(market_data) >= len(ret):
        mkt_ret = market_data['close'].pct_change(fill_method=None).dropna()
        # 对齐
        common_idx = ret.index.intersection(mkt_ret.index)
        if len(common_idx) < window + 5:
            residuals = ret
        else:
            r  = ret.loc[common_idx]
            mr = mkt_ret.loc[common_idx]
            # OLS: 仅用最近 60 日滚动回归
            betas   = r.rolling(60).cov(mr) / mr.rolling(60).var()
            alphas  = r.rolling(60).mean() - betas * mr.rolling(60).mean()
            residuals = r - (alphas + betas * mr)
    else:
        # 无大盘数据时：用自身超额（ret - MA_ret）作为残差代理
        residuals = ret - ret.rolling(20).mean()

    res_mom = residuals.rolling(window).sum()

    latest_price = float(close.iloc[-1])
    price_20max  = float(close.rolling(20).max().iloc[-1])
    is_price_new_high = latest_price >= price_20max * 0.98  # 接近创新高

    latest_res_mom = float(res_mom.iloc[-1]) if not np.isnan(res_mom.iloc[-1]) else 0.0
    res_mom_20max  = float(res_mom.rolling(20).max().iloc[-1]) if len(res_mom.dropna()) >= 5 else latest_res_mom
    is_res_not_high = latest_res_mom < res_mom_20max * 0.7  # 残差动量未创新高

    result['res_mom10']    = latest_res_mom
    result['is_diverging'] = is_price_new_high and is_res_not_high
    result['risk_score']   = 0.75 if result['is_diverging'] else 0.0
    return result


# ============================================================
# 因子4：近10日波动率跳升（高位震荡出货）
# 依据：波动率与预期收益负相关（高频行为金融）
# ============================================================

def calc_volatility_jump(data: pd.DataFrame,
                         vol_window: int = 10,
                         base_window: int = 60) -> Dict:
    """
    近10日波动率跳升
    Vol10 = std(Return_10d) * sqrt(252)
    VolDev = Vol10 / MA(Vol10, 60)
    避顶：VolDev > 2 且高位 → 剧烈震荡出货，不追
    """
    result = {'vol_dev': 1.0, 'is_jumping': False, 'risk_score': 0.0}

    if len(data) < base_window + 10:
        return result

    close = data['close']
    ret   = close.pct_change(fill_method=None)
    vol10 = ret.rolling(vol_window).std() * np.sqrt(252)
    vol_dev = vol10 / vol10.rolling(base_window).mean().replace(0, np.nan)

    latest_dev = float(vol_dev.iloc[-1]) if not np.isnan(vol_dev.iloc[-1]) else 1.0
    result['vol_dev'] = latest_dev

    is_high = float(close.iloc[-1]) >= float(close.rolling(20).max().iloc[-1]) * 0.90
    result['is_jumping'] = (latest_dev > 2.0) and is_high

    risk = np.clip((latest_dev - 1.0) / 1.5, 0, 1) * (1.0 if is_high else 0.4)
    result['risk_score'] = float(risk)
    return result


# ============================================================
# 因子5：缩量新高（最经典短线见顶）
# 全券商通用择时信号
# ============================================================

def calc_shrink_new_high(data: pd.DataFrame, window: int = 20) -> Dict:
    """
    缩量新高因子
    条件1: Close_t == Max(Close_20d)   ← 创新高
    条件2: Vol_t < 0.6 * MA(Vol_20d)  ← 缩量
    两条同时满足 → 极高概率短期顶
    """
    result = {'is_shrink_high': False, 'vol_ratio': 1.0, 'risk_score': 0.0}

    if len(data) < window + 5:
        return result

    close  = data['close']
    volume = data['volume']
    ma_vol = volume.rolling(window).mean()

    latest_close  = float(close.iloc[-1])
    max_close_20  = float(close.rolling(window).max().iloc[-1])
    latest_vol    = float(volume.iloc[-1])
    avg_vol       = float(ma_vol.iloc[-1]) if not np.isnan(ma_vol.iloc[-1]) else 1e-9

    vol_ratio = latest_vol / max(avg_vol, 1e-9)
    result['vol_ratio'] = vol_ratio

    is_new_high    = latest_close >= max_close_20 * 0.999
    is_shrink_vol  = vol_ratio < 0.6

    result['is_shrink_high'] = is_new_high and is_shrink_vol
    result['risk_score'] = 0.90 if result['is_shrink_high'] else (
        0.50 if is_new_high and vol_ratio < 0.8 else 0.0
    )
    return result


# ============================================================
# 因子6：超买强度（优化RSI）
# 依据：技术指标有效性学术检验 + 券商短线择时
# ============================================================

def calc_rsi_overbought(data: pd.DataFrame,
                        rsi_period: int = 14,
                        ob_threshold: float = 75.0,
                        strong_threshold: float = 82.0) -> Dict:
    """
    超买强度因子
    RSI14 超过75算超买，OB_3 = Count(RSI14>75, 3天)
    避顶：OB_3 >= 2 或 RSI14 > 82 → 短线见顶
    """
    result = {'rsi14': 50.0, 'ob3': 0, 'is_overbought': False, 'risk_score': 0.0}

    if len(data) < rsi_period + 10:
        return result

    close = data['close']
    delta = close.diff()
    gain  = delta.clip(lower=0)
    loss  = (-delta).clip(lower=0)

    avg_gain = gain.ewm(com=rsi_period - 1, min_periods=rsi_period).mean()
    avg_loss = loss.ewm(com=rsi_period - 1, min_periods=rsi_period).mean()

    rs  = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))

    latest_rsi = float(rsi.iloc[-1]) if not np.isnan(rsi.iloc[-1]) else 50.0
    ob3 = int((rsi.tail(3) > ob_threshold).sum())

    result['rsi14']       = latest_rsi
    result['ob3']         = ob3
    result['is_overbought'] = (ob3 >= 2) or (latest_rsi > strong_threshold)

    # 风险分：RSI超买越强风险越高
    risk = 0.0
    if latest_rsi > strong_threshold:
        risk = np.clip((latest_rsi - strong_threshold) / 10.0 + 0.7, 0, 1)
    elif ob3 >= 2:
        risk = 0.6
    elif ob3 >= 1:
        risk = 0.3
    result['risk_score'] = float(risk)
    return result


# ============================================================
# 因子7：成交额拥挤度（全市场占比）
# 依据：国君《微观结构拥挤度》、中信资金行为研报
# ============================================================

def calc_amount_crowding(data: pd.DataFrame,
                         total_market_amount: Optional[float] = None,
                         is_large_cap: bool = False) -> Dict:
    """
    成交额拥挤度
    AmtRatio = 个股成交额 / 全市场A股总成交额
    大盘股 > 1.2%，中小盘 > 0.7% → 资金拥挤，易短期见顶

    参数：
        data: K线数据，含 amount 列（成交额，元）
        total_market_amount: 全市场当日成交额（元），若为 None 则用历史均值估算
        is_large_cap: 是否为大盘股（市值 > 500亿）
    """
    result = {'amt_ratio': 0.0, 'is_crowded': False, 'risk_score': 0.0}

    # 兼容字段名
    col_candidates = ['amount', 'amt', 'money']
    amt_col = None
    for c in col_candidates:
        if c in data.columns:
            amt_col = c
            break

    if amt_col is None or len(data) < 5:
        return result

    latest_amt = float(data[amt_col].iloc[-1])

    # 若未提供全市场成交额，用固定参考值（A股日均成交约1万亿元 = 1e12）
    if total_market_amount is None or total_market_amount <= 0:
        total_market_amount = 1e12  # 保守估算1万亿

    amt_ratio = latest_amt / total_market_amount * 100  # 转换为百分比
    result['amt_ratio'] = amt_ratio

    threshold = 1.2 if is_large_cap else 0.7
    result['is_crowded'] = amt_ratio > threshold

    risk = np.clip((amt_ratio - threshold * 0.5) / (threshold * 1.5), 0, 1)
    result['risk_score'] = float(risk)
    return result


# ============================================================
# 因子8：融资买入占比（杠杆见顶）
# 依据：A股杠杆资金行为实证论文
# ============================================================

def calc_margin_buy_ratio(data: pd.DataFrame,
                          margin_buy_data: Optional[pd.Series] = None) -> Dict:
    """
    融资买入占比
    FinBuyRatio = 融资买入额 / 个股成交额
    > 10% → 杠杆过热；> 12% → 几乎必短期顶

    参数：
        data: K线数据，含 amount 列
        margin_buy_data: akshare 两融数据中的融资买入额（Series，index为日期）
    """
    result = {'fin_buy_ratio': 0.0, 'is_leveraged': False, 'risk_score': 0.0}

    if margin_buy_data is None or len(margin_buy_data) < 1:
        return result

    # 兼容字段名
    col_candidates = ['amount', 'amt', 'money']
    amt_col = None
    for c in col_candidates:
        if c in data.columns:
            amt_col = c
            break

    if amt_col is None or len(data) < 1:
        return result

    latest_amt = float(data[amt_col].iloc[-1])
    if latest_amt <= 0:
        return result

    # 对齐最新日期
    latest_margin = float(margin_buy_data.iloc[-1]) if len(margin_buy_data) > 0 else 0.0
    ratio = latest_margin / latest_amt * 100  # 百分比
    result['fin_buy_ratio'] = ratio

    result['is_leveraged'] = ratio > 10.0
    # 10%~12% 中等风险，12%以上高风险
    if ratio > 12.0:
        risk = np.clip(0.85 + (ratio - 12.0) / 10.0, 0, 1)
    elif ratio > 10.0:
        risk = 0.6 + (ratio - 10.0) / 10.0
    else:
        risk = np.clip(ratio / 15.0, 0, 0.4)
    result['risk_score'] = float(risk)
    return result


# ============================================================
# 因子9：上涨动能衰减（斜率拐头）
# 学术依据：趋势跟随与趋势反转论文
# ============================================================

def calc_momentum_decay(data: pd.DataFrame,
                        ma_window: int = 10,
                        slope_base: int = 5) -> Dict:
    """
    上涨动能衰减（斜率拐头）
    CloseMA10 = MA(Close, 10)
    Slope10 = linear slope of CloseMA10（最近10日）
    SlopeChg = Slope10 - MA(Slope10, 5)
    避顶：SlopeChg < 0 且高位 → 上涨乏力，快见顶
    """
    result = {'slope_chg': 0.0, 'slope_trend': 'up', 'is_decaying': False, 'risk_score': 0.0}

    if len(data) < ma_window + slope_base + 15:
        return result

    close = data['close']
    ma10  = close.rolling(ma_window).mean()

    # 滚动线性斜率（近10日的斜率）
    def rolling_slope(series: pd.Series, n: int = 10) -> pd.Series:
        slopes = pd.Series(np.nan, index=series.index)
        x = np.arange(n)
        for i in range(n - 1, len(series)):
            y = series.iloc[i - n + 1: i + 1].values
            if not np.any(np.isnan(y)):
                slope = np.polyfit(x, y, 1)[0]
                slopes.iloc[i] = slope
        return slopes

    # 为提高性能，只计算最近 slope_base + ma_window 天的斜率
    tail_len = slope_base + ma_window + 5
    ma10_tail = ma10.iloc[-min(tail_len * 2, len(ma10)):]
    slopes    = rolling_slope(ma10_tail, ma_window)

    slope_chg = slopes - slopes.rolling(slope_base).mean()
    latest_chg = float(slope_chg.iloc[-1]) if not np.isnan(slope_chg.iloc[-1]) else 0.0
    result['slope_chg'] = latest_chg

    is_high = float(close.iloc[-1]) >= float(close.rolling(20).max().iloc[-1]) * 0.88
    result['is_decaying'] = (latest_chg < 0) and is_high
    result['slope_trend'] = 'up' if latest_chg > 0 else 'down'

    # 风险：斜率越负且在高位，风险越高
    if is_high and latest_chg < 0:
        risk = np.clip(-latest_chg / (float(close.iloc[-1]) * 0.01 + 1e-9), 0, 1)
        risk = max(risk, 0.55)  # 至少0.55
    else:
        risk = 0.0
    result['risk_score'] = float(risk)
    return result


# ============================================================
# 因子10：近5日收益离散度（内部分歧加大）
# 依据：行为金融——分歧加大→一致性崩塌→见顶
# ============================================================

def calc_return_dispersion(data: pd.DataFrame,
                           short_window: int = 5,
                           base_window: int = 30) -> Dict:
    """
    近5日收益离散度
    Ret5Std = std(Return_5d)
    Ret5StdDev = Ret5Std / MA(Ret5Std, 30)
    避顶：Ret5StdDev > 2 且高位 → 分歧见顶
    """
    result = {'ret5_std_dev': 1.0, 'is_diverging': False, 'risk_score': 0.0}

    if len(data) < base_window + short_window + 5:
        return result

    close  = data['close']
    ret    = close.pct_change(fill_method=None)
    std5   = ret.rolling(short_window).std()
    std_dev = std5 / std5.rolling(base_window).mean().replace(0, np.nan)

    latest_dev = float(std_dev.iloc[-1]) if not np.isnan(std_dev.iloc[-1]) else 1.0
    result['ret5_std_dev'] = latest_dev

    is_high = float(close.iloc[-1]) >= float(close.rolling(20).max().iloc[-1]) * 0.88
    result['is_diverging'] = (latest_dev > 2.0) and is_high

    risk = np.clip((latest_dev - 1.0) / 1.5, 0, 1) * (1.0 if is_high else 0.3)
    result['risk_score'] = float(risk)
    return result


# ============================================================
# 综合防顶评分器
# ============================================================

class AntiTopFilter:
    """
    防短期见顶综合过滤器

    使用方式：
        atf = AntiTopFilter()
        result = atf.evaluate(stock_data)
        # result['anti_top_score']：0~1，越高代表见顶风险越大
        # result['signals']：触发的风险信号列表
        # result['should_filter']：是否应该过滤（触发2个以上避顶条件）
    """

    # 各因子权重（基于 IC 和研报置信度）
    FACTOR_WEIGHTS = {
        'shrink_new_high':     0.15,  # 最经典，权重最高
        'rsi_overbought':      0.13,
        'residual_momentum':   0.12,
        'turnover_deviation':  0.12,
        'vol_price_corr':      0.11,
        'momentum_decay':      0.11,
        'volatility_jump':     0.10,
        'return_dispersion':   0.09,
        'margin_buy_ratio':    0.08,  # 数据依赖外部，权重稍低
        'amount_crowding':     0.07,  # 依赖全市场数据
    }

    # 避顶触发阈值（风险分超过此值算触发）
    TRIGGER_THRESHOLD = 0.55

    def __init__(self):
        pass

    def evaluate(self,
                 data: pd.DataFrame,
                 market_data: Optional[pd.DataFrame] = None,
                 margin_buy_data: Optional[pd.Series] = None,
                 total_market_amount: Optional[float] = None,
                 is_large_cap: bool = False) -> Dict:
        """
        综合评估一只股票的见顶风险

        参数：
            data: 个股日K线 DataFrame，需含 close/high/low/volume 列
                  可选：turnover（换手率）、amount（成交额）
            market_data: 大盘日K线（用于残差动量，可选）
            margin_buy_data: 融资买入额序列（可选）
            total_market_amount: 全市场当日成交额（元，可选）
            is_large_cap: 是否大盘股（影响成交额阈值）

        返回：
            {
              'anti_top_score': float,    # 0~1 综合见顶风险分
              'signals': list[str],       # 触发的风险信号
              'triggered_count': int,     # 触发的避顶条件数量
              'should_filter': bool,      # 是否过滤（>= 2个条件触发）
              'details': dict,            # 各因子详情
            }
        """
        details  = {}
        signals  = []
        weighted_risk = 0.0

        # ── 因子1：异常换手率 ──
        f1 = calc_turnover_deviation(data)
        details['turnover_deviation'] = f1
        weighted_risk += f1['risk_score'] * self.FACTOR_WEIGHTS['turnover_deviation']
        if f1['is_crowded']:
            signals.append(f"换手率拥挤(Turn_Dev={f1['turn_dev']:.2f}x)")

        # ── 因子2：量价相关系数 ──
        f2 = calc_volume_price_corr(data)
        details['vol_price_corr'] = f2
        weighted_risk += f2['risk_score'] * self.FACTOR_WEIGHTS['vol_price_corr']
        if f2['is_diverging']:
            signals.append(f"量价背离(Corr={f2['corr20']:.3f})")

        # ── 因子3：残差动量衰减 ──
        f3 = calc_residual_momentum(data, market_data)
        details['residual_momentum'] = f3
        weighted_risk += f3['risk_score'] * self.FACTOR_WEIGHTS['residual_momentum']
        if f3['is_diverging']:
            signals.append(f"残差动量衰减(ResMOM={f3['res_mom10']:.4f})")

        # ── 因子4：波动率跳升 ──
        f4 = calc_volatility_jump(data)
        details['volatility_jump'] = f4
        weighted_risk += f4['risk_score'] * self.FACTOR_WEIGHTS['volatility_jump']
        if f4['is_jumping']:
            signals.append(f"波动率跳升(VolDev={f4['vol_dev']:.2f}x)")

        # ── 因子5：缩量新高 ──
        f5 = calc_shrink_new_high(data)
        details['shrink_new_high'] = f5
        weighted_risk += f5['risk_score'] * self.FACTOR_WEIGHTS['shrink_new_high']
        if f5['is_shrink_high']:
            signals.append(f"缩量新高(Vol_Ratio={f5['vol_ratio']:.2f})")

        # ── 因子6：RSI超买 ──
        f6 = calc_rsi_overbought(data)
        details['rsi_overbought'] = f6
        weighted_risk += f6['risk_score'] * self.FACTOR_WEIGHTS['rsi_overbought']
        if f6['is_overbought']:
            signals.append(f"RSI超买(RSI14={f6['rsi14']:.1f}, OB3={f6['ob3']})")

        # ── 因子7：成交额拥挤度 ──
        f7 = calc_amount_crowding(data, total_market_amount, is_large_cap)
        details['amount_crowding'] = f7
        weighted_risk += f7['risk_score'] * self.FACTOR_WEIGHTS['amount_crowding']
        if f7['is_crowded']:
            signals.append(f"成交额拥挤(AmtRatio={f7['amt_ratio']:.3f}%)")

        # ── 因子8：融资买入占比 ──
        f8 = calc_margin_buy_ratio(data, margin_buy_data)
        details['margin_buy_ratio'] = f8
        weighted_risk += f8['risk_score'] * self.FACTOR_WEIGHTS['margin_buy_ratio']
        if f8['is_leveraged']:
            signals.append(f"融资过热(FinBuyRatio={f8['fin_buy_ratio']:.1f}%)")

        # ── 因子9：动能衰减 ──
        f9 = calc_momentum_decay(data)
        details['momentum_decay'] = f9
        weighted_risk += f9['risk_score'] * self.FACTOR_WEIGHTS['momentum_decay']
        if f9['is_decaying']:
            signals.append(f"动能衰减(SlopeChg={f9['slope_chg']:.4f})")

        # ── 因子10：收益离散度 ──
        f10 = calc_return_dispersion(data)
        details['return_dispersion'] = f10
        weighted_risk += f10['risk_score'] * self.FACTOR_WEIGHTS['return_dispersion']
        if f10['is_diverging']:
            signals.append(f"分歧见顶(Ret5StdDev={f10['ret5_std_dev']:.2f}x)")

        anti_top_score = float(np.clip(weighted_risk, 0, 1))
        triggered_count = len(signals)

        # 核心规则：触发 >= 2 个条件 → 过滤不买
        should_filter = triggered_count >= 2

        return {
            'anti_top_score':  anti_top_score,
            'signals':         signals,
            'triggered_count': triggered_count,
            'should_filter':   should_filter,
            'details':         details,
        }

    def get_score_penalty(self, anti_top_result: Dict) -> float:
        """
        根据防顶评估结果返回评分惩罚系数（乘以此值降低综合评分）
        
        返回:
          0.95 ~ 1.0  正常（几乎无风险）
          0.80 ~ 0.95 轻度警告
          0.60 ~ 0.80 中度风险
          0.40 ~ 0.60 高度风险
          0.25 ~ 0.40 极度见顶风险
        """
        score = anti_top_result['anti_top_score']
        triggered = anti_top_result['triggered_count']

        if triggered == 0:
            return 1.0
        elif triggered == 1:
            return max(0.92, 1.0 - score * 0.15)
        elif triggered == 2:
            return max(0.75, 1.0 - score * 0.35)
        elif triggered == 3:
            return max(0.55, 1.0 - score * 0.55)
        else:
            return max(0.30, 1.0 - score * 0.75)


# ============================================================
# 便捷函数：快速计算所有10个因子的最终分数
# ============================================================

def calculate_anti_top_score(data: pd.DataFrame,
                              market_data: Optional[pd.DataFrame] = None,
                              margin_buy_data: Optional[pd.Series] = None,
                              total_market_amount: Optional[float] = None) -> Tuple[float, bool, list]:
    """
    快速接口：一行代码获取防顶评分

    返回:
      (anti_top_score, should_filter, signals)
      - anti_top_score: 0~1，越高越危险
      - should_filter:  True 表示当前不宜买入（有见顶风险）
      - signals:        触发的风险信号列表
    """
    atf = AntiTopFilter()
    result = atf.evaluate(data, market_data, margin_buy_data, total_market_amount)
    return result['anti_top_score'], result['should_filter'], result['signals']
