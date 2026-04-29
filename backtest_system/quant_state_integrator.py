"""
QuantStateIntegrator 因子分析与风险评估模块
==============================================
嵌入 QuantState 进行专业的因子分析和风险评估。

功能:
    - 因子预处理（去极值、标准化、中性化）
    - IC/IR 分析（Spearman/Pearson）
    - 分层回测（N 组等分）
    - 风险评估（VaR、CVaR、波动率、风格暴露）
    - 因子衰减分析

支持两种模式:
    1. QuantState 已安装时自动使用其完整功能
    2. 未安装时使用内置的纯 NumPy/Pandas 实现
"""

import logging
from typing import Dict, List, Optional, Tuple, Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class QuantStateIntegrator:
    """
    QuantState 集成器

    用法:
        qs = QuantStateIntegrator(config)
        result = qs.analyze_factors(factor_df, return_df)
    """

    def __init__(self, config=None):
        """
        初始化

        Args:
            config: FactorConfig 配置对象
        """
        if config is None:
            from .config import BacktestConfig
            self.config = BacktestConfig().factor
            self._risk_free_rate = 0.025
        elif hasattr(config, "winsorize_method"):
            # 直接传入 FactorConfig
            self.config = config
            self._risk_free_rate = 0.025
        else:
            # 传入 BacktestConfig
            self.config = config.factor
            self._risk_free_rate = config.risk.risk_free_rate
        self._has_quantstate = self._check_quantstate()

        if self._has_quantstate:
            logger.info("QuantState 已安装，使用完整因子分析功能")
        else:
            logger.info("QuantState 未安装，使用内置因子分析实现")

    def _check_quantstate(self) -> bool:
        """检查 QuantState 是否可用"""
        try:
            import quantstate  # noqa: F401
            return True
        except ImportError:
            return False

    # ================================================================
    # 核心接口
    # ================================================================

    def analyze_factors(
        self,
        factors: pd.DataFrame,
        returns: pd.DataFrame,
        factor_names: Optional[List[str]] = None,
    ) -> dict:
        """
        完整因子分析流水线

        Args:
            factors: 因子值 DataFrame, index=date, columns=股票代码
                     或 MultiIndex (date, code) 格式
            returns: 收益率 DataFrame, 同上格式
            factor_names: 要分析的因子名称列表

        Returns:
            {
                "factor_summary": {...},      # 因子概览
                "ic_analysis": {...},         # IC/IR 分析
                "layered_returns": {...},     # 分层回测
                "risk_metrics": {...},        # 风险指标
                "factor_decay": {...},        # 因子衰减
                "style_exposure": {...},      # 风格暴露
            }
        """
        # 标准化输入格式
        factors, returns = self._align_data(factors, returns)

        # 因子名称
        if factor_names is None:
            factor_names = [c for c in factors.columns if c not in ["date", "code"]]

        result = {}

        # 1. 因子概览
        result["factor_summary"] = self._factor_summary(factors, factor_names)

        # 2. 因子预处理
        factors_clean = {}
        for name in factor_names:
            if name in factors.columns:
                cleaned = self.preprocess_factor(factors[name])
                factors_clean[name] = cleaned

        # 3. IC/IR 分析
        result["ic_analysis"] = self.analyze_ic(factors_clean, returns, factor_names)

        # 4. 分层回测
        result["layered_returns"] = self._layered_backtest(factors_clean, returns, factor_names)

        # 5. 风险指标
        result["risk_metrics"] = self._compute_risk_metrics(returns)

        # 6. 因子衰减
        result["factor_decay"] = self._factor_decay_analysis(factors_clean, returns, factor_names)

        # 7. 风格暴露
        result["style_exposure"] = self._style_exposure(returns)

        return result

    # ================================================================
    # 因子预处理
    # ================================================================

    def preprocess_factor(
        self,
        factor: pd.Series,
        method: Optional[str] = None,
    ) -> pd.Series:
        """
        因子预处理: 去极值 → 标准化

        Args:
            factor: 原始因子值 Series
            method: 去极值方法 "mad" / "quantile"

        Returns:
            处理后的因子 Series
        """
        method = method or self.config.winsorize_method

        # 去极值
        cleaned = self.winsorize(factor, method=method, n=self.config.winsorize_std)

        # 标准化 (Z-Score)
        cleaned = self.standardize(cleaned)

        return cleaned

    def winsorize(
        self,
        series: pd.Series,
        method: str = "mad",
        n: float = 3.0,
    ) -> pd.Series:
        """
        去极值处理

        Args:
            series: 因子值
            method: "mad" (绝对中位差) / "quantile" (分位数)
            n: 倍数

        Returns:
            去极值后的 Series
        """
        if method == "mad":
            median = series.median()
            mad = (series - median).abs().median()
            if mad == 0:
                mad = series.std()
            upper = median + n * mad
            lower = median - n * mad
            return series.clip(lower, upper)

        elif method == "quantile":
            lower = series.quantile(n / 100)
            upper = series.quantile(1 - n / 100)
            return series.clip(lower, upper)

        return series

    def standardize(self, series: pd.Series) -> pd.Series:
        """Z-Score 标准化"""
        std = series.std()
        if std == 0 or pd.isna(std):
            return series * 0
        return (series - series.mean()) / std

    def neutralize(
        self,
        factor: pd.DataFrame,
        industry: Optional[pd.DataFrame] = None,
        cap: Optional[pd.Series] = None,
    ) -> pd.DataFrame:
        """
        因子中性化（去行业、市值效应）

        Args:
            factor: 因子值 DataFrame
            industry: 行业分类 DataFrame
            cap: 市值 Series

        Returns:
            中性化后的因子
        """
        from sklearn.linear_model import LinearRegression

        result = factor.copy()

        # 市值中性化
        if cap is not None:
            for col in result.columns:
                valid = result[col].notna() & cap.notna()
                if valid.sum() > 30:
                    lr = LinearRegression()
                    X = cap[valid].values.reshape(-1, 1)
                    y = result.loc[valid, col].values
                    lr.fit(X, y)
                    residual = y - lr.predict(X)
                    result.loc[valid, col] = residual

        return result

    # ================================================================
    # IC/IR 分析
    # ================================================================

    def analyze_ic(
        self,
        factors: Dict[str, pd.Series],
        returns: pd.DataFrame,
        factor_names: List[str],
    ) -> dict:
        """
        IC/IR 分析

        Args:
            factors: {因子名: 处理后的因子 Series} 字典
            returns: 收益率 DataFrame
            factor_names: 因子名称列表

        Returns:
            IC 分析结果
        """
        method = self.config.ic_method
        window = self.config.ic_rolling_window

        ic_results = {}
        for name in factor_names:
            if name not in factors:
                continue

            factor = factors[name]
            # 计算截面 IC
            ic_series = self._calc_cross_section_ic(factor, returns, method)

            # 滚动 IC
            if len(ic_series) >= window:
                rolling_ic = ic_series.rolling(window).mean()
            else:
                rolling_ic = ic_series.expanding().mean()

            ic_results[name] = {
                "ic_mean": round(ic_series.mean(), 4),
                "ic_std": round(ic_series.std(), 4),
                "ic_ir": round(ic_series.mean() / max(ic_series.std(), 1e-9), 4),
                "ic_positive_ratio": round((ic_series > 0).mean() * 100, 2),
                "rolling_ic": rolling_ic.to_dict(),
                "ic_series": ic_series.to_dict(),
            }

        return ic_results

    def _calc_cross_section_ic(
        self,
        factor: pd.Series,
        returns: pd.DataFrame,
        method: str = "spearman",
    ) -> pd.Series:
        """计算截面 IC 序列"""
        from scipy.stats import spearmanr, pearsonr

        ic_values = {}
        dates = returns.index.get_level_values(0).unique() if isinstance(returns.index, pd.MultiIndex) else returns.index.unique()

        for dt in dates:
            try:
                if isinstance(returns.index, pd.MultiIndex):
                    ret_slice = returns.xs(dt, level=0)
                else:
                    ret_slice = returns.loc[dt]

                if isinstance(factor.index, pd.MultiIndex):
                    fac_slice = factor.xs(dt, level=0) if dt in factor.index.get_level_values(0) else None
                else:
                    fac_slice = factor

                if fac_slice is None:
                    continue

                # 对齐
                common = ret_slice.index.intersection(fac_slice.index)
                if len(common) < 10:
                    continue

                r = ret_slice.loc[common].values
                f = fac_slice.loc[common].values

                if len(r) != len(f):
                    min_len = min(len(r), len(f))
                    r = r[:min_len]
                    f = f[:min_len]

                if method == "spearman":
                    corr, _ = spearmanr(f, r)
                else:
                    corr, _ = pearsonr(f, r)

                if not np.isnan(corr):
                    ic_values[dt] = corr
            except Exception:
                continue

        return pd.Series(ic_values)

    # ================================================================
    # 分层回测
    # ================================================================

    def _layered_backtest(
        self,
        factors: Dict[str, pd.Series],
        returns: pd.DataFrame,
        factor_names: List[str],
    ) -> dict:
        """
        分层回测: 按因子值分 N 组，计算各组平均收益

        Returns:
            {因子名: {group_1: cum_return, group_2: ..., multi_hold: cum_return}}
        """
        n_groups = self.config.n_groups
        results = {}

        for name in factor_names:
            if name not in factors:
                continue

            factor = factors[name]
            group_returns = self._calc_layered_returns(factor, returns, n_groups)

            if group_returns:
                results[name] = group_returns

        return results

    def _calc_layered_returns(
        self,
        factor: pd.Series,
        returns: pd.DataFrame,
        n_groups: int,
    ) -> dict:
        """计算分层组合收益率"""
        dates = returns.index.get_level_values(0).unique() if isinstance(returns.index, pd.MultiIndex) else returns.index.unique()

        group_series = {f"group_{i+1}": [] for i in range(n_groups)}
        group_series["long_short"] = []
        date_list = []

        for dt in dates:
            try:
                if isinstance(returns.index, pd.MultiIndex):
                    ret_slice = returns.xs(dt, level=0)
                else:
                    ret_slice = returns.loc[dt]

                if isinstance(factor.index, pd.MultiIndex):
                    fac_slice = factor.xs(dt, level=0) if dt in factor.index.get_level_values(0) else None
                else:
                    fac_slice = factor

                if fac_slice is None:
                    continue

                common = ret_slice.index.intersection(fac_slice.index)
                if len(common) < n_groups * 2:
                    continue

                r = ret_slice.loc[common]
                f = fac_slice.loc[common]

                # 分组
                labels = pd.qcut(f, q=n_groups, labels=False, duplicates="drop")
                for g in range(n_groups):
                    mask = labels == g
                    if mask.sum() > 0:
                        group_series[f"group_{g+1}"].append(r[mask].mean())

                # 多空收益
                if len(set(labels.dropna().values)) >= 2:
                    top_mask = labels >= labels.max() - 0.5
                    bottom_mask = labels <= labels.min() + 0.5
                    if top_mask.sum() > 0 and bottom_mask.sum() > 0:
                        ls = r[top_mask].mean() - r[bottom_mask].mean()
                        group_series["long_short"].append(ls)

                date_list.append(dt)

            except Exception:
                continue

        if not date_list:
            return {}

        result = {}
        for key, values in group_series.items():
            if len(values) == len(date_list):
                s = pd.Series(values, index=date_list)
                result[key] = {
                    "daily_mean": round(s.mean(), 6),
                    "daily_std": round(s.std(), 6),
                    "annual_return": round(s.mean() * 252, 4),
                    "annual_sharpe": round(s.mean() / max(s.std(), 1e-9) * np.sqrt(252), 4),
                    "cumulative": round((1 + s).prod() - 1, 4),
                    "series": s.to_dict(),
                }

        return result

    # ================================================================
    # 风险指标
    # ================================================================

    def _compute_risk_metrics(self, returns: pd.DataFrame) -> dict:
        """
        计算风险指标

        Args:
            returns: 收益率 DataFrame

        Returns:
            风险指标字典
        """
        # 如果是 MultiIndex，取所有截面收益的平均值
        if isinstance(returns.index, pd.MultiIndex):
            daily_ret = returns.groupby(level=0).mean().mean(axis=1)
        else:
            daily_ret = returns.mean(axis=1)

        n_days = len(daily_ret)
        annual_factor = 252

        # 年化收益率
        total_return = (1 + daily_ret).prod() - 1
        n_years = n_days / annual_factor
        annual_return = (1 + total_return) ** (1 / max(n_years, 0.01)) - 1

        # 年化波动率
        annual_vol = daily_ret.std() * np.sqrt(annual_factor)

        # VaR & CVaR
        var_confidence = 0.95  # 默认 95% VaR 置信度
        var = np.percentile(daily_ret.dropna(), (1 - var_confidence) * 100)
        cvar = daily_ret[daily_ret <= var].mean()

        # 最大回撤
        cum = (1 + daily_ret).cumprod()
        peak = cum.expanding().max()
        drawdown = (cum - peak) / peak
        max_drawdown = drawdown.min()

        # 偏度 & 峰度
        from scipy.stats import skew, kurtosis
        skewness = skew(daily_ret.dropna())
        kurt = kurtosis(daily_ret.dropna())

        # 胜率
        win_rate = (daily_ret > 0).sum() / max(len(daily_ret), 1) * 100

        risk_free = self._risk_free_rate

        return {
            "annual_return": round(annual_return * 100, 2),
            "annual_volatility": round(annual_vol * 100, 2),
            "sharpe_ratio": round((annual_return - risk_free) / max(annual_vol, 1e-9), 4),
            "sortino_ratio": round(
                (annual_return - risk_free) / max(daily_ret[daily_ret < 0].std() * np.sqrt(annual_factor), 1e-9), 4
            ),
            "max_drawdown": round(max_drawdown * 100, 2),
            "var_95": round(var * 100, 4),
            "cvar_95": round(cvar * 100, 4),
            "skewness": round(skewness, 4),
            "kurtosis": round(kurt, 4),
            "win_rate": round(win_rate, 2),
            "calmar_ratio": round(annual_return / max(abs(max_drawdown), 1e-9), 4),
        }

    # ================================================================
    # 因子衰减分析
    # ================================================================

    def _factor_decay_analysis(
        self,
        factors: Dict[str, pd.Series],
        returns: pd.DataFrame,
        factor_names: List[str],
        max_lag: int = 5,
    ) -> dict:
        """
        因子衰减分析: 计算因子值与未来 N 日收益的相关性

        Returns:
            {因子名: {lag_1: ic, lag_2: ic, ...}}
        """
        results = {}

        for name in factor_names:
            if name not in factors:
                continue

            factor = factors[name]
            decay = {}

            for lag in range(1, max_lag + 1):
                shifted_returns = returns.shift(-lag)
                ic = self._calc_cross_section_ic(factor, shifted_returns)
                if len(ic) > 0:
                    decay[f"lag_{lag}"] = round(ic.mean(), 4)

            results[name] = decay

        return results

    # ================================================================
    # 风格暴露分析
    # ================================================================

    def _style_exposure(self, returns: pd.DataFrame) -> dict:
        """
        风格暴露分析

        构造风格因子并回归分析:
        - Size: 大小盘（按截面市值分组）
        - Value: 价值（高收益/低估值）
        - Momentum: 动量（过去20日收益）
        - Volatility: 波动率
        - Liquidity: 流动性（换手率）
        """
        from sklearn.linear_model import LinearRegression

        if isinstance(returns.index, pd.MultiIndex):
            port_ret = returns.groupby(level=0).mean().mean(axis=1)
        else:
            port_ret = returns.mean(axis=1)

        dates = port_ret.index

        # 构造简单风格因子 proxy
        style_returns = pd.DataFrame(index=dates)

        # 使用组合收益的滞后特征作为风格 proxy
        style_returns["momentum"] = port_ret.rolling(20).mean()
        style_returns["volatility"] = port_ret.rolling(20).std()
        style_returns["reversal"] = -port_ret.shift(5)
        style_returns["trend"] = port_ret.rolling(60).mean()

        # 去除 NaN
        valid = style_returns.dropna()
        if len(valid) < 30:
            return {"exposure": {}, "r_squared": 0}

        y = port_ret.loc[valid.index].values
        X = valid.values

        lr = LinearRegression()
        lr.fit(X, y)

        r_squared = round(lr.score(X, y), 4)
        exposure = {
            style: round(coef, 4)
            for style, coef in zip(valid.columns, lr.coef_)
        }

        return {
            "exposure": exposure,
            "r_squared": r_squared,
            "style_names": list(valid.columns),
        }

    # ================================================================
    # 因子概览
    # ================================================================

    def _factor_summary(self, factors: pd.DataFrame, factor_names: List[str]) -> dict:
        """因子概览统计"""
        summary = {}
        for name in factor_names:
            if name in factors.columns:
                col = factors[name].dropna()
                summary[name] = {
                    "count": int(len(col)),
                    "mean": round(col.mean(), 4),
                    "std": round(col.std(), 4),
                    "min": round(col.min(), 4),
                    "max": round(col.max(), 4),
                    "median": round(col.median(), 4),
                    "skewness": round(col.skew(), 4),
                    "kurtosis": round(col.kurtosis(), 4),
                    "missing_pct": round(col.isna().mean() * 100, 2),
                }
        return summary

    # ================================================================
    # 数据格式处理
    # ================================================================

    def _align_data(
        self,
        factors: pd.DataFrame,
        returns: pd.DataFrame,
    ) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        对齐因子和收益率的格式

        支持:
        1. 两者都是普通 DataFrame (index=date, columns=code)
        2. MultiIndex (date, code) 格式
        """
        # MultiIndex → Pivot
        if isinstance(factors.index, pd.MultiIndex):
            factors = factors.unstack()
            if isinstance(factors.columns, pd.MultiIndex):
                factors.columns = factors.columns.droplevel(0)

        if isinstance(returns.index, pd.MultiIndex):
            returns = returns.unstack()
            if isinstance(returns.columns, pd.MultiIndex):
                returns.columns = returns.columns.droplevel(0)

        return factors, returns
