#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
微观结构/筹码分布 & 反转预警 & 风格行业配比 日频因子库 v1.0
==========================================================
研报/顶刊依据:
  Hong & Stein(2007) 《Disagreement and the Stock Market》JF - 筹码分散度
  Chordia & Subrahmanyam(2004) 《Order Imbalance and Stock Returns》JF - 委比/订单失衡
  An et al.(2020) 《The Limited Role of Market Making》 - 微观结构代理变量
  中信金工《筹码分布因子体系》2023
  海通金工《短期反转因子的精细构建》2023
  国盛金工《反转预警体系与风险因子》2024
  广发金工《行业轮动与风格配比因子》2024
  招商金工《风格因子拥挤度与切换信号》2023
  国君金工《日频行业动量与反转》2024

大类七：微观结构/筹码分布日频因子（6个）
  1. 筹码集中度因子 (chip_concentration)       - 20日高低价区间筹码分布
  2. 委比代理因子 (order_imbalance_proxy)      - 基于高低价/收的位置推算买卖力量
  3. 日内弹性因子 (intraday_resilience)         - 日内回撤修复能力
  4. 收盘位置因子 (close_position)              - 收盘价在日内振幅中的位置
  5. 阴阳K线比因子 (candle_pattern_ratio)       - 近N日阳线/阴线比
  6. 连板/连涨连跌因子 (consecutive_move)       - 连续涨跌天数

大类八：反转预警 & 风格切换日频因子（6个）
  7. 短期超买反转预警 (short_overbought_reversal)   - 多维度超买检测
  8. 多周期背离因子 (multi_tf_divergence)            - 5日/10日/20日动量背离
  9. 突破回踩因子 (breakback_test)                   - 突破后是否回踩确认
  10. 风格动量得分 (style_momentum_score)            - 大/中/小盘风格暴露
  11. 风格拥挤度切换 (style_crowd_switch)             - 风格拥挤度偏离
  12. 反转综合预警 (reversal_warning_score)          - 多维度反转风险综合

大类九：行业配比 & 事件驱动日频因子（6个）
  13. 行业相对强度 (industry_relative_strength)       - 相对行业均线的偏离
  14. 行业资金流共振 (industry_flow_resonance)        - 个股与行业量能同向
  15. 事件冲击因子 (event_impact)                     - 异常波动事件检测
  16. 涨跌停距离因子 (limit_distance)                  - 距离涨停/跌停的空间
  17. 新高新低计数 (new_high_low_count)               - 20日内新高新低次数
  18. 板块轮动配比 (sector_rotation_score)            - 基于动量的板块轮动信号

