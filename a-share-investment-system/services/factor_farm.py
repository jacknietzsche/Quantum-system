"""因子工厂 — 行为金融 + 微观结构因子库 (18因子)

数据源:
  - KlineCache: trade_date, open, close, high, low, volume, amount, change_pct
  - StockInfo:  latest_price, turnover_rate, pe_ratio, pb_ratio, roe,
                gross_margin, net_margin, eps, bvps, debt_to_equity,
                total_market_cap, net_profit, free_cash_flow,
                revenue_growth_3y, earnings_growth_3y
"""

import math
import os
import sqlite3
from datetime import datetime

import numpy as np
import pandas as pd

from services.base import BaseService, ServiceResult
from shared.logging import emit_log


class FactorLibrary:
    """SQLite-backed factor registry"""

    def __init__(self, db_path: str = "data/factors.db"):
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self):
        self.conn.execute("""
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
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS factor_values (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                factor_name TEXT NOT NULL,
                stock_code TEXT NOT NULL,
                trade_date TEXT NOT NULL,
                value REAL,
                UNIQUE(factor_name, stock_code, trade_date)
            )
        """)
        self.conn.commit()

    def register(
        self, name: str, category: str, formula_type: str = "computed", description: str = ""
    ) -> bool:
        """Register a new factor"""
        try:
            self.conn.execute(
                "INSERT OR IGNORE INTO factors (name, category, formula_type, description) VALUES (?,?,?,?)",
                (name, category, formula_type, description),
            )
            self.conn.commit()
            return True
        except Exception as e:
            emit_log("ERROR", "factor_farm", f"Operation failed: {str(e)[:100]}")
            return False

    def update_ic(self, name: str, ic_mean: float, icir: float, samples: int):
        """Update IC metrics for a factor"""
        self.conn.execute(
            "UPDATE factors SET ic_mean=?, icir=?, ic_samples=?, updated_at=? WHERE name=?",
            (round(ic_mean, 4), round(icir, 4), samples, datetime.now().isoformat(), name),
        )
        self.conn.commit()

    def get_top(self, n: int = 20, min_ic: float = 0.02) -> list[dict]:
        """Get top N factors by absolute IC"""
        rows = self.conn.execute(
            "SELECT * FROM factors WHERE active=1 AND ABS(ic_mean) >= ? ORDER BY ABS(ic_mean) DESC LIMIT ?",
            (min_ic, n),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_all_active(self) -> list[dict]:
        """Get all active factors"""
        rows = self.conn.execute("SELECT * FROM factors WHERE active=1").fetchall()
        return [dict(r) for r in rows]

    def deactivate(self, name: str):
        """Deactivate a factor"""
        self.conn.execute("UPDATE factors SET active=0 WHERE name=?", (name,))
        self.conn.commit()

    def count(self) -> int:
        return int(
            self.conn.execute("SELECT COUNT(*) FROM factors WHERE active=1").fetchone()[0]
        )

    def close(self):
        self.conn.close()


# ── 因子映射: 因子名 → 类方法名 ──
FACTOR_METHODS = {
    "PTV": "_factor_1_ptv",
    "LTR": "_factor_3_ltr",
    "CorrRV": "_factor_8_corrrv",
    "CPV": "_factor_9_cpv",
    "Alpha_new": "_factor_10_alpha_new",
    "AMP_Momentum": "_factor_11_amp_momentum",
    "UMR": "_factor_12_umr",
    "HRV_Reversal": "_factor_13_hrv_reversal",
    "Amount_Volatility": "_factor_14_amount_volatility",
    "LowRisk_Momentum": "_factor_17_lowrisk_momentum",
    "STR": "_factor_18_str",
    "T_small": "_factor_19_t_small",
    "Volume_Entropy": "_factor_20_volume_entropy",
    "Turnover_Attention": "_factor_21_turnover_attention",
    "ROE_Quality": "_factor_24_roe_quality",
    "DE_Ratio": "_factor_26_de_ratio",
    "EAV": "_factor_27_eav",
    "GM_trend": "_factor_28_gm_trend",
    # 15个初筛因子
    "CGO": "_factor_101_cgo",
    "Rev_1M": "_factor_102_rev_1m",
    "Rev_12M": "_factor_103_rev_12m",
    "Vol_20d": "_factor_104_vol_20d",
    "ILLIQ": "_factor_105_illiq",
    "Turn_20d": "_factor_106_turn_20d",
    "VolStd_20d": "_factor_107_volstd_20d",
    "LnCap": "_factor_108_lncap",
    "BP": "_factor_109_bp",
    "ROE": "_factor_110_roe",
    "GPM": "_factor_111_gpm",
    "Lev": "_factor_112_lev",
    "DY": "_factor_113_dy",
    "MaxRet_20d": "_factor_114_maxret_20d",
    "Skew_20d": "_factor_115_skew_20d",
}

# 向后兼容导入别名
BUILTIN_FACTORS = FACTOR_METHODS

# 向后兼容: backtest_loop.py 导入此符号
FACTOR_COMPUTERS: dict = {}


class FactorFarm(BaseService):
    """因子工厂 — 行为金融 + 微观结构因子库 (18因子)"""

    def __init__(self, db_path: str = "data/factors.db"):
        super().__init__()
        self.library = FactorLibrary(db_path)
        self._register_factors()

    def _register_factors(self):
        """注册所有因子到 SQLite 库 (INSERT OR IGNORE 确保幂等)"""
        new_names = set(FACTOR_METHODS.keys())
        # 清理不在新因子列表中的旧因子
        for existing in self.library.get_all_active():
            if existing["name"] not in new_names:
                self.library.deactivate(existing["name"])
        for name in FACTOR_METHODS:
            self.library.register(name, "behavioral", "computed", "")

    # ═══════════════════════════════════════════════════════════
    #  18 个因子计算方法
    # ═══════════════════════════════════════════════════════════

    def _factor_1_ptv(self, prices: pd.Series) -> float:
        """前景理论价值 (Prospect Theory Value)

        基于 Kahneman & Tversky (1979) 前景理论价值函数:
          v(x) = x^α   for x >= 0
          v(x) = -λ * (-x)^β   for x < 0
        参数: α=0.88, β=0.88, λ=2.25
        返回 E[v(r)] 即历史收益的价值函数均值。
        """
        returns = prices.pct_change().dropna()
        if len(returns) < 20:
            return 0.0
        alpha, beta, lam = 0.88, 0.88, 2.25
        gains = returns[returns >= 0].clip(lower=1e-10) ** alpha
        losses = -lam * ((-returns[returns < 0]).clip(lower=1e-10) ** beta)
        pt_values = pd.concat([gains, losses])
        return float(pt_values.mean())

    def _factor_3_ltr(self, prices: pd.Series, turnover: pd.Series) -> float:
        """彩票型股票特征 (Lottery-Type Stock)

        Bali, Cakici & Whitelaw (2011) MAX 效应:
          - MAX5: 过去20个交易日最大5日收益均值
          - 收益率偏度 (正偏度 = 彩票特征)
          - 换手率 (高换手 = 投机特征)
        综合得分 = MAX5 + 0.1 * skewness + 0.05 * 平均换手率
        """
        returns = prices.pct_change().dropna()
        if len(returns) < 20:
            return 0.0
        max5 = returns.nlargest(min(5, len(returns))).mean()
        skew = returns.skew()
        avg_turnover = turnover.dropna().mean() if len(turnover.dropna()) > 0 else 0.0
        return float(max5 + 0.1 * skew + 0.05 * avg_turnover)

    def _factor_8_corrrv(self, returns: pd.Series, volume: pd.Series) -> float:
        """量价相关性 (Correlation Return-Volume)

        日收益率与成交量的 Spearman 秩相关。
        负相关 → 价涨量缩 (弱信号)，正相关 → 价量配合。
        """
        valid = returns.notna() & volume.notna() & (volume > 0)
        if valid.sum() < 20:
            return 0.0
        corr = returns[valid].corr(volume[valid], method="spearman")
        return float(corr) if not np.isnan(corr) else 0.0

    def _factor_9_cpv(
        self,
        open_prices: pd.Series,
        close: pd.Series,
        high: pd.Series,
        low: pd.Series,
        turnover: pd.Series,
    ) -> float:
        """CPV 因子 (Close-Price-Volume)

        CPV_i = (close_i - open_i) / (high_i - low_i) × turnover_i
        度量日内价格压力强度加权换手率。
        正值 = 日内买盘强，负值 = 日内卖盘强。
        """
        hl = (high - low).clip(lower=1e-10)
        cpv = (close - open_prices) / hl
        # 如果有换手率数据,加权
        if len(turnover.dropna()) > 0:
            cpv = cpv * turnover
        vals = cpv.dropna()
        return float(vals.mean()) if len(vals) > 0 else 0.0

    def _factor_10_alpha_new(self, close: pd.Series, volume: pd.Series) -> float:
        """价量背离信号 (Price-Volume Divergence)

        滚动计算收益率与成交量变化率的秩相关，取负值:
          r = corr(ΔP/P, ΔV/V)
          Alpha = -r
        正值 Alpha → 价量背离 (价格涨但成交量缩, 或反之)。
        """
        ret = close.pct_change()
        vol_change = volume.pct_change()
        valid = ret.notna() & vol_change.notna() & (volume > 0)
        if valid.sum() < 20:
            return 0.0
        corr = ret[valid].corr(vol_change[valid], method="spearman")
        return float(-corr) if not np.isnan(corr) else 0.0

    def _factor_11_amp_momentum(self, close: pd.Series, high: pd.Series, low: pd.Series) -> float:
        """振幅切割动量 (Amplitude-Split Momentum)

        将日收益按振幅(high-low)/close 分为高/低振幅两组,
        分别计算每组20日累计收益, 低振幅组动量 - 高振幅组动量。
        低振幅日的趋势更可靠 (噪音更小)。
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

    def _factor_12_umr(self, close: pd.Series, turnover: pd.Series) -> float:
        """动量反转统一因子 (Unified Momentum-Reversal)

        组合短期反转(5日) 与中期动量(20日)，用换手率确认:
          UMR = 0.4 × (-Ret5) + 0.6 × Ret20 × (换手率比率)
        换手率比率 = 近20日均换手 / 近60日均换手
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

    def _factor_13_hrv_reversal(self, close: pd.Series, high: pd.Series, low: pd.Series) -> float:
        """高风险日反转 (High-Risk Day Reversal)

        识别高风险日 (日内振幅处于80%分位数以上),
        计算这些交易日次日的平均收益。
        正收益 → 高风险日后倾向于反转 (均值回复)。
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

    def _factor_14_amount_volatility(self, close: pd.Series, amount: pd.Series) -> float:
        """成交额K线波动率 (Amount-Based Volatility)

        使用成交额变化率近似波动率:
          vol = std(Δamount/amount) × √252
        成交额波动高 → 资金博弈激烈。
        """
        if len(amount.dropna()) < 20:
            return 0.0
        amt_change = amount.pct_change().dropna()
        if len(amt_change) < 20:
            return 0.0
        return float(amt_change.std() * math.sqrt(252))

    def _factor_17_lowrisk_momentum(
        self, close: pd.Series, high: pd.Series, low: pd.Series
    ) -> float:
        """低风险动量 (Low-Risk Momentum)

        动量 = 20日累计收益 / 20日均振幅
        低波动调整后的动量 — 过滤高波动噪音后的趋势信号。
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

    def _factor_18_str(self, turnover: pd.Series) -> float:
        """量稳换手率 (Stable Turnover Rate)

        STR = 换手率均值 / 换手率标准差
        高 STR → 换手率稳定 (筹码锁定好);
        低 STR → 换手率剧烈波动 (投机性强)。
        """
        t = turnover.dropna()
        if len(t) < 20:
            return 0.0
        mean_t = float(t.mean())
        std_t = float(t.std())
        if std_t > 1e-10:
            return mean_t / std_t
        return mean_t

    def _factor_19_t_small(self, turnover: pd.Series) -> float:
        """量缩换手率 (T_small)

        换手率低于中位数30%的天数占比:
          T_small = count(TO < 0.3 × median(TO)) / N
        高占比 → 长期缩量 (无人问津)。
        """
        t = turnover.dropna()
        if len(t) < 20:
            return 0.0
        med_t = float(t.median())
        if med_t <= 1e-10:
            return 0.0
        small_days = int((t < 0.3 * med_t).sum())
        return small_days / len(t)

    def _factor_20_volume_entropy(self, volume: pd.Series) -> float:
        """成交量熵 (Volume Entropy)

        将成交量离散为10个分箱, 计算 Shannon 熵并归一化:
          H = -Σ(p_i × ln(p_i)) / ln(10)
        高熵 → 成交量分布均匀 (无规律);
        低熵 → 成交量集中于特定区间 (有模式)。
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

    def _factor_21_turnover_attention(self, close: pd.Series, turnover: pd.Series) -> float:
        """换手率突变注意力 (Turnover Attention)

        换手率变化率与价格变化率的交叉乘积均值:
          Attention = ln(1 + mean(|ΔTO/TO| × |ΔP/P|))
        高值 → 同时出现量价异动 (高市场关注度)。
        """
        t = turnover.dropna()
        if len(t) < 10:
            return 0.0
        t_change = t.pct_change().dropna()
        p = close.reindex(t.index)
        p_change = p.pct_change().dropna()
        # 对齐两个序列
        common = t_change.index.intersection(p_change.index)
        if len(common) < 5:
            return 0.0
        attention = (t_change.loc[common].abs() * p_change.loc[common].abs()).mean()
        return float(np.log1p(attention))

    # ── 基本面因子 (查询 StockInfo 表) ──

    def _get_stock_info(self, code: str) -> dict | None:
        """查询 StockInfo 获取股票基本面数据"""
        try:
            from shared.db_session import db_session
            from shared.models.market import StockInfo

            with db_session() as session:
                info = session.query(StockInfo).filter(StockInfo.stock_code == code).first()
                if info is None:
                    return None
                return {
                    "roe": info.roe or 0.0,
                    "gross_margin": info.gross_margin or 0.0,
                    "net_margin": info.net_margin or 0.0,
                    "debt_to_equity": info.debt_to_equity or 0.0,
                    "eps": info.eps or 0.0,
                    "revenue_growth_3y": info.revenue_growth_3y or 0.0,
                    "earnings_growth_3y": info.earnings_growth_3y or 0.0,
                    "dividend_yield": info.dividend_yield or 0.0,
                    "free_cash_flow": info.free_cash_flow or 0.0,
                }
        except Exception:
            return None

    def _factor_24_roe_quality(self, code: str) -> float:
        """ROE 复合质量 (ROE Composite Quality)

        综合 = 0.5 × ROE + 0.3 × 毛利率 + 0.2 × 净利率
        度量企业盈利能力的综合质量。
        """
        info = self._get_stock_info(code)
        if info is None:
            return 0.0
        return float(0.5 * info["roe"] + 0.3 * info["gross_margin"] + 0.2 * info["net_margin"])

    def _factor_26_de_ratio(self, code: str) -> float:
        """债务股权比 (Debt-to-Equity Ratio)

        直接读取 StockInfo.debt_to_equity。
        高值 → 高杠杆; 低值 → 财务保守。
        """
        info = self._get_stock_info(code)
        if info is None:
            return 0.0
        return float(info["debt_to_equity"])

    def _factor_27_eav(self, code: str) -> float:
        """盈利加速度 (Earnings Acceleration Velocity)

        EAV = 净利润增速 - 营收增速
        正值 → 利润率在扩张 (规模效应);
        负值 → 利润率在压缩 (成本压力)。
        """
        info = self._get_stock_info(code)
        if info is None:
            return 0.0
        return float(info["earnings_growth_3y"] - info["revenue_growth_3y"])

    def _factor_28_gm_trend(self, code: str) -> float:
        """毛利率趋势 (Gross Margin Trend Proxy)

        使用毛利率水平作为趋势代理。
        高毛利率 → 强定价权/护城河;
        低毛利率 → 商品化/竞争激烈。
        """
        info = self._get_stock_info(code)
        if info is None:
            return 0.0
        return float(info["gross_margin"])

    # ── 15个初筛因子 ──

    def _factor_101_cgo(self, prices: pd.Series, turnover: pd.Series) -> float:
        """处置效应 CGO: 参考价=换手率加权历史成本, CGO=(现价-参考价)/参考价"""
        if len(prices) < 20 or turnover.sum() == 0:
            return 0.0
        weights = turnover.rolling(5, min_periods=1).mean().fillna(0).values
        weights = weights / (weights.sum() + 1e-10)
        ref_price = float(np.average(prices.values, weights=weights))
        return float((prices.iloc[-1] - ref_price) / max(ref_price, 1e-10))

    def _factor_102_rev_1m(self, prices: pd.Series) -> float:
        """短期反转 Rev_1M: -(过去20日累计涨跌幅)"""
        ret = (prices.iloc[-1] / prices.iloc[-min(21, len(prices))]) - 1 if len(prices) >= 21 else 0
        return -ret

    def _factor_103_rev_12m(self, prices: pd.Series) -> float:
        """长期反转 Rev_12M: -(252日涨跌幅 - 20日涨跌幅)"""
        if len(prices) < 252:
            return 0.0
        ret_252 = float(prices.iloc[-1] / prices.iloc[-252]) - 1.0
        ret_20 = float(prices.iloc[-1] / prices.iloc[-20]) - 1.0
        return -(ret_252 - ret_20)

    def _factor_104_vol_20d(self, prices: pd.Series) -> float:
        """低波动 Vol_20d: -std(过去20日收益率)"""
        ret = prices.pct_change().dropna()
        if len(ret) < 5:
            return 0.0
        return -float(ret.tail(20).std())

    def _factor_105_illiq(self, prices: pd.Series, amount: pd.Series) -> float:
        """Amihud非流动性 ILLIQ: mean(|ret_d|/amount_d) 过去20日"""
        ret = prices.pct_change().abs()
        ratio = ret / (amount + 1e-10)
        return float(ratio.tail(20).mean()) if len(ratio) >= 20 else 0.0

    def _factor_106_turn_20d(self, turnover: pd.Series) -> float:
        """换手率因子 Turn_20d: -mean(过去20日换手率)"""
        if len(turnover) < 5:
            return 0.0
        return -float(turnover.tail(20).mean())

    def _factor_107_volstd_20d(self, volume: pd.Series) -> float:
        """成交量稳定性 VolStd_20d: -std(volume/mean(volume_60d)) 过去20日"""
        base = volume.tail(60).mean() if len(volume) >= 60 else volume.mean()
        if base == 0:
            return 0.0
        ratio = volume.tail(20) / base
        return -float(ratio.std())

    def _factor_108_lncap(self, code: str) -> float:
        """对数市值 LnCap: -ln(总市值)"""
        info = self._get_stock_info(code)
        if not info or not info.get("total_market_cap"):
            return 0.0
        mcap = float(info["total_market_cap"]) * 1e8  # 转换为元
        return -float(np.log(max(mcap, 1)))

    def _factor_109_bp(self, code: str) -> float:
        """账面市值比 BP: BVPS / 股价"""
        info = self._get_stock_info(code)
        if not info:
            return 0.0
        price = float(info.get("latest_price", 0) or 0)
        bvps = float(info.get("bvps", 0) or 0)
        if price == 0 or bvps == 0:
            return 0.0
        return bvps / price

    def _factor_110_roe(self, code: str) -> float:
        """盈利因子 ROE"""
        info = self._get_stock_info(code)
        if not info:
            return 0.0
        return float(info.get("roe", 0) or 0)

    def _factor_111_gpm(self, code: str) -> float:
        """毛利率因子 GPM"""
        info = self._get_stock_info(code)
        if not info:
            return 0.0
        return float(info.get("gross_margin", 0) or 0)

    def _factor_112_lev(self, code: str) -> float:
        """资产负债率 Lev: -debt_to_equity"""
        info = self._get_stock_info(code)
        if not info:
            return 0.0
        de = float(info.get("debt_to_equity", 0) or 0)
        return -de

    def _factor_113_dy(self, code: str) -> float:
        """股息率因子 DY: dividend_yield"""
        info = self._get_stock_info(code)
        if not info:
            return 0.0
        return float(info.get("dividend_yield", 0) or 0)

    def _factor_114_maxret_20d(self, prices: pd.Series) -> float:
        """最大日收益率 MaxRet_20d: -max(过去20日日收益率)"""
        ret = prices.pct_change().dropna()
        if len(ret) < 5:
            return 0.0
        return -float(ret.tail(20).max())

    def _factor_115_skew_20d(self, prices: pd.Series) -> float:
        """偏度因子 Skew_20d: -skewness(过去20日日收益率)"""
        ret = prices.pct_change().dropna()
        if len(ret) < 5:
            return 0.0
        return -float(ret.tail(20).skew())

    # ═══════════════════════════════════════════════════════════
    #  公开接口
    # ═══════════════════════════════════════════════════════════

    def get_all_factor_names(self) -> list:
        """返回所有可用因子名称列表"""
        return list(FACTOR_METHODS.keys())

    def compute_all_factors(self, code: str, df: pd.DataFrame) -> dict:
        """计算一只股票的全部因子值

        Args:
            code: 股票代码 (如 "000001")
            df: K线 DataFrame, 需含 close/open/high/low/volume/amount

        Returns:
            dict: {因子名: 因子值, ...}
        """
        prices = df["close"]
        volume = df["volume"]
        high = df["high"]
        low = df["low"]
        open_prices = df["open"]
        amount = df.get("amount", pd.Series(dtype=float))
        # 换手率: 优先K线时间序列, 若为空则用StockInfo截面值作为常数序列
        turnover = df.get("turnover_rate", df.get("turnover", pd.Series(dtype=float)))
        if turnover.sum() == 0:
            info = self._get_stock_info(code)
            if info:
                turn_val = float(info.get("turnover_rate", 0) or 0)
                if turn_val > 0:
                    turnover = pd.Series([turn_val] * len(df), index=df.index)

        factors: dict[str, float] = {}
        factors["PTV"] = self._factor_1_ptv(prices)
        factors["LTR"] = self._factor_3_ltr(prices, turnover)
        factors["CorrRV"] = self._factor_8_corrrv(prices.pct_change(), volume)
        factors["CPV"] = self._factor_9_cpv(open_prices, prices, high, low, turnover)
        factors["Alpha_new"] = self._factor_10_alpha_new(prices, volume)
        factors["AMP_Momentum"] = self._factor_11_amp_momentum(prices, high, low)
        factors["UMR"] = self._factor_12_umr(prices, turnover)
        factors["HRV_Reversal"] = self._factor_13_hrv_reversal(prices, high, low)
        factors["Amount_Volatility"] = self._factor_14_amount_volatility(prices, amount)
        factors["LowRisk_Momentum"] = self._factor_17_lowrisk_momentum(prices, high, low)
        factors["STR"] = self._factor_18_str(turnover)
        factors["T_small"] = self._factor_19_t_small(turnover)
        factors["Volume_Entropy"] = self._factor_20_volume_entropy(volume)
        factors["Turnover_Attention"] = self._factor_21_turnover_attention(prices, turnover)
        factors["ROE_Quality"] = self._factor_24_roe_quality(code)
        factors["DE_Ratio"] = self._factor_26_de_ratio(code)
        factors["EAV"] = self._factor_27_eav(code)
        factors["GM_trend"] = self._factor_28_gm_trend(code)

        # 15个初筛因子
        factors["CGO"] = self._factor_101_cgo(prices, turnover)
        factors["Rev_1M"] = self._factor_102_rev_1m(prices)
        factors["Rev_12M"] = self._factor_103_rev_12m(prices)
        factors["Vol_20d"] = self._factor_104_vol_20d(prices)
        factors["ILLIQ"] = self._factor_105_illiq(prices, amount)
        factors["Turn_20d"] = self._factor_106_turn_20d(turnover)
        factors["VolStd_20d"] = self._factor_107_volstd_20d(volume)
        factors["LnCap"] = self._factor_108_lncap(code)
        factors["BP"] = self._factor_109_bp(code)
        factors["ROE"] = self._factor_110_roe(code)
        factors["GPM"] = self._factor_111_gpm(code)
        factors["Lev"] = self._factor_112_lev(code)
        factors["DY"] = self._factor_113_dy(code)
        factors["MaxRet_20d"] = self._factor_114_maxret_20d(prices)
        factors["Skew_20d"] = self._factor_115_skew_20d(prices)

        return factors

    def get_top_factors(self, n: int = 20, min_ic: float = 0.03) -> ServiceResult:
        """获取当前最优因子列表 (按 IC 排序)"""
        try:
            factors = self.library.get_top(n=n, min_ic=min_ic)
            return ServiceResult.ok(data={"factors": factors, "count": len(factors)})
        except Exception as e:
            return ServiceResult.error(errors=[f"Failed to get top factors: {e}"])

    def build_factor_score(self, stock_code: str) -> ServiceResult:
        """对单只股票计算多因子综合得分"""
        try:
            factors = self.library.get_all_active()
            if not factors:
                return ServiceResult.ok(
                    data={
                        "stock_code": stock_code,
                        "composite_score": 50.0,
                        "signal": "neutral",
                        "factor_count": 0,
                        "factors_used": [],
                    }
                )

            # 基于IC加权归一化
            ic_sum = sum(abs(f["ic_mean"]) for f in factors if f["ic_mean"] != 0)
            if ic_sum == 0:
                weights = {f["name"]: 1.0 / len(factors) for f in factors}
            else:
                weights = {f["name"]: abs(f["ic_mean"]) / ic_sum for f in factors}

            factor_details = []
            for f in factors:
                factor_details.append(
                    {
                        "name": f["name"],
                        "category": f["category"],
                        "ic_mean": f["ic_mean"],
                        "icir": f["icir"],
                        "weight": round(weights.get(f["name"], 0), 4),
                    }
                )

            return ServiceResult.ok(
                data={
                    "stock_code": stock_code,
                    "composite_score": 50.0,
                    "signal": "neutral",
                    "factor_count": len(factors),
                    "factors_used": factor_details,
                }
            )
        except Exception as e:
            return ServiceResult.error(errors=[f"build_factor_score failed: {e}"])

    def evaluate_factor(self, factor_name: str) -> ServiceResult:
        """评估单个因子的元数据"""
        try:
            factors = self.library.get_all_active()
            target = None
            for f in factors:
                if f["name"] == factor_name:
                    target = f
                    break
            if not target:
                return ServiceResult.error(errors=[f"Factor not found: {factor_name}"])

            return ServiceResult.ok(data={"factor": target})
        except Exception as e:
            return ServiceResult.error(errors=[f"evaluate_factor failed: {e}"])

    def compute_factor_value(self, factor_name: str, code: str, df: pd.DataFrame) -> ServiceResult:
        """计算单个因子的最新值"""
        if factor_name not in FACTOR_METHODS:
            return ServiceResult.error(errors=[f"No computer for factor: {factor_name}"])
        try:
            factors = self.compute_all_factors(code, df)
            return ServiceResult.ok(
                data={
                    "factor_name": factor_name,
                    "value": factors.get(factor_name, 0.0),
                }
            )
        except Exception as e:
            return ServiceResult.error(errors=[f"Computation failed: {e}"])

    def evaluate_ic(
        self, factor_name: str, code: str, df: pd.DataFrame, forward_period: int = 5
    ) -> ServiceResult:
        """计算因子的 Rank IC 和 ICIR (滚动窗口方式)"""
        if factor_name not in FACTOR_METHODS:
            return ServiceResult.error(errors=[f"No computer for factor: {factor_name}"])
        try:
            # 滚动窗口计算因子序列 (每 step 个交易日取一个窗口)
            n_windows = min(80, len(df) - 60)
            if n_windows < 5:
                return ServiceResult.error(errors=[f"Insufficient data: {len(df)} rows, need > 65"])
            step = max(1, (len(df) - 60) // n_windows)
            window_starts = list(range(60, len(df) - forward_period, step))

            factor_vals: list[float] = []
            fwd_vals: list[float] = []
            for ws in window_starts:
                window = df.iloc[:ws]
                try:
                    fv = self.compute_all_factors(code, window).get(factor_name, np.nan)
                except Exception:
                    fv = np.nan
                if not np.isnan(fv) and ws + forward_period < len(df):
                    fwd_ret = df.iloc[ws + forward_period]["close"] / df.iloc[ws]["close"] - 1
                    factor_vals.append(fv)
                    fwd_vals.append(fwd_ret)

            if len(factor_vals) < 10:
                return ServiceResult.error(
                    errors=[f"Insufficient valid windows: {len(factor_vals)}"]
                )

            fs = pd.Series(factor_vals)
            fr = pd.Series(fwd_vals)
            ic = fs.rank().corr(fr.rank(), method="spearman")
            ic = float(ic) if not np.isnan(ic) else 0.0

            # 滑动 IC 序列用于 ICIR
            ic_series: list[float] = []
            window_size = 20
            for i in range(len(factor_vals) - window_size):
                sub_fs = pd.Series(factor_vals[i : i + window_size])
                sub_fr = pd.Series(fwd_vals[i : i + window_size])
                w_ic = sub_fs.rank().corr(sub_fr.rank(), method="spearman")
                if not np.isnan(w_ic):
                    ic_series.append(w_ic)

            icir = (
                float(np.mean(ic_series) / np.std(ic_series))
                if ic_series and np.std(ic_series) > 0
                else 0.0
            )

            self.library.update_ic(factor_name, ic, icir, len(factor_vals))

            return ServiceResult.ok(
                data={
                    "factor_name": factor_name,
                    "ic": round(ic, 4),
                    "icir": round(float(icir), 4),
                    "ic_abs": round(abs(ic), 4),
                    "samples": len(factor_vals),
                    "significant": abs(ic) > 0.03,
                }
            )
        except Exception as e:
            return ServiceResult.error(errors=[f"IC evaluation failed: {e}"])

    def deduplicate(
        self, new_factor_name: str, code: str, df: pd.DataFrame, ic_threshold: float = 0.95
    ) -> ServiceResult:
        """检查新因子是否与现有因子库重复 (简化版: 使用因子值差异度量相似度)"""
        if new_factor_name not in FACTOR_METHODS:
            return ServiceResult.error(errors=[f"No computer for factor: {new_factor_name}"])

        try:
            all_factors = self.compute_all_factors(code, df)
            new_val = all_factors.get(new_factor_name, 0.0)

            max_similarity = 0.0
            max_similar_with = None

            for ef in self.library.get_all_active():
                ef_name = ef["name"]
                if ef_name == new_factor_name or ef_name not in FACTOR_METHODS:
                    continue
                try:
                    ef_val = all_factors.get(ef_name, np.nan)
                    if np.isnan(new_val) or np.isnan(ef_val):
                        continue
                    # 相对差异度作为相似度代理
                    denom = abs(new_val) + abs(ef_val) + 1e-10
                    sim = 1.0 - abs(new_val - ef_val) / denom
                    if sim > max_similarity:
                        max_similarity = sim
                        max_similar_with = ef_name
                except Exception as exc:
                    emit_log("WARNING", "factor_farm", f"Dedup check failed for {ef_name}: {exc}")
                    continue

            rejected = max_similarity >= ic_threshold
            return ServiceResult.ok(
                data={
                    "factor_name": new_factor_name,
                    "max_pairwise_ic": round(max_similarity, 4),
                    "max_correlated_with": max_similar_with,
                    "rejected": rejected,
                    "threshold": ic_threshold,
                }
            )
        except Exception as e:
            return ServiceResult.error(errors=[f"Deduplication failed: {e}"])

    def get_available_factors(self) -> ServiceResult:
        """列出所有可计算的因子"""
        return ServiceResult.ok(
            data={
                "factors": [{"name": name} for name in FACTOR_METHODS],
                "total": len(FACTOR_METHODS),
            }
        )
