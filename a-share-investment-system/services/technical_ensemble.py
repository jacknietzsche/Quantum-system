"""5策略技术分析集成 - 趋势/均值回归/动量/波动率/统计套利 + Hurst指数"""

import math
from typing import ClassVar

import numpy as np
import pandas as pd

from services.base import BaseService, ServiceResult


def safe_float(value, default=0.0):
    try:
        if pd.isna(value) or (isinstance(value, float) and math.isnan(value)):
            return default
        return float(value)
    except (ValueError, TypeError):
        return default


def calculate_rsi(prices_df: pd.DataFrame, period: int = 14) -> pd.Series:
    delta = prices_df["close"].diff()
    gain = delta.where(delta > 0, 0.0).rolling(period).mean()
    loss = (-delta.where(delta < 0, 0.0)).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100.0 - (100.0 / (1.0 + rs))


def calculate_ema(df: pd.DataFrame, window: int) -> pd.Series:
    return df["close"].ewm(span=window, adjust=False).mean()


def calculate_bollinger_bands(prices_df: pd.DataFrame, window: int = 20):
    sma = prices_df["close"].rolling(window).mean()
    std_dev = prices_df["close"].rolling(window).std()
    return sma + (std_dev * 2), sma - (std_dev * 2)


def calculate_adx(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    df = df.copy()
    df["high_low"] = df["high"] - df["low"]
    df["high_close"] = abs(df["high"] - df["close"].shift())
    df["low_close"] = abs(df["low"] - df["close"].shift())
    df["tr"] = df[["high_low", "high_close", "low_close"]].max(axis=1)
    df["up_move"] = df["high"] - df["high"].shift()
    df["down_move"] = df["low"].shift() - df["low"]
    df["plus_dm"] = np.where(
        (df["up_move"] > df["down_move"]) & (df["up_move"] > 0), df["up_move"], 0
    )
    df["minus_dm"] = np.where(
        (df["down_move"] > df["up_move"]) & (df["down_move"] > 0), df["down_move"], 0
    )
    df["+di"] = 100 * (df["plus_dm"].ewm(span=period).mean() / df["tr"].ewm(span=period).mean())
    df["-di"] = 100 * (df["minus_dm"].ewm(span=period).mean() / df["tr"].ewm(span=period).mean())
    df["dx"] = 100 * abs(df["+di"] - df["-di"]) / (df["+di"] + df["-di"])
    df["adx"] = df["dx"].ewm(span=period).mean()
    return df[["adx", "+di", "-di"]]


def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high_low = df["high"] - df["low"]
    high_close = abs(df["high"] - df["close"].shift())
    low_close = abs(df["low"] - df["close"].shift())
    true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    return true_range.rolling(period).mean()


def calculate_hurst_exponent(price_series: pd.Series, max_lag: int = 20) -> float:
    """Hurst指数: <0.5均值回归, =0.5随机游走, >0.5趋势"""
    lags = range(2, min(max_lag, len(price_series) // 2))
    tau = [
        max(
            1e-8,
            np.sqrt(np.std(np.subtract(price_series.values[lag:], price_series.values[:-lag]))),
        )
        for lag in lags
    ]
    try:
        reg = np.polyfit(np.log(list(lags)), np.log(tau), 1)
        return float(reg[0])
    except (ValueError, RuntimeWarning):
        return 0.5


def weighted_signal_combination(signals: dict, weights: dict) -> dict:
    signal_values = {"bullish": 1, "neutral": 0, "bearish": -1}
    weighted_sum = 0.0
    total_confidence = 0.0
    for strategy, signal in signals.items():
        numeric = signal_values.get(signal["signal"], 0)
        weight = weights.get(strategy, 0.2)
        confidence = signal.get("confidence", 0.5)
        weighted_sum += numeric * weight * confidence
        total_confidence += weight * confidence
    final_score = weighted_sum / total_confidence if total_confidence > 0 else 0
    if final_score > 0.2:
        signal = "bullish"
    elif final_score < -0.2:
        signal = "bearish"
    else:
        signal = "neutral"
    return {
        "signal": signal,
        "confidence": round(abs(final_score), 3),
        "raw_score": round(final_score, 3),
    }


class TechnicalEnsemble(BaseService):
    """5策略技术分析集成:趋势+均值回归+动量+波动率+统计套利"""

    STRATEGY_WEIGHTS: ClassVar[dict[str, float]] = {
        "trend": 0.25,
        "mean_reversion": 0.20,
        "momentum": 0.25,
        "volatility": 0.15,
        "stat_arb": 0.15,
    }

    def analyze(self, df: pd.DataFrame) -> ServiceResult:
        """对OHLCV数据运行全部5个策略并合并信号"""
        try:
            required_cols = {"close", "high", "low", "volume"}
            if not required_cols.issubset(df.columns):
                return ServiceResult.error(
                    errors=[f"Missing columns: {required_cols - set(df.columns)}"]
                )
            if len(df) < 60:
                return ServiceResult.error(errors=["Need at least 60 rows of price data"])

            signals = {
                "trend": self._trend(df),
                "mean_reversion": self._mean_reversion(df),
                "momentum": self._momentum(df),
                "volatility": self._volatility(df),
                "stat_arb": self._stat_arb(df),
            }
            combined = weighted_signal_combination(signals, self.STRATEGY_WEIGHTS)
            hurst = calculate_hurst_exponent(df["close"])

            return ServiceResult.ok(
                data={
                    "signal": combined["signal"],
                    "confidence": combined["confidence"],
                    "raw_score": combined["raw_score"],
                    "hurst_exponent": round(hurst, 3),
                    "hurst_interpretation": "均值回归"
                    if hurst < 0.4
                    else ("趋势" if hurst > 0.6 else "随机游走"),
                    "strategy_signals": signals,
                }
            )
        except Exception as e:
            return ServiceResult.error(errors=[f"TechnicalEnsemble failed: {e}"])

    def _trend(self, df: pd.DataFrame) -> dict:
        ema_8 = calculate_ema(df, 8)
        ema_21 = calculate_ema(df, 21)
        ema_55 = calculate_ema(df, 55)
        adx = calculate_adx(df, 14)
        short_trend = ema_8.iloc[-1] > ema_21.iloc[-1]
        medium_trend = ema_21.iloc[-1] > ema_55.iloc[-1]
        trend_strength = safe_float(adx["adx"].iloc[-1] / 100.0)
        if short_trend and medium_trend:
            return {
                "signal": "bullish",
                "confidence": min(trend_strength, 1.0),
                "metrics": {
                    "adx": round(safe_float(adx["adx"].iloc[-1]), 1),
                    "trend_strength": round(trend_strength, 2),
                },
            }
        if not short_trend and not medium_trend:
            return {
                "signal": "bearish",
                "confidence": min(trend_strength, 1.0),
                "metrics": {
                    "adx": round(safe_float(adx["adx"].iloc[-1]), 1),
                    "trend_strength": round(trend_strength, 2),
                },
            }
        return {
            "signal": "neutral",
            "confidence": 0.5,
            "metrics": {
                "adx": round(safe_float(adx["adx"].iloc[-1]), 1),
                "trend_strength": round(trend_strength, 2),
            },
        }

    def _mean_reversion(self, df: pd.DataFrame) -> dict:
        ma_50 = df["close"].rolling(50).mean()
        std_50 = df["close"].rolling(50).std()
        z_score = (df["close"] - ma_50) / std_50
        bb_upper, bb_lower = calculate_bollinger_bands(df)
        price_vs_bb = (df["close"].iloc[-1] - bb_lower.iloc[-1]) / max(
            bb_upper.iloc[-1] - bb_lower.iloc[-1], 0.01
        )
        rsi_14 = calculate_rsi(df, 14)
        z = safe_float(z_score.iloc[-1])
        if z < -2 and price_vs_bb < 0.2:
            return {
                "signal": "bullish",
                "confidence": min(abs(z) / 4, 1.0),
                "metrics": {
                    "z_score": round(z, 2),
                    "price_vs_bb": round(safe_float(price_vs_bb), 2),
                    "rsi_14": round(safe_float(rsi_14.iloc[-1]), 1),
                },
            }
        if z > 2 and price_vs_bb > 0.8:
            return {
                "signal": "bearish",
                "confidence": min(abs(z) / 4, 1.0),
                "metrics": {
                    "z_score": round(z, 2),
                    "price_vs_bb": round(safe_float(price_vs_bb), 2),
                    "rsi_14": round(safe_float(rsi_14.iloc[-1]), 1),
                },
            }
        return {
            "signal": "neutral",
            "confidence": 0.5,
            "metrics": {
                "z_score": round(z, 2),
                "price_vs_bb": round(safe_float(price_vs_bb), 2),
                "rsi_14": round(safe_float(rsi_14.iloc[-1]), 1),
            },
        }

    def _momentum(self, df: pd.DataFrame) -> dict:
        returns = df["close"].pct_change()
        mom_1m = safe_float(returns.rolling(21).sum().iloc[-1])
        mom_3m = safe_float(returns.rolling(63).sum().iloc[-1]) if len(df) >= 63 else mom_1m
        mom_6m = safe_float(returns.rolling(126).sum().iloc[-1]) if len(df) >= 126 else mom_1m
        momentum_score = 0.4 * mom_1m + 0.3 * mom_3m + 0.3 * mom_6m
        volume_ma = df["volume"].rolling(21).mean()
        volume_confirmed = safe_float(df["volume"].iloc[-1]) > safe_float(volume_ma.iloc[-1])
        if momentum_score > 0.05 and volume_confirmed:
            return {
                "signal": "bullish",
                "confidence": min(abs(momentum_score) * 5, 1.0),
                "metrics": {
                    "mom_1m": round(mom_1m, 3),
                    "mom_3m": round(mom_3m, 3),
                    "mom_6m": round(mom_6m, 3),
                    "vol_confirmed": volume_confirmed,
                },
            }
        if momentum_score < -0.05 and volume_confirmed:
            return {
                "signal": "bearish",
                "confidence": min(abs(momentum_score) * 5, 1.0),
                "metrics": {
                    "mom_1m": round(mom_1m, 3),
                    "mom_3m": round(mom_3m, 3),
                    "mom_6m": round(mom_6m, 3),
                    "vol_confirmed": volume_confirmed,
                },
            }
        return {
            "signal": "neutral",
            "confidence": 0.5,
            "metrics": {"mom_1m": round(mom_1m, 3), "momentum_score": round(momentum_score, 3)},
        }

    def _volatility(self, df: pd.DataFrame) -> dict:
        returns = df["close"].pct_change()
        hist_vol = returns.rolling(21).std() * math.sqrt(252)
        vol_ma = hist_vol.rolling(63).mean()
        vol_regime = safe_float(hist_vol.iloc[-1] / max(vol_ma.iloc[-1], 0.001))
        vol_z = safe_float(
            (hist_vol.iloc[-1] - vol_ma.iloc[-1]) / max(hist_vol.rolling(63).std().iloc[-1], 0.001)
        )
        atr = calculate_atr(df)
        atr_ratio = safe_float(atr.iloc[-1] / df["close"].iloc[-1])
        if vol_regime < 0.8 and vol_z < -1:
            return {
                "signal": "bullish",
                "confidence": min(abs(vol_z) / 3, 1.0),
                "metrics": {
                    "hist_vol": round(safe_float(hist_vol.iloc[-1]) * 100, 1),
                    "vol_regime": round(vol_regime, 2),
                    "vol_z": round(vol_z, 2),
                    "atr_ratio": round(atr_ratio, 3),
                },
            }
        if vol_regime > 1.2 and vol_z > 1:
            return {
                "signal": "bearish",
                "confidence": min(abs(vol_z) / 3, 1.0),
                "metrics": {
                    "hist_vol": round(safe_float(hist_vol.iloc[-1]) * 100, 1),
                    "vol_regime": round(vol_regime, 2),
                    "vol_z": round(vol_z, 2),
                    "atr_ratio": round(atr_ratio, 3),
                },
            }
        return {
            "signal": "neutral",
            "confidence": 0.5,
            "metrics": {
                "hist_vol": round(safe_float(hist_vol.iloc[-1]) * 100, 1),
                "vol_regime": round(vol_regime, 2),
                "atr_ratio": round(atr_ratio, 3),
            },
        }

    def _stat_arb(self, df: pd.DataFrame) -> dict:
        returns = df["close"].pct_change()
        skew = safe_float(returns.rolling(63).skew().iloc[-1])
        kurt = safe_float(returns.rolling(63).kurt().iloc[-1]) if len(df) >= 63 else 0
        hurst = calculate_hurst_exponent(df["close"])
        if hurst < 0.4 and skew > 1:
            return {
                "signal": "bullish",
                "confidence": min((0.5 - hurst) * 2, 1.0),
                "metrics": {
                    "hurst": round(hurst, 3),
                    "skewness": round(skew, 2),
                    "kurtosis": round(kurt, 2),
                },
            }
        if hurst < 0.4 and skew < -1:
            return {
                "signal": "bearish",
                "confidence": min((0.5 - hurst) * 2, 1.0),
                "metrics": {
                    "hurst": round(hurst, 3),
                    "skewness": round(skew, 2),
                    "kurtosis": round(kurt, 2),
                },
            }
        return {
            "signal": "neutral",
            "confidence": 0.5,
            "metrics": {
                "hurst": round(hurst, 3),
                "skewness": round(skew, 2),
                "kurtosis": round(kurt, 2),
            },
        }
