"""因子工厂 — 行为金融 + 微观结构因子库 (从遗留版 a-share-investment-system 移植)

移植自: a-share-investment-system/services/factor_farm.py
清理:
  - 去除 BaseService / ServiceResult 依赖,改用纯函数 + dict 返回
  - 去除 emit_log,改用 stdlib logging
  - 去除 db_session / SQLAlchemy 依赖,SQLite 注册表改用 sqlite3 直接访问
  - 保留全部 33 个因子算法 (行为金融/微观结构/初筛 15 个)

设计依据:
  - 前景理论 (Kahneman & Tversky 1979)
  - MAX 效应 (Bali, Cakici & Whitelaw 2011)
  - 低风险动量 (Ang et al. 2006)
  - 量价背离 (Lee & Swaminathan 2000)
"""
from __future__ import annotations

import logging
import math
import os
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


# Section: factor functions below


def factor_1_ptv(prices: pd.Series) -> float:
    """前景理论价值 (Prospect Theory Value)

    基于 Kahneman & Tversky (1979) 价值函数:
        v(x) = x^α   for x >= 0
        v(x) = -λ * (-x)^β   for x < 0
    参数: α=0.88, β=0.88, λ=2.25
    返回 E[v(r)] 历史收益价值函数均值。
    """
    returns = prices.pct_change().dropna()
    if len(returns) < 20:
        return 0.0
    alpha, beta, lam = 0.88, 0.88, 2.25
    gains = returns[returns >= 0].clip(lower=1e-10) ** alpha
    losses = -lam * ((-returns[returns < 0]).clip(lower=1e-10) ** beta)
    pt_values = pd.concat([gains, losses])
    return float(pt_values.mean())


def factor_3_ltr(prices: pd.Series, turnover: pd.Series) -> float:
    """彩票型股票特征 (Lottery-Type Stock, MAX 效应)

    综合得分 = MAX5 + 0.1 * skewness + 0.05 * avg_turnover
    """
    returns = prices.pct_change().dropna()
    if len(returns) < 20:
        return 0.0
    max5 = returns.nlargest(min(5, len(returns))).mean()
    skew = returns.skew()
    avg_turnover = turnover.dropna().mean() if len(turnover.dropna()) > 0 else 0.0
    return float(max5 + 0.1 * skew + 0.05 * avg_turnover)


def factor_8_corrrv(returns: pd.Series, volume: pd.Series) -> float:
    """量价相关性 (Correlation Return-Volume)

    日收益率与成交量的 Spearman 秩相关。
    """
    valid = returns.notna() & volume.notna() & (volume > 0)
    if valid.sum() < 20:
        return 0.0
    corr = returns[valid].corr(volume[valid], method="spearman")
    return float(corr) if not np.isnan(corr) else 0.0


def factor_9_cpv(
    open_prices: pd.Series,
    close: pd.Series,
    high: pd.Series,
    low: pd.Series,
    turnover: pd.Series,
) -> float:
    """CPV 因子 (Close-Price-Volume)

    CPV_i = (close_i - open_i) / (high_i - low_i) × turnover_i
    正值 = 日内买盘强, 负值 = 日内卖盘强。
    """
    hl = (high - low).clip(lower=1e-10)
    cpv = (close - open_prices) / hl
    if len(turnover.dropna()) > 0:
        cpv = cpv * turnover
    vals = cpv.dropna()
    return float(vals.mean()) if len(vals) > 0 else 0.0


def factor_10_alpha_new(close: pd.Series, volume: pd.Series) -> float:
    """价量背离信号 (Price-Volume Divergence)

    r = corr(ΔP/P, ΔV/V); Alpha = -r
    正值 → 价量背离。
    """
    ret = close.pct_change()
    vol_change = volume.pct_change()
    valid = ret.notna() & vol_change.notna() & (volume > 0)
    if valid.sum() < 20:
        return 0.0
    corr = ret[valid].corr(vol_change[valid], method="spearman")
    return float(-corr) if not np.isnan(corr) else 0.0


def factor_11_amp_momentum(close: pd.Series, high: pd.Series, low: pd.Series) -> float:
    """振幅切割动量 (Amplitude-Split Momentum)

    按振幅分为高/低两组, 分别计算 20 日累计收益, 低-高。
    """
    returns = close.pct_change()
    amplitude = ((high - low) / close).clip(lower=1e-10)
    med_amp = amplitude.rolling(20, min_periods=10).median()
    if med_amp.isna().all():
        return 0.0
    amp_signal = amplitude > med_amp
    high_ret = returns[amp_signal].tail(20).sum()
    low_ret = returns[~amp_signal].tail(20).sum()
    return float(low_ret - high_ret)


