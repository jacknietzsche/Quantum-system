"""
core.strategy — 策略与因子层
=============================
整合 v14 评分体系的所有因子模块，提供统一的评分接口。

提供:
  1. V15Scorer — v15 统一评分器（五层加权 + 防顶 + 因子引擎V2）
  2. StockFilter — 股票过滤器（ST/科创板/次新/高价）
  3. MarketAnalyzer — 市场环境分析器（北向/融资/资金流/板块）
  4. LLMBroker — LLM 增强代理（选股理由生成）

设计原则:
  - 评分逻辑与选股流程解耦
  - 任何新因子只需实现 calculate(df) → dict 接口即可接入
  - 评分结果标准化: {symbol, scores: {layer: value}, total_score}
  - 依赖注入：因子组件通过构造函数注入，便于测试和替换
"""

import os
import logging
import warnings as warnings_builtin
from datetime import datetime
from typing import Dict, List, Optional, Any, Protocol, runtime_checkable
from pathlib import Path
from abc import ABC, abstractmethod

import pandas as pd
import numpy as np

from core.config import QuantConfig, SelectionConfig

warnings_builtin.filterwarnings('ignore')
logger = logging.getLogger(__name__)

__all__ = [
    "V15Scorer",
    "V16Scorer",
    "StockFilter",
    "MarketAnalyzer",
    "LLMBroker",
]

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


# ================================================================
# 因子引擎抽象接口 (依赖注入基础)
# ================================================================

@runtime_checkable
class BaseFactorEngine(Protocol):
    """因子引擎抽象接口 - 所有因子计算器需实现此接口"""

    def calculate(self, df: pd.DataFrame) -> Dict:
        """
        计算因子并返回结果

        Args:
            df: 日频数据 DataFrame

        Returns:
            包含因子值的字典
        """
        ...


@runtime_checkable
class BaseAntiTopFilter(Protocol):
    """防顶过滤器抽象接口"""

    def evaluate(self, df: pd.DataFrame) -> Dict:
        """评估见顶风险"""
        ...

    def get_score_penalty(self, result: Dict) -> float:
        """根据评估结果计算惩罚系数"""
        ...


@runtime_checkable
class BaseStockSelector(Protocol):
    """选股器抽象接口"""

    def calculate_comprehensive_score(self, factors: Dict) -> float:
        """计算综合评分"""
        ...


class LazyComponentLoader:
    """
    延迟加载组件 - 解决循环依赖和启动性能问题

    用法:
        loader = LazyComponentLoader()
        selector = loader.get('selector')  # 首次访问时加载
    """

    def __init__(self):
        self._cache: Dict[str, Any] = {}

    def get(self, component_name: str) -> Any:
        """获取组件（延迟加载）"""
        if component_name in self._cache:
            return self._cache[component_name]

        component = self._load_component(component_name)
        if component:
            self._cache[component_name] = component
        return component

    def _load_component(self, name: str) -> Optional[Any]:
        """根据名称加载对应组件"""
        loaders = {
            'selector': self._load_selector,
            'enhanced_calc': self._load_enhanced_calc,
            'anti_top': self._load_anti_top,
            'factor_engine': self._load_factor_engine,
        }
        loader = loaders.get(name)
        return loader() if loader else None

    def _load_selector(self) -> Optional[Any]:
        try:
            from a_stock_selector_v12_optimized import HuanfangStockSelectorV12
            return HuanfangStockSelectorV12(use_real_data=False)
        except ImportError as e:
            logger.warning("选股器加载失败: %s", e)
            return None

    def _load_enhanced_calc(self) -> Optional[Any]:
        try:
            from enhanced_factor_calculator import EnhancedFactorCalculator
            return EnhancedFactorCalculator()
        except ImportError as e:
            logger.warning("增强因子计算器加载失败: %s", e)
            return None

    def _load_anti_top(self) -> Optional[Any]:
        try:
            from anti_top_factors import AntiTopFilter
            return AntiTopFilter()
        except ImportError as e:
            logger.warning("防顶过滤器加载失败: %s", e)
            return None

    def _load_factor_engine(self) -> Optional[Any]:
        try:
            from factor_engine_v2 import FactorEngineV2
            return FactorEngineV2()
        except ImportError as e:
            logger.warning("因子引擎V2加载失败: %s", e)
            return None

    def preload_all(self) -> None:
        """预加载所有组件（可选，用于预热）"""
        for name in ['selector', 'enhanced_calc', 'anti_top', 'factor_engine']:
            self.get(name)


# ================================================================
# StockFilter — 股票过滤器
# ================================================================

