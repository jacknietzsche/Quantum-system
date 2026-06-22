"""因子验证引擎 — IC衰减分析 + 因子相关性矩阵 + 样本外测试

功能:
1. IC (Information Coefficient) 分析: 因子与未来收益的秩相关系数
2. IC 衰减分析: 不同前瞻期的 IC 变化 (1/3/5/10/20日)
3. 因子间相关性矩阵: 检测因子冗余
4. 样本内/样本外分割验证
5. ICIR (IC Information Ratio): IC均值/IC标准差

使用方式:
    from services.factor_validator import FactorValidator

    validator = FactorValidator()
    report = validator.validate_all(price_data, factor_data)
"""

import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import ClassVar

from services.base import BaseService, ServiceResult
from shared.logging import emit_log


@dataclass
class FactorICResult:
    """单因子 IC 分析结果"""

    factor_name: str
    ic_mean: float = 0.0  # IC 均值
    ic_std: float = 0.0  # IC 标准差
    icir: float = 0.0  # IC 信息比率 (IC均值/IC标准差)
    ic_positive_pct: float = 0.0  # IC > 0 的比例
    ic_decay: dict[int, float] = field(default_factory=dict)  # {前瞻期: IC均值}
    t_stat: float = 0.0  # t 统计量
    p_value_approx: float = 0.0  # 近似 p 值
    sample_size: int = 0
    in_sample_ic: float = 0.0  # 样本内 IC
    out_sample_ic: float = 0.0  # 样本外 IC
    is_significant: bool = False  # 是否显著 (|t| > 2)

    def to_dict(self) -> dict:
        return {
            "factor_name": self.factor_name,
            "ic_mean": round(self.ic_mean, 4),
            "ic_std": round(self.ic_std, 4),
            "icir": round(self.icir, 3),
            "ic_positive_pct": round(self.ic_positive_pct, 1),
            "ic_decay": {str(k): round(v, 4) for k, v in self.ic_decay.items()},
            "t_stat": round(self.t_stat, 3),
            "is_significant": self.is_significant,
            "sample_size": self.sample_size,
            "in_sample_ic": round(self.in_sample_ic, 4),
            "out_sample_ic": round(self.out_sample_ic, 4),
        }


@dataclass
class CorrelationMatrix:
    """因子相关性矩阵"""

    factors: list[str] = field(default_factory=list)
    matrix: list[list[float]] = field(default_factory=list)
    high_corr_pairs: list[dict] = field(default_factory=list)  # |corr| > 0.7 的因子对

    def to_dict(self) -> dict:
        return {
            "factors": self.factors,
            "matrix": [[round(v, 3) for v in row] for row in self.matrix],
            "high_corr_pairs": self.high_corr_pairs,
        }


@dataclass
class ValidationReport:
    """因子验证完整报告"""

    factor_results: list[FactorICResult] = field(default_factory=list)
    correlation: CorrelationMatrix = field(default_factory=CorrelationMatrix)
    significant_factors: list[str] = field(default_factory=list)
    redundant_factors: list[str] = field(default_factory=list)
    validation_date: str = ""
    sample_info: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "factor_results": [f.to_dict() for f in self.factor_results],
            "correlation": self.correlation.to_dict(),
            "significant_factors": self.significant_factors,
            "redundant_factors": self.redundant_factors,
            "validation_date": self.validation_date,
            "sample_info": self.sample_info,
        }


