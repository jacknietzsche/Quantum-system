"""HardFilter - 三策略量化初筛 + 负面排除 + 配置验证 + 动态阈值"""

import logging
from collections.abc import Callable

from shared.logging import emit_log

logger = logging.getLogger(__name__)

CONFIG_REQUIRED_FIELDS = [
    "min_amount",
    "min_change_5d",
    "min_vol_ratio",
    "min_change_60d",
    "min_market_cap",
    "max_market_cap",
    "min_roe",
    "max_asset_liability_ratio",
    "min_turnover_rate",
]

REGIME_ADJUSTMENT = {
    "BULL": {
        "min_change_5d": 1.2,
        "min_change_60d": 1.2,  # 牛市中提高涨幅门槛
        "min_amount": 1.2,  # 提高成交额门槛
        "min_roe": 1.1,  # 提高ROE门槛
    },
    "BEAR": {
        "min_change_5d": 0.8,
        "min_change_60d": 0.8,  # 熊市中降低涨幅门槛
        "min_amount": 0.7,  # 降低成交额门槛
        "min_market_cap": 0.8,
        "max_market_cap": 1.3,  # 放宽市值范围
    },
    "VOLATILE": {
        "min_amount": 1.3,  # 高波动时要求更高流动性
        "min_vol_ratio": 1.2,  # 提高量比要求
    },
}


class ConfigValidator:
    """启动时校验HardFilter配置完整性"""

    @staticmethod
    def validate_all():
        """校验所有风格的配置,缺失必填字段时打印警告"""
        from shared.config import Config

        cfg = Config()
        styles = cfg.get("screening.styles", {})
        all_ok = True
        for style, style_cfg in styles.items():
            hf = style_cfg.get("hard_filters", {})
            missing = [f for f in CONFIG_REQUIRED_FIELDS if f not in hf]
            if missing:
                logger.warning(f"[ConfigValidator] {style}.hard_filters 缺少字段: {missing}")
                all_ok = False
        return all_ok


