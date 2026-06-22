"""绩效归因系统 — NAV曲线 + 基准对比 + 风险指标 + 收益归因

功能:
1. NAV 曲线: 从 DailyNAV 表构建每日净值序列
2. 基准对比: 对比沪深300收益
3. 风险指标: 夏普比率、最大回撤、Calmar比率、年化波动率
4. 收益归因: 选股收益 vs 择时收益 vs 仓位收益 (Brinson模型简化版)
"""

import math
from dataclasses import dataclass, field

from services.base import BaseService, ServiceResult
from shared.logging import emit_log


@dataclass
class PerformanceMetrics:
    """绩效指标集"""

    total_return_pct: float = 0.0
    annualized_return_pct: float = 0.0
    annualized_volatility_pct: float = 0.0
    sharpe_ratio: float = 0.0
    max_drawdown_pct: float = 0.0
    max_drawdown_date: str = ""
    calmar_ratio: float = 0.0
    win_rate_pct: float = 0.0
    profit_loss_ratio: float = 0.0
    trading_days: int = 0
    benchmark_return_pct: float = 0.0
    alpha_pct: float = 0.0
    beta: float = 0.0
    information_ratio: float = 0.0

    def to_dict(self) -> dict:
        return {
            "total_return_pct": round(self.total_return_pct, 2),
            "annualized_return_pct": round(self.annualized_return_pct, 2),
            "annualized_volatility_pct": round(self.annualized_volatility_pct, 2),
            "sharpe_ratio": round(self.sharpe_ratio, 3),
            "max_drawdown_pct": round(self.max_drawdown_pct, 2),
            "max_drawdown_date": self.max_drawdown_date,
            "calmar_ratio": round(self.calmar_ratio, 3),
            "win_rate_pct": round(self.win_rate_pct, 1),
            "profit_loss_ratio": round(self.profit_loss_ratio, 2),
            "trading_days": self.trading_days,
            "benchmark_return_pct": round(self.benchmark_return_pct, 2),
            "alpha_pct": round(self.alpha_pct, 2),
            "beta": round(self.beta, 3),
            "information_ratio": round(self.information_ratio, 3),
        }


@dataclass
class AttributionResult:
    """收益归因结果 (简化Brinson模型)"""

    selection_return_pct: float = 0.0  # 选股贡献
    timing_return_pct: float = 0.0  # 择时贡献
    interaction_return_pct: float = 0.0  # 交互项
    total_active_return_pct: float = 0.0
    top_contributors: list = field(default_factory=list)  # 贡献最大的持仓
    top_detractors: list = field(default_factory=list)  # 拖累最大的持仓

    def to_dict(self) -> dict:
        return {
            "selection_return_pct": round(self.selection_return_pct, 2),
            "timing_return_pct": round(self.timing_return_pct, 2),
            "interaction_return_pct": round(self.interaction_return_pct, 2),
            "total_active_return_pct": round(self.total_active_return_pct, 2),
            "top_contributors": self.top_contributors[:5],
            "top_detractors": self.top_detractors[:5],
        }


