"""日频技术指标计算 - 趋势/动量/超买超卖"""

import numpy as np
import pandas as pd

from shared.indicators import compute_all_ma, compute_rsi


def ma(values: list[float], window: int) -> list[float]:
    arr = np.array(values, dtype=float)
    if len(arr) < window:
        return list(arr)
    cumsum = np.cumsum(arr)
    cumsum[window:] = cumsum[window:] - cumsum[:-window]
    result = np.full_like(arr, np.nan)
    result[window - 1 :] = cumsum[window - 1 :] / window
    return [float(x) for x in result.tolist()]


def rsi(values: list[float], period: int = 14) -> float:
    if len(values) < period + 1:
        return 50.0
    deltas = np.diff(np.array(values[-period - 1 :], dtype=float))
    gains = deltas[deltas > 0].sum()
    losses = (-deltas[deltas < 0]).sum()
    if losses == 0:
        return 100.0
    rs = gains / losses
    return float(100.0 - 100.0 / (1.0 + rs))


def _ema(values: np.ndarray, period: int) -> np.ndarray:
    alpha = 2.0 / (period + 1)
    result = np.full_like(values, np.nan)
    result[0] = values[0]
    for i in range(1, len(values)):
        result[i] = alpha * values[i] + (1 - alpha) * result[i - 1]
    return result


def macd(values: list[float]) -> dict[str, float]:
    arr = np.array(values, dtype=float)
    if len(arr) < 26:
        return {"dif": 0.0, "dea": 0.0, "bar": 0.0}
    ema12 = _ema(arr, 12)
    ema26 = _ema(arr, 26)
    dif = ema12[-1] - ema26[-1]
    dif_series = ema12 - ema26
    dea = float(_ema(dif_series, 9)[-1]) if len(dif_series) >= 9 else 0.0
    bar = (dif - dea) * 2
    return {"dif": float(dif), "dea": float(dea), "bar": float(bar)}


def trend_strength(values: list[float]) -> float:
    if len(values) < 20:
        return 0.0
    ma5_list = ma(values, 5)
    ma20_list = ma(values, 20)
    if np.isnan(ma5_list[-1]) or np.isnan(ma20_list[-1]):
        return 0.0
    spread = (ma5_list[-1] - ma20_list[-1]) / ma20_list[-1] * 100
    if spread > 5:
        return min(100.0, 50.0 + spread * 5)
    if spread > 0:
        return 50.0 + spread * 5
    return max(0.0, 50.0 + spread * 5)


def macd_status(dif: float, dea: float, prev_dif: float, prev_dea: float) -> str:  # noqa: PLR0911
    if prev_dif <= prev_dea and dif > dea and dif > 0:
        return "GOLDEN_CROSS_ZERO"
    if prev_dif <= prev_dea and dif > dea:
        return "GOLDEN_CROSS"
    if prev_dif >= 0 and dif < 0:
        return "CROSSING_DOWN"
    if dif > dea and dif > 0:
        return "BULLISH"
    if dif < 0 and dea < 0:
        return "BEARISH"
    if prev_dif >= prev_dea and dif < dea:
        return "DEATH_CROSS"
    return "NEUTRAL"


class TrendAnalyzer:
    """日频趋势分析器 - 纯 NumPy,无 pandas 依赖"""

    @staticmethod
    def analyze(closes: list[float], volumes: list[float]) -> dict:
        if len(closes) < 20:
            return {"valid": False}

        mas = compute_all_ma(pd.Series(closes))

        prev = {"dif": 0.0, "dea": 0.0}
        curr = {"dif": 0.0, "dea": 0.0}
        if len(closes) >= 27:
            m = macd(closes[:-1])
            prev = {"dif": m["dif"], "dea": m["dea"]}
            m2 = macd(closes)
            curr = {"dif": m2["dif"], "dea": m2["dea"]}

        vol_arr = np.array(volumes, dtype=float)
        vol_5d_avg = float(np.mean(vol_arr[-6:-1])) if len(vol_arr) >= 6 else 1.0
        vol_ratio = float(vol_arr[-1] / max(vol_5d_avg, 0.01)) if vol_5d_avg > 0 else 1.0

        price = closes[-1]
        ma5_val = mas["ma5"] if not np.isnan(mas["ma5"]) else 0.0
        ma10_val = mas["ma10"] if not np.isnan(mas["ma10"]) else 0.0
        ma20_val = mas["ma20"] if not np.isnan(mas["ma20"]) else 0.0

        bias_ma5 = (price / ma5_val - 1) * 100 if ma5_val > 0 else 0.0
        bias_ma10 = (price / ma10_val - 1) * 100 if ma10_val > 0 else 0.0

        ma_uptrend = ma5_val > ma10_val > ma20_val and ma5_val > 0 and ma10_val > 0 and ma20_val > 0

        return {
            "valid": True,
            "ma5": ma5_val,
            "ma10": ma10_val,
            "ma20": ma20_val,
            "bias_ma5": bias_ma5,
            "bias_ma10": bias_ma10,
            "rsi_6": compute_rsi(pd.Series(closes), 6),
            "rsi_12": compute_rsi(pd.Series(closes), 12),
            "macd": macd(closes),
            "macd_status": macd_status(curr["dif"], curr["dea"], prev["dif"], prev["dea"]),
            "trend_strength": trend_strength(closes),
            "daily_volume_ratio": vol_ratio,
            "ma_uptrend": ma_uptrend,
        }