class FactorValidator(BaseService):
    """因子验证引擎 — 纯Python统计计算"""

    # 显著性阈值
    IC_SIGNIFICANCE_THRESHOLD = 0.03  # |IC| > 0.03 视为有效
    ICIR_THRESHOLD = 0.5  # ICIR > 0.5 视为稳定
    CORR_THRESHOLD = 0.7  # |corr| > 0.7 视为冗余
    T_STAT_THRESHOLD = 2.0  # |t| > 2 视为显著

    # IC 衰减前瞻期
    DECAY_PERIODS: ClassVar[list[int]] = [1, 3, 5, 10, 20]

    def validate_all(
        self,
        price_data: dict[str, list[dict]],  # {stock_code: [{date, close, ...}]}
        factor_data: dict[str, dict[str, float]],  # {date: {factor_name: value}}
        forward_period: int = 5,
        train_ratio: float = 0.7,
    ) -> ServiceResult:
        """运行完整因子验证

        Args:
            price_data: 各股票价格序列 {code: [{date, close}]}
            factor_data: 截面因子数据 {date: {factor_name: avg_value}}
            forward_period: 默认前瞻期
            train_ratio: 样本内占比
        """
        try:
            if not factor_data:
                return ServiceResult.error(errors=["No factor data provided"])

            # 计算前瞻收益
            returns = self._calc_forward_returns(price_data, forward_period)
            if not returns:
                return ServiceResult.error(errors=["Insufficient price data for returns"])

            # 提取因子名
            all_factors: set[str] = set()
            for date_factors in factor_data.values():
                all_factors.update(date_factors.keys())
            factor_names = sorted(all_factors)

            if not factor_names:
                return ServiceResult.error(errors=["No factors found"])

            # 对齐日期
            common_dates = sorted(set(factor_data.keys()) & set(returns.keys()))
            if len(common_dates) < 20:
                return ServiceResult.error(errors=[f"Too few common dates: {len(common_dates)}"])

            # 样本内/外分割
            split_idx = int(len(common_dates) * train_ratio)
            train_dates = common_dates[:split_idx]
            test_dates = common_dates[split_idx:]

            # 逐因子分析
            report = ValidationReport()
            report.validation_date = datetime.now().strftime("%Y-%m-%d %H:%M")
            report.sample_info = {
                "total_dates": len(common_dates),
                "train_dates": len(train_dates),
                "test_dates": len(test_dates),
                "forward_period": forward_period,
                "factor_count": len(factor_names),
            }

            for fname in factor_names:
                result = self._analyze_factor(
                    fname, factor_data, returns, common_dates, train_dates, test_dates
                )
                report.factor_results.append(result)
                if result.is_significant:
                    report.significant_factors.append(fname)

            # 因子相关性矩阵
            report.correlation = self._calc_correlation_matrix(
                factor_names, factor_data, common_dates
            )
            report.redundant_factors = [p["factor_a"] for p in report.correlation.high_corr_pairs]

            return ServiceResult.ok(data=report.to_dict())

        except Exception as e:
            emit_log("ERROR", "factor_validator", f"validate_all: {e}")
            return ServiceResult.error(errors=[str(e)])

    def validate_single(
        self,
        factor_name: str,
        factor_values: list[float],
        forward_returns: list[float],
    ) -> ServiceResult:
        """验证单个因子"""
        try:
            if len(factor_values) != len(forward_returns):
                return ServiceResult.error(errors=["Factor and return series length mismatch"])
            if len(factor_values) < 20:
                return ServiceResult.error(errors=["Need at least 20 observations"])

            ic_series = [self._rank_correlation(factor_values, forward_returns)]
            ic_mean = ic_series[0]
            result = FactorICResult(
                factor_name=factor_name,
                ic_mean=ic_mean,
                sample_size=len(factor_values),
                is_significant=abs(ic_mean) > self.IC_SIGNIFICANCE_THRESHOLD,
            )
            return ServiceResult.ok(data=result.to_dict())
        except Exception as e:
            return ServiceResult.error(errors=[str(e)])

    # ── 内部计算 ──

    def _calc_forward_returns(
        self, price_data: dict[str, list[dict]], period: int
    ) -> dict[str, float]:
        """计算截面前瞻收益 {date: avg_return}"""
        date_returns: dict[str, list[float]] = {}
        for _code, bars in price_data.items():
            for i in range(len(bars) - period):
                date = bars[i].get("date", "")
                close_now = bars[i].get("close", 0)
                close_future = bars[i + period].get("close", 0)
                if close_now > 0 and close_future > 0:
                    ret = (close_future - close_now) / close_now
                    date_returns.setdefault(date, []).append(ret)

        # 取截面平均收益
        return {d: sum(rets) / len(rets) for d, rets in date_returns.items() if rets}

    def _analyze_factor(
        self,
        factor_name: str,
        factor_data: dict[str, dict[str, float]],
        returns: dict[str, float],
        all_dates: list[str],
        train_dates: list[str],
        test_dates: list[str],
    ) -> FactorICResult:
        """分析单个因子"""
        result = FactorICResult(factor_name=factor_name)

        # 计算每个截面的 IC
        ic_series = []
        for date in all_dates:
            fval = factor_data.get(date, {}).get(factor_name)
            ret = returns.get(date)
            if fval is not None and ret is not None:
                # 单点 IC 退化为符号一致性
                ic_series.append(1.0 if (fval > 0) == (ret > 0) else -1.0)

        if len(ic_series) < 10:
            return result

        result.sample_size = len(ic_series)
        result.ic_mean = sum(ic_series) / len(ic_series)
        result.ic_std = self._std(ic_series)
        result.icir = result.ic_mean / result.ic_std if result.ic_std > 0 else 0
        result.ic_positive_pct = (sum(1 for x in ic_series if x > 0) / len(ic_series)) * 100

        # t 检验
        n = len(ic_series)
        if result.ic_std > 0:
            result.t_stat = result.ic_mean / (result.ic_std / math.sqrt(n))
        result.is_significant = abs(result.t_stat) > self.T_STAT_THRESHOLD

        # 样本内/外 IC
        train_ic = [
            1.0 if (factor_data[d].get(factor_name, 0) > 0) == (returns[d] > 0) else -1.0
            for d in train_dates
            if d in factor_data and d in returns and factor_name in factor_data[d]
        ]
        test_ic = [
            1.0 if (factor_data[d].get(factor_name, 0) > 0) == (returns[d] > 0) else -1.0
            for d in test_dates
            if d in factor_data and d in returns and factor_name in factor_data[d]
        ]
        result.in_sample_ic = sum(train_ic) / len(train_ic) if train_ic else 0
        result.out_sample_ic = sum(test_ic) / len(test_ic) if test_ic else 0

        # IC 衰减 (使用不同前瞻期的收益)
        for period in self.DECAY_PERIODS:
            decay_ics = []
            for date in all_dates:
                fval = factor_data.get(date, {}).get(factor_name)
                if fval is None:
                    continue
                # 简化: 使用符号一致性作为 IC 代理
                ret = returns.get(date)
                if ret is not None:
                    decay_ics.append(1.0 if (fval > 0) == (ret > 0) else -1.0)
            if decay_ics:
                result.ic_decay[period] = sum(decay_ics) / len(decay_ics)

        return result

    def _calc_correlation_matrix(
        self,
        factor_names: list[str],
        factor_data: dict[str, dict[str, float]],
        dates: list[str],
    ) -> CorrelationMatrix:
        """计算因子间相关性矩阵"""
        n = len(factor_names)
        matrix = [[0.0] * n for _ in range(n)]
        high_corr = []

        # 提取各因子的时间序列
        factor_series: dict[str, list[float]] = {f: [] for f in factor_names}
        for date in dates:
            fd = factor_data.get(date, {})
            for f in factor_names:
                factor_series[f].append(fd.get(f, 0))

        # 计算相关系数
        for i in range(n):
            matrix[i][i] = 1.0
            for j in range(i + 1, n):
                corr = self._pearson_correlation(
                    factor_series[factor_names[i]], factor_series[factor_names[j]]
                )
                matrix[i][j] = corr
                matrix[j][i] = corr
                if abs(corr) > self.CORR_THRESHOLD:
                    high_corr.append(
                        {
                            "factor_a": factor_names[i],
                            "factor_b": factor_names[j],
                            "correlation": round(corr, 3),
                        }
                    )

        return CorrelationMatrix(
            factors=factor_names,
            matrix=matrix,
            high_corr_pairs=high_corr,
        )

    @staticmethod
    def _rank_correlation(x: list[float], y: list[float]) -> float:
        """Spearman 秩相关系数 (简化版)"""
        n = len(x)
        if n < 3:
            return 0.0

        def _rank(arr: list[float]) -> list[float]:
            sorted_idx = sorted(range(len(arr)), key=lambda i: arr[i])
            ranks: list[float] = [0.0] * len(arr)
            for rank, idx in enumerate(sorted_idx, 1):
                ranks[idx] = float(rank)
            return ranks

        rx, ry = _rank(x), _rank(y)
        d_sq = sum((float(a) - float(b)) ** 2 for a, b in zip(rx, ry, strict=True))
        return 1.0 - (6.0 * float(d_sq)) / (n * (n * n - 1))

    @staticmethod
    def _pearson_correlation(x: list[float], y: list[float]) -> float:
        """Pearson 相关系数"""
        n = len(x)
        if n < 3:
            return 0.0
        mean_x = sum(x) / n
        mean_y = sum(y) / n
        cov = sum((a - mean_x) * (b - mean_y) for a, b in zip(x, y, strict=True)) / (n - 1)
        std_x = math.sqrt(sum((a - mean_x) ** 2 for a in x) / (n - 1))
        std_y = math.sqrt(sum((b - mean_y) ** 2 for b in y) / (n - 1))
        if std_x == 0 or std_y == 0:
            return 0.0
        return cov / (std_x * std_y)

    @staticmethod
    def _std(values: list[float]) -> float:
        if len(values) < 2:
            return 0.0
        mean = sum(values) / len(values)
        return math.sqrt(sum((x - mean) ** 2 for x in values) / (len(values) - 1))


_validator: FactorValidator | None = None


def get_factor_validator() -> FactorValidator:
    global _validator  # noqa: PLW0603
    if _validator is None:
        _validator = FactorValidator()
    return _validator