class HardFilter:
    """量化初筛引擎 - 短期/中期/长期三策略 + 通用负面排除 + 动态阈值"""

    def __init__(self, style: str = "hybrid", market_regime: str = "NEUTRAL"):
        self.style = style
        self.market_regime = market_regime
        self._consecutive_low_pass = 0
        self._load_config()

    def _load_config(self):
        from shared.config import Config

        cfg = Config()
        sc = cfg.get(f"screening.styles.{self.style}.hard_filters", {})
        self.min_amount = sc.get("min_amount", 100000000)
        self.min_change_5d = sc.get("min_change_5d", 5)
        self.min_vol_ratio = sc.get("min_vol_ratio", 1.5)
        self.min_change_60d = sc.get("min_change_60d", 20)
        self.min_market_cap = sc.get("min_market_cap", 50)
        self.max_market_cap = sc.get("max_market_cap", 500)
        self.min_roe = sc.get("min_roe", 15)
        self.max_debt_equity = sc.get("max_asset_liability_ratio", 1.5)
        self.min_turnover_rate = sc.get("min_turnover_rate", 0.5)
        self.min_hybrid_roe = sc.get("min_roe_hybrid", 10)

        # 加载 market_regime 覆盖
        regime_overrides = sc.get("regime_overrides", {})
        self._regime_overrides = regime_overrides

    def _apply_regime_adjustment(self):
        """根据市场状态动态调整阈值"""
        adjustment = REGIME_ADJUSTMENT.get(self.market_regime, {})
        for param, factor in adjustment.items():
            current = getattr(self, param, None)
            if current is not None and isinstance(current, (int, float)):
                new_val = current * factor
                setattr(self, param, new_val)

        # 加载配置中的 regime_overrides(优先级高于内置)
        override = self._regime_overrides.get(self.market_regime, {})
        for param, value in override.items():
            if hasattr(self, param):
                setattr(self, param, value)

    def _apply_low_pass_adjustment(self):
        """连续通过率<1%时自动降低所有阈值 (累计最多降50%)"""
        if self._consecutive_low_pass <= 0:
            return
        reduction = min(self._consecutive_low_pass * 0.10, 0.50)
        for attr in (
            "min_amount",
            "min_change_5d",
            "min_vol_ratio",
            "min_change_60d",
            "min_roe",
            "min_turnover_rate",
            "min_market_cap",
        ):
            current = getattr(self, attr, None)
            if current is not None and isinstance(current, (int, float)):
                setattr(self, attr, current * (1 - reduction))
        logger.info(f"[HardFilter] 低通过率熔断: 阈值降低{reduction:.0%}")

    def apply(self, universe: list[dict]) -> list[dict]:
        self._consecutive_low_pass = 0  # Reset each run to prevent accumulation
        self._apply_regime_adjustment()
        self._apply_low_pass_adjustment()

        universe = self._negative_exclusion(universe)
        candidates = self._get_filter()(universe)
        result = self._fallback_if_empty(candidates, universe)

        emit_log(
            "INFO",
            "screening",
            f"[{self.style}] HardFilter: {len(result)}/{len(universe)} 通过 "
            f"(负排除前={len(universe) + len(candidates) - len(result) if len(universe) > 0 else 0})",
        )
        pass_rate = len(result) / max(len(universe), 1)
        if pass_rate < 0.01 and len(universe) > 100:
            self._consecutive_low_pass += 1
        else:
            self._consecutive_low_pass = 0

        return result

    def _get_filter(self) -> Callable:
        style_map = {
            "limit_up": self._filter_short_term,
            "momentum": self._filter_mid_term,
            "value": self._filter_long_term,
            "hybrid": self._filter_hybrid,
        }
        return style_map.get(self.style, self._filter_hybrid)

    def _filter_short_term(self, stocks: list[dict]) -> list[dict]:
        """短期(1d-4w):成交额>1亿, 5日涨幅>5%, 量比>1.5, 均线多头, LHB净流入>0"""
        passed = []
        for s in stocks:
            tags = []
            lhb = s.get("lhb_net_buy")
            if lhb is not None and lhb < 0:
                continue
            if s.get("amount", 0) >= self.min_amount:
                tags.append("liquidity_amount_1e8")
            if s.get("change_pct_5d", -999) >= self.min_change_5d:
                tags.append("momentum_5d_pct")
            if s.get("volume_ratio", 0) >= self.min_vol_ratio:
                tags.append("volume_ratio_1_5")
            ma20, ma60 = s.get("ma20", 0), s.get("ma60", 0)
            if ma20 > 0 and ma60 > 0 and s.get("price", 0) > ma20 > ma60:
                tags.append("ma_bullish_alignment")
            if len(tags) == 4:
                s["admission_tags"] = tags
                passed.append(s)
        passed.sort(key=lambda x: x.get("amount", 0), reverse=True)
        return passed[:200]

    def _filter_mid_term(self, stocks: list[dict]) -> list[dict]:
        """中期(1-12m): 60日涨幅>20%, 股价>年线(或无年线时降级ma60), PE>0, 市值50-500亿, 净利润增长率>25%"""
        passed = []
        for s in stocks:
            tags = []
            eg = s.get("earnings_growth_3y", 0)
            if eg > 0 and eg < 50:
                continue
            if s.get("change_pct_60d", -999) >= self.min_change_60d:
                tags.append("momentum_60d_pct")
            # ma250 优先;数据不足时降级到 ma60
            ma250 = s.get("ma250", 0)
            if ma250 > 0 and s.get("price", 0) > ma250:
                tags.append("price_above_ma250")
            elif ma250 <= 0:
                ma60 = s.get("ma60", 0)
                if ma60 > 0 and s.get("price", 0) > ma60:
                    tags.append("price_above_ma60")
            if s.get("pe", 0) > 0:
                tags.append("pe_positive")
            mcap = s.get("market_cap", 0)
            if self.min_market_cap <= mcap <= self.max_market_cap:
                tags.append("mcap_in_range")
            if len(tags) == 4:
                s["admission_tags"] = tags
                passed.append(s)
        passed.sort(key=lambda x: x.get("change_pct_60d", 0), reverse=True)
        return passed[:200]

    def _filter_long_term(self, stocks: list[dict]) -> list[dict]:
        """长期(1y+): ROE>15%(当期), FCF>0, 负债率<60%, PE>0"""
        passed = []
        for s in stocks:
            tags = []
            if s.get("roe", 0) >= self.min_roe:
                tags.append("roe_above_15")
            if s.get("free_cash_flow", 0) > 0:
                tags.append("fcf_positive")
            debt = s.get("debt_to_equity", 0)
            if not debt or debt <= self.max_debt_equity:
                tags.append("debt_controlled")
            if s.get("pe", 0) > 0:
                tags.append("pe_positive")
            if len(tags) == 4:
                s["admission_tags"] = tags
                passed.append(s)
        passed.sort(key=lambda x: x.get("roe", 0), reverse=True)
        return passed[:200]

    def _filter_hybrid(self, stocks: list[dict]) -> list[dict]:
        """混合: 流动性+趋势+基本面(负债率>3直接淘汰)"""
        passed = []
        for s in stocks:
            tags = []
            if s.get("amount", 0) >= self.min_amount:
                tags.append("liquidity_amount_min")
            if s.get("turnover_rate", 0) >= self.min_turnover_rate:
                tags.append("turnover_rate_min")
            ma20 = s.get("ma20", 0)
            if ma20 > 0 and s.get("price", 0) > ma20:
                tags.append("price_above_ma20")
            if s.get("pe", 0) > 0:
                tags.append("pe_positive")
            if s.get("roe", 0) >= self.min_hybrid_roe:
                tags.append("roe_above_10")
            debt = s.get("debt_to_equity", 0)
            if not debt or debt <= 3:
                tags.append("debt_controlled")
            else:
                continue  # 高负债直接淘汰
            if len(tags) >= 5:
                s["admission_tags"] = tags
                passed.append(s)

        def _hybrid_score(s):
            score = 0
            score += min(s.get("turnover_rate", 0) * 5, 30)  # 换手率 0-30
            score += min(s.get("roe", 0) * 2, 30)  # ROE 0-30
            score += min(s.get("volume_ratio", 0) * 10, 20)  # 量比 0-20
            pe = s.get("pe", 0)
            if 5 < pe < 30:
                score += 20  # 合理PE区间
            elif 30 <= pe < 60:
                score += 10
            return score

        passed.sort(key=_hybrid_score, reverse=True)
        return passed[:200]

    def _negative_exclusion(self, stocks: list[dict]) -> list[dict]:
        """通用负面排除"""
        result = [
            s
            for s in stocks
            if not s.get("stock_name", "").startswith(("*ST", "ST", "退"))
            # 上市天数 > 250: 0=数据未填充则放行,有数据时严格检查
            and ((s.get("listing_days") or 0) == 0 or (s.get("listing_days") or 0) >= 250)
            and s.get("price", 0) > 0
        ]
        excluded = len(stocks) - len(result)
        listing_excluded = sum(
            1
            for s in stocks
            if (s.get("listing_days") or 0) > 0 and (s.get("listing_days") or 0) < 250
        )
        st_count = sum(1 for s in stocks if s.get("stock_name", "").startswith(("*ST", "ST", "退")))
        zero_price = sum(1 for s in stocks if s.get("price", 0) <= 0)
        if excluded > 0:
            emit_log(
                "INFO",
                "screening",
                f"负排除: {excluded}只排除(ST={st_count},零价={zero_price},上市天数不足={listing_excluded})",
            )
        return result

    @staticmethod
    def _fallback_if_empty(passed: list[dict], universe: list[dict]) -> list[dict]:
        if len(passed) >= 50:
            return passed
        before = len(passed)
        passed_set = {s.get("stock_code", "") for s in passed}
        extras = sorted(universe, key=lambda x: x.get("amount", 0), reverse=True)
        for s in extras:
            code = s.get("stock_code", "")
            if code in passed_set or s.get("price", 0) <= 0:
                continue
            passed.append(s)
            passed_set.add(code)
            if len(passed) >= 50:
                break
        if before < 50:
            emit_log(
                "WARNING",
                "screening",
                f"空结果回补: 初筛仅{before}只, 从universe补充{len(passed) - before}只 → {len(passed)}只",
            )
        return passed

    @staticmethod
    def get_style_admission_tags(style: str, stock: dict) -> list[str]:
        """基于 style 返回准入标签列表(纯计算,无副作用)"""
        style_tag_map = {
            "short_term": [
                "liquidity_amount_1e8",
                "momentum_5d_pct",
                "volume_ratio_1_5",
                "ma_bullish_alignment",
            ],
            "limit_up": [
                "liquidity_amount_1e8",
                "momentum_5d_pct",
                "volume_ratio_1_5",
                "ma_bullish_alignment",
            ],
            "mid_term": ["momentum_60d_pct", "price_above_ma250", "pe_positive", "mcap_in_range"],
            "momentum": ["momentum_60d_pct", "price_above_ma250", "pe_positive", "mcap_in_range"],
            "long_term": ["roe_above_15", "fcf_positive", "debt_controlled", "pe_positive"],
            "value": ["roe_above_15", "fcf_positive", "debt_controlled", "pe_positive"],
            "hybrid": [
                "liquidity_amount_min",
                "turnover_rate_min",
                "price_above_ma20",
                "pe_positive",
                "roe_above_10",
                "debt_controlled",
            ],
        }
        expected = style_tag_map.get(style, [])
        actual = stock.get("admission_tags", [])
        return [t for t in expected if t in actual]
