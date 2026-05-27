#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
因子权重优化器 - 基于IC有效性和风险调整收益优化
================================================

优化目标：
1. 提升 Sharpe Ratio
2. 提升 Sortino Ratio
3. 减少负偏态（Skew）
4. 降低最大回撤

方法：
1. 基于历史IC序列的动态权重调整
2. 因子相关性去冗余
3. 风险预算分配

参考：
- 多因子量化策略的因子权重优化方法
- 风险平价（Risk Parity）因子配置
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)

__all__ = [
    "FactorWeightOptimizer",
    "RiskAdjustedWeightOptimizer",
    "FactorICStats",
    "create_weight_optimizer",
]


@dataclass
class FactorICStats:
    """因子IC统计"""
    mean_ic: float          # 平均IC
    ic_ir: float            # IC_IR (信息比)
    win_rate: float         # IC胜率
    std_ic: float           # IC标准差
    recent_ic: float        # 最近IC


class FactorWeightOptimizer:
    """因子权重优化器"""
    
    def __init__(self):
        self._factor_ic_history: Dict[str, List[float]] = {}
        self._factor_returns: Dict[str, List[float]] = {}
        
    def record_factor_signal(self, factor_name: str, signal: float, forward_return: float):
        """记录因子信号和未来收益（用于计算IC）"""
        if factor_name not in self._factor_ic_history:
            self._factor_ic_history[factor_name] = []
            self._factor_returns[factor_name] = []
        
        self._factor_ic_history[factor_name].append(signal)
        self._factor_returns[factor_name].append(forward_return)
        
        # 保持最近252天数据
        if len(self._factor_ic_history[factor_name]) > 252:
            self._factor_ic_history[factor_name] = self._factor_ic_history[factor_name][-252:]
            self._factor_returns[factor_name] = self._factor_returns[factor_name][-252:]
    
    def calculate_ic_stats(self, factor_name: str) -> Optional[FactorICStats]:
        """计算因子IC统计"""
        if factor_name not in self._factor_ic_history:
            return None
        
        signals = np.array(self._factor_ic_history[factor_name])
        returns = np.array(self._factor_returns[factor_name])
        
        if len(signals) < 20 or len(returns) < 20:
            return None
        
        # 计算IC（Spearman相关系数）
        try:
            from scipy.stats import spearmanr
            ic, _ = spearmanr(signals, returns)
        except Exception as e:
            logger.debug("spearmanr failed, falling back to corrcoef: %s", e)
            ic = np.corrcoef(signals, returns)[0, 1]
        
        if np.isnan(ic):
            return None
        
        # 计算统计量
        mean_ic = ic
        std_ic = np.std(signals) if np.std(signals) > 0 else 1.0
        ic_ir = mean_ic / std_ic if std_ic > 0 else 0
        
        # IC胜率
        ic_signs = np.sign(signals[:-1] * returns[1:])
        win_rate = np.mean(ic_signs > 0) if len(ic_signs) > 0 else 0.5
        
        # 最近IC（最近20天）
        recent_ic = np.mean(ic[-20:]) if len(ic) >= 20 else mean_ic
        
        return FactorICStats(
            mean_ic=mean_ic,
            ic_ir=ic_ir,
            win_rate=win_rate,
            std_ic=std_ic,
            recent_ic=recent_ic
        )
    
    def optimize_weights(
        self, 
        base_weights: Dict[str, float],
        target_sharpe: float = 1.0,
        risk_budget: Optional[Dict[str, float]] = None
    ) -> Dict[str, float]:
        """
        优化因子权重
        
        优化策略：
        1. 基于IC_IR分配权重（高IR因子获得更高权重）
        2. 风险预算约束
        3. 动态调整（近期表现好的因子获得更高权重）
        """
        factor_stats = {}
        
        # 计算各因子IC统计
        for factor_name in base_weights.keys():
            stats = self.calculate_ic_stats(factor_name)
            if stats:
                factor_stats[factor_name] = stats
        
        if not factor_stats:
            return base_weights  # 数据不足，返回基础权重
        
        # 计算优化权重
        optimized_weights = {}
        
        # 1. 基于IC_IR的权重（信息比越高，权重越高）
        ir_scores = {}
        for factor_name, stats in factor_stats.items():
            # 综合评分：IR * 胜率 * 近期表现
            score = stats.ic_ir * stats.win_rate * (1 + stats.recent_ic)
            ir_scores[factor_name] = max(score, 0.01)  # 避免负权重
        
        # 归一化
        total_score = sum(ir_scores.values())
        for factor_name, score in ir_scores.items():
            optimized_weights[factor_name] = score / total_score
        
        # 2. 混合基础权重（保留部分基础权重以保持稳定性）
        blend_factor = 0.6  # 60%优化权重，40%基础权重
        
        final_weights = {}
        for factor_name in base_weights.keys():
            opt_w = optimized_weights.get(factor_name, 0)
            base_w = base_weights.get(factor_name, 0)
            final_weights[factor_name] = blend_factor * opt_w + (1 - blend_factor) * base_w
        
        # 3. 归一化
        total = sum(final_weights.values())
        if total > 0:
            final_weights = {k: v/total for k, v in final_weights.items()}
        
        return final_weights


