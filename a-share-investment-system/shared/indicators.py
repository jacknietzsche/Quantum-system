"""技术指标计算库 — 纯 NumPy/Pandas 实现,零外部依赖"""

import numpy as np
import pandas as pd


def compute_ma(close: pd.Series, window: int) -> float:
    """计算移动平均线"""
    return float(close.rolling(window).mean().iloc[-1])


def compute_all_ma(close: pd.Series) -> dict[str, float]:
    """计算多周期移动平均线 (MA5/10/20/60)"""
    return {
        "ma5": compute_ma(close, 5),
        "ma10": compute_ma(close, 10),
        "ma20": compute_ma(close, 20),
        "ma60": compute_ma(close, 60) if len(close) >= 60 else compute_ma(close, 20),
    }


def compute_rsi(close: pd.Series, window: int = 14) -> float:
    """计算 RSI 指标"""
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0).rolling(window).mean().iloc[-1]
    loss = (-delta.where(delta < 0, 0.0)).rolling(window).mean().iloc[-1]
    if loss == 0 or np.isnan(loss) or np.isnan(gain):
        return 50.0
    rs = gain / loss
    return float(100 - 100 / (1 + rs))


def compute_volatility(close: pd.Series, window: int = 20) -> float:
    """计算年化波动率"""
    returns = close.pct_change()
    std = returns.rolling(window).std().iloc[-1]
    return float(std * (252**0.5)) if std and not np.isnan(std) else 0.0


def compute_max_drawdown(close: pd.Series) -> float:
    """计算最大回撤"""
    cummax = close.cummax()
    dd = ((close - cummax) / cummax).min()
    return float(dd) if not np.isnan(dd) else 0.0


def classify_trend(ma5: float, ma10: float, ma20: float) -> str:
    """趋势分类: 上升 / 下降 / 震荡"""
    if ma5 > ma10 > ma20:
        return "上升"
    if ma5 < ma10 < ma20:
        return "下降"
    return "震荡"


def classify_ma_alignment(ma5: float, ma10: float, ma20: float, ma60: float) -> str:
    """均线排列: 多头 / 空头 / 交叉"""
    if ma5 > ma10 > ma20 > ma60:
        return "多头"
    if ma5 < ma10 < ma20 < ma60:
        return "空头"
    return "交叉"


def compute_all_indicators(close: pd.Series) -> dict:
    """批量计算所有常用技术指标"""
    mas = compute_all_ma(close)
    rsi = compute_rsi(close)
    vol = compute_volatility(close)
    max_dd = compute_max_drawdown(close)
    trend = classify_trend(mas["ma5"], mas["ma10"], mas["ma20"])
    alignment = classify_ma_alignment(mas["ma5"], mas["ma10"], mas["ma20"], mas["ma60"])
    return {
        **mas,
        "rsi_14": rsi,
        "volatility_20d": vol,
        "max_drawdown_60d": max_dd,
        "trend": trend,
        "ma_alignment": alignment,
    }