class PerformanceEngine(BaseService):
    """绩效归因引擎 — 纯Python计算, 无需LLM"""

    RISK_FREE_RATE = 0.02  # 无风险收益率 (年化 2%)
    TRADING_DAYS_PER_YEAR = 244  # A股年交易日

    def __init__(self):
        super().__init__()
        self._benchmark_cache: dict[str, list[dict]] = {}

    # ── 公开接口 ──

    def compute_performance(
        self,
        portfolio_type: str = "value",
        days: int = 250,
    ) -> ServiceResult:
        """计算完整绩效报告"""
        try:
            nav_series = self._get_nav_series(portfolio_type, days)
            if len(nav_series) < 2:
                return ServiceResult.degraded(
                    data={"metrics": PerformanceMetrics().to_dict()},
                    errors=["NAV数据不足, 至少需要2个交易日"],
                )

            benchmark_series = self._get_benchmark_series(days)
            metrics = self._calc_metrics(nav_series, benchmark_series)
            attribution = self._calc_attribution(portfolio_type, nav_series)

            return ServiceResult.ok(
                data={
                    "metrics": metrics.to_dict(),
                    "attribution": attribution.to_dict(),
                    "nav_curve": [
                        {"date": d["date"], "nav": d["nav"], "return_pct": d.get("daily_return", 0)}
                        for d in nav_series
                    ],
                    "benchmark_curve": [
                        {"date": d["date"], "nav": d["nav"]} for d in benchmark_series
                    ]
                    if benchmark_series
                    else [],
                    "period": {
                        "start": nav_series[0]["date"],
                        "end": nav_series[-1]["date"],
                        "days": len(nav_series),
                    },
                }
            )
        except Exception as e:
            emit_log("ERROR", "performance", f"compute_performance: {e}")
            return ServiceResult.error(errors=[str(e)])

    def get_nav_curve(self, portfolio_type: str = "value", days: int = 250) -> ServiceResult:
        """仅返回NAV曲线(轻量接口)"""
        try:
            nav_series = self._get_nav_series(portfolio_type, days)
            return ServiceResult.ok(data={"nav_curve": nav_series})
        except Exception as e:
            return ServiceResult.error(errors=[str(e)])

    def get_yearly_breakdown(self, portfolio_type: str = "value") -> ServiceResult:
        """分年度绩效拆解"""
        try:
            nav_series = self._get_nav_series(portfolio_type, days=1000)
            if not nav_series:
                return ServiceResult.ok(data={"years": []})

            yearly: dict[str, list[dict]] = {}
            for entry in nav_series:
                year = entry["date"][:4]
                if year not in yearly:
                    yearly[year] = []
                yearly[year].append(entry)

            results = []
            for year, entries in sorted(yearly.items()):
                if len(entries) < 2:
                    continue
                start_nav = entries[0]["nav"]
                end_nav = entries[-1]["nav"]
                ret = ((end_nav / start_nav) - 1) * 100 if start_nav > 0 else 0
                daily_returns = [e.get("daily_return", 0) for e in entries if "daily_return" in e]
                vol = (
                    self._std(daily_returns) * math.sqrt(self.TRADING_DAYS_PER_YEAR) * 100
                    if daily_returns
                    else 0
                )
                max_dd = self._max_drawdown(entries)

                results.append(
                    {
                        "year": year,
                        "return_pct": round(ret, 2),
                        "volatility_pct": round(vol, 2),
                        "max_drawdown_pct": round(max_dd["max_drawdown_pct"], 2),
                        "trading_days": len(entries),
                    }
                )

            return ServiceResult.ok(data={"years": results})
        except Exception as e:
            return ServiceResult.error(errors=[str(e)])

    # ── NAV 数据获取 ──

    def _get_nav_series(self, portfolio_type: str, days: int) -> list[dict]:
        """从 DailyNAV 表获取净值序列, 按日期正序"""
        from shared.models import DailyNAV, get_session

        session = get_session()
        try:
            rows = (
                session.query(DailyNAV)
                .filter_by(portfolio_type=portfolio_type)
                .order_by(DailyNAV.date.asc())
                .limit(days)
                .all()
            )
            if not rows:
                return []

            series = []
            prev_nav = None
            for r in rows:
                nav = r.total_asset if r.total_asset and r.total_asset > 0 else None
                if nav is None:
                    continue
                daily_return = ((nav / prev_nav) - 1) if prev_nav and prev_nav > 0 else 0
                series.append(
                    {
                        "date": r.date,
                        "nav": round(nav, 2),
                        "daily_return": round(daily_return, 6),
                        "position_count": r.position_count or 0,
                    }
                )
                prev_nav = nav
            return series
        finally:
            session.close()

    def _get_benchmark_series(self, days: int) -> list[dict]:
        """获取沪深300基准数据 (从数据总线或缓存)"""
        cache_key = f"hs300_{days}"
        if cache_key in self._benchmark_cache:
            return self._benchmark_cache[cache_key]

        try:
            # 尝试从 StockInfo 获取沪深300 ETF (510300) 数据作为基准代理
            from shared.models import KlineCache, get_session

            session = get_session()
            try:
                rows = (
                    session.query(KlineCache)
                    .filter_by(stock_code="000300")
                    .order_by(KlineCache.trade_date.asc())
                    .limit(days)
                    .all()
                )
                if not rows:
                    # 降级: 使用 510300 ETF
                    rows = (
                        session.query(KlineCache)
                        .filter_by(stock_code="510300")
                        .order_by(KlineCache.trade_date.asc())
                        .limit(days)
                        .all()
                    )

                if rows:
                    base_price = rows[0].close if rows[0].close > 0 else 1
                    series = [
                        {
                            "date": r.trade_date,
                            "nav": round(r.close / base_price, 6),
                            "close": r.close,
                        }
                        for r in rows
                        if r.close and r.close > 0
                    ]
                    self._benchmark_cache[cache_key] = series
                    return series
            finally:
                session.close()
        except Exception as e:
            emit_log("WARNING", "performance", f"Benchmark fetch failed: {e}")

        return []

    # ── 指标计算 ──

    def _calc_metrics(
        self, nav_series: list[dict], benchmark_series: list[dict]
    ) -> PerformanceMetrics:
        """计算完整绩效指标"""
        m = PerformanceMetrics()
        m.trading_days = len(nav_series)

        if m.trading_days < 2:
            return m

        # 总收益
        start_nav = nav_series[0]["nav"]
        end_nav = nav_series[-1]["nav"]
        m.total_return_pct = ((end_nav / start_nav) - 1) * 100 if start_nav > 0 else 0

        # 年化收益
        years = m.trading_days / self.TRADING_DAYS_PER_YEAR
        if years > 0 and start_nav > 0:
            m.annualized_return_pct = ((end_nav / start_nav) ** (1 / years) - 1) * 100

        # 日收益率序列
        daily_returns = [e["daily_return"] for e in nav_series if "daily_return" in e]
        if not daily_returns:
            return m

        # 年化波动率
        std = self._std(daily_returns)
        m.annualized_volatility_pct = std * math.sqrt(self.TRADING_DAYS_PER_YEAR) * 100

        if m.annualized_volatility_pct > 0:
            m.sharpe_ratio = (
                m.annualized_return_pct - self.RISK_FREE_RATE * 100
            ) / m.annualized_volatility_pct

        # 最大回撤
        dd = self._max_drawdown(nav_series)
        m.max_drawdown_pct = dd["max_drawdown_pct"]
        m.max_drawdown_date = dd.get("max_drawdown_date", "")

        # Calmar 比率
        if m.max_drawdown_pct > 0:
            m.calmar_ratio = m.annualized_return_pct / m.max_drawdown_pct

        # 胜率
        wins = sum(1 for r in daily_returns if r > 0)
        m.win_rate_pct = (wins / len(daily_returns)) * 100 if daily_returns else 0

        # 盈亏比
        gains = [r for r in daily_returns if r > 0]
        losses = [abs(r) for r in daily_returns if r < 0]
        avg_gain = sum(gains) / len(gains) if gains else 0
        avg_loss = sum(losses) / len(losses) if losses else 0
        m.profit_loss_ratio = (avg_gain / avg_loss) if avg_loss > 0 else 0

        # 基准对比
        if benchmark_series and len(benchmark_series) >= 2:
            bm_start = benchmark_series[0]["nav"]
            bm_end = benchmark_series[-1]["nav"]
            m.benchmark_return_pct = ((bm_end / bm_start) - 1) * 100 if bm_start > 0 else 0
            m.alpha_pct = m.total_return_pct - m.benchmark_return_pct

            # Beta & Information Ratio
            bm_returns = []
            aligned_returns = []
            bm_map = {b["date"]: b["nav"] for b in benchmark_series}
            prev_bm = None
            for entry in nav_series:
                bm_nav = bm_map.get(entry["date"])
                if bm_nav and prev_bm:
                    bm_ret = (bm_nav / prev_bm) - 1
                    bm_returns.append(bm_ret)
                    aligned_returns.append(entry.get("daily_return", 0))
                if bm_nav:
                    prev_bm = bm_nav

            if len(bm_returns) >= 20:
                m.beta = self._beta(aligned_returns, bm_returns)
                tracking_error = self._std(
                    [a - b for a, b in zip(aligned_returns, bm_returns, strict=True)]
                ) * math.sqrt(self.TRADING_DAYS_PER_YEAR)
                if tracking_error > 0:
                    m.information_ratio = (
                        m.annualized_return_pct - m.benchmark_return_pct * 100
                    ) / (tracking_error * 100)

        return m

    def _calc_attribution(self, portfolio_type: str, nav_series: list[dict]) -> AttributionResult:
        """简化Brinson归因 — 基于持仓贡献"""
        attr = AttributionResult()

        try:
            from shared.models import Portfolio, StockInfo, TradeStatus, get_session

            session = get_session()
            try:
                holdings = (
                    session.query(Portfolio)
                    .filter_by(status=TradeStatus.HOLDING, portfolio_type=portfolio_type)
                    .all()
                )

                if not holdings:
                    return attr

                contributors = []
                for h in holdings:
                    if not h.current_price or not h.buy_price or h.buy_price <= 0:
                        continue
                    ret_pct = ((h.current_price - h.buy_price) / h.buy_price) * 100
                    weight = (h.current_price * h.quantity) if h.quantity else 0
                    contribution = ret_pct * weight  # 加权贡献

                    info = session.query(StockInfo).filter_by(stock_code=h.stock_code).first()
                    contributors.append(
                        {
                            "stock_code": h.stock_code,
                            "stock_name": h.stock_name,
                            "return_pct": round(ret_pct, 2),
                            "weight": round(weight, 2),
                            "contribution": round(contribution, 2),
                            "industry": info.industry if info else "",
                        }
                    )

                contributors.sort(key=lambda x: x["contribution"], reverse=True)
                attr.top_contributors = contributors[:5]
                attr.top_detractors = contributors[-5:] if len(contributors) > 5 else []
                attr.top_detractors.reverse()

                total_weight = sum(c["weight"] for c in contributors)
                if total_weight > 0:
                    weighted_return = sum(c["contribution"] for c in contributors) / total_weight
                    attr.selection_return_pct = round(weighted_return, 2)
                    attr.total_active_return_pct = round(weighted_return, 2)

            finally:
                session.close()
        except Exception as e:
            emit_log("WARNING", "performance", f"Attribution calc: {e}")

        return attr

    # ── 统计工具 ──

    @staticmethod
    def _std(values: list[float]) -> float:
        """标准差 (样本标准差)"""
        if len(values) < 2:
            return 0.0
        mean = sum(values) / len(values)
        variance = sum((x - mean) ** 2 for x in values) / (len(values) - 1)
        return math.sqrt(variance)

    @staticmethod
    def _max_drawdown(nav_series: list[dict]) -> dict:
        """最大回撤计算"""
        max_dd = 0.0
        peak = 0.0
        dd_date = ""
        for entry in nav_series:
            nav = entry["nav"]
            peak = max(peak, nav)
            if peak > 0:
                dd = (peak - nav) / peak
                if dd > max_dd:
                    max_dd = dd
                    dd_date = entry.get("date", "")
        return {
            "max_drawdown_pct": max_dd * 100,
            "max_drawdown_date": dd_date,
        }

    @staticmethod
    def _beta(portfolio_returns: list[float], benchmark_returns: list[float]) -> float:
        """计算 Beta 系数"""
        if len(portfolio_returns) != len(benchmark_returns) or len(portfolio_returns) < 10:
            return 1.0
        n = len(portfolio_returns)
        mean_p = sum(portfolio_returns) / n
        mean_b = sum(benchmark_returns) / n
        cov = sum(
            (p - mean_p) * (b - mean_b)
            for p, b in zip(portfolio_returns, benchmark_returns, strict=True)
        ) / (n - 1)
        var_b = sum((b - mean_b) ** 2 for b in benchmark_returns) / (n - 1)
        return cov / var_b if var_b > 0 else 1.0


# ── 模块级单例 ──
_engine: PerformanceEngine | None = None


def get_performance_engine() -> PerformanceEngine:
    global _engine  # noqa: PLW0603
    if _engine is None:
        _engine = PerformanceEngine()
    return _engine
