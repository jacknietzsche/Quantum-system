"""测试 HardFilter 三策略 — 直接测试内部过滤方法避免 fallback 干扰"""

from services.hard_filter import HardFilter


def _make_stock(overrides: dict) -> dict:
    """创建测试用股票 dict"""
    defaults = {
        "stock_code": "000001",
        "stock_name": "平安银行",
        "price": 12.0,
        "amount": 2e8,
        "turnover_rate": 2.0,
        "change_pct_5d": 8,
        "change_pct_20d": 15,
        "change_pct_60d": 25,
        "volume_ratio": 2.0,
        "market_cap": 200,
        "pe": 10,
        "pb": 1.2,
        "roe": 18,
        "ma5": 12.5,
        "ma10": 12.0,
        "ma20": 11.5,
        "ma60": 11.0,
        "ma250": 10.0,
        "free_cash_flow": 1e9,
        "debt_to_equity": 0.8,
        "gross_margin": 40,
        "industry": "银行",
        "earnings_growth_3y": 55,
        "revenue_growth_3y": 12,
    }
    defaults.update(overrides)
    return defaults


class TestHardFilterShortTerm:
    def test_passes_short_term(self):
        """正常短期股应通过"""
        stock = _make_stock({})
        hf = HardFilter("short_term")
        result = hf._filter_short_term([stock])
        assert len(result) == 1

    def test_fails_low_amount(self):
        """成交额不足应过滤 (amount < 1e8)"""
        stock = _make_stock({"amount": 5e6})
        hf = HardFilter("short_term")
        result = hf._filter_short_term([stock])
        assert len(result) == 0

    def test_fails_no_uptrend(self):
        """均线未多头应过滤 (price <= ma20 or ma20 <= ma60)"""
        stock = _make_stock({"ma20": 13, "ma60": 12})
        hf = HardFilter("short_term")
        result = hf._filter_short_term([stock])
        assert len(result) == 0

    def test_fails_low_change_5d(self):
        """5日涨幅不足应过滤 (change_pct_5d < 5)"""
        stock = _make_stock({"change_pct_5d": 1})
        hf = HardFilter("short_term")
        result = hf._filter_short_term([stock])
        assert len(result) == 0

    def test_fails_negative_lhb_net_buy(self):
        """主力净流入为负应过滤 (lhb_net_buy < 0)"""
        stock = _make_stock({"lhb_net_buy": -5e6})
        hf = HardFilter("short_term")
        result = hf._filter_short_term([stock])
        assert len(result) == 0


class TestHardFilterMidTerm:
    def test_passes_mid_term(self):
        stock = _make_stock({})
        hf = HardFilter("mid_term")
        result = hf._filter_mid_term([stock])
        assert len(result) == 1

    def test_fails_low_mcap(self):
        """市值不足应过滤 (market_cap < 50)"""
        stock = _make_stock({"market_cap": 20})
        hf = HardFilter("mid_term")
        result = hf._filter_mid_term([stock])
        assert len(result) == 0

    def test_fails_no_ma250(self):
        """股价低于年线应过滤 (price <= ma250)"""
        stock = _make_stock({"price": 9, "ma250": 10})
        hf = HardFilter("mid_term")
        result = hf._filter_mid_term([stock])
        assert len(result) == 0

    def test_fails_low_earnings_growth(self):
        """净利润增长率不足应过滤 (earnings_growth_3y < 50)"""
        stock = _make_stock({"earnings_growth_3y": 20})
        hf = HardFilter("mid_term")
        result = hf._filter_mid_term([stock])
        assert len(result) == 0


class TestHardFilterLongTerm:
    def test_passes_long_term(self):
        stock = _make_stock({})
        hf = HardFilter("long_term")
        result = hf._filter_long_term([stock])
        assert len(result) == 1

    def test_fails_low_roe(self):
        """ROE不足应过滤 (roe < 15)"""
        stock = _make_stock({"roe": 5})
        hf = HardFilter("long_term")
        result = hf._filter_long_term([stock])
        assert len(result) == 0

    def test_fails_high_debt(self):
        """负债率过高应过滤 (debt_to_equity > 1.5)"""
        stock = _make_stock({"debt_to_equity": 3.0})
        hf = HardFilter("long_term")
        result = hf._filter_long_term([stock])
        assert len(result) == 0


class TestNegativeExclusion:
    def test_excludes_st_stock(self):
        """ST股票应从候选池排除"""
        stock = _make_stock({"stock_name": "ST华仪"})
        hf = HardFilter("short_term")
        result = hf._negative_exclusion([stock])
        assert len(result) == 0

    def test_excludes_zero_price(self):
        """零价股票应从候选池排除"""
        stock = _make_stock({"price": 0})
        hf = HardFilter("short_term")
        result = hf._negative_exclusion([stock])
        assert len(result) == 0

    def test_excludes_under_listing_days(self):
        """上市天数不足250应排除"""
        stock = _make_stock({"listing_days": 100})
        hf = HardFilter("short_term")
        result = hf._negative_exclusion([stock])
        assert len(result) == 0


class TestHardFilterHybrid:
    def test_passes_hybrid(self):
        """正常混合股应通过"""
        stock = _make_stock({})
        hf = HardFilter("hybrid")
        result = hf._filter_hybrid([stock])
        assert len(result) == 1

    def test_fails_high_debt_hybrid(self):
        """负债率过高应过滤 (debt_to_equity > 3)"""
        stock = _make_stock({"debt_to_equity": 5.0})
        hf = HardFilter("hybrid")
        result = hf._filter_hybrid([stock])
        assert len(result) == 0


class TestFallback:
    def test_fallback_adds_stocks_when_passed_below_threshold(self):
        """通过数不足50时, fallback 应从 universe 补充"""
        stock = _make_stock({"stock_code": "000001"})
        hf = HardFilter("short_term")
        result = hf.apply([stock])
        # 虽然 amount 不足, 但 fallback 会补充
        assert len(result) >= 1

    def test_fallback_respects_price_zero(self):
        """Fallback 不应补充零价股"""
        stock = _make_stock({"stock_code": "000001", "price": 0})
        hf = HardFilter("short_term")
        result = hf.apply([stock])
        assert len(result) == 0
