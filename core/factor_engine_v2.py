#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
因子引擎 v2 - 统一集成所有日频因子模块
==========================================
将4个因子模块的计算结果统一整合，输出综合调整系数供主评分系统使用。

模块结构：
  factor_engine_v2.py (本文件)
    ├── momentum_factors.py           (大类1+2: 动量5 + 量价6 = 11个因子)
    ├── capital_flow_factors.py       (大类3+4: 资金流6 + 流动性5 = 11个因子)
    ├── volatility_sentiment_factors.py (大类5+6: 波动率高阶矩6 + 情绪拥挤5 = 11个因子)
    └── microstructure_reversal_factors.py (大类7+8+9: 微观6 + 反转6 + 行业6 = 18个因子)

总计：51个日频因子

集成模式：
  1. 每个模块的 calculate_all() 返回 dict
  2. FactorEngineV2 统一调用，生成综合调整系数
  3. 主程序只需调用 engine.calculate(df) → 获取 adjustment_coef

评分逻辑：
  动量正面(20%) + 量价正面(15%) + 资金流正面(15%) + 流动性正面(10%) +
  波动率风险(10%) + 情绪拥挤(10%) + 微观结构(10%) + 反转风险(10%)

  正面因子 → 加分（乘数 > 1.0）
  风险因子 → 惩罚（乘数 < 1.0）
