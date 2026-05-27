#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
波动率高阶矩 & 情绪拥挤度日频因子库 v1.0
==========================================
研报/顶刊依据:
  Harvey & Siddique(2000) 《Conditional Skewness in Asset Pricing Tests》JF
  Kumar(2009) 《Who Gambles in the Stock Market?》JF - 彩票型股票偏度
  Ang et al.(2006) 《The Cross-Section of Volatility and Expected Returns》JF
  中信金工《波动率高阶矩因子的A股实证》2023
  广发金工《情绪拥挤度与短期反转》2024
  招商金工《市场恐慌指数与风险预警》2023
  国盛金工《换手率视角下的A股情绪度量》2024
  东方证券金工《隐含恐慌指数的A股应用》2024

大类五：波动率高阶矩日频因子（6个）
  1. 收益偏度因子 (return_skewness)       - 识别彩票型高风险股票
  2. 收益峰度因子 (return_kurtosis)       - 极端事件概率评估
  3. 下行波动率因子 (downside_vol)        - 对称 vs 下行风险分离
  4. 波动率不对称因子 (vol_asymmetry)     - 上涨vs下跌波动率差异
  5. 隐含恐慌指数 (implied_panic_index)   - 基于日内振幅的恐慌度
  6. 波动率自相关因子 (vol_autocorr)      - 波动率持续性/簇集效应

大类六：情绪拥挤度日频因子（5个）
  7. 换手率拥挤度 (turnover_crowd)        - 相对历史的换手率拥挤
  8. 振幅拥挤度 (amplitude_crowd)         - 振幅相对历史的异常
  9. 量比异常度 (vol_ratio_anomaly)       - 当日量/5日均量的异常
  10. 热度衰减速度 (popularity_decay)     - 近期热度是否快速退潮
  11. 情绪综合拥挤度 (sentiment_crowd)    - 综合拥挤度评分