def factor_12_umr(close: pd.Series, turnover: pd.Series) -> float:
    """动量反转统一因子 (Unified Momentum-Reversal)

    UMR = 0.4 × (-Ret5) + 0.6 × Ret20 × (换手率比率)
    """
    returns = close.pct_change().dropna()
    if len(returns) < 25:
        return 0.0
    ret5 = returns.tail(5).sum()
    ret20 = returns.tail(25).iloc[:-5].sum() if len(returns) >= 25 else 0.0
    vol_ratio = 1.0
    t = turnover.dropna()
    if len(t) >= 60:
        short_vol = t.tail(20).mean()
        long_vol = t.tail(60).mean()
        vol_ratio = short_vol / long_vol if long_vol > 0 else 1.0
    elif len(t) >= 20:
        short_vol = t.tail(20).mean()
        long_vol = t.mean()
        vol_ratio = short_vol / long_vol if long_vol > 0 else 1.0
    umr = 0.4 * (-ret5) + 0.6 * ret20 * vol_ratio
    return float(umr)


def factor_13_hrv_reversal(close: pd.Series, high: pd.Series, low: pd.Series) -> float:
    """高风险日反转 (High-Risk Day Reversal)

    振幅处于 80% 分位数以上的交易日次日平均收益。
    """
    returns = close.pct_change().dropna()
    daily_vol = ((high - low) / close).clip(lower=1e-10)
    if len(daily_vol) < 20:
        return 0.0
    threshold = daily_vol.quantile(0.8)
    high_risk = daily_vol > threshold
    next_day_ret = returns.shift(-1)
    post_hr = next_day_ret[high_risk].dropna()
    if len(post_hr) < 5:
        return 0.0
    return float(post_hr.mean())


def factor_14_amount_volatility(close: pd.Series, amount: pd.Series) -> float:
    """成交额K线波动率 (Amount-Based Volatility)

    vol = std(Δamount/amount) × √252
    """
    if len(amount.dropna()) < 20:
        return 0.0
    amt_change = amount.pct_change().dropna()
    if len(amt_change) < 20:
        return 0.0
    return float(amt_change.std() * math.sqrt(252))


def factor_17_lowrisk_momentum(close: pd.Series, high: pd.Series, low: pd.Series) -> float:
    """低风险动量 (Low-Risk Momentum)

    动量 = 20日累计收益 / 20日均振幅
    """
    returns = close.pct_change()
    if len(returns.dropna()) < 20:
        return 0.0
    mom_20d = returns.tail(20).sum()
    amplitude = ((high - low) / close).clip(lower=1e-10)
    avg_vol = amplitude.tail(20).mean()
    if avg_vol > 0:
        return float(mom_20d / avg_vol)
    return float(mom_20d)


def factor_18_str(turnover: pd.Series) -> float:
    """量稳换手率 (Stable Turnover Rate)

    STR = 换手率均值 / 换手率标准差
    """
    t = turnover.dropna()
    if len(t) < 20:
        return 0.0
    mean_t = float(t.mean())
    std_t = float(t.std())
    if std_t > 1e-10:
        return mean_t / std_t
    return mean_t


def factor_19_t_small(turnover: pd.Series) -> float:
    """量缩换手率 (T_small)

    T_small = count(TO < 0.3 × median(TO)) / N
    """
    t = turnover.dropna()
    if len(t) < 20:
        return 0.0
    med_t = float(t.median())
    if med_t <= 1e-10:
        return 0.0
    small_days = int((t < 0.3 * med_t).sum())
    return small_days / len(t)


def factor_20_volume_entropy(volume: pd.Series) -> float:
    """成交量熵 (Volume Entropy)

    H = -Σ(p_i × ln(p_i)) / ln(10), 10 分箱归一化。
    """
    v = volume.dropna()
    if len(v) < 20 or v.sum() == 0:
        return 0.0
    bins = 10
    v_binned = pd.cut(v, bins=bins, labels=False)
    probs = v_binned.value_counts(normalize=True).values
    entropy = -np.sum(probs * np.log(probs + 1e-10))
    max_entropy = np.log(bins)
    if max_entropy > 0:
        return float(entropy / max_entropy)
    return 0.0