class StockFilter:
    """
    股票过滤器 — 预筛除不合格标的

    过滤规则:
    - ST/*ST 股票
    - 科创板 (688xxx)
    - 次新股 (< N 天数据)
    - 高价股 (> 100 元)
    """

    def __init__(self, config: Optional[SelectionConfig] = None):
        self.cfg = config or SelectionConfig()

    def filter_dataframe(self, stocks_df: pd.DataFrame, name_map: Dict[str, str]) -> pd.DataFrame:
        """
        对股票列表 DataFrame 进行预过滤

        Args:
            stocks_df: DataFrame with columns [symbol, bs_code, name, market]
            name_map: {code: name} 名称映射

        Returns:
            过滤后的 DataFrame
        """
        if self.cfg.filter_st:
            mask_st = ~stocks_df['name'].str.contains(r'ST', case=False, na=False)
            stocks_df = stocks_df[mask_st].copy()

        if self.cfg.filter_kcb:
            mask_kcb = ~stocks_df['symbol'].str.match(r'^688')
            stocks_df = stocks_df[mask_kcb].copy()

        return stocks_df

    def filter_by_data(
        self,
        stock_data: Dict[str, pd.DataFrame],
        min_rows: Optional[int] = None,
    ) -> Dict[str, pd.DataFrame]:
        """
        基于实际数据过滤（次新股、高价股）

        Args:
            stock_data: {symbol: DataFrame}
            min_rows: 最小数据行数（默认 = 80% * cfg.ipo_days）

        Returns:
            过滤后的 stock_data
        """
        if min_rows is None:
            min_rows = int(self.cfg.filter_ipo_days * 0.8)

        filtered = {}
        ipo_count = 0
        price_count = 0

        for sym, df in stock_data.items():
            if len(df) < min_rows:
                ipo_count += 1
                continue
            if self.cfg.filter_max_price and df['close'].iloc[-1] > self.cfg.filter_max_price:
                price_count += 1
                continue
            filtered[sym] = df

        if ipo_count > 0:
            logger.info("  次新股过滤: {len(stock_data)} → {len(filtered)} (%s 只)", ipo_count)
        if price_count > 0:
            logger.info("  高价股过滤: {len(stock_data)} → {len(filtered)} (%s 只)", price_count)

        return filtered

    def filter_price(self, stock_data: Dict[str, pd.DataFrame]) -> Dict[str, pd.DataFrame]:
        """仅过滤高价股"""
        return {
            sym: df for sym, df in stock_data.items()
            if not self.cfg.filter_max_price or df['close'].iloc[-1] <= self.cfg.filter_max_price
        }

    # ===== V15 改进：选股池精细化筛选 =====

    def filter_by_liquidity(
        self,
        stock_data: Dict[str, pd.DataFrame],
    ) -> Dict[str, pd.DataFrame]:
        """
        流动性过滤 - 基于换手率和成交额

        过滤规则:
        - 日均换手率 < filter_min_turnover (%)
        - 日均成交额 < filter_min_avg_amount (元)
        - 成交额排名 > filter_top_by_volume
        """
        if not stock_data:
            return stock_data

        # 计算每只股票的流动指标
        liquidity_scores = {}
        for sym, df in stock_data.items():
            if len(df) < 20:
                continue
            # 近期20日平均
            recent = df.tail(20)
            # 兼容 'turn' 和 'turnover' 列
            if 'turn' in recent.columns:
                avg_turn = recent['turn'].mean()
            elif 'turnover' in recent.columns:
                avg_turn = recent['turnover'].mean()
            else:
                avg_turn = 0
            avg_amount = recent['amount'].mean() if 'amount' in recent.columns else 0
            liquidity_scores[sym] = {
                'turn': avg_turn,
                'amount': avg_amount,
            }

        if not liquidity_scores:
            return stock_data

        # 过滤低换手率
        filtered = {}
        low_turn_count = 0
        low_amount_count = 0

        for sym, scores in liquidity_scores.items():
            if scores['turn'] < self.cfg.filter_min_turnover:
                low_turn_count += 1
                continue
            if scores['amount'] < self.cfg.filter_min_avg_amount:
                low_amount_count += 1
                continue
            filtered[sym] = stock_data[sym]

        # 按成交额排序，取前N只
        if self.cfg.filter_top_by_volume > 0 and filtered:
            sorted_stocks = sorted(
                liquidity_scores.items(),
                key=lambda x: x[1]['amount'],
                reverse=True
            )
            top_codes = set([s[0] for s in sorted_stocks[:self.cfg.filter_top_by_volume]])
            filtered = {k: v for k, v in filtered.items() if k in top_codes}

        if low_turn_count > 0:
            logger.info("  低换手率过滤: {len(stock_data)} → {len(filtered)} (%s 只)", low_turn_count)
        if low_amount_count > 0:
            logger.info("  低成交额过滤: {len(stock_data)} → {len(filtered)} (%s 只)", low_amount_count)

        return filtered

    def filter_by_suspended_days(
        self,
        stock_data: Dict[str, pd.DataFrame],
    ) -> Dict[str, pd.DataFrame]:
        """停牌天数过滤 - 过滤连续停牌超过N天的股票"""
        if not stock_data or self.cfg.filter_max_suspended_days <= 0:
            return stock_data

        filtered = {}
        suspended_count = 0

        for sym, df in stock_data.items():
            if len(df) < 5:
                suspended_count += 1
                continue

            # 检查最近N天是否有交易
            recent = df.tail(self.cfg.filter_max_suspended_days + 5)
            # 换手率为0可能是停牌
            if 'turn' in recent.columns:
                zero_turn_days = (recent['turn'] == 0).sum()
                if zero_turn_days >= self.cfg.filter_max_suspended_days:
                    suspended_count += 1
                    continue

            filtered[sym] = df

        if suspended_count > 0:
            logger.info("  停牌过滤: {len(stock_data)} → {len(filtered)} (%s 只)", suspended_count)

        return filtered


