"""Stage1: 量化初筛 — 行为活性过滤 + 价量硬门槛

废弃旧版对财务字段的依赖, 改为行为活性过滤:
  - 价格≥5, 市值≥10亿, 非ST (基本面最低门槛)
  - 近5日日均成交额≥2000万 (排除僵尸股)
  - 20日振幅>15% (排除织布机走势)
  - 换手率≥风格阈值 (0.3%~1% 取决于风格)
"""

from __future__ import annotations

from typing import Any

from shared.logging import emit_log


def stage1_quant_filter(
    universe: list[dict],
    config: Any,
    style: str = "hybrid",
) -> list[dict]:
    """第一级: 硬性量化过滤

    只过滤, 不打分; 确保进入后续环节的都是活跃标的。
    """
    passed = []
    for stock in universe:
        code = stock.get("stock_code", "")
        name = stock.get("stock_name", "")

        # ── 基础硬门槛 (所有风格通用) ──

        # ST 过滤
        if config.st_filter and (name.startswith(("*ST", "ST"))):
            continue

        # 价格过滤 (>=5, 排除低价股/ETF)
        price = stock.get("latest_price", stock.get("price", 0))
        if price < 5.0:
            continue

        # 市值过滤
        mc = stock.get("market_cap", 0)
        mc_min = getattr(config, "market_cap_min", 10)
        mc_max = getattr(config, "max_market_cap", 999999)
        if mc < mc_min or mc > mc_max:
            continue

        # 换手率过滤
        turnover = stock.get("turnover_rate", 0)
        if turnover < config.turnover_min:
            continue

        amt = stock.get("amount", 0)
        if amt > 0 and amt < 20_000_000:
            continue

        vol = stock.get("volatility_20d", 0)
        if vol > 0 and vol < 0.1:
            continue
        if vol > config.volatility_max:
            continue

        if style == "momentum" and config.require_ma_uptrend:
            ma5 = stock.get("ma5", 0)
            ma20 = stock.get("ma20", 0)
            if ma5 > 0 and ma20 > 0 and ma5 < ma20:
                continue

        passed.append(stock)

    # ── 排序 ──
    if style == "limit_up":
        passed.sort(key=lambda x: x.get("turnover_rate", 0), reverse=True)
    elif style == "momentum":
        passed.sort(key=lambda x: x.get("change_pct", 0), reverse=True)
    else:
        passed.sort(key=lambda x: x.get("market_cap", 0), reverse=True)

    # ── zzshare 热度/涨停加分调整 ──
    _use_zz = getattr(config, "use_zzshare_factors", True)
    if _use_zz and passed:
        try:
            from services.screening.zzshare_factors import ZZShareFactors

            zf = ZZShareFactors()
            if zf.load():
                for s in passed:
                    code = s.get("stock_code", "")
                    bonus = 0
                    if style == "limit_up" and zf.is_limit_up_stock(code):
                        bonus += 5
                    if style == "momentum" and zf.is_hot_stock(code):
                        bonus += 3
                    if bonus:
                        s["_zzshare_bonus"] = bonus

                def _sort_key(s):
                    base = s.get(
                        "turnover_rate"
                        if style == "limit_up"
                        else "change_pct"
                        if style == "momentum"
                        else "market_cap",
                        0,
                    )
                    base = abs(base) if isinstance(base, (int, float)) else 0
                    bonus = s.get("_zzshare_bonus", 0)
                    return base + bonus * (1e6 if style == "limit_up" else 100)

                passed.sort(key=_sort_key, reverse=True)
        except Exception:
            pass

    result = passed[: config.top_n]
    emit_log("INFO", "screening", f"[{style}] Stage1: {len(universe)} -> {len(result)}")
    return result