def factor_21_turnover_attention(close: pd.Series, turnover: pd.Series) -> float:
    """换手率突变注意力 (Turnover Attention)

    Attention = ln(1 + mean(|ΔTO/TO| × |ΔP/P|))
    """
    t = turnover.dropna()
    if len(t) < 10:
        return 0.0
    t_change = t.pct_change().dropna()
    p = close.reindex(t.index)
    p_change = p.pct_change().dropna()
    common = t_change.index.intersection(p_change.index)
    if len(common) < 5:
        return 0.0
    attention = (t_change.loc[common].abs() * p_change.loc[common].abs()).mean()
    return float(np.log1p(attention))


# ── 15 个初筛因子 ──


def factor_101_cgo(prices: pd.Series, turnover: pd.Series) -> float:
    """处置效应 CGO: 参考价=换手率加权历史成本"""
    if len(prices) < 20 or turnover.sum() == 0:
        return 0.0
    weights = turnover.rolling(5, min_periods=1).mean().fillna(0).values
    weights = weights / (weights.sum() + 1e-10)
    ref_price = float(np.average(prices.values, weights=weights))
    return float((prices.iloc[-1] - ref_price) / max(ref_price, 1e-10))


def factor_102_rev_1m(prices: pd.Series) -> float:
    """短期反转 Rev_1M: -(过去20日累计涨跌幅)"""
    ret = (prices.iloc[-1] / prices.iloc[-min(21, len(prices))]) - 1 if len(prices) >= 21 else 0.0
    return -float(ret)


def factor_103_rev_12m(prices: pd.Series) -> float:
    """长期反转 Rev_12M: -(252日涨跌幅 - 20日涨跌幅)"""
    if len(prices) < 252:
        return 0.0
    ret_252 = float(prices.iloc[-1] / prices.iloc[-252]) - 1.0
    ret_20 = float(prices.iloc[-1] / prices.iloc[-20]) - 1.0
    return -(ret_252 - ret_20)


def factor_104_vol_20d(prices: pd.Series) -> float:
    """低波动 Vol_20d: -std(过去20日收益率)"""
    ret = prices.pct_change().dropna()
    if len(ret) < 5:
        return 0.0
    return -float(ret.tail(20).std())


def factor_105_illiq(prices: pd.Series, amount: pd.Series) -> float:
    """Amihud 非流动性 ILLIQ: mean(|ret_d|/amount_d) 过去20日"""
    ret = prices.pct_change().abs()
    ratio = ret / (amount + 1e-10)
    return float(ratio.tail(20).mean()) if len(ratio) >= 20 else 0.0


def factor_106_turn_20d(turnover: pd.Series) -> float:
    """换手率因子 Turn_20d: -mean(过去20日换手率)"""
    if len(turnover) < 5:
        return 0.0
    return -float(turnover.tail(20).mean())


def factor_107_volstd_20d(volume: pd.Series) -> float:
    """成交量稳定性 VolStd_20d: -std(volume/mean(volume_60d)) 过去20日"""
    base = volume.tail(60).mean() if len(volume) >= 60 else volume.mean()
    if base == 0:
        return 0.0
    ratio = volume.tail(20) / base
    return -float(ratio.std())


def factor_108_lncap(total_market_cap: float | None) -> float:
    """对数市值 LnCap: -ln(总市值亿元)"""
    if not total_market_cap:
        return 0.0
    mcap = float(total_market_cap)
    return -float(np.log(max(mcap, 1.0)))


def factor_109_bp(price: float | None, bvps: float | None) -> float:
    """账面市值比 BP: BVPS / 股价"""
    if not price or not bvps:
        return 0.0
    if price == 0 or bvps == 0:
        return 0.0
    return float(bvps) / float(price)


def factor_110_roe(roe: float | None) -> float:
    """盈利因子 ROE"""
    return float(roe) if roe else 0.0


def factor_111_gpm(gross_margin: float | None) -> float:
    """毛利率因子 GPM"""
    return float(gross_margin) if gross_margin else 0.0


def factor_112_lev(debt_to_equity: float | None) -> float:
    """资产负债率 Lev: -debt_to_equity"""
    if debt_to_equity is None:
        return 0.0
    return -float(debt_to_equity)


def factor_113_dy(dividend_yield: float | None) -> float:
    """股息率因子 DY"""
    return float(dividend_yield) if dividend_yield else 0.0


def factor_114_maxret_20d(prices: pd.Series) -> float:
    """最大日收益率 MaxRet_20d: -max(过去20日日收益率)"""
    ret = prices.pct_change().dropna()
    if len(ret) < 5:
        return 0.0
    return -float(ret.tail(20).max())


