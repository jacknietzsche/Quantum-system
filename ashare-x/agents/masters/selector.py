"""大师Agent选择算法。

设计依据: S04 §4.11, experiments exp12.5。
根据股票特征自动选择最相关的3个大师。
"""

from __future__ import annotations


def select_masters(stock_profile: dict) -> list[str]:
    """
    根据股票特征选择最相关的3个大师。

    Args:
        stock_profile: {pe_ratio, roe, volatility, growth}

    Returns:
        推荐的3个大师名称列表
    """
    pe = stock_profile.get("pe_ratio", 20)
    roe = stock_profile.get("roe", 15)
    volatility = stock_profile.get("volatility", 0.3)
    growth = stock_profile.get("revenue_growth", 0.1)

    scores: dict[str, int] = {}

    # 巴菲特: 低PE + 高ROE + 低波动  # noqa: ERA001
    scores["buffett"] = 0
    if pe < 25:
        scores["buffett"] += 2
    if roe > 15:
        scores["buffett"] += 2
    if volatility < 0.3:
        scores["buffett"] += 1

    # 芒格: 高ROE + 合理PE + 稳定增长  # noqa: ERA001
    scores["munger"] = 0
    if roe > 20:
        scores["munger"] += 2
    if 10 < pe < 30:
        scores["munger"] += 1
    if 0.05 < growth < 0.3:
        scores["munger"] += 1

    # 林奇: 成长性 + 合理估值  # noqa: ERA001
    scores["lynch"] = 0
    if growth > 0.2:
        scores["lynch"] += 2
    if pe < growth * 100:
        scores["lynch"] += 2

    # 伯里: 高波动 + 低PE  # noqa: ERA001
    scores["burry"] = 0
    if volatility > 0.4:
        scores["burry"] += 2
    if pe < 15:
        scores["burry"] += 2

    # 伍德: 高成长 + 高波动  # noqa: ERA001
    scores["wood"] = 0
    if growth > 0.3:
        scores["wood"] += 2
    if volatility > 0.35:
        scores["wood"] += 1

    # 德鲁肯米勒: 中等波动 + 稳定增长  # noqa: ERA001
    scores["druckenmiller"] = 0
    if 0.2 < volatility < 0.4:
        scores["druckenmiller"] += 2
    if growth > 0.1:
        scores["druckenmiller"] += 1

    # 费雪: 高成长 + 高ROE  # noqa: ERA001
    scores["fisher"] = 0
    if growth > 0.25:
        scores["fisher"] += 2
    if roe > 20:
        scores["fisher"] += 1

    # 按分数排序，取前3
    sorted_masters = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return [name for name, score in sorted_masters[:3] if score > 0]