class RiskAdjustedWeightOptimizer:
    """风险调整权重优化器 - 专门针对Sharpe/Sortino优化"""
    
    def __init__(self):
        self._returns_history: List[float] = []
        self._weights_history: List[Dict[str, float]] = []
        
    def add_return(self, portfolio_return: float):
        """添加组合收益记录"""
        self._returns_history.append(portfolio_return)
        
        # 保持最近252天
        if len(self._returns_history) > 252:
            self._returns_history = self._returns_history[-252:]
    
    def calculate_sharpe(self, returns: List[float], risk_free_rate: float = 0.0) -> float:
        """计算Sharpe比率"""
        if len(returns) < 20:
            return 0.0
        
        r = np.array(returns)
        excess_return = r - risk_free_rate
        
        mean_ret = np.mean(excess_return)
        std_ret = np.std(excess_return)
        
        if std_ret <= 0:
            return 0.0
        
        # 年化
        sharpe = mean_ret / std_ret * np.sqrt(252)
        
        return sharpe
    
    def calculate_sortino(self, returns: List[float], risk_free_rate: float = 0.0) -> float:
        """计算Sortino比率"""
        if len(returns) < 20:
            return 0.0
        
        r = np.array(returns)
        excess_return = r - risk_free_rate
        
        mean_ret = np.mean(excess_return)
        
        # 下行波动率
        downside_returns = excess_return[excess_return < 0]
        
        if len(downside_returns) == 0:
            return float('inf') if mean_ret > 0 else 0.0
        
        downside_std = np.std(downside_returns)
        
        if downside_std <= 0:
            return 0.0
        
        # 年化
        sortino = mean_ret / downside_std * np.sqrt(252)
        
        return sortino
    
    def calculate_skew(self, returns: List[float]) -> float:
        """计算偏度"""
        if len(returns) < 30:
            return 0.0
        
        r = np.array(returns)
        mean = np.mean(r)
        std = np.std(r)
        
        if std <= 0:
            return 0.0
        
        skew = np.mean(((r - mean) / std) ** 3)
        
        return skew
    
    def get_risk_metrics(self) -> Dict[str, float]:
        """获取当前风险指标"""
        returns = self._returns_history
        
        if len(returns) < 20:
            return {
                "sharpe": 0.0,
                "sortino": 0.0,
                "skew": 0.0,
                "max_drawdown": 0.0,
                "volatility": 0.0,
            }
        
        sharpe = self.calculate_sharpe(returns)
        sortino = self.calculate_sortino(returns)
        skew = self.calculate_skew(returns)
        
        # 最大回撤
        cumulative = np.cumprod(1 + np.array(returns))
        peak = np.maximum.accumulate(cumulative)
        drawdown = (cumulative - peak) / peak
        max_dd = np.min(drawdown) if len(drawdown) > 0 else 0.0
        
        # 波动率
        volatility = np.std(returns) * np.sqrt(252)
        
        return {
            "sharpe": sharpe,
            "sortino": sortino,
            "skew": skew,
            "max_drawdown": max_dd,
            "volatility": volatility,
        }
    
    def suggest_weight_adjustment(
        self, 
        current_weights: Dict[str, float],
        factor_returns: Dict[str, float]
    ) -> Dict[str, float]:
        """
        基于风险指标建议权重调整
        
        策略：
        1. 如果Skew < -0.3， 降低高波动因子权重
        2. 如果Sharpe < 1.0， 增加高IC因子权重
        3. 如果MaxDD > 10%， 降低整体风险敞口
        """
        metrics = self.get_risk_metrics()
        
        adjusted_weights = current_weights.copy()
        
        # 1. 偏度调整：如果负偏态严重，降低反转因子权重
        if metrics["skew"] < -0.3:
            reversal_penalty = min(1.0, 0.5 + metrics["skew"])
            for factor in ["reversal", "short_term_reversal", "mean_reversion"]:
                if factor in adjusted_weights:
                    adjusted_weights[factor] *= reversal_penalty
            logger.info(f"偏度调整: {metrics['skew']:.2f}, 反转因子权重降低")
        
        # 2. Sharpe调整：如果Sharpe低，增加动量因子
        if metrics["sharpe"] < 1.0:
            momentum_boost = min(1.2, 1.0 + (1.0 - metrics["sharpe"]) * 0.3)
            for factor in ["momentum", "trend", "ma_trend"]:
                if factor in adjusted_weights:
                    adjusted_weights[factor] *= momentum_boost
            logger.info(f"Sharpe调整: {metrics['sharpe']:.2f}, 动量因子权重提升")
        
        # 3. 回撤调整：如果MaxDD过高，降低整体敞口
        if abs(metrics["max_drawdown"]) > 0.10:
            exposure_reduction = 1.0 - min(0.5, abs(metrics["max_drawdown"]) - 0.10) * 2
            adjusted_weights = {k: v * exposure_reduction for k, v in adjusted_weights.items()}
            logger.info(f"回撤调整: {metrics['max_drawdown']:.1%}, 整体敞口降至{exposure_reduction:.0%}")
        
        # 归一化
        total = sum(adjusted_weights.values())
        if total > 0:
            adjusted_weights = {k: v/total for k, v in adjusted_weights.items()}
        
        return adjusted_weights


def create_weight_optimizer() -> Tuple[FactorWeightOptimizer, RiskAdjustedWeightOptimizer]:
    """创建权重优化器（便捷函数）"""
    return FactorWeightOptimizer(), RiskAdjustedWeightOptimizer()