def factor_115_skew_20d(prices: pd.Series) -> float:
    """偏度因子 Skew_20d: -skewness(过去20日日收益率)"""
    ret = prices.pct_change().dropna()
    if len(ret) < 5:
        return 0.0
    return -float(ret.tail(20).skew())


# 基本面因子 (接受 dict 参数)


def factor_24_roe_quality(info: dict[str, Any]) -> float:
    """ROE 复合质量 = 0.5*ROE + 0.3*毛利率 + 0.2*净利率"""
    return float(
        0.5 * info.get("roe", 0)
        + 0.3 * info.get("gross_margin", 0)
        + 0.2 * info.get("net_margin", 0)
    )


def factor_26_de_ratio(info: dict[str, Any]) -> float:
    """债务股权比 D/E"""
    return float(info.get("debt_to_equity", 0) or 0)


def factor_27_eav(info: dict[str, Any]) -> float:
    """盈利加速度 EAV = 净利润增速 - 营收增速"""
    return float(info.get("earnings_growth_3y", 0) - info.get("revenue_growth_3y", 0))


def factor_28_gm_trend(info: dict[str, Any]) -> float:
    """毛利率趋势代理 (毛利率水平)"""
    return float(info.get("gross_margin", 0) or 0)


# Section: factor registry and dispatcher


@dataclass
class FactorSpec:
    """因子元数据。"""

    name: str
    category: str
    description: str
    func: Any  # Callable[..., float]


def build_default_registry() -> dict[str, FactorSpec]:
    """构造 33 个默认因子的注册表。"""
    return {
        # 行为金融 / 微观结构 (19 个)
        "PTV": FactorSpec("PTV", "behavioral", "前景理论价值", factor_1_ptv),
        "LTR": FactorSpec("LTR", "behavioral", "彩票型股票 MAX 效应", factor_3_ltr),
        "CorrRV": FactorSpec("CorrRV", "behavioral", "量价秩相关", factor_8_corrrv),
        "CPV": FactorSpec("CPV", "behavioral", "收盘-开盘-量 三因子", factor_9_cpv),
        "Alpha_new": FactorSpec("Alpha_new", "behavioral", "价量背离", factor_10_alpha_new),
        "AMP_Momentum": FactorSpec(
            "AMP_Momentum", "behavioral", "振幅切割动量", factor_11_amp_momentum
        ),
        "UMR": FactorSpec("UMR", "behavioral", "动量反转统一", factor_12_umr),
        "HRV_Reversal": FactorSpec(
            "HRV_Reversal", "behavioral", "高风险日反转", factor_13_hrv_reversal
        ),
        "Amount_Volatility": FactorSpec(
            "Amount_Volatility", "behavioral", "成交额波动率", factor_14_amount_volatility
        ),
        "LowRisk_Momentum": FactorSpec(
            "LowRisk_Momentum", "behavioral", "低风险动量", factor_17_lowrisk_momentum
        ),
        "STR": FactorSpec("STR", "behavioral", "量稳换手率", factor_18_str),
        "T_small": FactorSpec("T_small", "behavioral", "量缩换手率", factor_19_t_small),
        "Volume_Entropy": FactorSpec(
            "Volume_Entropy", "behavioral", "成交量熵", factor_20_volume_entropy
        ),
        "Turnover_Attention": FactorSpec(
            "Turnover_Attention", "behavioral", "换手率突变注意力", factor_21_turnover_attention
        ),
        "ROE_Quality": FactorSpec(
            "ROE_Quality", "fundamental", "ROE 复合质量", factor_24_roe_quality
        ),
        "DE_Ratio": FactorSpec("DE_Ratio", "fundamental", "债务股权比", factor_26_de_ratio),
        "EAV": FactorSpec("EAV", "fundamental", "盈利加速度", factor_27_eav),
        "GM_trend": FactorSpec("GM_trend", "fundamental", "毛利率趋势", factor_28_gm_trend),
        # 初筛 (15 个)
        "CGO": FactorSpec("CGO", "pre_screen", "处置效应", factor_101_cgo),
        "Rev_1M": FactorSpec("Rev_1M", "pre_screen", "短期反转", factor_102_rev_1m),
        "Rev_12M": FactorSpec("Rev_12M", "pre_screen", "长期反转", factor_103_rev_12m),
        "Vol_20d": FactorSpec("Vol_20d", "pre_screen", "低波动", factor_104_vol_20d),
        "ILLIQ": FactorSpec("ILLIQ", "pre_screen", "Amihud 非流动性", factor_105_illiq),
        "Turn_20d": FactorSpec("Turn_20d", "pre_screen", "换手率", factor_106_turn_20d),
        "VolStd_20d": FactorSpec("VolStd_20d", "pre_screen", "成交量稳定性", factor_107_volstd_20d),
        "LnCap": FactorSpec("LnCap", "pre_screen", "对数市值", factor_108_lncap),
        "BP": FactorSpec("BP", "pre_screen", "账面市值比", factor_109_bp),
        "ROE": FactorSpec("ROE", "pre_screen", "ROE 截面", factor_110_roe),
        "GPM": FactorSpec("GPM", "pre_screen", "毛利率", factor_111_gpm),
        "Lev": FactorSpec("Lev", "pre_screen", "杠杆率", factor_112_lev),
        "DY": FactorSpec("DY", "pre_screen", "股息率", factor_113_dy),
        "MaxRet_20d": FactorSpec("MaxRet_20d", "pre_screen", "最大日收益", factor_114_maxret_20d),
        "Skew_20d": FactorSpec("Skew_20d", "pre_screen", "偏度", factor_115_skew_20d),
    }


