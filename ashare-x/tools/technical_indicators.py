"""技术指标计算（MA/MACD/RSI/Bollinger）。

设计依据: S05 §5.11, experiments exp2.1-2.3。
纯pandas实现，无需额外依赖。50只股票0.11秒。
"""

from __future__ import annotations

import pandas as pd


def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    计算技术指标（输入需要有 close 列）。
    返回包含新列的DataFrame。
    """
    result = df.copy()

    # MA均线
    result["ma5"] = result["close"].rolling(5).mean()
    result["ma10"] = result["close"].rolling(10).mean()
    result["ma20"] = result["close"].rolling(20).mean()
    result["ma60"] = result["close"].rolling(60).mean()

    # MACD
    ema12 = result["close"].ewm(span=12).mean()
    ema26 = result["close"].ewm(span=26).mean()
    result["macd"] = ema12 - ema26
    result["macd_signal"] = result["macd"].ewm(span=9).mean()
    result["macd_hist"] = result["macd"] - result["macd_signal"]

    # RSI
    delta = result["close"].diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss
    result["rsi_14"] = 100 - (100 / (1 + rs))

    # Bollinger Bands
    result["bb_mid"] = result["close"].rolling(20).mean()
    result["bb_std"] = result["close"].rolling(20).std()
    result["bb_upper"] = result["bb_mid"] + 2 * result["bb_std"]
    result["bb_lower"] = result["bb_mid"] - 2 * result["bb_std"]

    # ATR
    high_low = result["high"] - result["low"]
    high_close = (result["high"] - result["close"].shift()).abs()
    low_close = (result["low"] - result["close"].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    result["atr_14"] = tr.rolling(14).mean()

    return result


def get_latest_indicators(df: pd.DataFrame) -> dict:
    """获取最新一行的技术指标值。"""
    computed = compute_indicators(df)
    latest = computed.iloc[-1]
    return {
        "close": latest.get("close"),
        "ma5": latest.get("ma5"),
        "ma20": latest.get("ma20"),
        "ma60": latest.get("ma60"),
        "macd": latest.get("macd"),
        "macd_signal": latest.get("macd_signal"),
        "rsi_14": latest.get("rsi_14"),
        "bb_upper": latest.get("bb_upper"),
        "bb_lower": latest.get("bb_lower"),
        "atr_14": latest.get("atr_14"),
    }