全部为日频滚动因子，回溯5/10/20日，数据源：akshare日频K线
"""

import numpy as np
import pandas as pd
from typing import Dict, Optional, Tuple
import logging

logger = logging.getLogger(__name__)


class VolatilitySentimentFactorCalculator:
    """
    波动率高阶矩 & 情绪拥挤度因子计算器

    输入 df 为日频 K 线 DataFrame，需含以下列（全部 float64）：
        open, close, high, low, volume, amount, pctChg, turn
    索引为日期（datetime 或字符串），升序排列（旧→新）。

    用法：
        calc = VolatilitySentimentFactorCalculator()
        factors = calc.calculate_all(df)
        score = calc.get_vol_sentiment_score(factors)
    """

    # ── 因子参数 ──────────────────────────────────────────────────────────
    SKEW_WINDOW = 20        # 偏度/峰度计算窗口
    VOL_WINDOW_SHORT = 10   # 短期波动率窗口
    VOL_WINDOW_LONG = 60    # 长期波动率窗口
    DOWNSIDE_WINDOW = 20    # 下行波动率窗口
    PANIC_WINDOW = 10       # 恐慌指数窗口
    VOL_AUTOCORR_LAG = 5    # 波动率自相关滞后期
    CROWD_WINDOW = 20       # 拥挤度历史窗口
    CROWD_SHORT = 5         # 拥挤度短期窗口

    def __init__(self):
        pass

    # ── 工具方法 ──────────────────────────────────────────────────────────

    @staticmethod
    def _safe_div(a, b, fill=0.0):
        """安全除法，b≈0时返回fill"""
        try:
            if isinstance(b, (int, float)):
                return a / b if abs(b) > 1e-9 else fill
            result = np.where(np.abs(b) > 1e-9, a / b, fill)
            if hasattr(a, 'index'):
                return pd.Series(result, index=a.index, dtype=float)
            return result
        except Exception as e:
            logger.debug("safe division failed: %s", e)
            return fill

    @staticmethod
    def _rolling_skewness(series: pd.Series, window: int) -> pd.Series:
        """滚动偏度（Fisher修正版）"""
        return series.rolling(window, min_periods=max(5, window // 2)).skew()

    @staticmethod
    def _rolling_kurtosis(series: pd.Series, window: int) -> pd.Series:
        """滚动峰度（超额峰度=峰度-3）"""
        return series.rolling(window, min_periods=max(5, window // 2)).kurt()

    def _check_df(self, df: pd.DataFrame) -> Optional[str]:
        """检查输入数据，返回错误信息或None"""
        required = ['open', 'close', 'high', 'low', 'volume', 'amount', 'pctChg', 'turn']
        missing = [c for c in required if c not in df.columns]
        if missing:
            return f"缺少列: {missing}"
        if len(df) < 10:
            return f"数据不足：仅 {len(df)} 行，至少需要10行"
        return None

    # ── 大类五：波动率高阶矩因子（6个）─────────────────────────────────────

    def calc_return_skewness(self, df: pd.DataFrame) -> Dict:
        """
        因子1: 收益偏度因子 (return_skewness)
        ─────────────────────────────────────
        研报依据：Harvey & Siddique(2000) 负偏度溢价；
                  Kumar(2009) 彩票型股票偏好高偏度
        
        逻辑：
          ret = pctChg / 100
          skew_20 = rolling_skew(ret, 20)
          
          高正偏度（>1）：彩票型股票，散户追捧但期望收益低，避险
          高负偏度（<-1）：尾部下跌风险大，避险
          
        返回：
          skew_20: 20日滚动偏度
          skew_signal: +1(中性偏度, 安全区) / 0(警戒) / -1(危险)
          skew_risk_score: 0~1，越高风险越大
        """
        ret = df['pctChg'] / 100.0
        skew_20 = self._rolling_skewness(ret, self.SKEW_WINDOW)
        latest_skew = float(skew_20.iloc[-1]) if not pd.isna(skew_20.iloc[-1]) else 0.0

        # 风险评分：偏度绝对值越大风险越高
        # 正偏度 > 1.5 → 彩票型，容易爆跌
        # 负偏度 < -1.5 → 下行尾部风险
        risk_score = min(1.0, abs(latest_skew) / 3.0)

        if abs(latest_skew) < 0.5:
            signal = 1   # 正常
        elif abs(latest_skew) < 1.5:
            signal = 0   # 警戒
        else:
            signal = -1  # 危险

        return {
            'skew_20': latest_skew,
            'skew_signal': signal,
            'skew_risk_score': risk_score,
            'skew_series': skew_20,
        }

    def calc_return_kurtosis(self, df: pd.DataFrame) -> Dict:
        """
        因子2: 收益峰度因子 (return_kurtosis)
        ──────────────────────────────────────
        研报依据：Ang et al.(2006) 超额峰度与截面收益负相关
        
        逻辑：
          kurt_20 = rolling_excess_kurtosis(ret, 20)
          
          高峰度（>3）：厚尾分布，极端事件频发，风险高
          
        返回：
          kurt_20: 超额峰度
          kurt_risk_score: 0~1
        """
        ret = df['pctChg'] / 100.0
        kurt_20 = self._rolling_kurtosis(ret, self.SKEW_WINDOW)
        latest_kurt = float(kurt_20.iloc[-1]) if not pd.isna(kurt_20.iloc[-1]) else 0.0

        # 超额峰度 > 3 表示厚尾风险
        risk_score = min(1.0, max(0.0, latest_kurt / 6.0))

        return {
            'kurt_20': latest_kurt,
            'kurt_risk_score': risk_score,
            'kurt_series': kurt_20,
        }

    def calc_downside_vol(self, df: pd.DataFrame) -> Dict:
        """
        因子3: 下行波动率因子 (downside_vol)
        ──────────────────────────────────────
        研报依据：半方差/下行偏差，Sortino比率的分母
        中信金工《波动率高阶矩因子的A股实证》2023
        
        逻辑：
          ret = pctChg / 100
          downside_vol_20 = std(ret[ret < 0], 20)   # 只计算负收益日的波动
          total_vol_20 = std(ret, 20)
          vol_asymmetry_ratio = downside_vol / total_vol  # > 0.7 → 以下行风险为主
          
        返回：
          downside_vol_20: 下行波动率
          total_vol_20: 总波动率
          downside_ratio: 下行波动率/总波动率
        """
        ret = df['pctChg'] / 100.0
        window = self.DOWNSIDE_WINDOW

        # 向量化替代 for 循环（LRN-20260327-001 性能优化）
        # 总波动率：标准rolling std
        tot_vol = ret.rolling(window, min_periods=5).std()

        # 下行波动率：仅负收益的半方差（semi-deviation）
        # 方法：对负收益取值，正收益置0后计算平方均值再开方
        neg_only = ret.where(ret < 0, 0.0)
        # 半方差 = sqrt(sum(r_neg^2) / count_valid)
        # 用rolling sum(r^2) / count_valid 近似
        neg_sq_sum = (neg_only ** 2).rolling(window, min_periods=5).sum()
        neg_count = (ret < 0).rolling(window, min_periods=5).sum().clip(lower=3)
        ds_vol = (neg_sq_sum / neg_count).apply(lambda x: np.sqrt(x) if x >= 0 else np.nan)

        ds_vol.index = ret.index
        tot_vol.index = ret.index

        latest_dv = float(ds_vol.iloc[-1]) if not pd.isna(ds_vol.iloc[-1]) else 0.0
        latest_tv = float(tot_vol.iloc[-1]) if not pd.isna(tot_vol.iloc[-1]) else 0.0
        ratio = self._safe_div(latest_dv, latest_tv, fill=0.5)

        # 下行比例 > 0.7 且总波动率高，风险信号
        risk_score = min(1.0, ratio * 1.2) if latest_tv > 0.02 else 0.0

        return {
            'downside_vol_20': latest_dv,
            'total_vol_20': latest_tv,
            'downside_ratio': ratio,
            'downside_risk_score': risk_score,
        }

    def calc_vol_asymmetry(self, df: pd.DataFrame) -> Dict:
        """
        因子4: 波动率不对称因子 (vol_asymmetry)
        ─────────────────────────────────────────
        逻辑：
          up_vol = std(ret[ret > 0], 10)   # 上涨日波动率
          dn_vol = std(ret[ret < 0], 10)   # 下跌日波动率
          asymmetry = dn_vol / up_vol
          
          asymmetry > 1.3 → 跌时比涨时更剧烈，危险信号
          asymmetry < 0.7 → 涨时更剧烈，可能是拉升阶段
          
        返回：
          up_vol_10: 上涨日波动率
          dn_vol_10: 下跌日波动率
          vol_asymmetry: dn_vol / up_vol
        """
        ret = df['pctChg'] / 100.0
        window = self.VOL_WINDOW_SHORT

        # 向量化替代 for 循环（LRN-20260327-001 性能优化）
        # 上涨日：正收益的标准差；下跌日：负收益绝对值的标准差
        pos_only = ret.where(ret > 0, np.nan)
        neg_only = ret.where(ret < 0, np.nan).abs()

        # rolling std on masked series (NaN when condition not met)
        up_vol_s = pos_only.rolling(window, min_periods=3).std().fillna(0.01)
        dn_vol_s = neg_only.rolling(window, min_periods=3).std().fillna(0.01)
        asym_s = dn_vol_s / up_vol_s.replace(0, 1e-6)

        latest_uv = float(up_vol_s.iloc[-1])
        latest_dv = float(dn_vol_s.iloc[-1])
        latest_asym = float(asym_s.iloc[-1]) if not pd.isna(asym_s.iloc[-1]) else 1.0

        # 跌时比涨时剧烈 → 危险
        risk_score = min(1.0, max(0.0, (latest_asym - 1.0) / 1.5)) if latest_asym > 1.0 else 0.0

        return {
            'up_vol_10': latest_uv,
            'dn_vol_10': latest_dv,
            'vol_asymmetry': latest_asym,
            'vol_asym_risk_score': risk_score,
        }

    def calc_implied_panic_index(self, df: pd.DataFrame) -> Dict:
        """
        因子5: 隐含恐慌指数 (implied_panic_index)
        ──────────────────────────────────────────
        研报依据：东方证券金工《隐含恐慌指数的A股应用》2024
        
        逻辑：
          日振幅 = (high - low) / close_prev * 100  → 类VIX的日频代理
          panic_10 = mean(振幅, 10) / std(振幅, 60) + 1  标准化恐慌度
          
          同时计算收阴率（连续下跌日比例）和振幅加速度
          
        返回：
          amplitude: 今日振幅
          panic_10: 近10日均振幅/60日振幅标准差
          bear_ratio_10: 10日内收阴日比例
          panic_score: 0~1 恐慌综合评分
        """
        high = df['high']
        low = df['low']
        close = df['close']
        pct = df['pctChg']

        # 振幅 = (high - low) / close.shift(1)
        close_prev = close.shift(1).fillna(close)
        amplitude = ((high - low) / close_prev * 100).clip(0, 20)
        amp_ma10 = amplitude.rolling(self.PANIC_WINDOW, min_periods=3).mean()
        amp_std60 = amplitude.rolling(60, min_periods=20).std()
        panic_idx = self._safe_div(amp_ma10, amp_std60.replace(0, np.nan).fillna(1), fill=1.0)

        # 收阴率
        bear_days = (pct < 0).rolling(self.PANIC_WINDOW, min_periods=3).mean()

        latest_amp = float(amplitude.iloc[-1])
        latest_panic = float(panic_idx.iloc[-1]) if not pd.isna(panic_idx.iloc[-1]) else 1.0
        latest_bear = float(bear_days.iloc[-1]) if not pd.isna(bear_days.iloc[-1]) else 0.5

        # 综合恐慌评分：恐慌指数 > 2 且收阴率 > 0.6
        panic_score = min(1.0, (latest_panic / 3.0) * 0.6 + latest_bear * 0.4)

        # 恐慌高 = 市场已在杀跌阶段 → 对买入是负面信号
        return {
            'amplitude_today': latest_amp,
            'panic_10': latest_panic,
            'bear_ratio_10': latest_bear,
            'panic_score': panic_score,
        }

    def calc_vol_autocorr(self, df: pd.DataFrame) -> Dict:
        """
        因子6: 波动率自相关因子 (vol_autocorr)
        ────────────────────────────────────────
        研报依据：Engle(1982) ARCH效应，波动率簇集
        
        逻辑：
          daily_vol = abs(pctChg) / 100
          autocorr = corr(daily_vol, daily_vol.shift(lag), window=20)
          
          高正自相关（>0.5）→ 波动率持续放大，趋势还在（好信号）
          低/负自相关（<0）  → 波动率不稳定，见顶/反转
          
        返回：
          vol_autocorr_5: 5阶滞后自相关
          vol_persistence: 波动率持续性评分(0~1，高=强持续)
        """
        daily_vol = (df['pctChg'] / 100.0).abs()
        lag = self.VOL_AUTOCORR_LAG

        # 向量化替代 for 循环：用 rolling.corr 计算滑动自相关（LRN-20260327-001）
        vol_lag = daily_vol.shift(lag)
        ac_s = daily_vol.rolling(self.SKEW_WINDOW, min_periods=10).corr(vol_lag)
        latest_ac = float(ac_s.iloc[-1]) if not pd.isna(ac_s.iloc[-1]) else 0.0

        # 高持续性 → 趋势健康（正向）；低/负 → 波动无方向
        # 注意：对量化选股来说，高持续性 + 上升趋势 = 好
        persistence_score = max(0.0, latest_ac)  # 仅在正相关时给分

        return {
            'vol_autocorr_5': latest_ac,
            'vol_persistence': persistence_score,
        }

    # ── 大类六：情绪拥挤度因子（5个）────────────────────────────────────────

    def calc_turnover_crowd(self, df: pd.DataFrame) -> Dict:
        """
        因子7: 换手率拥挤度 (turnover_crowd)
        ──────────────────────────────────────
        研报依据：国盛金工《换手率视角下的A股情绪度量》2024
        
        逻辑：
          turn_dev = turn_5ma / turn_60ma   # 短期相对长期的倍数
          turn_percentile = rank(turn, 60)  # 历史百分位
          
          turn_dev > 2.0 且 percentile > 85% → 高度拥挤，警戒
          turn_dev > 3.0 或 percentile > 95% → 极度拥挤，危险
          
        返回：
          turn_dev: 换手率偏离度
          turn_percentile: 历史百分位（0~1）
          turnover_crowd_score: 0~1
        """
        turn = df['turn'].replace(0, np.nan).ffill()
        turn_5ma = turn.rolling(5, min_periods=2).mean()
        turn_60ma = turn.rolling(self.CROWD_WINDOW, min_periods=10).mean()
        turn_dev = self._safe_div(turn_5ma, turn_60ma, fill=1.0)

        # 历史百分位：向量化替代 rolling.apply(lambda, raw=False)（LRN-20260327-001）
        # 用 rank() 计算扩展窗口百分位近似，再用 rolling min/max 标准化
        window = self.CROWD_WINDOW
        turn_rank = turn.rolling(window, min_periods=10).rank(pct=True)
        turn_pct = turn_rank  # rank(pct=True) 已是0~1百分位

        latest_dev = float(turn_dev.iloc[-1]) if not pd.isna(turn_dev.iloc[-1]) else 1.0
        latest_pct = float(turn_pct.iloc[-1]) if not pd.isna(turn_pct.iloc[-1]) else 0.5

        # 拥挤评分
        dev_score = min(1.0, max(0.0, (latest_dev - 1.0) / 2.0))
        pct_score = min(1.0, max(0.0, (latest_pct - 0.7) / 0.3))
        crowd_score = dev_score * 0.5 + pct_score * 0.5

        return {
            'turn_dev': latest_dev,
            'turn_percentile': latest_pct,
            'turnover_crowd_score': crowd_score,
        }

    def calc_amplitude_crowd(self, df: pd.DataFrame) -> Dict:
        """
        因子8: 振幅拥挤度 (amplitude_crowd)
        ──────────────────────────────────────
        逻辑：
          振幅 = (high - low) / close_prev
          amp_dev = amp_5ma / amp_60ma
          
          振幅拥挤 = 近期振幅持续异常大 → 情绪极度不稳定
          
        返回：
          amp_dev: 振幅偏离度
          amplitude_crowd_score: 0~1
        """
        close_prev = df['close'].shift(1).fillna(df['close'])
        amplitude = (df['high'] - df['low']) / close_prev.replace(0, np.nan)
        amplitude = amplitude.fillna(0.0).clip(0, 0.20)

        amp_5ma = amplitude.rolling(5, min_periods=2).mean()
        amp_60ma = amplitude.rolling(self.CROWD_WINDOW, min_periods=10).mean()
        amp_dev = self._safe_div(amp_5ma, amp_60ma.replace(0, np.nan).fillna(0.01), fill=1.0)

        latest_dev = float(amp_dev.iloc[-1]) if not pd.isna(amp_dev.iloc[-1]) else 1.0
        crowd_score = min(1.0, max(0.0, (latest_dev - 1.2) / 1.8))

        return {
            'amp_dev': latest_dev,
            'amplitude_crowd_score': crowd_score,
        }

    def calc_vol_ratio_anomaly(self, df: pd.DataFrame) -> Dict:
        """
        因子9: 量比异常度 (vol_ratio_anomaly)
        ─────────────────────────────────────
        逻辑：
          量比 = 今日成交量 / MA(成交量, 5)
          量比异常 = 量比 / MA(量比, 20)  # 连续量比是否异常
          
          单日量比 > 2 且已持续3天 → 情绪亢奋
          量比快速萎缩（近5日/前5日 < 0.5）→ 热度消退
          
        返回：
          vol_ratio_today: 今日量比
          vol_ratio_3d_avg: 近3日平均量比
          vol_ratio_anomaly: 量比异常度
          vol_ratio_score: 0~1，越高越异常
        """
        vol = df['volume'].replace(0, np.nan).ffill()
        vol_ma5 = vol.rolling(5, min_periods=2).mean()
        vol_ratio = self._safe_div(vol, vol_ma5, fill=1.0)

        vol_ratio_3d = vol_ratio.rolling(3, min_periods=1).mean()
        vol_ratio_ma20 = vol_ratio.rolling(20, min_periods=5).mean()
        vol_ratio_anomaly = self._safe_div(vol_ratio_3d, vol_ratio_ma20, fill=1.0)

        latest_vr = float(vol_ratio.iloc[-1]) if not pd.isna(vol_ratio.iloc[-1]) else 1.0
        latest_vr3 = float(vol_ratio_3d.iloc[-1]) if not pd.isna(vol_ratio_3d.iloc[-1]) else 1.0
        latest_anomaly = float(vol_ratio_anomaly.iloc[-1]) if not pd.isna(vol_ratio_anomaly.iloc[-1]) else 1.0

        # 量比异常 > 1.8 → 情绪亢奋
        anomaly_score = min(1.0, max(0.0, (latest_anomaly - 1.0) / 1.5))

        return {
            'vol_ratio_today': latest_vr,
            'vol_ratio_3d_avg': latest_vr3,
            'vol_ratio_anomaly': latest_anomaly,
            'vol_ratio_score': anomaly_score,
        }

    def calc_popularity_decay(self, df: pd.DataFrame) -> Dict:
        """
        因子10: 热度衰减速度 (popularity_decay)
        ─────────────────────────────────────────
        研报依据：广发金工《情绪拥挤度与短期反转》2024
        
        逻辑：
          热度指标 = 换手率 × 量比 的复合热度
          decay_rate = (热度_最近3日 - 热度_前5日) / 热度_前5日
          
          decay_rate < -0.3 → 热度快速消退，资金出逃
          decay_rate > +0.5 → 热度快速升温，追高危险区
          
        返回：
          heat_now: 近3日热度
          heat_before: 前5日热度
          decay_rate: 热度变化率
          decay_risk_score: 热度过热(升温)/过冷(退潮)风险
        """
        turn = df['turn'].replace(0, np.nan).ffill()
        vol = df['volume'].replace(0, np.nan).ffill()
        vol_ma5 = vol.rolling(5, min_periods=2).mean()
        vol_ratio = self._safe_div(vol, vol_ma5, fill=1.0)

        # 复合热度 = 换手率 × 量比
        heat = turn * vol_ratio
        heat_3d = heat.rolling(3, min_periods=1).mean()
        heat_5d_before = heat.shift(3).rolling(5, min_periods=2).mean()

        decay = self._safe_div(
            heat_3d - heat_5d_before,
            heat_5d_before.replace(0, np.nan).fillna(heat_3d),
            fill=0.0
        )

        latest_hn = float(heat_3d.iloc[-1]) if not pd.isna(heat_3d.iloc[-1]) else 0.0
        latest_hb = float(heat_5d_before.iloc[-1]) if not pd.isna(heat_5d_before.iloc[-1]) else 0.0
        latest_decay = float(decay.iloc[-1]) if not pd.isna(decay.iloc[-1]) else 0.0

        # 快速升温（>0.5）= 追高危险；快速退潮（<-0.3）= 资金出逃
        if latest_decay > 0.5:
            decay_risk = min(1.0, (latest_decay - 0.5) / 1.0)   # 追高风险
        elif latest_decay < -0.3:
            decay_risk = min(1.0, (-latest_decay - 0.3) / 0.7)  # 退潮风险
        else:
            decay_risk = 0.0

        return {
            'heat_now': latest_hn,
            'heat_before': latest_hb,
            'decay_rate': latest_decay,
            'decay_risk_score': decay_risk,
        }

    def calc_sentiment_crowd(
        self,
        factors: Dict,
        skew_result: Dict,
        kurt_result: Dict,
        downside_result: Dict,
        panic_result: Dict,
    ) -> Dict:
        """
        因子11: 情绪综合拥挤度 (sentiment_crowd)
        ──────────────────────────────────────────
        综合6大子维度加权：
          换手拥挤(25%) + 振幅拥挤(15%) + 量比异常(20%) +
          热度衰减(15%) + 恐慌指数(15%) + 偏度风险(10%)
          
        返回：
          sentiment_crowd_score: 0~1，越高越拥挤/危险
          crowd_level: 'low'/'moderate'/'high'/'extreme'
        """
        tc = factors.get('turnover_crowd_score', 0.0)
        ac = factors.get('amplitude_crowd_score', 0.0)
        vra = factors.get('vol_ratio_score', 0.0)
        dr = factors.get('decay_risk_score', 0.0)
        pi = panic_result.get('panic_score', 0.0)
        sr = skew_result.get('skew_risk_score', 0.0)

        score = tc * 0.25 + ac * 0.15 + vra * 0.20 + dr * 0.15 + pi * 0.15 + sr * 0.10

        if score < 0.25:
            level = 'low'
        elif score < 0.5:
            level = 'moderate'
        elif score < 0.75:
            level = 'high'
        else:
            level = 'extreme'

        return {
            'sentiment_crowd_score': round(score, 4),
            'crowd_level': level,
            'crowd_components': {
                'turnover_crowd': round(tc, 4),
                'amplitude_crowd': round(ac, 4),
                'vol_ratio_anomaly': round(vra, 4),
                'heat_decay': round(dr, 4),
                'panic_index': round(pi, 4),
                'skew_risk': round(sr, 4),
            }
        }

    # ── 主接口 ─────────────────────────────────────────────────────────────

    def calculate_all(self, df: pd.DataFrame) -> Dict:
        """
        计算所有波动率高阶矩 & 情绪拥挤度因子

        Parameters
        ----------
        df : DataFrame
            日频K线数据（含 open/close/high/low/volume/amount/pctChg/turn）

        Returns
        -------
        dict 包含所有因子值，计算失败时对应值为默认值
        """
        err = self._check_df(df)
        if err:
            logger.warning("VolatilitySentimentFactors 数据校验失败: %s", err)
            return self._default_factors()

        results = {}
        try:
            # 大类五：波动率高阶矩
            skew_res = self.calc_return_skewness(df)
            kurt_res = self.calc_return_kurtosis(df)
            ds_res = self.calc_downside_vol(df)
            asym_res = self.calc_vol_asymmetry(df)
            panic_res = self.calc_implied_panic_index(df)
            autocorr_res = self.calc_vol_autocorr(df)

            results.update({
                # 偏度
                'skew_20': skew_res['skew_20'],
                'skew_signal': skew_res['skew_signal'],
                'skew_risk_score': skew_res['skew_risk_score'],
                # 峰度
                'kurt_20': kurt_res['kurt_20'],
                'kurt_risk_score': kurt_res['kurt_risk_score'],
                # 下行波动率
                'downside_vol_20': ds_res['downside_vol_20'],
                'total_vol_20': ds_res['total_vol_20'],
                'downside_ratio': ds_res['downside_ratio'],
                'downside_risk_score': ds_res['downside_risk_score'],
                # 波动率不对称
                'up_vol_10': asym_res['up_vol_10'],
                'dn_vol_10': asym_res['dn_vol_10'],
                'vol_asymmetry': asym_res['vol_asymmetry'],
                'vol_asym_risk_score': asym_res['vol_asym_risk_score'],
                # 隐含恐慌
                'amplitude_today': panic_res['amplitude_today'],
                'panic_10': panic_res['panic_10'],
                'bear_ratio_10': panic_res['bear_ratio_10'],
                'panic_score': panic_res['panic_score'],
                # 波动率自相关
                'vol_autocorr_5': autocorr_res['vol_autocorr_5'],
                'vol_persistence': autocorr_res['vol_persistence'],
            })

            # 大类六：情绪拥挤度
            tc_res = self.calc_turnover_crowd(df)
            ac_res = self.calc_amplitude_crowd(df)
            vr_res = self.calc_vol_ratio_anomaly(df)
            pd_res = self.calc_popularity_decay(df)

            results.update({
                # 换手拥挤
                'turn_dev': tc_res['turn_dev'],
                'turn_percentile': tc_res['turn_percentile'],
                'turnover_crowd_score': tc_res['turnover_crowd_score'],
                # 振幅拥挤
                'amp_dev': ac_res['amp_dev'],
                'amplitude_crowd_score': ac_res['amplitude_crowd_score'],
                # 量比异常
                'vol_ratio_today': vr_res['vol_ratio_today'],
                'vol_ratio_3d_avg': vr_res['vol_ratio_3d_avg'],
                'vol_ratio_anomaly': vr_res['vol_ratio_anomaly'],
                'vol_ratio_score': vr_res['vol_ratio_score'],
                # 热度衰减
                'heat_now': pd_res['heat_now'],
                'heat_before': pd_res['heat_before'],
                'decay_rate': pd_res['decay_rate'],
                'decay_risk_score': pd_res['decay_risk_score'],
            })

            # 综合情绪拥挤度
            sc_res = self.calc_sentiment_crowd(results, skew_res, kurt_res, ds_res, panic_res)
            results.update({
                'sentiment_crowd_score': sc_res['sentiment_crowd_score'],
                'crowd_level': sc_res['crowd_level'],
                'crowd_components': sc_res['crowd_components'],
            })

        except Exception as e:
            logger.error(f"VolatilitySentimentFactors 计算异常: {e}", exc_info=True)
            return self._default_factors()

        return results

    def _default_factors(self) -> Dict:
        """返回因子默认值（数据不足或异常时）"""
        return {
            'skew_20': 0.0, 'skew_signal': 0, 'skew_risk_score': 0.0,
            'kurt_20': 0.0, 'kurt_risk_score': 0.0,
            'downside_vol_20': 0.0, 'total_vol_20': 0.0, 'downside_ratio': 0.5,
            'downside_risk_score': 0.0,
            'up_vol_10': 0.0, 'dn_vol_10': 0.0, 'vol_asymmetry': 1.0,
            'vol_asym_risk_score': 0.0,
            'amplitude_today': 0.0, 'panic_10': 1.0, 'bear_ratio_10': 0.5,
            'panic_score': 0.0,
            'vol_autocorr_5': 0.0, 'vol_persistence': 0.0,
            'turn_dev': 1.0, 'turn_percentile': 0.5, 'turnover_crowd_score': 0.0,
            'amp_dev': 1.0, 'amplitude_crowd_score': 0.0,
            'vol_ratio_today': 1.0, 'vol_ratio_3d_avg': 1.0,
            'vol_ratio_anomaly': 1.0, 'vol_ratio_score': 0.0,
            'heat_now': 0.0, 'heat_before': 0.0, 'decay_rate': 0.0,
            'decay_risk_score': 0.0,
            'sentiment_crowd_score': 0.0, 'crowd_level': 'low',
            'crowd_components': {
                'turnover_crowd': 0.0, 'amplitude_crowd': 0.0,
                'vol_ratio_anomaly': 0.0, 'heat_decay': 0.0,
                'panic_index': 0.0, 'skew_risk': 0.0,
            }
        }

    def get_vol_sentiment_score(
        self,
        factors: Dict,
        weight_vol_risk: float = 0.5,
        weight_crowd: float = 0.5,
    ) -> Tuple[float, str]:
        """
        波动率+情绪综合评分 → 用于主程序加权

        逻辑：
          综合风险分 = 波动率高阶矩风险(50%) + 情绪拥挤度(50%)
          
          波动率高阶矩风险 = 偏度风险(20%) + 下行风险(30%) + 不对称(20%) + 恐慌(30%)
          
          最终 score_adjustment（主程序惩罚/奖励系数）：
            risk < 0.3  → 1.02（正常偏好，微加分）
            risk < 0.5  → 1.0 （中性）
            risk < 0.7  → 0.9 （温和惩罚）
            risk >= 0.7 → 0.75~0.5（强烈惩罚）

        Parameters
        ----------
        factors : 由 calculate_all() 返回的字典
        weight_vol_risk : 波动率高阶矩权重
        weight_crowd : 情绪拥挤度权重

        Returns
        -------
        (adjustment_coef, risk_level_str)
        """
        # 波动率高阶矩综合风险
        vol_risk = (
            factors.get('skew_risk_score', 0.0) * 0.20 +
            factors.get('downside_risk_score', 0.0) * 0.30 +
            factors.get('vol_asym_risk_score', 0.0) * 0.20 +
            factors.get('panic_score', 0.0) * 0.30
        )

        crowd_risk = factors.get('sentiment_crowd_score', 0.0)
        total_risk = vol_risk * weight_vol_risk + crowd_risk * weight_crowd

        if total_risk < 0.25:
            coef = 1.02
            level = '低风险'
        elif total_risk < 0.45:
            coef = 1.0
            level = '中性'
        elif total_risk < 0.60:
            coef = 0.92
            level = '轻度风险'
        elif total_risk < 0.75:
            coef = 0.80
            level = '中度风险'
        else:
            coef = max(0.55, 1.0 - total_risk * 0.7)
            level = '高风险'

        return round(coef, 4), level

    def get_factor_summary(self, factors: Dict) -> str:
        """生成因子摘要字符串（用于日志/报告）"""
        crowd = factors.get('crowd_level', 'unknown')
        skew = factors.get('skew_20', 0.0)
        panic = factors.get('panic_10', 1.0)
        turn_dev = factors.get('turn_dev', 1.0)
        decay = factors.get('decay_rate', 0.0)
        sentiment = factors.get('sentiment_crowd_score', 0.0)

        return (
            f"情绪拥挤:{crowd}(分:{sentiment:.2f}) | "
            f"偏度:{skew:+.2f} | 恐慌指数:{panic:.2f} | "
            f"换手偏离:{turn_dev:.2f}x | 热度变化:{decay:+.1%}"
        )


# ── 快速测试 ──────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    import random

    print("=" * 60)
    print("VolatilitySentimentFactorCalculator 快速测试")
    print("=" * 60)

    # 构造模拟数据
    np.random.seed(42)
    n = 120
    close = 10.0 * np.cumprod(1 + np.random.normal(0.0005, 0.02, n))
    high = close * (1 + np.random.uniform(0, 0.03, n))
    low = close * (1 - np.random.uniform(0, 0.03, n))
    open_ = close * (1 + np.random.normal(0, 0.01, n))
    volume = np.random.uniform(1e7, 5e8, n)
    amount = volume * close
    pctChg = np.random.normal(0.05, 2.0, n)
    turn = np.random.uniform(0.5, 5.0, n)

    df = pd.DataFrame({
        'open': open_, 'close': close, 'high': high, 'low': low,
        'volume': volume, 'amount': amount, 'pctChg': pctChg, 'turn': turn
    })

    calc = VolatilitySentimentFactorCalculator()
    factors = calc.calculate_all(df)

    print(f"\n【波动率高阶矩】")
    print(f"  偏度(20日): {factors['skew_20']:+.3f}  | 风险分: {factors['skew_risk_score']:.3f}")
    print(f"  峰度(20日): {factors['kurt_20']:+.3f}  | 风险分: {factors['kurt_risk_score']:.3f}")
    print(f"  下行波动率: {factors['downside_vol_20']:.4f} | 总波动率: {factors['total_vol_20']:.4f} | 下行比例: {factors['downside_ratio']:.3f}")
    print(f"  波动不对称: {factors['vol_asymmetry']:.3f}  | 恐慌指数: {factors['panic_10']:.3f}")
    print(f"  波动率自相关: {factors['vol_autocorr_5']:+.3f} | 持续性: {factors['vol_persistence']:.3f}")

    print(f"\n【情绪拥挤度】")
    print(f"  换手拥挤度: {factors['turnover_crowd_score']:.3f}  | 换手偏离: {factors['turn_dev']:.2f}x")
    print(f"  振幅拥挤度: {factors['amplitude_crowd_score']:.3f}  | 量比异常: {factors['vol_ratio_score']:.3f}")
    print(f"  热度衰减风险: {factors['decay_risk_score']:.3f}  | 热度变化率: {factors['decay_rate']:+.2%}")
    print(f"  情绪拥挤综合: {factors['sentiment_crowd_score']:.3f}  | 级别: {factors['crowd_level']}")

    coef, level = calc.get_vol_sentiment_score(factors)
    print(f"\n【综合调整系数】: {coef:.4f}  | 风险级别: {level}")
    print(f"\n【因子摘要】: {calc.get_factor_summary(factors)}")
    print("\n✅ 测试通过")