# ═══════════════════════════════════════════════════════════
# Section: FactorFarm high-level API
# ═══════════════════════════════════════════════════════════


@dataclass
class FactorLibrary:
    """SQLite-backed factor registry (移植版, 去除 ServiceResult)。"""

    db_path: str = "data/factors.db"
    _conn: sqlite3.Connection | None = field(default=None, init=False, repr=False)

    def __post_init__(self):
        os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)
        self._conn = sqlite3.connect(self.db_path)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        if self._conn is None:
            raise RuntimeError("FactorLibrary not connected")
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS factors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                category TEXT NOT NULL DEFAULT 'custom',
                formula_type TEXT NOT NULL DEFAULT 'computed',
                description TEXT DEFAULT '',
                ic_mean REAL DEFAULT 0.0,
                icir REAL DEFAULT 0.0,
                ic_samples INTEGER DEFAULT 0,
                active INTEGER DEFAULT 1,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS factor_values (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                factor_name TEXT NOT NULL,
                stock_code TEXT NOT NULL,
                trade_date TEXT NOT NULL,
                value REAL,
                UNIQUE(factor_name, stock_code, trade_date)
            )
        """)
        self._conn.commit()

    def register(self, name: str, category: str, description: str = "") -> bool:
        if self._conn is None:
            return False
        try:
            self._conn.execute(
                "INSERT OR IGNORE INTO factors (name, category, formula_type, description) "
                "VALUES (?,?,?,?)",
                (name, category, "computed", description),
            )
            self._conn.commit()
            return True
        except sqlite3.Error as e:
            logger.error("register factor %s failed: %s", name, e)
            return False

    def update_ic(self, name: str, ic_mean: float, icir: float, samples: int) -> None:
        if self._conn is None:
            return
        self._conn.execute(
            "UPDATE factors SET ic_mean=?, icir=?, ic_samples=?, updated_at=? WHERE name=?",
            (round(ic_mean, 4), round(icir, 4), samples, datetime.now().isoformat(), name),
        )
        self._conn.commit()

    def get_top(self, n: int = 20, min_ic: float = 0.02) -> list[dict[str, Any]]:
        if self._conn is None:
            return []
        rows = self._conn.execute(
            "SELECT * FROM factors WHERE active=1 AND ABS(ic_mean) >= ? "
            "ORDER BY ABS(ic_mean) DESC LIMIT ?",
            (min_ic, n),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_all_active(self) -> list[dict[str, Any]]:
        if self._conn is None:
            return []
        rows = self._conn.execute("SELECT * FROM factors WHERE active=1").fetchall()
        return [dict(r) for r in rows]

    def deactivate(self, name: str) -> None:
        if self._conn is None:
            return
        self._conn.execute("UPDATE factors SET active=0 WHERE name=?", (name,))
        self._conn.commit()

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None


@dataclass
class FactorFarm:
    """因子工厂主入口 (移植自遗留版)。"""

    db_path: str = "data/factors.db"
    library: FactorLibrary | None = None
    registry: dict[str, FactorSpec] = field(default_factory=build_default_registry)

    def __post_init__(self):
        if self.library is None:
            self.library = FactorLibrary(self.db_path)
        self._register_factors()

    def _register_factors(self) -> None:
        if self.library is None:
            return
        new_names = set(self.registry.keys())
        for existing in self.library.get_all_active():
            if existing["name"] not in new_names:
                self.library.deactivate(existing["name"])
        for name, spec in self.registry.items():
            self.library.register(name, spec.category, spec.description)

    def get_all_factor_names(self) -> list[str]:
        return list(self.registry.keys())

    def compute_all_factors(
        self, code: str, df: pd.DataFrame, info: dict[str, Any] | None = None
    ) -> dict[str, float]:
        """计算一只股票的全部因子值。

        Args:
            code: 股票代码
            df: K线 DataFrame, 需含 close/open/high/low/volume/amount
            info: 基本面 dict (可选, 用于 fundamental 类因子)

        Returns:
            {因子名: 因子值, ...}
        """
        if df.empty:
            return {}
        prices = df["close"]
        volume = df["volume"]
        high = df["high"]
        low = df["low"]
        open_prices = df["open"]
        amount = df.get("amount", pd.Series(dtype=float))
        turnover = df.get("turnover_rate", df.get("turnover", pd.Series(dtype=float)))
        if turnover.sum() == 0 and info:
            turn_val = float(info.get("turnover_rate", 0) or 0)
            if turn_val > 0:
                turnover = pd.Series([turn_val] * len(df), index=df.index)
        info = info or {}

        factors: dict[str, float] = {}
        try:
            factors["PTV"] = factor_1_ptv(prices)
            factors["LTR"] = factor_3_ltr(prices, turnover)
            factors["CorrRV"] = factor_8_corrrv(prices.pct_change(), volume)
            factors["CPV"] = factor_9_cpv(open_prices, prices, high, low, turnover)
            factors["Alpha_new"] = factor_10_alpha_new(prices, volume)
            factors["AMP_Momentum"] = factor_11_amp_momentum(prices, high, low)
            factors["UMR"] = factor_12_umr(prices, turnover)
            factors["HRV_Reversal"] = factor_13_hrv_reversal(prices, high, low)
            factors["Amount_Volatility"] = factor_14_amount_volatility(prices, amount)
            factors["LowRisk_Momentum"] = factor_17_lowrisk_momentum(prices, high, low)
            factors["STR"] = factor_18_str(turnover)
            factors["T_small"] = factor_19_t_small(turnover)
            factors["Volume_Entropy"] = factor_20_volume_entropy(volume)
            factors["Turnover_Attention"] = factor_21_turnover_attention(prices, turnover)
            factors["ROE_Quality"] = factor_24_roe_quality(info)
            factors["DE_Ratio"] = factor_26_de_ratio(info)
            factors["EAV"] = factor_27_eav(info)
            factors["GM_trend"] = factor_28_gm_trend(info)

            factors["CGO"] = factor_101_cgo(prices, turnover)
            factors["Rev_1M"] = factor_102_rev_1m(prices)
            factors["Rev_12M"] = factor_103_rev_12m(prices)
            factors["Vol_20d"] = factor_104_vol_20d(prices)
            factors["ILLIQ"] = factor_105_illiq(prices, amount)
            factors["Turn_20d"] = factor_106_turn_20d(turnover)
            factors["VolStd_20d"] = factor_107_volstd_20d(volume)
            factors["LnCap"] = factor_108_lncap(info.get("total_market_cap"))
            factors["BP"] = factor_109_bp(info.get("latest_price"), info.get("bvps"))
            factors["ROE"] = factor_110_roe(info.get("roe"))
            factors["GPM"] = factor_111_gpm(info.get("gross_margin"))
            factors["Lev"] = factor_112_lev(info.get("debt_to_equity"))
            factors["DY"] = factor_113_dy(info.get("dividend_yield"))
            factors["MaxRet_20d"] = factor_114_maxret_20d(prices)
            factors["Skew_20d"] = factor_115_skew_20d(prices)
        except Exception as e:
            logger.error("compute_all_factors(%s) failed: %s", code, e)
        return factors

    def get_top_factors(self, n: int = 20, min_ic: float = 0.03) -> dict[str, Any]:
        """获取当前最优因子 (按 IC 排序)。"""
        if self.library is None:
            return {"factors": [], "count": 0}
        try:
            factors = self.library.get_top(n=n, min_ic=min_ic)
            return {"factors": factors, "count": len(factors)}
        except Exception as e:
            logger.error("get_top_factors failed: %s", e)
            return {"factors": [], "count": 0, "error": str(e)}