# ================================================================
# V15Scorer — v15 统一评分器
# ================================================================

class V15Scorer:
    """
    v15 统一评分器 — 五层加权评分 + 防顶过滤 + 因子引擎V2

    评分模型:
    1. 基础因子 (50%): v12 的 9 因子综合评分（MACD、RSI、布林带等）
    2. 增强因子 (20%): 假突破过滤 + 动量加速 + K线形态 + VWAP
    3. 市场环境 (15%): 北向资金 + 融资融券 + 大盘资金流 + 板块强度
    4. 因子引擎V2 (15%): 51个日频因子综合调整系数
    5. 防顶惩罚: 10因子见顶风险评估

    用法:
        # 基础用法（自动加载组件）
        scorer = V15Scorer(config)
        result = scorer.score(sym, sdf, market_state, fund_data)

        # 依赖注入用法（便于测试和自定义）
        scorer = V15Scorer(
            config,
            selector=my_selector,
            enhanced_calc=my_calc,
            anti_top=my_anti_top,
            factor_engine=my_engine
        )

    Attributes:
        total_score: 最终评分 (0-1)
        base_score: 基础因子评分
        enhanced_score: 增强因子评分
        factor_v2_coef: 因子引擎V2调整系数
        anti_top_penalty: 防顶惩罚系数
    """

    def __init__(
        self,
        config: Optional[QuantConfig] = None,
        selector: Optional[Any] = None,
        enhanced_calc: Optional[Any] = None,
        anti_top: Optional[Any] = None,
        factor_engine: Optional[Any] = None,
        use_lazy_load: bool = True,
    ):
        """
        初始化 V15Scorer

        Args:
            config: 量化配置
            selector: 选股器实例（可选，优先级高于自动加载）
            enhanced_calc: 增强因子计算器实例（可选）
            anti_top: 防顶过滤器实例（可选）
            factor_engine: 因子引擎实例（可选）
            use_lazy_load: 是否使用延迟加载（默认True）
        """
        self.cfg = config or QuantConfig()

        # 依赖注入优先，否则使用延迟加载
        if selector or enhanced_calc or anti_top or factor_engine:
            self._components = {
                "selector": selector,
                "enhanced_calc": enhanced_calc,
                "anti_top": anti_top,
                "factor_engine": factor_engine,
            }
            self._initialized = True
            self._lazy_loader = None
        else:
            self._components = None
            self._initialized = False
            self._lazy_loader = LazyComponentLoader() if use_lazy_load else None

    def _ensure_init(self):
        """确保组件已初始化（延迟加载）"""
        if self._initialized:
            return

        if self._lazy_loader:
            self._components = {
                "selector": self._lazy_loader.get('selector'),
                "enhanced_calc": self._lazy_loader.get('enhanced_calc'),
                "anti_top": self._lazy_loader.get('anti_top'),
                "factor_engine": self._lazy_loader.get('factor_engine'),
            }
        else:
            # 兼容旧代码：直接导入
            try:
                from a_stock_selector_v12_optimized import HuanfangStockSelectorV12
                from enhanced_factor_calculator import EnhancedFactorCalculator
                from anti_top_factors import AntiTopFilter
                from factor_engine_v2 import FactorEngineV2

                self._components = {
                    "selector": HuanfangStockSelectorV12(use_real_data=False),
                    "enhanced_calc": EnhancedFactorCalculator(),
                    "anti_top": AntiTopFilter(),
                    "factor_engine": FactorEngineV2(),
                }
            except ImportError as e:
                logger.error("V15Scorer 组件导入失败: %s", e)
                raise

        self._initialized = True
        logger.info("V15Scorer 组件初始化完成")

    def _simple_score(
        self,
        symbol: str,
        df: pd.DataFrame,
        market_state: Optional[dict] = None,
        stock_fund_data: Optional[dict] = None,
        market_factors: Optional[dict] = None,
    ) -> dict:
        """
        简单评分（当依赖模块不可用时使用）
        基于技术指标计算基础评分
        """
        try:
            if df is None or len(df) < 20:
                return None
            
            # 计算简单技术指标
            close = df['close']
            volume = df['volume']
            
            # 1. 动量评分 (20日涨幅)
            returns_20 = (close.iloc[-1] / close.iloc[-20] - 1) if len(df) >= 20 else 0
            momentum_score = np.clip((returns_20 + 0.2) / 0.4, 0, 1) if returns_20 else 0.5
            
            # 2. 成交量评分 (近期量能)
            vol_ma5 = volume.iloc[-5:].mean()
            vol_ma20 = volume.iloc[-20:].mean() if len(df) >= 20 else vol_ma5
            volume_score = np.clip(vol_ma5 / vol_ma20 if vol_ma20 > 0 else 1, 0.5, 1.5)
            
            # 3. 趋势评分 (简单均线)
            ma5 = close.iloc[-5:].mean()
            ma20 = close.iloc[-20:].mean() if len(df) >= 20 else close.mean()
            trend_score = 1.0 if ma5 > ma20 else 0.5
            
            # 4. 波动率评分 (20日标准差)
            returns = close.pct_change().dropna()
            vol = returns.std() if len(returns) >= 20 else 0.02
            volatility_score = np.clip(1 - vol * 10, 0.3, 1.0)
            
            # 综合评分
            base_score = (momentum_score * 0.3 + volume_score * 0.2 + 
                         trend_score * 0.3 + volatility_score * 0.2)
            base_score = float(np.clip(base_score, 0, 1))
            
            # 防顶惩罚 (简化版)
            anti_top_penalty = 1.0
            if returns_20 > 0.5:  # 涨幅超过50%可能有风险
                anti_top_penalty = 0.8
            
            # 最终评分
            final_score = base_score * anti_top_penalty
            
            return {
                'symbol': symbol,
                'total_score': final_score,
                'base_score': base_score,
                'enhanced_score': base_score * 0.8,
                'raw_score': final_score,
                'anti_top_score': anti_top_penalty,
                'anti_top_signals': [],
                'anti_top_triggered': 0,
                'anti_top_filter': False,
                'anti_top_penalty': anti_top_penalty,
                'factor_v2_coef': 1.0,
                'factor_v2_risk': {},
                'factor_v2_categories': {},
                'volatility': vol,
                'cvar': float(np.percentile(returns, 5)) if len(returns) >= 20 else 0,
                'price': float(close.iloc[-1]),
                'change_pct': float((close.iloc[-1] / close.iloc[-2] - 1) * 100) if len(df) >= 2 else 0,
                'volume': float(volume.iloc[-1]),
                'factors': {
                    'momentum_score': momentum_score,
                    'volume_score': volume_score,
                    'trend_score': trend_score,
                    'volatility_score': volatility_score,
                },
            }
        except Exception as e:
            logger.debug("简单评分失败 %s: %s", symbol, e)
            return None

    def score(
        self,
        symbol: str,
        df: pd.DataFrame,
        market_state: Optional[dict] = None,
        stock_fund_data: Optional[dict] = None,
        market_factors: Optional[dict] = None,
    ) -> dict:
        """
        对单只股票进行完整评分

        Args:
            symbol: 股票代码
            df: 日频数据 DataFrame
            market_state: 市场环境状态
            stock_fund_data: 个股资金流数据
            market_factors: 市场因子（包含 aggressiveness 等）

        Returns:
            评分结果字典
        """
        self._ensure_init()

        selector = self._components["selector"]
        enhanced_calc = self._components["enhanced_calc"]
        anti_top = self._components["anti_top"]
        factor_engine = self._components["factor_engine"]

        # 检查组件是否可用，如果不可用使用简单评分
        if selector is None or enhanced_calc is None:
            return self._simple_score(symbol, df, market_state, stock_fund_data, market_factors)

        # 1. 基础评分 (v12 9因子)
        factor_calc = selector.factor_calculator
        factors = factor_calc.calculate_all_factors(df)
        if not factors:
            return None

        base_score = selector.calculate_comprehensive_score(factors)

        # 2. 增强评分
        sector_strengths = {}
        if stock_fund_data:
            sector_strengths = stock_fund_data

        enhanced_factors = enhanced_calc.calculate_stock_factors(
            df, fund_data=stock_fund_data, sector_strengths=sector_strengths
        )

        if market_factors:
            enhanced_score = enhanced_calc.get_adjusted_score(enhanced_factors, market_factors)
        else:
            enhanced_score = base_score * 0.8

        # 提取关键增强因子
        fake_breakout_score = 0
        breakout_validity = 0
        momentum_score = 0
        vwap_trend = 0
        if enhanced_factors:
            for fname in ['fake_breakout_score', 'breakout_validity',
                          'enhanced_momentum_score', 'vwap_trend']:
                s = enhanced_factors.get(fname)
                if s is not None and not s.empty:
                    val = float(s.iloc[-1])
                    if fname == 'fake_breakout_score': fake_breakout_score = val
                    elif fname == 'breakout_validity': breakout_validity = val
                    elif fname == 'enhanced_momentum_score': momentum_score = val
                    elif fname == 'vwap_trend': vwap_trend = val

        # 3. 市场环境调整
        market_mult = 1.0
        if market_state and isinstance(market_state, dict):
            aggressiveness = market_state.get('aggressiveness', 0.5)
            market_mult = 0.7 + aggressiveness * 0.6

        # 4. 加权计算
        weight_base = self.cfg.selection.weight_base
        weight_enhanced = self.cfg.selection.weight_enhanced
        weight_market = self.cfg.selection.weight_market
        weight_factor_v2 = self.cfg.selection.weight_factor_v2

        final = base_score * weight_base + enhanced_score * weight_enhanced
        final *= market_mult

        # 5. 资金流入加分
        if stock_fund_data:
            fund_score = stock_fund_data.get('fund_flow_score', 0)
            final += fund_score * 0.1

        # 假突破二次惩罚
        if stock_fund_data and stock_fund_data.get('fake_breakout_score', 0) > 0.7:
            if stock_fund_data.get('breakout_validity', 0) < 0.3:
                final *= 0.85

        raw_score = float(np.clip(final, 0, 1))

        # 6. 防顶惩罚
        anti_top_result = anti_top.evaluate(df)
        penalty = anti_top.get_score_penalty(anti_top_result)

        # 7. 因子引擎V2
        factor_v2_result = factor_engine.calculate(df)
        factor_v2_coef = factor_v2_result['adjustment_coef']

        final_score = raw_score * penalty * factor_v2_coef
        final_score = float(np.clip(final_score, 0, 1))

        # 合并因子数据
        all_factors = dict(factors)
        all_factors['base_score'] = base_score
        all_factors['enhanced_score'] = enhanced_score
        all_factors['final_score'] = final_score
        all_factors['fake_breakout_score'] = fake_breakout_score
        all_factors['breakout_validity'] = breakout_validity
        all_factors['momentum_score'] = momentum_score
        all_factors['vwap_trend'] = vwap_trend

        # 学术因子
        academic_keys = ['ab_turnover', 'max_ret_reversal', 'idio_volatility',
                       'amihud_illiq', 'vol_shock', 'overnight_gap',
                       'price_jump', 'flow_persistence', 'late_breakout_ratio',
                       'academic_score']
        for ak in academic_keys:
            if ak in enhanced_factors and not enhanced_factors[ak].empty:
                all_factors[ak] = float(enhanced_factors[ak].iloc[-1])

        # 防顶因子
        all_factors['anti_top_score'] = anti_top_result['anti_top_score']
        all_factors['anti_top_triggered'] = anti_top_result['triggered_count']
        all_factors['anti_top_penalty'] = penalty

        # 因子引擎V2
        all_factors['factor_v2_coef'] = factor_v2_coef
        all_factors['factor_v2_overall_signal'] = factor_v2_result['risk_summary'].get('overall_signal', 'neutral')
        for k, v in factor_v2_result['all_factors'].items():
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                all_factors[f'v2_{k}'] = float(v)

        returns = df['close'].pct_change(fill_method=None).dropna()
        vol = float(returns.std()) if len(returns) >= 20 else 0.0
        cvar = float(np.percentile(returns, 5)) if len(returns) >= 20 else 0.0

        return {
            'symbol': symbol,
            'total_score': final_score,
            'base_score': base_score,
            'enhanced_score': enhanced_score,
            'raw_score': raw_score,
            'anti_top_score': anti_top_result['anti_top_score'],
            'anti_top_signals': anti_top_result['signals'],
            'anti_top_triggered': anti_top_result['triggered_count'],
            'anti_top_filter': anti_top_result['should_filter'],
            'anti_top_penalty': penalty,
            'factor_v2_coef': factor_v2_coef,
            'factor_v2_risk': factor_v2_result['risk_summary'],
            'factor_v2_categories': factor_v2_result['category_scores'],
            'volatility': vol,
            'cvar': cvar,
            'price': float(df['close'].iloc[-1]),
            'change_pct': float((df['close'].iloc[-1] / df['close'].iloc[-2] - 1) * 100)
                          if len(df) >= 2 else 0.0,
            'volume': float(df['volume'].iloc[-1]) if len(df) > 0 else 0.0,
            'factors': {
                k: float(v.iloc[-1]) if hasattr(v, 'iloc') and not v.empty
                else float(v) if not isinstance(v, pd.Series) else 0
                for k, v in all_factors.items()
            },
        }

    def score_batch(
        self,
        stock_data: Dict[str, pd.DataFrame],
        market_state: Optional[dict] = None,
        fund_flow_rank: Optional[dict] = None,
        market_factors: Optional[dict] = None,
        batch_print: int = 500,
        max_workers: int = 4,
    ) -> List[dict]:
        """
        批量评分（并行优化）

        Args:
            stock_data: {symbol: DataFrame}
            market_state: 市场环境状态
            fund_flow_rank: 个股资金流排名
            market_factors: 市场因子
            batch_print: 每N只打印进度
            max_workers: 并行线程数（默认4）

        Returns:
            排序后的评分结果列表
        """
        self._ensure_init()

        # 小批量直接串行（避免线程开销）
        if len(stock_data) <= 50:
            return self._score_batch_serial(
                stock_data, market_state, fund_flow_rank, market_factors, batch_print
            )

        # 大批量并行计算
        return self._score_batch_parallel(
            stock_data, market_state, fund_flow_rank, market_factors, batch_print, max_workers
        )

    def _score_batch_serial(
        self,
        stock_data: Dict[str, pd.DataFrame],
        market_state: Optional[dict],
        fund_flow_rank: Optional[dict],
        market_factors: Optional[dict],
        batch_print: int,
    ) -> List[dict]:
        """串行批量评分（小批量时使用）"""
        results = []
        errors = 0

        for i, (sym, sdf) in enumerate(stock_data.items()):
            try:
                stock_fund_data = fund_flow_rank.get(sym, None) if fund_flow_rank else None
                result = self.score(sym, sdf, market_state, stock_fund_data, market_factors)
                if result:
                    results.append(result)
            except Exception as e:
                logger.debug("scoring failed for %s: %s", sym, e)
                errors += 1

            if (i + 1) % batch_print == 0:
                logger.info(f"  评分进度 {i+1}/{len(stock_data)} | 已评分 {len(results)}")

        results.sort(key=lambda x: x['total_score'], reverse=True)
        logger.info("  评分完成: {len(results)} 只 | 失败: %s 只", errors)
        return results

    def _score_batch_parallel(
        self,
        stock_data: Dict[str, pd.DataFrame],
        market_state: Optional[dict],
        fund_flow_rank: Optional[dict],
        market_factors: Optional[dict],
        batch_print: int,
        max_workers: int,
    ) -> List[dict]:
        """并行批量评分（大批量时使用）"""
        from concurrent.futures import ThreadPoolExecutor, as_completed
        import threading

        results = []
        errors = [0]  # 使用列表以便在闭包中修改
        lock = threading.Lock()
        processed = [0]

        def _score_one(item):
            sym, sdf = item
            try:
                stock_fund_data = fund_flow_rank.get(sym, None) if fund_flow_rank else None
                result = self.score(sym, sdf, market_state, stock_fund_data, market_factors)
                if result:
                    with lock:
                        results.append(result)
                return True
            except Exception as e:
                logger.debug("parallel scoring failed for %s: %s", sym, e)
                with lock:
                    errors[0] += 1
                return False

        items = list(stock_data.items())
        total = len(items)

        logger.info("  启动并行评分: %s 只股票, %s 线程", total, max_workers)

        with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix='scorer') as executor:
            futures = {executor.submit(_score_one, item): item for item in items}

            for future in as_completed(futures):
                future.result()  # 触发异常
                processed[0] += 1
                if processed[0] % batch_print == 0 or processed[0] == total:
                    logger.info("  评分进度 {processed[0]}/%s | 已评分 {len(results)}", total)

        results.sort(key=lambda x: x['total_score'], reverse=True)
        logger.info(f"  评分完成: {len(results)} 只 | 失败: {errors[0]} 只")
        return results


