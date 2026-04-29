"""
factors — 因子计算引擎包
=========================

包含:
  - behavioral_classic_factors: 行为金融学因子 + 经典多因子
  - factor_engine_v2: 因子引擎V2（51个日频因子）
  - microstructure_reversal_factors: 微结构反转因子
  - enhanced_factor_calculator: 增强因子计算器
  - anti_top_factors: 防顶因子
  - academic_factors: 学术因子

主要接口:
  - FactorEngineV2: 因子引擎核心类
  - EnhancedFactorCalculator: 增强因子计算
  - AntiTopFilter: 防顶过滤器
  - BehavioralClassicFactors: 行为金融学+经典多因子

设计原则:
  - 所有因子计算必须通过 FactorEngineV2 统一接口
  - 因子命名规范: {category}_{name}_{direction}
  - 返回值范围: 0-1 (归一化) 或 带方向的原始值
"""

from .factor_engine_v2 import FactorEngineV2

__all__ = [
    "FactorEngineV2",
]