"""

import warnings
warnings.filterwarnings('ignore')

import logging
import time
from typing import Dict, Optional, Tuple, List
import numpy as np

logger = logging.getLogger("factor_engine_v2")

__all__ = [
    "FactorEngineV2",
]


class FactorEngineV2:
    """
    v2 因子引擎 - 统一集成51个日频因子

    用法：
        engine = FactorEngineV2()
        result = engine.calculate(df)
        # result['adjustment_coef'] → 综合调整系数
        # result['all_factors'] → 所有51个因子值
        # result['category_scores'] → 各大类评分
        # result['risk_summary'] → 风险摘要
    """

    # 各大类在综合评分中的权重
    # 调整原则：越是有效的因子越增加权重，同时保持均衡
    # IC有效性参考：学术因子综合+5.8%，处置效应+3.2~3.5%，资金流+2.9~3.1%，动量+2.8~3.0%
    # 新增：行为金融学+经典多因子权重重新分配
    WEIGHTS = {
        'momentum': 0.12,          # 动量正面信号 (IC ~3.0%, 优化权重)
        'vol_price': 0.06,         # 量价结构正面 (优化权重)
        'capital_flow': 0.10,      # 资金流正面 (IC ~3.1%, 优化权重)
        'liquidity': 0.05,         # 流动性正面 (优化权重)
        'volatility_risk': 0.08,   # 波动率风险（惩罚）(增加权重)
        'sentiment_crowd': 0.07,   # 情绪拥挤（惩罚）(增加权重)
        'microstructure': 0.05,    # 微观结构正面 (优化权重)
        'reversal_risk': 0.07,     # 反转风险（惩罚）(增加权重)
        'disposition_effect': 0.20,# 处置效应（行为金融核心因子，IC ~3.5%，保持权重)
        'behavioral_classic': 0.20,# 行为金融学+经典多因子 (IC综合预计~4-5%，保持权重)
    }

    def __init__(self, enable_modules: Optional[Dict[str, bool]] = None):
        """
        Parameters
        ----------
        enable_modules : dict, optional
            控制启用哪些因子模块。默认全部启用。
            例: {'momentum': True, 'capital_flow': False}
        """
        self.enable = {
            'momentum': True,
            'capital_flow': True,
            'volatility_sentiment': True,
            'microstructure_reversal': True,
            'disposition_effect': True,
            'behavioral_classic': True,  # 新增：行为金融学+经典多因子
        }
        if enable_modules:
            self.enable.update(enable_modules)

        self._calcs = {}
        self._init_calculators()

    def _init_calculators(self):
        """延迟导入因子模块（避免循环依赖和启动时间）"""
        if self.enable.get('momentum'):
            try:
                from momentum_factors import MomentumFactorCalculator
                self._calcs['momentum'] = MomentumFactorCalculator()
            except ImportError as e:
                logger.warning("momentum_factors 模块导入失败: %s", e)
                self.enable['momentum'] = False

        if self.enable.get('capital_flow'):
            try:
                from capital_flow_factors import CapitalFlowFactorCalculator
                self._calcs['capital_flow'] = CapitalFlowFactorCalculator()
            except ImportError as e:
                logger.warning("capital_flow_factors 模块导入失败: %s", e)
                self.enable['capital_flow'] = False

        if self.enable.get('volatility_sentiment'):
            try:
                from volatility_sentiment_factors import VolatilitySentimentFactorCalculator
                self._calcs['volatility_sentiment'] = VolatilitySentimentFactorCalculator()
            except ImportError as e:
                logger.warning("volatility_sentiment_factors 模块导入失败: %s", e)
                self.enable['volatility_sentiment'] = False

        if self.enable.get('microstructure_reversal'):
            try:
                from microstructure_reversal_factors import MicrostructureReversalFactorCalculator
                self._calcs['microstructure_reversal'] = MicrostructureReversalFactorCalculator()
            except ImportError as e:
                logger.warning("microstructure_reversal_factors 模块导入失败: %s", e)
                self.enable['microstructure_reversal'] = False

        if self.enable.get('disposition_effect'):
            try:
                from disposition_effect_factors import DispositionEffectCalculator
                self._calcs['disposition_effect'] = DispositionEffectCalculator()
            except ImportError as e:
                logger.warning("disposition_effect_factors 模块导入失败: %s", e)
                self.enable['disposition_effect'] = False

        if self.enable.get('behavioral_classic'):
            try:
                from behavioral_classic_factors import BehavioralClassicFactorCalculator
                self._calcs['behavioral_classic'] = BehavioralClassicFactorCalculator()
            except ImportError as e:
                logger.warning("behavioral_classic_factors 模块导入失败: %s", e)
                self.enable['behavioral_classic'] = False

    # ===== V15 改进：新因子计算器 =====
    def calculate_liquidity_factors(self, df) -> Dict:
        """计算流动性因子"""
        result = {}
        if len(df) < 20:
            return {'liquidity_score': 0.5}

        # 日均成交额
        avg_amount = df['amount'].tail(20).mean() if 'amount' in df.columns else 0
        result['avg_amount_20d'] = avg_amount

        # 平均换手率
        avg_turn = df['turn'].tail(20).mean() if 'turn' in df.columns else 0
        result['avg_turnover_20d'] = avg_turn

        # Amihud 非流动性指标
        if 'amount' in df.columns and 'pct_change' in df.columns:
            returns = df['pct_change'].dropna().tail(20)
            amounts = df['amount'].tail(20)
            if len(returns) > 0 and amounts.sum() > 0:
                amihud = (returns.abs() / amounts).mean()
                result['amihud_illiquidity'] = amihud
                # Amihud 越低，流动性越好
                result['liquidity_score'] = np.clip(1 - amihud * 1e6, 0, 1) if amihud > 0 else 0.5
            else:
                result['liquidity_score'] = 0.5
        else:
            result['liquidity_score'] = 0.5

        return result

    def calculate_quality_factors(self, df) -> Dict:
        """计算质量因子（需要基本面数据，此处用技术指标近似）"""
        result = {}
        if len(df) < 20:
            return {'quality_score': 0.5}

        # 收益稳定性（20日收益标准差的倒数）
        returns = df['pct_change'].dropna().tail(20)
        if len(returns) > 5:
            volatility = returns.std()
            result['return_volatility'] = volatility
            result['stability_score'] = np.clip(1 - volatility / 10, 0, 1)
        else:
            result['stability_score'] = 0.5

        # 上涨趋势强度
        if len(df) >= 20:
            ma5 = df['close'].tail(5).mean()
            ma20 = df['close'].tail(20).mean()
            trend_strength = ma5 / ma20 - 1 if ma20 > 0 else 0
            result['trend_strength'] = trend_strength
            result['trend_score'] = np.clip(trend_strength * 10 + 0.5, 0, 1)
        else:
            result['trend_score'] = 0.5

        # 综合质量评分
        result['quality_score'] = (result.get('stability_score', 0.5) * 0.5 +
                                   result.get('trend_score', 0.5) * 0.5)

        return result

    def calculate_low_vol_factors(self, df) -> Dict:
        """计算低波动因子"""
        result = {}
        if len(df) < 20:
            return {'low_vol_score': 0.5}

        # 20日波动率
        returns = df['pct_change'].dropna().tail(20)
        if len(returns) > 5:
            vol_20d = returns.std()
            result['volatility_20d'] = vol_20d
            # 波动率越低越好
            result['low_vol_score'] = np.clip(1 - vol_20d / 5, 0, 1)
        else:
            result['low_vol_score'] = 0.5

        # 60日波动率（如果数据足够）
        if len(df) >= 60:
            returns_60 = df['pct_change'].dropna().tail(60)
            if len(returns_60) > 30:
                vol_60d = returns_60.std()
                result['volatility_60d'] = vol_60d
                result['low_vol_60d_score'] = np.clip(1 - vol_60d / 8, 0, 1)
                # 综合
                result['low_vol_score'] = (result['low_vol_score'] * 0.6 +
                                           result.get('low_vol_60d_score', 0.5) * 0.4)

        return result

    # ===== V15 改进：IC验证 =====
    def validate_factors_ic(self, factor_values: List[float], returns: List[float]) -> Dict:
        """
        验证因子IC值（信息系数）

        Args:
            factor_values: 因子值列表
            returns: 收益率列表

        Returns:
            {'ic': float, 'is_valid': bool}
        """
        if len(factor_values) < 30 or len(returns) < 30:
            return {'ic': 0, 'is_valid': False, 'reason': '数据不足'}

        # 计算Spearman相关系数（IC）
        try:
            from scipy.stats import spearmanr
            ic, p_value = spearmanr(factor_values, returns)
            return {
                'ic': ic if not np.isnan(ic) else 0,
                'p_value': p_value,
                'is_valid': abs(ic) >= 0.05,  # IC绝对值 >= 0.05 视为有效
            }
        except ImportError:
            # 无scipy时使用简单相关
            ic = np.corrcoef(factor_values, returns)[0, 1]
            return {'ic': ic if not np.isnan(ic) else 0, 'is_valid': abs(ic) >= 0.05}

    def _normalize_df(self, df) -> 'pd.DataFrame':
        """
        列名标准化适配层（LRN-20260326-003 修复）
        兼容 stock_data.py 输出的列名（pct_change）与因子模块期望的列名（pctChg）
        同时补充缺失的 turn 列（用成交额/收盘价/100 估算，单位：%）

        优化：仅在需要时复制DataFrame，避免不必要的内存开销
        """
        import pandas as pd
        needs_copy = False

        # pct_change → pctChg（baostock返回后被stock_data.py重命名）
        if 'pct_change' in df.columns and 'pctChg' not in df.columns:
            df = df.copy() if not needs_copy else df
            needs_copy = True
            df['pctChg'] = df['pct_change']
        # 如果仍无 pctChg，用 close 计算
        elif 'pctChg' not in df.columns and 'close' in df.columns:
            df = df.copy() if not needs_copy else df
            needs_copy = True
            df['pctChg'] = df['close'].pct_change(fill_method=None) * 100

        # 补充 turn 列（baostock 未请求该字段时缺失）
        # 近似换手率 = 成交量 / 流通股本 * 100
        # 无流通股本数据时，用成交额/(收盘价*1e8)*100 粗估（1亿股基准）
        if 'turn' not in df.columns:
            df = df.copy() if not needs_copy else df
            needs_copy = True
            if 'amount' in df.columns and 'close' in df.columns:
                df['turn'] = df['amount'] / (df['close'] * 1e8) * 100
                df['turn'] = df['turn'].fillna(1.0).clip(0.01, 50.0)
            else:
                df['turn'] = 1.0  # 默认值1%

        return df

    def calculate(self, df) -> Dict:
        """
        计算所有因子并返回综合结果

        Parameters
        ----------
        df : DataFrame
            日频K线数据，需含 open/close/high/low/volume/amount/pctChg/turn
            兼容输入: pct_change（由 stock_data.py 输出），turn 列可缺失（自动估算）

        Returns
        -------
        dict: {
            'adjustment_coef': float,       # 综合调整系数
            'all_factors': dict,            # 所有因子原始值
            'category_scores': dict,        # 各大类评分
            'risk_summary': dict,           # 风险摘要
            'engine_version': str,          # 引擎版本
        }
        """
        # 列名标准化（兼容 pct_change/pctChg，补充缺失的 turn）
        df = self._normalize_df(df)

        all_factors = {}
        category_scores = {}

        # ── 1. 动量 & 量价 (momentum_factors.py) ──
        if self.enable.get('momentum') and 'momentum' in self._calcs:
            try:
                # MomentumFactorCalculator 的方法名为 calculate，不是 calculate_all（LRN-20260326-003）
                _calc_fn = getattr(self._calcs['momentum'], 'calculate_all', None) or \
                           getattr(self._calcs['momentum'], 'calculate', None)
                mom_result = _calc_fn(df)
                all_factors.update({
                    k: float(v) if not isinstance(v, (dict, list, str)) else v
                    for k, v in mom_result.items()
                })
                # 展开 details 子字典（overnight_mom, intraday_mom 等供 _calc_momentum_score 使用）
                if isinstance(mom_result.get('details'), dict):
                    all_factors.update({
                        k: float(v) if isinstance(v, (int, float)) else v
                        for k, v in mom_result['details'].items()
                    })
                # 动量正面评分（传入 details 展开的字典）
                mom_merged = {**mom_result, **mom_result.get('details', {})}
                category_scores['momentum'] = self._calc_momentum_score(mom_merged)
                category_scores['vol_price'] = self._calc_vol_price_score(mom_merged)
            except Exception as e:
                logger.debug("动量因子计算失败: %s", e)
                category_scores['momentum'] = 0.5
                category_scores['vol_price'] = 0.5

        # ── 2. 资金流 & 流动性 (capital_flow_factors.py) ──
        if self.enable.get('capital_flow') and 'capital_flow' in self._calcs:
            try:
                # CapitalFlowFactorCalculator 的方法名为 calculate，不是 calculate_all（LRN-20260326-003）
                _calc_fn = getattr(self._calcs['capital_flow'], 'calculate_all', None) or \
                           getattr(self._calcs['capital_flow'], 'calculate', None)
                cf_result = _calc_fn(df)
                # 先 flatten 顶层，再将 details 子字典展开到顶层（供 _calc_liquidity_score 使用）
                all_factors.update({
                    k: float(v) if not isinstance(v, (dict, list, str)) else v
                    for k, v in cf_result.items()
                })
                # 展开 details 子字典（amihud_chg, turnover_chg 等）
                if isinstance(cf_result.get('details'), dict):
                    all_factors.update({
                        k: float(v) if isinstance(v, (int, float)) else v
                        for k, v in cf_result['details'].items()
                    })
                category_scores['capital_flow'] = self._calc_capital_flow_score(cf_result)
                # _calc_liquidity_score 需要 details 里的键，传入合并字典
                cf_merged = {**cf_result, **cf_result.get('details', {})}
                category_scores['liquidity'] = self._calc_liquidity_score(cf_merged)
            except Exception as e:
                logger.debug("资金流因子计算失败: %s", e)
                category_scores['capital_flow'] = 0.5
                category_scores['liquidity'] = 0.5

        # ── 3. 波动率 & 情绪 (volatility_sentiment_factors.py) ──
        if self.enable.get('volatility_sentiment') and 'volatility_sentiment' in self._calcs:
            try:
                vs_result = self._calcs['volatility_sentiment'].calculate_all(df)
                all_factors.update({
                    k: float(v) if not isinstance(v, (dict, list, str)) else v
                    for k, v in vs_result.items()
                })
                # 波动率风险（惩罚方向）
                vs_coef, vs_level = self._calcs['volatility_sentiment'].get_vol_sentiment_score(vs_result)
                category_scores['volatility_risk'] = 1.0 - vs_coef  # 反转：低风险=高分
                category_scores['sentiment_crowd'] = 1.0 - vs_result.get('sentiment_crowd_score', 0.0)
            except Exception as e:
                logger.debug("波动率情绪因子计算失败: %s", e)
                category_scores['volatility_risk'] = 0.5
                category_scores['sentiment_crowd'] = 0.5

        # ── 4. 微观结构 & 反转 & 行业 (microstructure_reversal_factors.py) ──
        if self.enable.get('microstructure_reversal') and 'microstructure_reversal' in self._calcs:
            try:
                mr_result = self._calcs['microstructure_reversal'].calculate_all(df)
                all_factors.update({
                    k: float(v) if not isinstance(v, (dict, list, str)) else v
                    for k, v in mr_result.items()
                })
                mr_coef, mr_level = self._calcs['microstructure_reversal'].get_comprehensive_score(mr_result)
                # 微观结构正面评分
                micro_positive = (
                    mr_result.get('obi_persistence', 0.5) * 0.25 +
                    mr_result.get('resilience_10d', 0.5) * 0.25 +
                    mr_result.get('close_pos_score', 0.5) * 0.25 +
                    (1.0 - mr_result.get('chip_risk_score', 0.5)) * 0.25
                )
                category_scores['microstructure'] = np.clip(micro_positive, 0, 1)
                # 反转风险（惩罚方向）
                category_scores['reversal_risk'] = 1.0 - mr_result.get('reversal_warning_score', 0.0)
            except Exception as e:
                logger.debug("微观结构反转因子计算失败: %s", e)
                category_scores['microstructure'] = 0.5
                category_scores['reversal_risk'] = 0.5

        # ── 5. 处置效应 (disposition_effect_factors.py) ──
        if self.enable.get('disposition_effect') and 'disposition_effect' in self._calcs:
            try:
                de_result = self._calcs['disposition_effect'].calculate_all(df)
                all_factors.update({
                    k: float(v) if isinstance(v, (int, float, np.floating)) else v
                    for k, v in de_result.items()
                })
                de_coef, de_signal = self._calcs['disposition_effect'].get_de_adjustment(de_result)
                # 处置效应评分: 将调整系数映射到0-1评分
                # coef > 1 = 正面(洗盘信号), coef < 1 = 负面(避顶/卖压)
                category_scores['disposition_effect'] = np.clip(0.5 + (de_coef - 1.0) * 5, 0, 1)
            except Exception as e:
                logger.debug("处置效应因子计算失败: %s", e)
                category_scores['disposition_effect'] = 0.5

        # ── 6. 行为金融学 + 经典多因子 (behavioral_classic_factors.py) ──
        if self.enable.get('behavioral_classic') and 'behavioral_classic' in self._calcs:
            try:
                bc_result = self._calcs['behavioral_classic'].calculate_all(df)
                all_factors.update({
                    k: float(v) if isinstance(v, (int, float, np.floating)) else v
                    for k, v in bc_result.items()
                })
                # 使用复合调整系数作为评分
                bc_adjustment = bc_result.get('composite_adjustment', 1.0)
                category_scores['behavioral_classic'] = np.clip(0.5 + (bc_adjustment - 1.0) * 10, 0, 1)
            except Exception as e:
                logger.debug("行为金融学+经典多因子计算失败: %s", e)
                category_scores['behavioral_classic'] = 0.5

        # ── 综合评分 → 调整系数 ──
        adjustment_coef = self._compute_adjustment(category_scores)

        # ── 风险摘要 ──
        risk_summary = self._build_risk_summary(all_factors, category_scores)

        return {
            'adjustment_coef': round(adjustment_coef, 4),
            'all_factors': all_factors,
            'category_scores': {k: round(v, 4) for k, v in category_scores.items()},
            'risk_summary': risk_summary,
            'engine_version': 'v2.0',
        }

    def _calc_momentum_score(self, factors: Dict) -> float:
        """动量正面评分 (0~1)"""
        # 隔夜动量 + 日内动量 + 动量一致性
        overnight = abs(factors.get('overnight_mom', 0))
        intraday = abs(factors.get('intraday_mom', 0))
        consistency = factors.get('mom_consistency', 0)
        tail_end = factors.get('tail_end_mom', 0)

        score = (
            min(1.0, overnight * 10) * 0.20 +
            min(1.0, intraday * 10) * 0.20 +
            consistency * 0.30 +
            max(0, tail_end) * 0.15 +
            min(1.0, max(0, 1.0 - factors.get('mom_reversal_warning', 0))) * 0.15
        )
        return float(np.clip(score, 0, 1))

    def _calc_vol_price_score(self, factors: Dict) -> float:
        """量价结构正面评分 (0~1)"""
        up_down_ratio = factors.get('up_down_vol_ratio', 1.0)
        vol_lead = factors.get('vol_lead_lag', 0.0)
        divergence = factors.get('price_vol_divergence', 0.0)
        stability = factors.get('turnover_stability', 0.5)
        shrink_warn = factors.get('shrink_rise_warning', 0.0)
        surge_warn = factors.get('surge_vol_stall_warning', 0.0)

        score = (
            min(1.0, max(0, (up_down_ratio - 0.8) / 0.4)) * 0.20 +   # 涨量>跌量
            min(1.0, max(0, vol_lead)) * 0.15 +                        # 量能领先
            min(1.0, max(0, 1.0 - divergence)) * 0.20 +                # 低背离
            stability * 0.20 +                                           # 换手稳定
            min(1.0, max(0, 1.0 - shrink_warn)) * 0.10 +               # 无缩量涨
            min(1.0, max(0, 1.0 - surge_warn)) * 0.15                  # 无放量滞
        )
        return float(np.clip(score, 0, 1))

    def _calc_capital_flow_score(self, factors: Dict) -> float:
        """资金流正面评分 (0~1)"""
        flow_strength = factors.get('flow_strength_score', 0.5)
        persistence = factors.get('main_flow_persistence', 0.0)
        retail_warning = factors.get('retail_takeover_warning', 0.0)
        divergence = factors.get('price_capital_divergence', 0.0)

        score = (
            flow_strength * 0.40 +
            min(1.0, max(0, persistence)) * 0.25 +
            min(1.0, max(0, 1.0 - retail_warning)) * 0.15 +
            min(1.0, max(0, 1.0 - divergence)) * 0.20
        )
        return float(np.clip(score, 0, 1))

    def _calc_liquidity_score(self, factors: Dict) -> float:
        """流动性正面评分 (0~1)"""
        amihud_chg = factors.get('amihud_chg', 0.0)
        turnover_chg = factors.get('turnover_chg', 0.0)
        liquidity_score = factors.get('liquidity_score', 0.5)

        score = (
            liquidity_score * 0.50 +
            min(1.0, max(0, 0.5 + amihud_chg * 5)) * 0.25 +    # Amihud变化
            min(1.0, max(0, 0.5 + turnover_chg * 5)) * 0.25      # 换手变化
        )
        return float(np.clip(score, 0, 1))

    def _compute_adjustment(self, category_scores: Dict) -> float:
        """
        根据各大类评分计算综合调整系数

        正面类别（越高越好）：
          momentum, vol_price, capital_flow, liquidity, microstructure
        风险类别（越高越好=越安全）：
          volatility_risk, sentiment_crowd, reversal_risk
        """
        total = 0.0
        for cat, weight in self.WEIGHTS.items():
            cat_score = category_scores.get(cat, 0.5)
            total += cat_score * weight

        # total 范围 0~1，映射到调整系数
        # total > 0.6 → 加分 (1.02~1.05)
        # total 0.4~0.6 → 中性 (0.98~1.02)
        # total 0.2~0.4 → 惩罚 (0.90~0.98)
        # total < 0.2 → 强惩罚 (0.75~0.90)

        if total >= 0.65:
            coef = 1.02 + (total - 0.65) * 0.10   # 1.02 ~ 1.07
        elif total >= 0.50:
            coef = 0.98 + (total - 0.50) * 0.267   # 0.98 ~ 1.02
        elif total >= 0.35:
            coef = 0.90 + (total - 0.35) * 0.533   # 0.90 ~ 0.98
        else:
            coef = 0.75 + total * 0.429             # 0.75 ~ 0.90

        return float(np.clip(coef, 0.70, 1.10))

    def _build_risk_summary(self, all_factors: Dict, category_scores: Dict) -> Dict:
        """构建风险摘要"""
        warnings_list = []

        # 反转预警
        warning_level = all_factors.get('warning_level', 'safe')
        if warning_level in ('warning', 'danger'):
            warnings_list.append(f"反转预警: {warning_level}")

        # 情绪拥挤
        crowd_level = all_factors.get('crowd_level', 'low')
        if crowd_level in ('high', 'extreme'):
            warnings_list.append(f"情绪拥挤: {crowd_level}")

        # 超买
        if all_factors.get('reversal_warning', False):
            warnings_list.append("short_overbought")

        # 处置效应避顶
        if all_factors.get('top_avoidance', False):
            for trig in all_factors.get('top_triggers', []):
                warnings_list.append(f"DE_top: {trig}")

        # 处置效应卖压
        sell_prob = all_factors.get('sell_probability', 50)
        if sell_prob > 70:
            warnings_list.append(f"high_sell_pressure: {sell_prob:.0f}%")
            warnings_list.append("短期超买")

        # 动能衰竭
        exhaustion = all_factors.get('momentum_exhaustion', 0)
        if exhaustion > 0.5:
            warnings_list.append(f"动能衰竭: {exhaustion:.0%}")

        # 量价背离
        resonance = all_factors.get('resonance_signal', '')
        if resonance == 'divergence':
            warnings_list.append("量价背离")

        # 背离信号
        div_signal = all_factors.get('divergence_signal', '')
        if div_signal == 'bearish_divergence':
            warnings_list.append("多周期看跌背离")

        # 正面信号
        positives_list = []

        obi = all_factors.get('obi_signal', '')
        if obi == 'buy_dominant':
            positives_list.append("买盘主导")

        resilience = all_factors.get('resilience_signal', '')
        if resilience == 'strong_buyer':
            positives_list.append("日内弹性强")

        hl = all_factors.get('hl_signal', '')
        if hl == 'strong_uptrend':
            positives_list.append("频繁创新高")

        breakout = all_factors.get('breakout_signal', '')
        if breakout == 'confirmed_breakout':
            positives_list.append("突破回踩确认")

        pattern = all_factors.get('pattern_signal', '')
        if pattern == 'bottom_reversal':
            positives_list.append("K线底部反转")

        # 处置效应洗盘信号
        if all_factors.get('washout_signal', False):
            positives_list.append("DE_washout_buy")
        sell_p = all_factors.get('sell_probability', 50)
        if sell_p < 25:
            positives_list.append(f"low_sell_pressure: {sell_p:.0f}%")

        return {
            'warning_count': len(warnings_list),
            'warnings': warnings_list,
            'positive_count': len(positives_list),
            'positives': positives_list,
            'overall_signal': 'positive' if len(positives_list) > len(warnings_list) + 1
                           else ('negative' if len(warnings_list) > len(positives_list) + 1
                                 else 'neutral'),
        }

    def get_enabled_modules(self) -> Dict[str, bool]:
        """返回当前启用的模块状态"""
        return dict(self.enable)

    def get_module_info(self) -> List[Dict]:
        """返回所有模块信息"""
        info = [
            {
                'name': 'momentum_factors',
                'description': '动量 & 量价结构 (11个因子)',
                'enabled': self.enable.get('momentum', False),
                'categories': ['日内动量(5)', '量价结构(6)'],
                'weight': f"{self.WEIGHTS['momentum'] + self.WEIGHTS['vol_price']:.0%}",
            },
            {
                'name': 'capital_flow_factors',
                'description': '资金流 & 流动性 (11个因子)',
                'enabled': self.enable.get('capital_flow', False),
                'categories': ['资金流(6)', '流动性(5)'],
                'weight': f"{self.WEIGHTS['capital_flow'] + self.WEIGHTS['liquidity']:.0%}",
            },
            {
                'name': 'volatility_sentiment_factors',
                'description': '波动率 & 情绪拥挤 (11个因子)',
                'enabled': self.enable.get('volatility_sentiment', False),
                'categories': ['波动率高阶矩(6)', '情绪拥挤(5)'],
                'weight': f"{self.WEIGHTS['volatility_risk'] + self.WEIGHTS['sentiment_crowd']:.0%}",
            },
            {
                'name': 'microstructure_reversal_factors',
                'description': 'Microstructure & Reversal & Industry (18 factors)',
                'enabled': self.enable.get('microstructure_reversal', False),
                'categories': ['Microstructure(6)', 'Reversal(6)', 'Industry(6)'],
                'weight': f"{self.WEIGHTS['microstructure'] + self.WEIGHTS['reversal_risk']:.0%}",
            },
            {
                'name': 'disposition_effect_factors',
                'description': 'Disposition Effect / Retail Sell Probability (DE factor)',
                'enabled': self.enable.get('disposition_effect', False),
                'categories': ['ProfitRatio(V1)', 'SellProb(V2)', 'MarketDE(V3)'],
                'weight': f"{self.WEIGHTS['disposition_effect']:.0%}",
            },
            {
                'name': 'behavioral_classic_factors',
                'description': 'Behavioral Finance + Classic Multi-Factors (8 factors)',
                'enabled': self.enable.get('behavioral_classic', False),
                'categories': ['CGO/VNSP/CDE/ΔDE(4)', 'Momentum/LT_REV(2)', 'Quality/LowVol(2)'],
                'weight': f"{self.WEIGHTS['behavioral_classic']:.0%}",
            },
        ]
        return info


# ===================================================================
# 快速测试
# ===================================================================

if __name__ == '__main__':
    import pandas as pd

    print("=" * 60)
    print("FactorEngineV2 快速测试")
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

    engine = FactorEngineV2()

    print("\n[模块状态]")
    for m in engine.get_module_info():
        status = "[ON]" if m['enabled'] else "[OFF]"
        print(f"  {status} {m['name']}: {m['description']} (权重:{m['weight']})")

    print("\n[因子计算中...]")
    t0 = time.time()
    result = engine.calculate(df)
    t1 = time.time()

    print(f"\n[计算耗时] {t1-t0:.3f}s")
    print(f"\n[综合调整系数] {result['adjustment_coef']:.4f}")
    print(f"[引擎版本] {result['engine_version']}")

    print(f"\n[各大类评分]")
    for cat, score in result['category_scores'].items():
        w = engine.WEIGHTS.get(cat, 0)
        bar = '#' * int(score * 30)
        print(f"  {cat:20s}: {score:.4f} (w={w:.0%}) |{bar}")

    print(f"\n[风险摘要]")
    risk = result['risk_summary']
    print(f"  总体信号: {risk['overall_signal']}")
    print(f"  预警({risk['warning_count']}): {risk['warnings'] or '无'}")
    print(f"  正面({risk['positive_count']}): {risk['positives'] or '无'}")

    print(f"\n[因子总数] {len(result['all_factors'])}")
    print("\n[PASS] FactorEngineV2 测试通过")
