"""市场状态检测工具。

设计依据: S08 §8.2, experiments exp9.1。
4指标综合评分 → 市场状态。
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def detect_market_state(indices_data: dict) -> str:
    """
    市场状态检测:
    1. 上证20日涨跌幅
    2. 涨跌家数比
    3. 成交量/20日均量
    4. 北向资金5日净流入
    综合评分 → 市场状态
    """
    sh_change_20d = indices_data.get("sh_change_20d", 0)
    advance_count = indices_data.get("advance_count", 0)
    decline_count = indices_data.get("decline_count", 0)
    volume = indices_data.get("volume", 0)
    volume_ma20 = indices_data.get("volume_ma20", volume)
    north_flow_5d = indices_data.get("north_flow_5d", 0)

    total = advance_count + decline_count
    advance_ratio = advance_count / total if total > 0 else 0.5
    volume_ratio = volume / volume_ma20 if volume_ma20 > 0 else 1.0

    score = 0
    # 趋势
    if sh_change_20d > 0.05:
        score += 2
    elif sh_change_20d > 0:
        score += 1
    elif sh_change_20d < -0.05:
        score -= 2
    elif sh_change_20d < 0:
        score -= 1

    # 广度
    if advance_ratio > 0.65:
        score += 1
    elif advance_ratio < 0.35:
        score -= 1

    # 活跃度
    if volume_ratio > 1.5:
        score += 1
    elif volume_ratio < 0.5:
        score -= 1

    # 外资
    if north_flow_5d > 50:
        score += 1
    elif north_flow_5d < -50:
        score -= 1

    # 映射到状态
    if score >= 4:
        return "BULL"
    if score >= 1:
        return "NEUTRAL"
    if score >= -1:
        return "NEUTRAL"
    if score >= -4:
        return "BEAR"
    return "PANIC"


def get_position_cap(state: str) -> float:
    """根据市场状态返回仓位上限。"""
    caps = {
        "PANIC": 0.10,
        "BEAR": 0.30,
        "NEUTRAL": 0.60,
        "BULL": 0.80,
        "OVERHEAT": 0.50,
    }
    return caps.get(state, 0.50)