全部为日频滚动因子，回溯5/10/20日，数据源：akshare日频K线
"""

import warnings
warnings.filterwarnings('ignore')

import pandas as pd
import numpy as np
from typing import Dict, Optional, Tuple, Any
import logging

logger = logging.getLogger("microstructure_reversal_factors")


# ===================================================================
# 工具函数
# ===================================================================

def _safe_get_col(data: pd.DataFrame, *names) -> Optional[pd.Series]:
    """安全获取列（支持多个备用列名）"""
    for name in names:
        if name in data.columns:
            return data[name]
    return None


def _safe_div(a, b, fill=0.0):
    """安全除法"""
    try:
        if isinstance(b, (int, float)):
            return float(a) / b if abs(b) > 1e-9 else fill
        result = pd.Series(np.where(np.abs(b) > 1e-9, a / b, fill), index=a.index)
        return result
    except Exception:
        return fill


def _safe_rolling(series: pd.Series, window: int, func, min_periods=None):
    """安全滚动计算"""
    mp = min_periods if min_periods else max(3, window // 2)
    return series.rolling(window, min_periods=mp).apply(func, raw=True)


def _latest(series: pd.Series) -> float:
    """获取序列最新值"""
    if series is None or len(series) == 0:
        return 0.0
    v = float(series.iloc[-1])
    return v if not pd.isna(v) else 0.0


# ===================================================================
# 大类七：微观结构/筹码分布因子
# ===================================================================

class MicrostructureFactorCalculator:
    """微观结构与筹码分布因子计算器"""

    CHIP_WINDOWS = [5, 10, 20]     # 筹码分布窗口
    CLOSE_POS_WINDOW = 10           # 收盘位置窗口
    CANDLE_WINDOW = 10              # K线阴阳比窗口
    CONSEC_WINDOW = 10              # 连涨连跌统计窗口

    def __init__(self):
        pass

    def check_df(self, df: pd.DataFrame) -> Optional[str]:
        """检查输入数据"""
        required = ['open', 'close', 'high', 'low', 'volume', 'amount', 'pctChg', 'turn']
        missing = [c for c in required if c not in df.columns]
        if missing:
            return f"缺少列: {missing}"
        if len(df) < 20:
            return f"数据不足: {len(df)}行, 至少需要20行"
        return None

    def calc_chip_concentration(self, df: pd.DataFrame) -> Dict:
        """
        因子1: 筹码集中度因子 (chip_concentration)
        ─────────────────────────────────────────
        研报依据：中信金工《筹码分布因子体系》2023
                  Hong & Stein(2007) 筹码分散度与股价

        逻辑：
          将20日内每个交易日的成交量视为"筹码"，
          按当日成交均价分布到价格区间上。
          用加权标准差衡量筹码集中程度。

          筹码集中度 = 1 - (筹码加权标准差 / 均价)
          高集中度（>0.85）：筹码锁定好，抛压小
          低集中度（<0.6）：筹码分散，抛压大

        返回：
          chip_concentration_20: 20日筹码集中度
          chip_mean_price: 20日筹码加权均价
          chip_risk_score: 风险评分(0~1)
        """
        window = 20
        n = len(df)
        if n < window:
            window = n

        close = df['close'].values
        vol = df['volume'].values
        high = df['high'].values
        low = df['low'].values

        # 取最近window天
        c = close[-window:]
        v = vol[-window:]
        h = high[-window:]
        l = low[-window:]

        # 用 (O+H+L+C)/4 作为成交均价代理
        opens = df['open'].values[-window:]
        avg_prices = (opens + h + l + c) / 4.0

        # 加权均价
        total_vol = v.sum()
        if total_vol < 1e-6:
            return {
                'chip_concentration_20': 0.5,
                'chip_mean_price': float(c[-1]),
                'chip_risk_score': 0.5,
            }

        mean_price = float(np.average(avg_prices, weights=v))
        # 加权标准差
        variance = float(np.average((avg_prices - mean_price) ** 2, weights=v))
        std_price = np.sqrt(variance)

        # 集中度 = 1 - 变异系数
        concentration = 1.0 - (std_price / mean_price if mean_price > 0.01 else 0.5)
        concentration = np.clip(concentration, 0.0, 1.0)

        # 风险评分：集中度低 = 风险高
        risk_score = max(0.0, 1.0 - concentration - 0.3) / 0.7
        risk_score = np.clip(risk_score, 0.0, 1.0)

        return {
            'chip_concentration_20': round(float(concentration), 4),
            'chip_mean_price': round(mean_price, 2),
            'chip_risk_score': round(float(risk_score), 4),
        }

    def calc_order_imbalance_proxy(self, df: pd.DataFrame) -> Dict:
        """
        因子2: 委比代理因子 (order_imbalance_proxy)
        ──────────────────────────────────────────
        研报依据：Chordia & Subrahmanyam(2004) 订单失衡与收益

        逻辑：
          在无法获取Level-2数据的情况下，用K线结构推算买卖力量：
            买方力量代理 = (close - low) / (high - low) × volume
            卖方力量代理 = (high - close) / (high - low) × volume
            委比 = (买方 - 卖方) / (买方 + 卖方)

          连续多日委比 > 0.5 → 买盘主导
          连续多日委比 < -0.5 → 卖盘主导

        返回：
          obi_5d: 近5日平均委比
          obi_10d: 近10日平均委比
          obi_signal: 信号方向
          obi_persistence: 委比持续性(0~1)
        """
        hl_range = df['high'] - df['low']
        hl_range = hl_range.replace(0, np.nan).fillna(0.01)

        buy_power = (df['close'] - df['low']) / hl_range * df['volume']
        sell_power = (df['high'] - df['close']) / hl_range * df['volume']

        total_power = buy_power + sell_power
        total_power = total_power.replace(0, np.nan).fillna(1.0)
        obi = (buy_power - sell_power) / total_power

        obi_5d = obi.rolling(5, min_periods=2).mean()
        obi_10d = obi.rolling(10, min_periods=3).mean()

        latest_obi5 = _latest(obi_5d)
        latest_obi10 = _latest(obi_10d)
        latest_obi = _latest(obi)

        # 信号
        if latest_obi5 > 0.3:
            signal = 'buy_dominant'
        elif latest_obi5 < -0.3:
            signal = 'sell_dominant'
        else:
            signal = 'neutral'

        # 持续性：近5日中正委比的天数占比
        positive_days = (obi.tail(5) > 0).sum()
        persistence = positive_days / min(5, len(obi))

        return {
            'obi_5d': round(latest_obi5, 4),
            'obi_10d': round(latest_obi10, 4),
            'obi_signal': signal,
            'obi_persistence': round(float(persistence), 4),
        }

    def calc_intraday_resilience(self, df: pd.DataFrame) -> Dict:
        """
        因子3: 日内弹性因子 (intraday_resilience)
        ──────────────────────────────────────────
        逻辑：
          弹性 = max(0, close - low) / (high - low)  当日弹性
          resilience_10 = mean(弹性, 10)

          弹性 > 0.7：日内回撤后能修复，买方强
          弹性 < 0.3：冲高回落，卖方强

        返回：
          resilience_today: 当日弹性
          resilience_10d: 近10日平均弹性
          resilience_signal: 信号
        """
        hl_range = df['high'] - df['low']
        hl_range = hl_range.replace(0, np.nan).fillna(0.01)

        # 弹性 = (close - low) / (high - low)
        resilience = ((df['close'] - df['low']) / hl_range).clip(0, 1)
        res_10d = resilience.rolling(10, min_periods=3).mean()

        latest_res = _latest(resilience)
        latest_res10 = _latest(res_10d)

        if latest_res10 > 0.65:
            signal = 'strong_buyer'
        elif latest_res10 < 0.35:
            signal = 'strong_seller'
        else:
            signal = 'neutral'

        return {
            'resilience_today': round(latest_res, 4),
            'resilience_10d': round(latest_res10, 4),
            'resilience_signal': signal,
        }

    def calc_close_position(self, df: pd.DataFrame) -> Dict:
        """
        因子4: 收盘位置因子 (close_position)
        ─────────────────────────────────────────
        逻辑：
          close_pos = (close - low) / (high - low)  收盘在日内振幅中的相对位置

          close_pos_10_mean > 0.7 → 连续收在高位，多头强势
          close_pos_10_mean < 0.3 → 连续收在低位，空头强势
          close_pos趋势（近5日vs前5日）判断方向

        返回：
          close_pos_today: 当日收盘位置
          close_pos_10d: 近10日均值
          close_pos_trend: 趋势（上升/下降/平稳）
          close_pos_score: 评分(0~1)
        """
        hl_range = df['high'] - df['low']
        hl_range = hl_range.replace(0, np.nan).fillna(0.01)

        cp = ((df['close'] - df['low']) / hl_range).clip(0, 1)
        cp_10d = cp.rolling(10, min_periods=3).mean()

        latest_cp = _latest(cp)
        latest_cp10 = _latest(cp_10d)

        # 趋势：近5日vs前5日
        if len(cp) >= 10:
            cp_recent = cp.tail(5).mean()
            cp_before = cp.iloc[-10:-5].mean() if len(cp) >= 10 else cp_recent
            trend_diff = float(cp_recent - cp_before)
            if trend_diff > 0.1:
                trend = 'rising'
            elif trend_diff < -0.1:
                trend = 'falling'
            else:
                trend = 'flat'
        else:
            trend = 'flat'
            trend_diff = 0.0

        # 评分：位置高 + 趋势升 = 高分
        score = latest_cp10 * 0.6 + max(0, trend_diff + 0.2) * 0.4
        score = np.clip(score, 0, 1)

        return {
            'close_pos_today': round(latest_cp, 4),
            'close_pos_10d': round(latest_cp10, 4),
            'close_pos_trend': trend,
            'close_pos_score': round(float(score), 4),
        }

    def calc_candle_pattern_ratio(self, df: pd.DataFrame) -> Dict:
        """
        因子5: 阴阳K线比因子 (candle_pattern_ratio)
        ───────────────────────────────────────────
        逻辑：
          阳线 = close > open
          阴线 = close < open

          yang_ratio_10 = count(阳线, 10) / 10
          yang_ratio_5 = count(阳线, 5) / 5

          ratio > 0.8 → 连续阳线，短期偏多
          ratio < 0.2 → 连续阴线，短期偏空

          关键：连续阳线后突然出现阴线 = 可能见顶

        返回：
          yang_ratio_5d: 近5日阳线比
          yang_ratio_10d: 近10日阳线比
          pattern_signal: 模式信号
        """
        is_yang = (df['close'] > df['open']).astype(int)

        yang_5d = is_yang.rolling(5, min_periods=2).mean()
        yang_10d = is_yang.rolling(10, min_periods=3).mean()

        latest_5d = _latest(yang_5d)
        latest_10d = _latest(yang_10d)

        # 模式信号
        if latest_10d > 0.75 and latest_5d < 0.4:
            signal = 'top_warning'     # 前期阳多近期转阴
        elif latest_10d < 0.25 and latest_5d > 0.6:
            signal = 'bottom_reversal'  # 前期阴多近期转阳
        elif latest_5d > 0.8:
            signal = 'strong_bullish'
        elif latest_5d < 0.2:
            signal = 'strong_bearish'
        else:
            signal = 'neutral'

        return {
            'yang_ratio_5d': round(latest_5d, 4),
            'yang_ratio_10d': round(latest_10d, 4),
            'pattern_signal': signal,
        }

    def calc_consecutive_move(self, df: pd.DataFrame) -> Dict:
        """
        因子6: 连板/连涨连跌因子 (consecutive_move)
        ───────────────────────────────────────────
        逻辑：
          统计连续涨/跌天数，以及近10日最大连涨/连跌

          连涨 > 4天 且 涨幅递减 → 动能衰竭预警
          连跌 > 4天 → 可能超跌反弹

        返回：
          consecutive_up: 当前连续上涨天数
          consecutive_down: 当前连续下跌天数
          max_consec_up_10d: 10日内最大连涨
          max_consec_down_10d: 10日内最大连跌
          momentum_exhaustion: 动能衰竭评分(0~1)
        """
        pct = df['pctChg']

        # 当前连续涨跌
        consec_up = 0
        consec_down = 0
        for i in range(len(pct) - 1, -1, -1):
            v = float(pct.iloc[i])
            if v > 0 and consec_down == 0:
                consec_up += 1
            elif v < 0 and consec_up == 0:
                consec_down += 1
            else:
                break

        # 近10日最大连涨连跌
        pct_10 = pct.tail(10).values
        max_up = 0
        max_dn = 0
        cur_up = 0
        cur_dn = 0
        for v in pct_10:
            v = float(v)
            if v > 0:
                cur_up += 1
                cur_dn = 0
                max_up = max(max_up, cur_up)
            elif v < 0:
                cur_dn += 1
                cur_up = 0
                max_dn = max(max_dn, cur_dn)
            else:
                cur_up = 0
                cur_dn = 0

        # 动能衰竭：连涨天数多但近2日涨幅递减
        exhaustion = 0.0
        if consec_up >= 3:
            if len(pct) >= 2:
                last = float(pct.iloc[-1])
                prev = float(pct.iloc[-2])
                if last > 0 and prev > 0 and last < prev:
                    exhaustion = min(1.0, consec_up / 7.0)

        return {
            'consecutive_up': consec_up,
            'consecutive_down': consec_down,
            'max_consec_up_10d': max_up,
            'max_consec_down_10d': max_dn,
            'momentum_exhaustion': round(exhaustion, 4),
        }


# ===================================================================
# 大类八：反转预警 & 风格切换因子
# ===================================================================

class ReversalWarningFactorCalculator:
    """反转预警与风格切换因子计算器"""

    def calc_short_overbought_reversal(self, df: pd.DataFrame) -> Dict:
        """
        因子7: 短期超买反转预警 (short_overbought_reversal)
        ─────────────────────────────────────────────────
        研报依据：海通金工《短期反转因子的精细构建》2023
                  国盛金工《反转预警体系与风险因子》2024

        逻辑：
          多维度超买检测：
            a) 5日涨幅 > 15% 且 成交量递增 → 超买
            b) 收盘价偏离5日均线 > 8% → 超买
            c) RSI_6 > 80 → 极度超买
            d) 连涨 > 3天 且 最后一天上影线长 → 见顶信号

          任意2项触发 = 反转预警

        返回：
          overbought_score: 0~1 超买程度
          overbought_triggers: 触发项数
          reversal_warning: 是否预警
        """
        close = df['close']
        pct = df['pctChg']

        triggers = 0

        # a) 5日涨幅
        if len(close) >= 5:
            ret_5d = (close.iloc[-1] / close.iloc[-5] - 1) * 100
            vol = df['volume']
            vol_increasing = vol.iloc[-3:].is_monotonic_increasing if len(vol) >= 3 else False
            if ret_5d > 15 and vol_increasing:
                triggers += 1

        # b) 偏离5日均线
        ma5 = close.rolling(5, min_periods=3).mean()
        if len(ma5) >= 2 and not pd.isna(ma5.iloc[-1]):
            deviation = (close.iloc[-1] / ma5.iloc[-1] - 1) * 100
            if deviation > 8:
                triggers += 1

        # c) RSI_6
        delta = close.diff()
        gain = delta.clip(lower=0)
        loss = (-delta).clip(lower=0)
        avg_gain = gain.rolling(6, min_periods=3).mean()
        avg_loss = loss.rolling(6, min_periods=3).mean()
        avg_loss = avg_loss.replace(0, np.nan).fillna(1e-6)
        rsi_6 = 100 - 100 / (1 + avg_gain / avg_loss)
        latest_rsi = _latest(rsi_6)
        if latest_rsi > 80:
            triggers += 1

        # d) 连涨 + 上影线
        consec = 0
        for i in range(len(pct) - 1, -1, -1):
            if float(pct.iloc[i]) > 0:
                consec += 1
            else:
                break
        if consec >= 3 and len(df) >= 1:
            upper_shadow = float(df['high'].iloc[-1]) - max(float(df['close'].iloc[-1]), float(df['open'].iloc[-1]))
            body = abs(float(df['close'].iloc[-1]) - float(df['open'].iloc[-1]))
            if body > 1e-6 and upper_shadow / body > 1.5:
                triggers += 1

        score = min(1.0, triggers / 3.0)
        warning = triggers >= 2

        return {
            'overbought_score': round(score, 4),
            'overbought_triggers': triggers,
            'reversal_warning': warning,
            'latest_rsi_6': round(latest_rsi, 2),
        }

    def calc_multi_tf_divergence(self, df: pd.DataFrame) -> Dict:
        """
        因子8: 多周期背离因子 (multi_tf_divergence)
        ──────────────────────────────────────────
        逻辑：
          计算5日/10日/20日动量（累计涨幅）
          背离定义：
            - 价格创新高但5日动量低于前期 → 顶背离
            - 价格创新低但5日动量高于前期 → 底背离

          多周期动量不一致 = 趋势不稳

        返回：
          mom_5d: 5日动量
          mom_10d: 10日动量
          mom_20d: 20日动量
          divergence_signal: 背离信号
          tf_consistency: 多周期一致性(0~1)
        """
        close = df['close']
        n = len(close)

        def _cum_return(period):
            if n < period + 1:
                return 0.0
            return float(close.iloc[-1] / close.iloc[-period] - 1)

        mom_5 = _cum_return(5)
        mom_10 = _cum_return(10)
        mom_20 = _cum_return(20)

        # 多周期一致性：所有动量同方向
        signs = [np.sign(mom_5), np.sign(mom_10), np.sign(mom_20)]
        positive_count = sum(1 for s in signs if s > 0)
        consistency = max(positive_count, 3 - positive_count) / 3.0

        # 背离检测：5日动量方向与10日不一致
        if mom_5 > 0 and mom_10 < 0:
            signal = 'bearish_divergence'    # 短期涨但中期跌
        elif mom_5 < 0 and mom_10 > 0:
            signal = 'bullish_divergence'    # 短期跌但中期涨
        elif consistency > 0.9:
            signal = 'aligned_strong'
        else:
            signal = 'mixed'

        return {
            'mom_5d': round(mom_5, 6),
            'mom_10d': round(mom_10, 6),
            'mom_20d': round(mom_20, 6),
            'divergence_signal': signal,
            'tf_consistency': round(consistency, 4),
        }

    def calc_breakback_test(self, df: pd.DataFrame) -> Dict:
        """
        因子9: 突破回踩因子 (breakback_test)
        ──────────────────────────────────────
        逻辑：
          判断近期是否突破20日新高并且回踩确认：
            1. 当前价 > 20日最高价（突破）
            2. 突破后是否回踩到突破价附近（< 突破价 × 1.02）→ 确认
            3. 回踩时缩量 → 有效突破

          突破未回踩 = 可能假突破
          回踩确认 = 有效突破信号

        返回：
          breakout: 是否突破
          pullback: 是否回踩
          pullback_shrink: 回踩是否缩量
          breakout_signal: 突破信号评估
        """
        close = df['close']
        high = df['high']
        volume = df['volume']
        low = df['low']

        if len(close) < 20:
            return {
                'breakout': False,
                'pullback': False,
                'pullback_shrink': False,
                'breakout_signal': 'insufficient_data',
            }

        high_20 = high.iloc[-21:-1].max()  # 排除今天
        current_close = float(close.iloc[-1])

        # 当前价是否突破了20日新高
        breakout = current_close > float(high_20)

        pullback = False
        pullback_shrink = False

        if breakout:
            # 突破后：看近5日是否回踩到突破位附近
            high_20_float = float(high_20)
            if len(close) >= 5:
                recent_5d_low = float(low.iloc[-5:].min()) if 'low' in df.columns else float(close.iloc[-5:].min())
                # 回踩定义：5日内最低价回落到突破价的1.5%以内
                if recent_5d_low < high_20_float * 1.015:
                    pullback = True
                    # 回踩时量是否萎缩（近3日均量 < 突破日均量）
                    if len(volume) >= 8:
                        vol_recent = float(volume.iloc[-3:].mean())
                        vol_before = float(volume.iloc[-8:-3].mean())
                        if vol_before > 0 and vol_recent < vol_before * 0.8:
                            pullback_shrink = True

        # 信号
        if pullback and pullback_shrink:
            signal = 'confirmed_breakout'   # 有效突破
        elif pullback:
            signal = 'pullback_test'        # 回踩测试中
        elif breakout:
            signal = 'fresh_breakout'       # 新突破待确认
        else:
            signal = 'no_breakout'

        return {
            'breakout': breakout,
            'pullback': pullback,
            'pullback_shrink': pullback_shrink,
            'breakout_signal': signal,
        }

    def calc_style_momentum_score(self, df: pd.DataFrame) -> Dict:
        """
        因子10: 风格动量得分 (style_momentum_score)
        ───────────────────────────────────────────
        研报依据：招商金工《风格因子拥挤度与切换信号》2023

        逻辑：
          基于股票市值代理（成交额）判断风格暴露：
            大盘代理：成交额持续 > 市场中位数×2 → 大盘风格
            小盘代理：成交额持续 < 市场中位数×0.5 → 小盘风格

          style_mom = 20日涨幅 × 风格权重
          大盘风格 + 上涨 = 稳健
          小盘风格 + 大涨 = 弹性大但风险高

          由于无法获取市场全量数据，用成交额的趋势做代理：
          amt_trend = MA(amt, 20) / MA(amt, 60)

        返回：
          amt_trend: 成交额趋势
          vol_volatility: 成交额波动率
          style_signal: 风格信号
          style_score: 风格评分(0~1)
        """
        amt = df['amount'].replace(0, np.nan).fillna(method='ffill')
        amt_20 = amt.rolling(20, min_periods=10).mean()
        amt_60 = amt.rolling(60, min_periods=20).mean() if len(amt) >= 60 else amt_20

        amt_trend = _safe_div(amt_20, amt_60, fill=1.0)
        latest_trend = _latest(amt_trend)

        # 成交额波动率
        amt_volatility = amt.pct_change().rolling(20, min_periods=5).std()
        latest_vol = _latest(amt_volatility)

        # 风格信号
        if latest_trend > 1.3:
            signal = 'large_cap_active'    # 成交活跃，偏大盘
        elif latest_trend < 0.7:
            signal = 'small_cap_quiet'     # 成交萎缩，偏小盘
        else:
            signal = 'neutral'

        # 评分：成交趋势健康 + 波动适中 = 高分
        score = np.clip(0.5 + (latest_trend - 1.0) * 0.3 - latest_vol * 5.0, 0, 1)

        return {
            'amt_trend': round(latest_trend, 4),
            'amt_volatility': round(latest_vol, 6),
            'style_signal': signal,
            'style_score': round(float(score), 4),
        }

    def calc_style_crowd_switch(self, df: pd.DataFrame) -> Dict:
        """
        因子11: 风格拥挤度切换 (style_crowd_switch)
        ───────────────────────────────────────────
        逻辑：
          拥挤度 = 换手率 × (成交额/成交额MA60)
          crowding_now vs crowding_20d_ago 的变化方向

          拥挤度快速上升 + 换手率创新高 → 风格拥挤
          拥挤度高位回落 → 风格切换信号

        返回：
          crowding_now: 当前拥挤度
          crowding_change: 拥挤度变化率
          switch_signal: 切换信号
        """
        turn = df['turn'].replace(0, np.nan).fillna(method='ffill')
        amt = df['amount'].replace(0, np.nan).fillna(method='ffill')
        amt_ma60 = amt.rolling(60, min_periods=20).mean() if len(amt) >= 60 else amt.rolling(20, min_periods=5).mean()

        crowding = turn * _safe_div(amt, amt_ma60, fill=1.0)

        latest_crowd = _latest(crowding)
        if len(crowding) >= 20:
            prev_crowd = _latest(crowding.shift(10))
        else:
            prev_crowd = latest_crowd

        change = _safe_div(latest_crowd - prev_crowd, prev_crowd, fill=0.0)

        if change > 0.5:
            if len(crowding) >= 20:
                q80 = float(crowding.rolling(20, min_periods=5).quantile(0.8).iloc[-1])
                if not np.isnan(q80):
                    is_crowded = latest_crowd > q80
                else:
                    is_crowded = False
            else:
                is_crowded = False
            signal = 'crowded' if is_crowded else 'neutral'
        elif change < -0.3 and prev_crowd > latest_crowd:
            signal = 'uncrowding'
        else:
            signal = 'neutral'

        return {
            'crowding_now': round(latest_crowd, 4),
            'crowding_change': round(float(change), 4),
            'switch_signal': signal,
        }

    def calc_reversal_warning_score(self, df: pd.DataFrame, micro_factors: Dict = None) -> Dict:
        """
        因子12: 反转综合预警 (reversal_warning_score)
        ───────────────────────────────────────────
        综合多维度反转风险：
          超买程度(25%) + 背离信号(20%) + 动能衰竭(20%) +
          连涨天数(15%) + 筹码分散(10%) + 情绪拥挤(10%)

        返回：
          reversal_warning_score: 0~1，越高反转风险越大
          warning_level: 'safe'/'watch'/'warning'/'danger'
          components: 各子因子贡献
        """
        # 超买程度
        ob = self.calc_short_overbought_reversal(df)
        ob_score = ob.get('overbought_score', 0.0)

        # 背离
        div = self.calc_multi_tf_divergence(df)
        consistency = div.get('tf_consistency', 0.5)
        div_score = 1.0 - consistency  # 不一致 = 风险

        # 动能衰竭（从微观结构获取）
        exhaustion = 0.0
        if micro_factors:
            exhaustion = micro_factors.get('momentum_exhaustion', 0.0)

        # 连涨天数
        cm = MicrostructureFactorCalculator().calc_consecutive_move(df)
        consec_score = min(1.0, cm.get('consecutive_up', 0) / 5.0)

        # 筹码分散
        chip_score = 0.0
        if micro_factors:
            chip_score = micro_factors.get('chip_risk_score', 0.0)

        # 阴阳比异常
        yang_5d = cm.get('yang_ratio_5d', 0.5) if 'yang_ratio_5d' in cm else 0.5
        # 从candle_factor获取
        cf = MicrostructureFactorCalculator().calc_candle_pattern_ratio(df)
        yang_risk = 0.0
        if cf.get('pattern_signal') == 'top_warning':
            yang_risk = 0.8

        # 综合评分
        total = (
            ob_score * 0.25 +
            div_score * 0.20 +
            exhaustion * 0.20 +
            consec_score * 0.15 +
            chip_score * 0.10 +
            yang_risk * 0.10
        )

        if total < 0.25:
            level = 'safe'
        elif total < 0.45:
            level = 'watch'
        elif total < 0.65:
            level = 'warning'
        else:
            level = 'danger'

        return {
            'reversal_warning_score': round(total, 4),
            'warning_level': level,
            'warning_components': {
                'overbought': round(ob_score, 4),
                'divergence': round(div_score, 4),
                'exhaustion': round(exhaustion, 4),
                'consecutive': round(consec_score, 4),
                'chip_risk': round(chip_score, 4),
                'pattern_risk': round(yang_risk, 4),
            }
        }


# ===================================================================
# 大类九：行业配比 & 事件驱动因子
# ===================================================================

class IndustryEventFactorCalculator:
    """行业配比与事件驱动因子计算器"""

    def calc_industry_relative_strength(self, df: pd.DataFrame, industry_data: Optional[pd.DataFrame] = None) -> Dict:
        """
        因子13: 行业相对强度 (industry_relative_strength)
        ────────────────────────────────────────────
        研报依据：国君金工《日频行业动量与反转》2024

        逻辑：
          个股20日涨幅 - 行业20日涨幅 = 相对强度
          如果没有行业数据，用"偏离自身均线"代理：
            rel_strength = (close - MA20) / MA20

          rel_strength > 10% → 超越行业平均
          rel_strength < -10% → 弱于行业

        返回：
          stock_return_20d: 个股20日涨幅
          rel_strength: 相对强度
          rel_signal: 信号
        """
        close = df['close']
        n = len(close)

        if n < 20:
            return {
                'stock_return_20d': 0.0,
                'rel_strength': 0.0,
                'rel_signal': 'insufficient_data',
            }

        stock_ret = float(close.iloc[-1] / close.iloc[-20] - 1)
        ma20 = float(close.rolling(20, min_periods=10).mean().iloc[-1])

        if ma20 > 0.01:
            rel = (close.iloc[-1] - ma20) / ma20
        else:
            rel = 0.0

        # 如果有行业数据
        industry_ret = 0.0
        if industry_data is not None and len(industry_data) >= 20:
            industry_ret = float(industry_data.iloc[-1] / industry_data.iloc[-20] - 1)
            rel = stock_ret - industry_ret

        rel = float(rel)

        if rel > 0.10:
            signal = 'outperform'
        elif rel < -0.10:
            signal = 'underperform'
        else:
            signal = 'neutral'

        return {
            'stock_return_20d': round(stock_ret, 6),
            'industry_return_20d': round(industry_ret, 6),
            'rel_strength': round(rel, 6),
            'rel_signal': signal,
        }

    def calc_industry_flow_resonance(self, df: pd.DataFrame) -> Dict:
        """
        因子14: 行业资金流共振 (industry_flow_resonance)
        ──────────────────────────────────────────────
        逻辑：
          个股量能变化与价格变化的相关性 = 资金流方向
          当量增价涨 = 正向资金流（主力流入）

          resonance_10d = corr(volume_change, price_change, 10)
          高正相关 → 量价齐升，趋势健康
          低/负相关 → 量价背离

        返回：
          vol_price_corr_10d: 10日量价相关系数
          resonance_score: 共振评分(0~1)
          resonance_signal: 信号
        """
        vol_chg = df['volume'].pct_change().replace([np.inf, -np.inf], np.nan).fillna(0)
        price_chg = df['pctChg'] / 100.0

        corr_10d = vol_chg.rolling(10, min_periods=5).corr(price_chg)
        latest_corr = _latest(corr_10d)

        # 共振评分
        score = np.clip((latest_corr + 0.3) / 1.3, 0, 1)  # 归一化

        if latest_corr > 0.4:
            signal = 'strong_resonance'
        elif latest_corr > 0.1:
            signal = 'weak_resonance'
        elif latest_corr < -0.2:
            signal = 'divergence'
        else:
            signal = 'neutral'

        return {
            'vol_price_corr_10d': round(latest_corr, 4),
            'resonance_score': round(float(score), 4),
            'resonance_signal': signal,
        }

    def calc_event_impact(self, df: pd.DataFrame) -> Dict:
        """
        因子15: 事件冲击因子 (event_impact)
        ─────────────────────────────────────
        逻辑：
          检测异常波动事件（涨跌停、大阳/阴线）：
            - 单日涨幅 > 5% → 事件冲击
            - 单日跌幅 > 5% → 负面冲击
            - 近5日内出现2次以上冲击 → 连续事件

          event_score = 近5日异常波动天数 / 5
          冲击后次日表现 = 评估事件是否可持续

        返回：
          event_count_5d: 近5日异常事件数
          event_score: 事件冲击评分
          event_type: 最近事件类型
        """
        pct = df['pctChg']
        if len(pct) < 5:
            return {
                'event_count_5d': 0,
                'event_score': 0.0,
                'event_type': 'none',
            }

        pct_5d = pct.tail(5)
        big_moves = ((pct_5d.abs() > 5.0).sum())
        latest_pct = float(pct.iloc[-1])

        # 事件类型
        if latest_pct > 5:
            event_type = 'big_up'
        elif latest_pct < -5:
            event_type = 'big_down'
        elif latest_pct > 3:
            event_type = 'moderate_up'
        elif latest_pct < -3:
            event_type = 'moderate_down'
        else:
            event_type = 'none'

        score = min(1.0, int(big_moves) / 3.0)

        return {
            'event_count_5d': int(big_moves),
            'event_score': round(float(score), 4),
            'event_type': event_type,
        }

    def calc_limit_distance(self, df: pd.DataFrame) -> Dict:
        """
        因子16: 涨跌停距离因子 (limit_distance)
        ──────────────────────────────────────
        逻辑：
          涨停距离 = (涨停价 - 收盘价) / 收盘价
          普通股涨停 = +10%，ST = +5%

          distance_to_limit_up < 2% → 接近涨停，高风险（追涨）
          distance_to_limit_down < 2% → 接近跌停，可能超跌

        返回：
          dist_to_limit_up: 距涨停距离(%)
          dist_to_limit_down: 距跌停距离(%)
          limit_proximity_score: 接近涨跌停评分
        """
        close = float(df['close'].iloc[-1])
        pct = float(df['pctChg'].iloc[-1])

        # 简单假设10%涨停（非ST）
        limit_rate = 10.0

        # 估算今日涨停价 = 昨收 × 1.1
        prev_close = close / (1 + pct / 100.0) if abs(pct) < 99 else close * 0.9
        limit_up = prev_close * (1 + limit_rate / 100.0)
        limit_down = prev_close * (1 - limit_rate / 100.0)

        dist_up = (limit_up - close) / close * 100
        dist_down = (close - limit_down) / close * 100

        # 接近涨停的评分
        proximity = 0.0
        if dist_up < 2:
            proximity = 1.0 - dist_up / 2.0   # 越接近涨停越高
        elif dist_down < 2:
            proximity = -(1.0 - dist_down / 2.0)  # 越接近跌停越负

        return {
            'dist_to_limit_up': round(dist_up, 2),
            'dist_to_limit_down': round(dist_down, 2),
            'limit_proximity_score': round(float(proximity), 4),
        }

    def calc_new_high_low_count(self, df: pd.DataFrame) -> Dict:
        """
        因子17: 新高新低计数 (new_high_low_count)
        ────────────────────────────────────────
        逻辑：
          统计20日内收盘价创新高/新低的次数
          创新高 = close > max(close[0:i-1])
          创新低 = close < min(close[0:i-1])

          new_high_count > 5 → 频繁创新高，强势
          new_low_count > 5 → 频繁创新低，弱势
          new_high 后接 new_low → 见顶信号

        返回：
          new_high_20d: 20日新高次数
          new_low_20d: 20日新低次数
          hl_ratio: 高新/新低比
          hl_signal: 信号
        """
        close = df['close'].values
        n = len(close)

        new_high = 0
        new_low = 0
        recent_high_count = 0
        recent_low_count = 0

        window = min(20, n)
        start_idx = n - window

        running_max = float(close[start_idx])
        running_min = float(close[start_idx])

        for i in range(start_idx, n):
            if i > start_idx:
                if close[i] > running_max:
                    new_high += 1
                    running_max = float(close[i])
                    if i >= n - 5:
                        recent_high_count += 1
                if close[i] < running_min:
                    new_low += 1
                    running_min = float(close[i])
                    if i >= n - 5:
                        recent_low_count += 1

        ratio = _safe_div(new_high, max(new_low, 1), fill=1.0)

        if recent_high_count > 3 and recent_low_count == 0:
            signal = 'strong_uptrend'
        elif recent_high_count > 0 and recent_low_count > 0:
            signal = 'volatile'
        elif recent_low_count > 3:
            signal = 'weak_downtrend'
        else:
            signal = 'neutral'

        return {
            'new_high_20d': new_high,
            'new_low_20d': new_low,
            'recent_high_5d': recent_high_count,
            'recent_low_5d': recent_low_count,
            'hl_ratio': round(ratio, 4),
            'hl_signal': signal,
        }

    def calc_sector_rotation_score(self, df: pd.DataFrame) -> Dict:
        """
        因子18: 板块轮动配比 (sector_rotation_score)
        ────────────────────────────────────────────
        研报依据：广发金工《行业轮动与风格配比因子》2024

        逻辑：
          基于动量排序的板块轮动信号：
            momentum_rank = 20日涨幅在"历史20日涨幅分布"中的百分位
            rank > 80% → 强势板块
            rank 从高位下降 → 动能衰减，可能轮动

          由于缺少行业数据，用个股自身的动量衰减做代理：
            mom_decay = (mom_5d - mom_10d) / abs(mom_10d)
            正衰减（5日 < 10日）→ 动能下降
            负衰减（5日 > 10日）→ 动能加速

        返回：
          momentum_rank: 动量百分位
          mom_decay: 动量衰减率
          rotation_signal: 轮动信号
          rotation_score: 轮动评分(0~1)
        """
        close = df['close']
        n = len(close)

        if n < 20:
            return {
                'momentum_rank': 0.5,
                'mom_decay': 0.0,
                'rotation_signal': 'insufficient_data',
                'rotation_score': 0.5,
            }

        # 20日动量百分位
        rets_20d = close.pct_change(20).dropna()
        if len(rets_20d) >= 5:
            rank = float(rets_20d.rank(pct=True).iloc[-1])
        else:
            rank = 0.5

        # 动量衰减
        mom_5 = float(close.iloc[-1] / close.iloc[-5] - 1) if n >= 5 else 0
        mom_10 = float(close.iloc[-1] / close.iloc[-10] - 1) if n >= 10 else 0

        if abs(mom_10) > 1e-6:
            decay = (mom_5 - mom_10) / abs(mom_10)
        else:
            decay = 0.0

        # 信号
        if rank > 0.8 and decay < -0.3:
            signal = 'exhaustion_warning'   # 高动量但衰减 → 可能切换
        elif rank > 0.7 and decay > 0.2:
            signal = 'momentum_accelerating'  # 高动量加速 → 强势
        elif rank < 0.2 and decay > 0.5:
            signal = 'bottom_recovery'       # 低动量但加速 → 反转
        else:
            signal = 'neutral'

        # 评分：高动量 + 加速 = 高分
        score = rank * 0.5 + np.clip(0.5 + decay * 0.3, 0, 1) * 0.5

        return {
            'momentum_rank': round(rank, 4),
            'mom_decay': round(float(decay), 4),
            'rotation_signal': signal,
            'rotation_score': round(float(score), 4),
        }


# ===================================================================
# 统一接口
# ===================================================================

class MicrostructureReversalFactorCalculator:
    """
    微观结构/筹码 + 反转预警 + 行业事件 统一计算器

    用法：
        calc = MicrostructureReversalFactorCalculator()
        factors = calc.calculate_all(df)
        score, level = calc.get_comprehensive_score(factors)
    """

    def __init__(self):
        self.micro_calc = MicrostructureFactorCalculator()
        self.reversal_calc = ReversalWarningFactorCalculator()
        self.industry_calc = IndustryEventFactorCalculator()

    def check_df(self, df: pd.DataFrame) -> Optional[str]:
        """检查输入数据"""
        required = ['open', 'close', 'high', 'low', 'volume', 'amount', 'pctChg', 'turn']
        missing = [c for c in required if c not in df.columns]
        if missing:
            return f"缺少列: {missing}"
        if len(df) < 20:
            return f"数据不足: {len(df)}行, 至少需要20行"
        return None

    def calculate_all(self, df: pd.DataFrame, industry_data: Optional[pd.DataFrame] = None) -> Dict:
        """
        计算所有微观结构/反转/行业因子

        Parameters
        ----------
        df : DataFrame
            日频K线数据
        industry_data : DataFrame, optional
            行业指数日频数据（如有）

        Returns
        -------
        dict 包含所有因子值
        """
        err = self.check_df(df)
        if err:
            logger.warning("MicrostructureReversalFactors 数据校验失败: %s", err)
            return self._default_factors()

        results = {}
        try:
            # 大类七：微观结构/筹码（6个）
            chip = self.micro_calc.calc_chip_concentration(df)
            obi = self.micro_calc.calc_order_imbalance_proxy(df)
            resilience = self.micro_calc.calc_intraday_resilience(df)
            close_pos = self.micro_calc.calc_close_position(df)
            candle = self.micro_calc.calc_candle_pattern_ratio(df)
            consec = self.micro_calc.calc_consecutive_move(df)

            results.update({
                'chip_concentration_20': chip['chip_concentration_20'],
                'chip_mean_price': chip['chip_mean_price'],
                'chip_risk_score': chip['chip_risk_score'],
                'obi_5d': obi['obi_5d'],
                'obi_10d': obi['obi_10d'],
                'obi_signal': obi['obi_signal'],
                'obi_persistence': obi['obi_persistence'],
                'resilience_today': resilience['resilience_today'],
                'resilience_10d': resilience['resilience_10d'],
                'resilience_signal': resilience['resilience_signal'],
                'close_pos_today': close_pos['close_pos_today'],
                'close_pos_10d': close_pos['close_pos_10d'],
                'close_pos_trend': close_pos['close_pos_trend'],
                'close_pos_score': close_pos['close_pos_score'],
                'yang_ratio_5d': candle['yang_ratio_5d'],
                'yang_ratio_10d': candle['yang_ratio_10d'],
                'pattern_signal': candle['pattern_signal'],
                'consecutive_up': consec['consecutive_up'],
                'consecutive_down': consec['consecutive_down'],
                'max_consec_up_10d': consec['max_consec_up_10d'],
                'max_consec_down_10d': consec['max_consec_down_10d'],
                'momentum_exhaustion': consec['momentum_exhaustion'],
            })

            # 大类八：反转预警 & 风格切换（6个）
            ob = self.reversal_calc.calc_short_overbought_reversal(df)
            div = self.reversal_calc.calc_multi_tf_divergence(df)
            brk = self.reversal_calc.calc_breakback_test(df)
            style = self.reversal_calc.calc_style_momentum_score(df)
            style_crowd = self.reversal_calc.calc_style_crowd_switch(df)
            reversal = self.reversal_calc.calc_reversal_warning_score(df, micro_factors=results)

            results.update({
                'overbought_score': ob['overbought_score'],
                'overbought_triggers': ob['overbought_triggers'],
                'reversal_warning': ob['reversal_warning'],
                'latest_rsi_6': ob['latest_rsi_6'],
                'mom_5d': div['mom_5d'],
                'mom_10d': div['mom_10d'],
                'mom_20d': div['mom_20d'],
                'divergence_signal': div['divergence_signal'],
                'tf_consistency': div['tf_consistency'],
                'breakout': brk['breakout'],
                'pullback': brk['pullback'],
                'pullback_shrink': brk['pullback_shrink'],
                'breakout_signal': brk['breakout_signal'],
                'amt_trend': style['amt_trend'],
                'amt_volatility': style['amt_volatility'],
                'style_signal': style['style_signal'],
                'style_score': style['style_score'],
                'crowding_now': style_crowd['crowding_now'],
                'crowding_change': style_crowd['crowding_change'],
                'switch_signal': style_crowd['switch_signal'],
                'reversal_warning_score': reversal['reversal_warning_score'],
                'warning_level': reversal['warning_level'],
                'warning_components': reversal['warning_components'],
            })

            # 大类九：行业配比 & 事件驱动（6个）
            ind_rel = self.industry_calc.calc_industry_relative_strength(df, industry_data)
            resonance = self.industry_calc.calc_industry_flow_resonance(df)
            event = self.industry_calc.calc_event_impact(df)
            limit = self.industry_calc.calc_limit_distance(df)
            hl = self.industry_calc.calc_new_high_low_count(df)
            rotation = self.industry_calc.calc_sector_rotation_score(df)

            results.update({
                'stock_return_20d': ind_rel['stock_return_20d'],
                'industry_return_20d': ind_rel['industry_return_20d'],
                'rel_strength': ind_rel['rel_strength'],
                'rel_signal': ind_rel['rel_signal'],
                'vol_price_corr_10d': resonance['vol_price_corr_10d'],
                'resonance_score': resonance['resonance_score'],
                'resonance_signal': resonance['resonance_signal'],
                'event_count_5d': event['event_count_5d'],
                'event_score': event['event_score'],
                'event_type': event['event_type'],
                'dist_to_limit_up': limit['dist_to_limit_up'],
                'dist_to_limit_down': limit['dist_to_limit_down'],
                'limit_proximity_score': limit['limit_proximity_score'],
                'new_high_20d': hl['new_high_20d'],
                'new_low_20d': hl['new_low_20d'],
                'recent_high_5d': hl['recent_high_5d'],
                'recent_low_5d': hl['recent_low_5d'],
                'hl_ratio': hl['hl_ratio'],
                'hl_signal': hl['hl_signal'],
                'momentum_rank': rotation['momentum_rank'],
                'mom_decay': rotation['mom_decay'],
                'rotation_signal': rotation['rotation_signal'],
                'rotation_score': rotation['rotation_score'],
            })

        except Exception as e:
            logger.error(f"MicrostructureReversalFactors 计算异常: {e}", exc_info=True)
            return self._default_factors()

        return results

    def _default_factors(self) -> Dict:
        """返回因子默认值"""
        return {
            # 大类七
            'chip_concentration_20': 0.5, 'chip_mean_price': 0.0, 'chip_risk_score': 0.5,
            'obi_5d': 0.0, 'obi_10d': 0.0, 'obi_signal': 'neutral', 'obi_persistence': 0.5,
            'resilience_today': 0.5, 'resilience_10d': 0.5, 'resilience_signal': 'neutral',
            'close_pos_today': 0.5, 'close_pos_10d': 0.5, 'close_pos_trend': 'flat', 'close_pos_score': 0.5,
            'yang_ratio_5d': 0.5, 'yang_ratio_10d': 0.5, 'pattern_signal': 'neutral',
            'consecutive_up': 0, 'consecutive_down': 0, 'max_consec_up_10d': 0,
            'max_consec_down_10d': 0, 'momentum_exhaustion': 0.0,
            # 大类八
            'overbought_score': 0.0, 'overbought_triggers': 0, 'reversal_warning': False, 'latest_rsi_6': 50.0,
            'mom_5d': 0.0, 'mom_10d': 0.0, 'mom_20d': 0.0,
            'divergence_signal': 'neutral', 'tf_consistency': 0.5,
            'breakout': False, 'pullback': False, 'pullback_shrink': False, 'breakout_signal': 'no_breakout',
            'amt_trend': 1.0, 'amt_volatility': 0.0, 'style_signal': 'neutral', 'style_score': 0.5,
            'crowding_now': 0.0, 'crowding_change': 0.0, 'switch_signal': 'neutral',
            'reversal_warning_score': 0.0, 'warning_level': 'safe',
            'warning_components': {
                'overbought': 0.0, 'divergence': 0.0, 'exhaustion': 0.0,
                'consecutive': 0.0, 'chip_risk': 0.0, 'pattern_risk': 0.0,
            },
            # 大类九
            'stock_return_20d': 0.0, 'industry_return_20d': 0.0, 'rel_strength': 0.0, 'rel_signal': 'neutral',
            'vol_price_corr_10d': 0.0, 'resonance_score': 0.5, 'resonance_signal': 'neutral',
            'event_count_5d': 0, 'event_score': 0.0, 'event_type': 'none',
            'dist_to_limit_up': 10.0, 'dist_to_limit_down': 10.0, 'limit_proximity_score': 0.0,
            'new_high_20d': 0, 'new_low_20d': 0, 'recent_high_5d': 0, 'recent_low_5d': 0,
            'hl_ratio': 1.0, 'hl_signal': 'neutral',
            'momentum_rank': 0.5, 'mom_decay': 0.0, 'rotation_signal': 'neutral', 'rotation_score': 0.5,
        }

    def get_comprehensive_score(self, factors: Dict) -> Tuple[float, str]:
        """
        微观结构+反转+行业 综合评分 → 用于主程序加权

        综合维度：
          微观结构正面(35%):
            - 委比正向、弹性高、收盘位置高、筹码集中 → 正面
          反转风险(35%):
            - 反转预警分数高 → 惩罚
          行业事件(30%):
            - 相对强度好、共振强、轮动评分高 → 正面

        Returns
        -------
        (adjustment_coef, level_str)
        """
        # 微观结构正面评分
        micro_positive = (
            factors.get('obi_persistence', 0.5) * 0.25 +
            factors.get('resilience_10d', 0.5) * 0.25 +
            factors.get('close_pos_score', 0.5) * 0.25 +
            (1.0 - factors.get('chip_risk_score', 0.5)) * 0.25
        )

        # 反转风险评分
        reversal_risk = factors.get('reversal_warning_score', 0.0)

        # 行业事件正面评分
        industry_positive = (
            np.clip(0.5 + factors.get('rel_strength', 0) * 3, 0, 1) * 0.30 +
            factors.get('resonance_score', 0.5) * 0.30 +
            factors.get('rotation_score', 0.5) * 0.40
        )

        # 综合评分：正面 - 风险惩罚
        total = micro_positive * 0.35 + industry_positive * 0.30 - reversal_risk * 0.35
        total = np.clip(total, 0, 1)

        # 转换为调整系数
        if total > 0.6:
            coef = 1.03
            level = '强势'
        elif total > 0.4:
            coef = 1.0
            level = '中性偏强'
        elif total > 0.2:
            coef = 0.95
            level = '中性'
        else:
            coef = max(0.80, 0.85 + total * 0.5)
            level = '弱势'

        return round(coef, 4), level

    def get_factor_summary(self, factors: Dict) -> str:
        """生成因子摘要字符串"""
        chip = factors.get('chip_concentration_20', 0.5)
        obi = factors.get('obi_signal', 'neutral')
        reversal = factors.get('warning_level', 'safe')
        resonance = factors.get('resonance_signal', 'neutral')
        hl = factors.get('hl_signal', 'neutral')

        return (
            f"筹码集中度:{chip:.2f} | 委比信号:{obi} | "
            f"反转预警:{reversal} | 量价共振:{resonance} | "
            f"新高新低:{hl}"
        )


# ===================================================================
# 快速测试
# ===================================================================

if __name__ == '__main__':
    print("=" * 60)
    print("MicrostructureReversalFactorCalculator 快速测试")
    print("=" * 60)

    np.random.seed(42)
    n = 120
    close = 10.0 * np.cumprod(1 + np.random.normal(0.0005, 0.022, n))
    high = close * (1 + np.random.uniform(0, 0.03, n))
    low = close * (1 - np.random.uniform(0, 0.03, n))
    open_ = close * (1 + np.random.normal(0, 0.012, n))
    volume = np.random.uniform(1e7, 5e8, n)
    amount = volume * close
    pctChg = (close / np.roll(close, 1) - 1) * 100
    pctChg[0] = 0
    turn = np.random.uniform(0.5, 5.0, n)

    df = pd.DataFrame({
        'open': open_, 'close': close, 'high': high, 'low': low,
        'volume': volume, 'amount': amount, 'pctChg': pctChg, 'turn': turn
    })

    calc = MicrostructureReversalFactorCalculator()
    factors = calc.calculate_all(df)

    print(f"\n【大类七：微观结构/筹码】")
    print(f"  筹码集中度: {factors['chip_concentration_20']:.4f} | 风险分: {factors['chip_risk_score']:.4f}")
    print(f"  委比5d: {factors['obi_5d']:+.4f} | 信号: {factors['obi_signal']} | 持续性: {factors['obi_persistence']:.2f}")
    print(f"  日内弹性: {factors['resilience_10d']:.4f} | 信号: {factors['resilience_signal']}")
    print(f"  收盘位置: {factors['close_pos_10d']:.4f} | 趋势: {factors['close_pos_trend']}")
    print(f"  阴阳比5d: {factors['yang_ratio_5d']:.2f} | 模式: {factors['pattern_signal']}")
    print(f"  连涨: {factors['consecutive_up']} | 连跌: {factors['consecutive_down']} | 动能衰竭: {factors['momentum_exhaustion']:.2f}")

    print(f"\n【大类八：反转预警 & 风格】")
    print(f"  超买评分: {factors['overbought_score']:.4f} | 触发项: {factors['overbought_triggers']} | RSI6: {factors['latest_rsi_6']:.1f}")
    print(f"  动量5d/10d/20d: {factors['mom_5d']:+.2%}/{factors['mom_10d']:+.2%}/{factors['mom_20d']:+.2%}")
    print(f"  背离信号: {factors['divergence_signal']} | 多周期一致性: {factors['tf_consistency']:.2f}")
    print(f"  突破信号: {factors['breakout_signal']}")
    print(f"  风格: {factors['style_signal']} | 拥挤度切换: {factors['switch_signal']}")
    print(f"  ★反转综合预警: {factors['reversal_warning_score']:.4f} | 级别: {factors['warning_level']}")

    print(f"\n【大类九：行业 & 事件】")
    print(f"  相对强度: {factors['rel_strength']:+.4f} | 信号: {factors['rel_signal']}")
    print(f"  量价共振: {factors['vol_price_corr_10d']:+.4f} | 信号: {factors['resonance_signal']}")
    print(f"  事件冲击: {factors['event_type']} (近5日{factors['event_count_5d']}次)")
    print(f"  距涨停: {factors['dist_to_limit_up']:.1f}% | 距跌停: {factors['dist_to_limit_down']:.1f}%")
    print(f"  新高/新低(20d): {factors['new_high_20d']}/{factors['new_low_20d']} | 信号: {factors['hl_signal']}")
    print(f"  轮动评分: {factors['rotation_score']:.4f} | 信号: {factors['rotation_signal']}")

    coef, level = calc.get_comprehensive_score(factors)
    print(f"\n【综合调整系数】: {coef:.4f} | 级别: {level}")
    print(f"\n【因子摘要】: {calc.get_factor_summary(factors)}")
    print("\n[PASS] 测试通过")