# ================================================================
# V16Scorer — v16 统一评分器（优化版）
# ================================================================

class V16Scorer(V15Scorer):
    """
    v16 统一评分器 — 优化版，增强风险控制和策略稳定性

    评分模型 (优化):
    1. 基础因子 (20%): v12 的 9 因子综合评分（MACD、RSI、布林带等）
    2. 增强因子 (35%): 假突破过滤 + 动量加速 + K线形态 + VWAP
    3. 市场环境 (15%): 北向资金 + 融资融券 + 大盘资金流 + 板块强度
    4. 因子引擎V2 (30%): 51个日频因子综合调整系数（增强行为金融因子权重）
    5. 风险控制: 波动率约束 + 回撤控制 + 行业分散化

    优化重点:
    - 提升风险调整后收益
    - 降低最大回撤
    - 增强策略稳定性
    - 调仓周期控制在7个自然日以内

    用法:
        scorer = V16Scorer(config)
        result = scorer.score(sym, sdf, market_state, fund_data)
    """

    def __init__(
        self,
        config: Optional[QuantConfig] = None,
        selector: Optional[Any] = None,
        enhanced_calc: Optional[Any] = None,
        anti_top: Optional[Any] = None,
        factor_engine: Optional[Any] = None,
        use_lazy_load: bool = True,
    ):
        """
        初始化 V16Scorer

        Args:
            config: 量化配置
            selector: 选股器实例（可选，优先级高于自动加载）
            enhanced_calc: 增强因子计算器实例（可选）
            anti_top: 防顶过滤器实例（可选）
            factor_engine: 因子引擎实例（可选）
            use_lazy_load: 是否使用延迟加载（默认True）
        """
        # 直接调用 V15Scorer 的 __init__ 方法
        V15Scorer.__init__(
            self,
            config=config,
            selector=selector,
            enhanced_calc=enhanced_calc,
            anti_top=anti_top,
            factor_engine=factor_engine,
            use_lazy_load=use_lazy_load
        )
        logger.info("V16Scorer 初始化完成")

    def score(
        self,
        symbol: str,
        df: pd.DataFrame,
        market_state: Optional[dict] = None,
        stock_fund_data: Optional[dict] = None,
        market_factors: Optional[dict] = None,
    ) -> dict:
        """
        对单只股票进行完整评分（优化版）

        Args:
            symbol: 股票代码
            df: 日频数据 DataFrame
            market_state: 市场环境状态
            stock_fund_data: 个股资金流数据
            market_factors: 市场因子（包含 aggressiveness 等）

        Returns:
            评分结果字典
        """
        self._ensure_init()

        selector = self._components["selector"]
        enhanced_calc = self._components["enhanced_calc"]
        anti_top = self._components["anti_top"]
        factor_engine = self._components["factor_engine"]

        # 检查组件是否可用，如果不可用使用简单评分
        if selector is None or enhanced_calc is None:
            return self._simple_score(symbol, df, market_state, stock_fund_data, market_factors)

        # 1. 基础评分 (v12 9因子)
        factor_calc = selector.factor_calculator
        factors = factor_calc.calculate_all_factors(df)
        if not factors:
            return None

        base_score = selector.calculate_comprehensive_score(factors)

        # 2. 增强评分
        sector_strengths = {}
        if stock_fund_data:
            sector_strengths = stock_fund_data

        enhanced_factors = enhanced_calc.calculate_stock_factors(
            df, fund_data=stock_fund_data, sector_strengths=sector_strengths
        )

        if market_factors:
            enhanced_score = enhanced_calc.get_adjusted_score(enhanced_factors, market_factors)
        else:
            enhanced_score = base_score * 0.8

        # 提取关键增强因子
        fake_breakout_score = 0
        breakout_validity = 0
        momentum_score = 0
        vwap_trend = 0
        if enhanced_factors:
            for fname in ['fake_breakout_score', 'breakout_validity',
                          'enhanced_momentum_score', 'vwap_trend']:
                s = enhanced_factors.get(fname)
                if s is not None and not s.empty:
                    val = float(s.iloc[-1])
                    if fname == 'fake_breakout_score': fake_breakout_score = val
                    elif fname == 'breakout_validity': breakout_validity = val
                    elif fname == 'enhanced_momentum_score': momentum_score = val
                    elif fname == 'vwap_trend': vwap_trend = val

        # 3. 市场环境调整
        market_mult = 1.0
        if market_state and isinstance(market_state, dict):
            aggressiveness = market_state.get('aggressiveness', 0.5)
            market_mult = 0.7 + aggressiveness * 0.6

        # 4. 加权计算（优化权重）
        weight_base = self.cfg.selection.weight_base
        weight_enhanced = self.cfg.selection.weight_enhanced
        weight_market = self.cfg.selection.weight_market
        weight_factor_v2 = self.cfg.selection.weight_factor_v2

        final = base_score * weight_base + enhanced_score * weight_enhanced
        final *= market_mult

        # 5. 资金流入加分
        if stock_fund_data:
            fund_score = stock_fund_data.get('fund_flow_score', 0)
            final += fund_score * 0.1

        # 假突破二次惩罚
        if stock_fund_data and stock_fund_data.get('fake_breakout_score', 0) > 0.7:
            if stock_fund_data.get('breakout_validity', 0) < 0.3:
                final *= 0.85

        raw_score = float(np.clip(final, 0, 1))

        # 6. 防顶惩罚
        anti_top_result = anti_top.evaluate(df)
        penalty = anti_top.get_score_penalty(anti_top_result)

        # 7. 因子引擎V2（优化版）
        factor_v2_result = factor_engine.calculate(df)
        factor_v2_coef = factor_v2_result['adjustment_coef']

        # 8. 风险控制调整
        risk_adjustment = 1.0
        
        # 波动率控制
        returns = df['close'].pct_change(fill_method=None).dropna()
        if len(returns) >= 20:
            vol = float(returns.std())
            annualized_vol = vol * np.sqrt(252)
            if annualized_vol > self.cfg.selection.max_volatility:
                risk_adjustment *= 0.8
        
        # 回撤控制
        if len(df) >= 20:
            close_prices = df['close']
            rolling_max = close_prices.rolling(window=20).max()
            drawdown = (close_prices - rolling_max) / rolling_max
            max_drawdown = drawdown.min()
            if max_drawdown < -self.cfg.selection.stop_loss_pct:
                risk_adjustment *= 0.7

        # 最终评分
        final_score = raw_score * penalty * factor_v2_coef * risk_adjustment
        final_score = float(np.clip(final_score, 0, 1))

        # 合并因子数据
        all_factors = dict(factors)
        all_factors['base_score'] = base_score
        all_factors['enhanced_score'] = enhanced_score
        all_factors['final_score'] = final_score
        all_factors['fake_breakout_score'] = fake_breakout_score
        all_factors['breakout_validity'] = breakout_validity
        all_factors['momentum_score'] = momentum_score
        all_factors['vwap_trend'] = vwap_trend

        # 学术因子
        academic_keys = ['ab_turnover', 'max_ret_reversal', 'idio_volatility',
                       'amihud_illiq', 'vol_shock', 'overnight_gap',
                       'price_jump', 'flow_persistence', 'late_breakout_ratio',
                       'academic_score']
        for ak in academic_keys:
            if ak in enhanced_factors and not enhanced_factors[ak].empty:
                all_factors[ak] = float(enhanced_factors[ak].iloc[-1])

        # 防顶因子
        all_factors['anti_top_score'] = anti_top_result['anti_top_score']
        all_factors['anti_top_triggered'] = anti_top_result['triggered_count']
        all_factors['anti_top_penalty'] = penalty

        # 因子引擎V2
        all_factors['factor_v2_coef'] = factor_v2_coef
        all_factors['factor_v2_overall_signal'] = factor_v2_result['risk_summary'].get('overall_signal', 'neutral')
        for k, v in factor_v2_result['all_factors'].items():
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                all_factors[f'v2_{k}'] = float(v)

        # 风险指标
        vol = float(returns.std()) if len(returns) >= 20 else 0.0
        cvar = float(np.percentile(returns, 5)) if len(returns) >= 20 else 0.0

        return {
            'symbol': symbol,
            'total_score': final_score,
            'base_score': base_score,
            'enhanced_score': enhanced_score,
            'raw_score': raw_score,
            'anti_top_score': anti_top_result['anti_top_score'],
            'anti_top_signals': anti_top_result['signals'],
            'anti_top_triggered': anti_top_result['triggered_count'],
            'anti_top_filter': anti_top_result['should_filter'],
            'anti_top_penalty': penalty,
            'factor_v2_coef': factor_v2_coef,
            'factor_v2_risk': factor_v2_result['risk_summary'],
            'factor_v2_categories': factor_v2_result['category_scores'],
            'volatility': vol,
            'cvar': cvar,
            'price': float(df['close'].iloc[-1]),
            'change_pct': float((df['close'].iloc[-1] / df['close'].iloc[-2] - 1) * 100)
                          if len(df) >= 2 else 0.0,
            'volume': float(df['volume'].iloc[-1]) if len(df) > 0 else 0.0,
            'risk_adjustment': risk_adjustment,
            'factors': {
                k: float(v.iloc[-1]) if hasattr(v, 'iloc') and not v.empty
                else float(v) if not isinstance(v, pd.Series) else 0
                for k, v in all_factors.items()
            },
        }


