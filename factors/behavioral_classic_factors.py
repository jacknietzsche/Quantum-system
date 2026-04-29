#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
行为金融学因子 + 经典多因子模型
=======================================
整合以下因子：

一、行为金融学因子（处置效应变体）
1. 资本利得突出量（CGO）- 负向
2. V型处置效应因子（VNSP）- 负向  
3. 筹码分布处置效应因子（CDE）- 负向
4. 处置效应变化因子（ΔDE）- 正向（创新）

二、经典多因子模型（长期有效）
1. 质量因子（Quality）- 正向
2. 动量因子（Momentum）- 正向
3. 长期反转因子（LT_REV）- 负向
4. 价值因子（Value）- 正向（需基本面数据）
5. 低波因子（Low Volatility）- 正向
6. 盈利因子（Profitability）- 正向（需基本面数据）

使用建议：
- 计算前进行行业中性化和市值中性化处理
- 行为因子与传统因子组合使用，降低单一因子周期性失效风险
- 最终合成：FinalScore = ∑ w_k * z(Factor_k)
"""

import warnings
warnings.filterwarnings('ignore')

import numpy as np
import pandas as pd
from typing import Dict, Optional, Tuple, List
import logging
from scipy.stats import zscore

logger = logging.getLogger("behavioral_classic_factors")


class BehavioralClassicFactorCalculator:
    """
    行为金融学 + 经典多因子计算器
    
    因子分类：
    - 正向因子 (越高越好): Quality, Momentum, Value, LowVol, Profitability, ΔDE
    - 负向因子 (越低越好): CGO, VNSP, CDE, LT_REV
    
    计算流程：
    1. 计算原始因子值
    2. 标准化 (z-score)
    3. 合并正负向因子得到综合评分
    """
    
    def __init__(self):
        # 参考价格窗口
        self.REF_WINDOW = 20
        # CGO计算窗口
        self.CGO_WINDOW = 60
        # VNSP计算参数
        self.VNSP_PROFIT_THRESH = 0.10
        self.VNSP_LOSS_THRESH = -0.10
        # CDE近似参数
        self.CDE_WINDOW = 30
        # ΔDE计算窗口
        self.DDE_WINDOW = 20
        # 动量/反转计算窗口
        self.MOMENTUM_WINDOW = 252  # 12个月，交易日约252天
        self.LT_REV_WINDOW = 756    # 36个月，约756交易日
        self.SKIP_RECENT = 21       # 跳过最近1个月
    
    def check_df(self, df):
        """检查数据完整性"""
        required = ['open', 'close', 'high', 'low', 'volume', 'amount', 'pctChg']
        missing = [c for c in required if c not in df.columns]
        if missing:
            return f"missing: {missing}"
        if len(df) < max(self.CGO_WINDOW, self.LT_REV_WINDOW + self.SKIP_RECENT):
            return f"need at least {self.LT_REV_WINDOW + self.SKIP_RECENT} rows, got {len(df)}"
        return None
    
    def calculate_reference_price(self, df):
        """
        计算参考价格（历史换手率加权平均成本）
        公式：R_i,t = Σ(p_j * turn_j) / Σ(turn_j), j = t-59 to t
        其中 p_j 为收盘价，turn_j 为换手率
        """
        if 'turn' not in df.columns:
            # 估算换手率 = amount / (close * 1e8) * 100
            df['turn'] = df['amount'] / (df['close'] * 1e8) * 100
        
        close = df['close'].astype(float)
        turn = df['turn'].replace(0, np.nan).fillna(method='ffill').astype(float)
        
        # 加权平均
        weighted_price = close * turn
        ref_price = weighted_price.rolling(self.CGO_WINDOW, min_periods=20).sum() / \
                    turn.rolling(self.CGO_WINDOW, min_periods=20).sum()
        
        return ref_price.fillna(method='ffill')
    
    def calculate_cgo(self, df, ref_price=None):
        """
        1. 资本利得突出量（CGO）- 负向因子
        公式: CGO_{i,t} = (P_{i,t} - R_{i,t}) / P_{i,t}
        CGO越高 → 未来收益越低
        """
        if ref_price is None:
            ref_price = self.calculate_reference_price(df)
        
        close = df['close']
        latest_close = float(close.iloc[-1])
        latest_ref = float(ref_price.iloc[-1])
        
        if latest_close > 0.01:
            cgo_raw = (latest_close - latest_ref) / latest_close
        else:
            cgo_raw = 0.0
        
        # 历史序列计算
        cgo_series = (close - ref_price) / close
        cgo_series = cgo_series.replace([np.inf, -np.inf], np.nan).fillna(0)
        
        # 标准化为负向因子（数值越高风险越大）
        # 这里使用最近20日的平均值
        if len(cgo_series) >= 20:
            cgo_20d = float(cgo_series.tail(20).mean())
        else:
            cgo_20d = float(cgo_series.mean())
        
        return {
            'cgo_raw': round(float(cgo_raw), 6),
            'cgo_20d': round(cgo_20d, 6),
            'ref_price': round(latest_ref, 4),
            'current_price': round(latest_close, 4),
            'signal': 'high_risk' if cgo_20d > 0.15 else 'moderate_risk' if cgo_20d > 0.05 else 'low_risk'
        }
    
    def calculate_vnsp(self, df):
        """
        2. V型处置效应因子（VNSP）- 负向
        简化公式: VNSP = max(0, g) * w_g + min(0, l) * w_l
        其中 g 为盈利幅度，l 为亏损幅度
        w_g = 0.6, w_l = 0.4 使函数呈V型
        """
        close = df['close']
        ref_price = self.calculate_reference_price(df)
        
        # 当前盈利/亏损幅度
        latest_close = float(close.iloc[-1])
        latest_ref = float(ref_price.iloc[-1])
        gain_ratio = (latest_close - latest_ref) / latest_ref if latest_ref > 0.01 else 0.0
        
        # 盈利幅度
        g = max(0, gain_ratio)
        # 亏损幅度（取绝对值）
        l = min(0, gain_ratio)
        
        # V型权重
        w_g = 0.6  # 盈利部分权重
        w_l = 0.4  # 亏损部分权重
        
        vnsp_raw = g * w_g + abs(l) * w_l
        
        # 历史序列
        gain_series = (close - ref_price) / ref_price
        g_series = np.maximum(gain_series, 0)
        l_series = np.minimum(gain_series, 0)
        vnsp_series = g_series * w_g + np.abs(l_series) * w_l
        
        if len(vnsp_series) >= 20:
            vnsp_20d = float(vnsp_series.tail(20).mean())
        else:
            vnsp_20d = float(vnsp_series.mean())
        
        return {
            'vnsp_raw': round(float(vnsp_raw), 6),
            'vnsp_20d': round(vnsp_20d, 6),
            'gain_ratio': round(float(gain_ratio), 6),
            'is_profit': gain_ratio > 0,
            'signal': 'extreme_vnsp' if vnsp_20d > 0.20 else 'high_vnsp' if vnsp_20d > 0.10 else 'moderate_vnsp'
        }
    
    def calculate_cde(self, df):
        """
        3. 筹码分布处置效应因子（CDE）- 负向
        近似计算：基于历史成交量和价格计算加权成本分布
        简化公式: CDE = Σ(Volume(p) * (P_t - p)) / Σ(Volume(p))
        """
        close = df['close']
        volume = df['volume']
        
        if len(df) < self.CDE_WINDOW:
            return {'cde_raw': 0, 'cde_20d': 0, 'signal': 'insufficient_data'}
        
        # 取最近窗口数据
        recent_close = close.iloc[-self.CDE_WINDOW:]
        recent_volume = volume.iloc[-self.CDE_WINDOW:]
        
        # 当前价格
        current_price = float(close.iloc[-1])
        
        # 计算加权成本偏离度
        price_diff = current_price - recent_close
        weighted_diff = (price_diff * recent_volume).sum() / recent_volume.sum()
        
        # 标准化
        cde_raw = float(weighted_diff / current_price if current_price > 0.01 else 0)
        
        # 历史序列（滑动窗口）
        cde_values = []
        for i in range(len(df) - self.CDE_WINDOW + 1):
            window_close = close.iloc[i:i+self.CDE_WINDOW]
            window_volume = volume.iloc[i:i+self.CDE_WINDOW]
            window_current = float(window_close.iloc[-1])
            price_diff_window = window_current - window_close
            weighted = (price_diff_window * window_volume).sum() / window_volume.sum()
            cde_val = weighted / window_current if window_current > 0.01 else 0
            cde_values.append(cde_val)
        
        cde_series = pd.Series(cde_values)
        if len(cde_series) >= 20:
            cde_20d = float(cde_series.tail(20).mean())
        else:
            cde_20d = float(cde_series.mean()) if len(cde_series) > 0 else 0
        
        return {
            'cde_raw': round(float(cde_raw), 6),
            'cde_20d': round(cde_20d, 6),
            'signal': 'high_sell_pressure' if cde_20d > 0.08 else 'moderate_sell_pressure'
        }
    
    def calculate_dde(self, df):
        """
        4. 处置效应变化因子（ΔDE）- 正向
        计算处置效应不对称程度的一阶差分
        简化: 基于CGO的变化率
        ΔDE_t = CGO_t - CGO_{t-1}
        """
        cgo_result = self.calculate_cgo(df)
        cgo_series = (df['close'] - self.calculate_reference_price(df)) / df['close']
        cgo_series = cgo_series.replace([np.inf, -np.inf], np.nan).fillna(0)
        
        if len(cgo_series) < 2:
            return {'dde_raw': 0, 'dde_20d': 0, 'signal': 'insufficient_data'}
        
        # 一阶差分
        dde_series = cgo_series.diff()
        
        # 最近变化
        dde_raw = float(dde_series.iloc[-1]) if not np.isnan(dde_series.iloc[-1]) else 0
        
        # 最近窗口平均
        if len(dde_series) >= self.DDE_WINDOW:
            dde_20d = float(dde_series.tail(self.DDE_WINDOW).mean())
        else:
            dde_20d = float(dde_series.mean())
        
        return {
            'dde_raw': round(dde_raw, 6),
            'dde_20d': round(dde_20d, 6),
            'signal': 'positive_dde' if dde_20d > 0.01 else 'negative_dde' if dde_20d < -0.01 else 'neutral_dde'
        }
    
    def calculate_momentum(self, df):
        """
        经典动量因子（Momentum）- 正向
        MOM_{i,t} = P_{i,t} / P_{i,t-252} - 1
        跳过最近21个交易日（约1个月）
        """
        if len(df) < self.MOMENTUM_WINDOW + self.SKIP_RECENT:
            return {'momentum_raw': 0, 'signal': 'insufficient_data'}
        
        close = df['close']
        past_idx = -(self.MOMENTUM_WINDOW + self.SKIP_RECENT)
        recent_idx = -self.SKIP_RECENT
        
        past_price = float(close.iloc[past_idx])
        recent_price = float(close.iloc[recent_idx])
        
        momentum_raw = recent_price / past_price - 1 if past_price > 0.01 else 0
        
        return {
            'momentum_raw': round(float(momentum_raw), 6),
            'signal': 'strong_momentum' if momentum_raw > 0.20 else 'weak_momentum' if momentum_raw > 0 else 'negative_momentum'
        }
    
    def calculate_lt_reversal(self, df):
        """
        长期反转因子（LT_REV）- 负向
        LT_REV_{i,t} = P_{i,t} / P_{i,t-756} - 1
        跳过最近21个交易日
        """
        if len(df) < self.LT_REV_WINDOW + self.SKIP_RECENT:
            return {'lt_rev_raw': 0, 'signal': 'insufficient_data'}
        
        close = df['close']
        past_idx = -(self.LT_REV_WINDOW + self.SKIP_RECENT)
        recent_idx = -self.SKIP_RECENT
        
        past_price = float(close.iloc[past_idx])
        recent_price = float(close.iloc[recent_idx])
        
        lt_rev_raw = recent_price / past_price - 1 if past_price > 0.01 else 0
        
        return {
            'lt_rev_raw': round(float(lt_rev_raw), 6),
            'signal': 'strong_reversal' if lt_rev_raw > 0.30 else 'weak_reversal' if lt_rev_raw > 0.15 else 'neutral'
        }
    
    def calculate_quality_approx(self, df):
        """
        质量因子近似（基于技术指标）- 正向
        简化: Q = z(收益稳定性) + z(趋势强度) - z(波动率)
        """
        if len(df) < 60:
            return {'quality_score': 0.5, 'signal': 'insufficient_data'}
        
        close = df['close']
        returns = df['pctChg'] / 100.0
        
        # 1. 收益稳定性（60日收益标准差的倒数）
        if len(returns) >= 60:
            vol_60d = returns.tail(60).std()
            stability = 1.0 / (vol_60d + 0.01) if vol_60d > 0 else 10.0
        else:
            stability = 5.0
        
        # 2. 趋势强度（MA5/MA60比率）
        ma5 = close.tail(5).mean()
        ma60 = close.tail(60).mean()
        trend_strength = ma5 / ma60 - 1 if ma60 > 0.01 else 0
        
        # 3. 回撤控制（最近20日最大回撤的负值）
        if len(close) >= 20:
            window_close = close.tail(20)
            cummax = window_close.cummax()
            drawdown = (window_close - cummax) / cummax
            max_dd = float(drawdown.min()) if not drawdown.empty else 0
            dd_control = -max_dd  # 回撤越小越好
        else:
            dd_control = 0
        
        # 组合质量评分（0-1范围）
        quality_score = (
            np.clip(stability / 20.0, 0, 1) * 0.4 +
            np.clip(trend_strength + 0.5, 0, 1) * 0.4 + 
            np.clip(dd_control + 0.5, 0, 1) * 0.2
        )
        
        return {
            'quality_score': round(float(quality_score), 4),
            'stability': round(float(stability), 4),
            'trend_strength': round(float(trend_strength), 6),
            'signal': 'high_quality' if quality_score > 0.7 else 'medium_quality' if quality_score > 0.5 else 'low_quality'
        }
    
    def calculate_low_volatility(self, df):
        """
        低波动因子（Low Volatility）- 正向
        LowVol_{i,t} = -σ_{i, t-252}
        波动率越低得分越高
        """
        if len(df) < self.MOMENTUM_WINDOW:
            return {'low_vol_score': 0.5, 'signal': 'insufficient_data'}
        
        returns = df['pctChg'] / 100.0
        vol_252d = returns.tail(self.MOMENTUM_WINDOW).std()
        
        # 波动率越低越好，映射到0-1分数
        # 典型A股年化波动率约20-40%，映射: 20%→1.0, 40%→0.5, 60%→0.0
        if vol_252d > 0:
            low_vol_score = np.clip(1.0 - (vol_252d - 0.20) / 0.40, 0, 1)
        else:
            low_vol_score = 0.5
        
        return {
            'low_vol_score': round(float(low_vol_score), 4),
            'volatility_252d': round(float(vol_252d), 6),
            'signal': 'very_low_vol' if low_vol_score > 0.8 else 'low_vol' if low_vol_score > 0.6 else 'high_vol'
        }
    
    def calculate_all(self, df):
        """
        计算所有因子
        """
        err = self.check_df(df)
        if err:
            logger.warning("BehavioralClassic check failed: %s", err)
            return self._defaults()
        
        try:
            # 计算所有因子
            cgo = self.calculate_cgo(df)
            vnsp = self.calculate_vnsp(df)
            cde = self.calculate_cde(df)
            dde = self.calculate_dde(df)
            momentum = self.calculate_momentum(df)
            lt_rev = self.calculate_lt_reversal(df)
            quality = self.calculate_quality_approx(df)
            low_vol = self.calculate_low_volatility(df)
            
            # 汇总所有因子值（用于标准化）
            factor_values = {
                'cgo': cgo['cgo_20d'],           # 负向
                'vnsp': vnsp['vnsp_20d'],        # 负向
                'cde': cde['cde_20d'],           # 负向
                'dde': dde['dde_20d'],           # 正向
                'momentum': momentum.get('momentum_raw', 0),  # 正向
                'lt_rev': lt_rev.get('lt_rev_raw', 0),        # 负向
                'quality': quality['quality_score'],          # 正向
                'low_vol': low_vol['low_vol_score'],          # 正向
            }
            
            # 标准化因子值（z-score）
            # 注意：这里使用固定均值和标准差近似，实际应使用横截面数据
            factor_scores = {}
            for name, value in factor_values.items():
                # 简化标准化：映射到0-1范围
                if name in ['cgo', 'vnsp', 'cde', 'lt_rev']:  # 负向因子
                    # 值越小越好，反转处理
                    factor_scores[name] = np.clip(1.0 - abs(value) / 0.3, 0, 1)
                else:  # 正向因子
                    if name == 'dde':
                        factor_scores[name] = np.clip(0.5 + value * 10, 0, 1)
                    elif name == 'momentum':
                        factor_scores[name] = np.clip(0.5 + value * 2, 0, 1)
                    else:  # quality, low_vol
                        factor_scores[name] = value
            
            # 综合评分（加权平均）
            # 权重分配：行为因子40%，经典因子60%
            weights = {
                'cgo': 0.10,     # 负向
                'vnsp': 0.10,    # 负向
                'cde': 0.10,     # 负向
                'dde': 0.10,     # 正向（创新）
                'momentum': 0.15,  # 正向
                'lt_rev': 0.10,    # 负向
                'quality': 0.20,    # 正向
                'low_vol': 0.15,    # 正向
            }
            
            composite_score = sum(factor_scores.get(name, 0.5) * weight 
                                 for name, weight in weights.items())
            
            # 风险信号汇总
            risk_signals = []
            if cgo['signal'] == 'high_risk':
                risk_signals.append('high_cgo_risk')
            if vnsp['signal'] == 'extreme_vnsp':
                risk_signals.append('extreme_vnsp')
            if cde['signal'] == 'high_sell_pressure':
                risk_signals.append('high_cde_pressure')
            if lt_rev.get('signal') == 'strong_reversal':
                risk_signals.append('strong_reversal_risk')
            
            # 正面信号汇总
            positive_signals = []
            if dde['signal'] == 'positive_dde':
                positive_signals.append('positive_dde')
            if momentum.get('signal') == 'strong_momentum':
                positive_signals.append('strong_momentum')
            if quality['signal'] == 'high_quality':
                positive_signals.append('high_quality')
            if low_vol['signal'] == 'very_low_vol':
                positive_signals.append('very_low_vol')
            
            return {
                # 原始因子值
                'cgo_raw': cgo['cgo_raw'],
                'cgo_20d': cgo['cgo_20d'],
                'vnsp_raw': vnsp['vnsp_raw'],
                'vnsp_20d': vnsp['vnsp_20d'],
                'cde_raw': cde['cde_raw'],
                'cde_20d': cde['cde_20d'],
                'dde_raw': dde['dde_raw'],
                'dde_20d': dde['dde_20d'],
                'momentum_raw': momentum.get('momentum_raw', 0),
                'lt_rev_raw': lt_rev.get('lt_rev_raw', 0),
                'quality_score': quality['quality_score'],
                'low_vol_score': low_vol['low_vol_score'],
                'volatility_252d': low_vol['volatility_252d'],
                
                # 标准化因子评分
                'factor_scores': {k: round(v, 4) for k, v in factor_scores.items()},
                
                # 综合结果
                'composite_score': round(float(composite_score), 4),
                'composite_adjustment': round(0.9 + composite_score * 0.2, 4),  # 映射到0.9-1.1范围
                
                # 信号
                'risk_signals': risk_signals,
                'positive_signals': positive_signals,
                'risk_count': len(risk_signals),
                'positive_count': len(positive_signals),
                
                # 原始信号
                'cgo_signal': cgo['signal'],
                'vnsp_signal': vnsp['signal'],
                'cde_signal': cde['signal'],
                'dde_signal': dde['signal'],
                'momentum_signal': momentum.get('signal', ''),
                'lt_rev_signal': lt_rev.get('signal', ''),
                'quality_signal': quality['signal'],
                'low_vol_signal': low_vol['signal'],
            }
            
        except Exception as e:
            logger.error(f"BehavioralClassic error: {e}", exc_info=True)
            return self._defaults()
    
    def _defaults(self):
        """默认返回值"""
        return {
            'cgo_raw': 0, 'cgo_20d': 0,
            'vnsp_raw': 0, 'vnsp_20d': 0,
            'cde_raw': 0, 'cde_20d': 0,
            'dde_raw': 0, 'dde_20d': 0,
            'momentum_raw': 0,
            'lt_rev_raw': 0,
            'quality_score': 0.5,
            'low_vol_score': 0.5,
            'volatility_252d': 0.3,
            'factor_scores': {},
            'composite_score': 0.5,
            'composite_adjustment': 1.0,
            'risk_signals': [],
            'positive_signals': [],
            'risk_count': 0,
            'positive_count': 0,
            'cgo_signal': 'insufficient_data',
            'vnsp_signal': 'insufficient_data',
            'cde_signal': 'insufficient_data',
            'dde_signal': 'insufficient_data',
            'momentum_signal': '',
            'lt_rev_signal': '',
            'quality_signal': 'insufficient_data',
            'low_vol_signal': 'insufficient_data',
        }
    
    def get_factor_summary(self, factors):
        """生成因子摘要"""
        parts = []
        
        # 行为因子
        if factors.get('cgo_20d', 0) > 0.1:
            parts.append(f"CGO↑{factors['cgo_20d']:.1%}")
        if factors.get('vnsp_20d', 0) > 0.15:
            parts.append(f"VNSP↑{factors['vnsp_20d']:.1%}")
        if factors.get('dde_20d', 0) > 0.01:
            parts.append(f"ΔDE↑{factors['dde_20d']:.1%}")
        
        # 经典因子
        if factors.get('momentum_raw', 0) > 0.2:
            parts.append(f"MOM↑{factors['momentum_raw']:.0%}")
        if factors.get('lt_rev_raw', 0) > 0.3:
            parts.append(f"LT_REV↓{factors['lt_rev_raw']:.0%}")
        if factors.get('quality_score', 0) > 0.7:
            parts.append(f"QUAL↑{factors['quality_score']:.0%}")
        if factors.get('low_vol_score', 0) > 0.8:
            parts.append(f"LOWVOL↑{factors['low_vol_score']:.0%}")
        
        if parts:
            return " | ".join(parts)
        else:
            return "neutral"
    
    def get_adjustment_coef(self, factors):
        """获取调整系数"""
        return factors.get('composite_adjustment', 1.0)


if __name__ == '__main__':
    print("=" * 60)
    print("BehavioralClassicFactorCalculator Test")
    print("=" * 60)
    
    np.random.seed(42)
    n = 800  # 需要足够数据支持长期反转计算
    
    # 生成测试数据
    trend = np.linspace(0, 0.5, n)
    noise = np.random.normal(0, 0.03, n)
    close = 10.0 * np.cumprod(1 + trend / n + noise / n)
    high = close * (1 + np.random.uniform(0, 0.04, n))
    low = close * (1 - np.random.uniform(0, 0.04, n))
    open_ = close * (1 + np.random.normal(0, 0.015, n))
    volume = np.random.uniform(1e7, 5e8, n)
    amount = volume * close
    pctChg = (close / np.roll(close, 1) - 1) * 100
    pctChg[0] = 0
    
    df = pd.DataFrame({
        'open': open_, 'close': close, 'high': high, 'low': low,
        'volume': volume, 'amount': amount, 'pctChg': pctChg
    })
    
    calculator = BehavioralClassicFactorCalculator()
    result = calculator.calculate_all(df)
    
    print("\n[行为金融学因子]")
    print(f"  CGO (负向): {result['cgo_20d']:.3%} - {result['cgo_signal']}")
    print(f"  VNSP (负向): {result['vnsp_20d']:.3%} - {result['vnsp_signal']}")
    print(f"  CDE (负向): {result['cde_20d']:.3%} - {result['cde_signal']}")
    print(f"  ΔDE (正向): {result['dde_20d']:.3%} - {result['dde_signal']}")
    
    print("\n[经典多因子]")
    print(f"  动量 (正向): {result.get('momentum_raw', 0):.2%} - {result.get('momentum_signal', '')}")
    print(f"  长期反转 (负向): {result.get('lt_rev_raw', 0):.2%} - {result.get('lt_rev_signal', '')}")
    print(f"  质量因子: {result['quality_score']:.3f} - {result['quality_signal']}")
    print(f"  低波因子: {result['low_vol_score']:.3f} - {result['low_vol_signal']}")
    print(f"  252日波动率: {result['volatility_252d']:.2%}")
    
    print("\n[标准化因子评分]")
    for name, score in result['factor_scores'].items():
        print(f"  {name:12s}: {score:.3f}")
    
    print(f"\n[综合评分] {result['composite_score']:.3f}")
    print(f"[调整系数] {result['composite_adjustment']:.4f}")
    print(f"[风险信号数] {result['risk_count']}: {result['risk_signals']}")
    print(f"[正面信号数] {result['positive_count']}: {result['positive_signals']}")
    print(f"[因子摘要] {calculator.get_factor_summary(result)}")
    
    print("\n[PASS] BehavioralClassicFactorCalculator 测试通过")