# ================================================================
# MarketAnalyzer — 市场环境分析器
# ================================================================


class MarketAnalyzer:
    """
    市场环境分析器 — 分析市场整体状态和资金流向

    功能:
    1. 北向资金分析
    2. 融资融券分析
    3. 大盘资金流分析
    4. 板块强度分析
    """

    def __init__(self, config: Optional[QuantConfig] = None):
        self.cfg = config or QuantConfig()
        self.lazy_loader = LazyComponentLoader()

    def analyze_market_state(self) -> dict:
        """分析当前市场状态"""
        try:
            from market_factors import MarketStateAnalyzer
            analyzer = MarketStateAnalyzer()
            return analyzer.get_market_state()
        except ImportError:
            # 简化版市场状态分析
            return {
                'market_breadth': 0.5,
                'fund_flow': 0.0,
                'volatility': 0.2,
                'trend': 'neutral',
                'aggressiveness': 0.5
            }

    def get_sector_strengths(self) -> dict:
        """获取板块强度"""
        try:
            from sector_analyzer import SectorAnalyzer
            analyzer = SectorAnalyzer()
            return analyzer.get_sector_strengths()
        except ImportError:
            return {}


# ================================================================
# LLMBroker — LLM 增强代理
# ================================================================


class LLMBroker:
    """
    LLM 增强代理 — 为选股决策提供自然语言理由

    功能:
    1. 生成选股理由
    2. 分析市场热点
    3. 提供投资建议
    """

    def __init__(self, config: Optional[QuantConfig] = None):
        self.cfg = config or QuantConfig()

    def generate_selection_reason(self, symbol: str, factors: dict) -> str:
        """
        为选中的股票生成选股理由

        Args:
            symbol: 股票代码
            factors: 因子数据

        Returns:
            选股理由文本
        """
        try:
            from llm_analyzer import LLMAnalyzer
            analyzer = LLMAnalyzer()
            return analyzer.generate_reason(symbol, factors)
        except ImportError:
            # 简化版选股理由生成
            score = factors.get('total_score', 0)
            base_score = factors.get('base_score', 0)
            enhanced_score = factors.get('enhanced_score', 0)

            reason = f"股票 {symbol} 综合评分 {score:.2f}，"
            reason += f"基础因子评分 {base_score:.2f}，"
            reason += f"增强因子评分 {enhanced_score:.2f}。"
            reason += "技术指标表现良好，具备投资潜力。"

            return reason

    def analyze_market_hotspots(self) -> str:
        """
        分析当前市场热点

        Returns:
            市场热点分析文本
        """
        try:
            from llm_analyzer import LLMAnalyzer
            analyzer = LLMAnalyzer()
            return analyzer.analyze_hotspots()
        except ImportError:
            return "当前市场热点分析不可用，建议关注行业龙头和资金流入板块。"
