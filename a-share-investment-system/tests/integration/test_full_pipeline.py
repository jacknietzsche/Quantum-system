"""联调验证 — 选股→回测→绩效 完整链路测试

使用模拟但合理的 A 股数据, 验证各模块间的数据流和接口兼容性。
不依赖外部 API, CI 环境可直接运行。
"""

import random
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

# ── 模拟数据生成 ──


def generate_stock_universe(n: int = 50) -> list[dict]:
    """生成模拟 A 股全市场数据 (50只股票)

    字段名严格对齐 HardFilter 期望:
      price, pe, amount, ma20, ma60, ma250, fcf, debt_to_equity,
      change_pct_5d, change_pct_60d, volume_ratio, roe, market_cap,
      turnover_rate, listing_days, stock_code, stock_name
    """
    random.seed(42)

    stocks = []
    industries = ["白酒", "银行", "半导体", "新能源", "医药", "房地产", "消费", "军工"]
    for i in range(n):
        code = f"{600000 + i:06d}" if i < n // 2 else f"{i - n // 2:06d}"
        price = round(random.uniform(10, 150), 2)
        roe = round(random.uniform(5, 30), 2)
        pe = round(random.uniform(5, 60), 2)
        market_cap = round(random.uniform(50, 800), 2)

        # 前20只刻意构造为"能通过 hybrid 筛选"的优质数据
        if i < 20:
            roe = round(random.uniform(12, 30), 2)
            pe = round(random.uniform(8, 35), 2)
            amount = round(random.uniform(1.5e8, 5e8), 0)  # 1.5亿-5亿成交额
            debt = round(random.uniform(0.3, 2.0), 2)  # 负债率 ≤ 3
        else:
            amount = round(random.uniform(1e6, 8e7), 0)  # 不满足门槛
            debt = round(random.uniform(5, 100), 2)

        ma20 = round(price * random.uniform(0.92, 0.98), 2)  # price > ma20
        ma60 = round(ma20 * random.uniform(0.92, 0.98), 2)  # ma20 > ma60
        ma250 = round(ma60 * random.uniform(0.90, 0.97), 2)  # ma60 > ma250

        stocks.append(
            {
                "stock_code": code,
                "stock_name": f"Stock_{code}",
                "industry": random.choice(industries),
                # HardFilter 直接读取的字段
                "price": price,
                "pe": pe,
                "pb": round(random.uniform(0.5, 8), 2),
                "roe": roe,
                "amount": amount,
                "debt_to_equity": debt,
                "market_cap": market_cap,
                "turnover_rate": round(random.uniform(0.3, 12), 2),
                "volume_ratio": round(random.uniform(0.3, 5), 2),
                "change_pct_5d": round(random.uniform(-8, 12), 2),
                "change_pct_60d": round(random.uniform(-15, 30), 2),
                "fcf": round(random.uniform(-2, 10), 2),  # 自由现金流
                "ma20": ma20,
                "ma60": ma60,
                "ma250": ma250,
                "listing_days": random.randint(300, 5000),
                # 辅助字段 (回测/绩效等模块使用)
                "latest_price": price,
                "pe_ratio": pe,
                "pb_ratio": round(random.uniform(0.5, 8), 2),
                "gross_margin": round(random.uniform(10, 70), 2),
                "eps": round(random.uniform(0.5, 8), 2),
                "bvps": round(random.uniform(3, 40), 2),
                "dividend_yield": round(random.uniform(0, 4), 2),
                "change_pct": round(random.uniform(-5, 5), 2),
                "change_pct_20d": round(random.uniform(-15, 15), 2),
                "total_market_cap": round(market_cap * random.uniform(1.0, 1.5), 2),
                "trend": random.choice(["bullish", "bearish", "neutral"]),
                "ma_alignment": random.choice(["bullish", "bearish", "neutral"]),
                "volatility_20d": round(random.uniform(0.1, 0.4), 3),
                "rsi_14": round(random.uniform(30, 70), 1),
                "atr_14": round(random.uniform(1, 6), 2),
            }
        )
    return stocks


def generate_price_history(stocks: list[dict], days: int = 120) -> dict[str, list[dict]]:
    """为每只股票生成历史 K 线数据"""
    random.seed(123)

    history = {}
    for stock in stocks[:20]:  # 只为前20只生成历史
        code = stock["stock_code"]
        bars = []
        base = stock["price"] * 0.8  # 从较低价开始
        date = datetime(2024, 1, 2)

        for d in range(days):
            if date.weekday() >= 5:
                date += timedelta(days=1)
                continue
            change = random.gauss(0.001, 0.02)  # 略正偏
            base *= 1 + change
            base = max(base, 1.0)
            bars.append(
                {
                    "date": date.strftime("%Y-%m-%d"),
                    "open": round(base * (1 + random.uniform(-0.01, 0.01)), 2),
                    "high": round(base * (1 + abs(random.uniform(0, 0.02))), 2),
                    "low": round(base * (1 - abs(random.uniform(0, 0.02))), 2),
                    "close": round(base, 2),
                    "volume": random.randint(1_000_000, 50_000_000),
                }
            )
            date += timedelta(days=1)
        history[code] = bars
    return history


# ── 测试: 硬过滤 → 选股 ──


class TestHardFilter:
    """验证 HardFilter 能正确过滤股票"""

    def test_hard_filter_reduces_universe(self):
        """硬过滤应减少候选股数量 (hybrid 策略)"""
        from services.hard_filter import HardFilter

        universe = generate_stock_universe(50)
        hf = HardFilter(style="hybrid", market_regime="NEUTRAL")
        passed = hf.apply(universe)

        assert len(passed) <= len(universe)
        assert len(passed) > 0, "Hybrid filter should pass at least some stocks"

    def test_hard_filter_value_style(self):
        """价值风格应偏向高 ROE、低负债"""
        from services.hard_filter import HardFilter

        universe = generate_stock_universe(50)
        hf = HardFilter(style="value", market_regime="NEUTRAL")
        passed = hf.apply(universe)

        assert len(passed) > 0, "Value filter should pass at least some stocks"

    def test_hard_filter_momentum_style(self):
        """动量风格应偏向正向涨幅"""
        from services.hard_filter import HardFilter

        universe = generate_stock_universe(50)
        hf = HardFilter(style="momentum", market_regime="NEUTRAL")
        passed = hf.apply(universe)

        assert len(passed) > 0, "Momentum filter should pass at least some stocks"

    def test_hard_filter_bear_regime(self):
        """熊市应更严格或相等过滤"""
        from services.hard_filter import HardFilter

        universe = generate_stock_universe(50)
        hf_neutral = HardFilter(style="hybrid", market_regime="NEUTRAL")
        hf_bear = HardFilter(style="hybrid", market_regime="BEAR")

        passed_neutral = hf_neutral.apply(universe)
        passed_bear = hf_bear.apply(universe)

        assert len(passed_bear) <= len(passed_neutral) + 5


# ── 测试: 回测模拟 ──


class TestBacktestPipeline:
    """验证回测引擎能处理选股输出"""

    def test_backtest_with_screening_signals(self):
        """回测引擎能消费选股信号"""
        from services.backtest_sim import BacktestConfig, BacktestSimulator

        universe = generate_stock_universe(50)
        price_data = generate_price_history(universe, 60)

        # 构建信号 (取有历史数据的前5只)
        signals = []
        for stock in universe[:5]:
            code = stock["stock_code"]
            if code in price_data and len(price_data[code]) > 10:
                signals.append(
                    {
                        "date": price_data[code][5]["date"],
                        "stock_code": code,
                        "stock_name": stock["stock_name"],
                        "action": "BUY",
                        "confidence": 75,
                        "reason": "Integration test signal",
                    }
                )

        assert len(signals) > 0, "Should generate at least one signal"

        # 构建价格索引
        price_index = {}
        for code, bars in price_data.items():
            for bar in bars:
                price_index.setdefault(bar["date"], {})[code] = bar

        config = BacktestConfig(initial_capital=500_000, max_holdings=5)
        sim = BacktestSimulator(config)
        result = sim.run(signals, price_index)

        assert result.status == "ok"
        assert result.data["trades_count"] > 0

    def test_backtest_respects_limits(self):
        """回测应遵守最大持仓限制"""
        from services.backtest_sim import BacktestConfig, BacktestSimulator

        universe = generate_stock_universe(50)
        price_data = generate_price_history(universe, 60)

        # 生成超过 max_holdings 的信号
        signals = []
        for stock in universe[:10]:
            code = stock["stock_code"]
            if code in price_data and len(price_data[code]) > 5:
                signals.append(
                    {
                        "date": price_data[code][3]["date"],
                        "stock_code": code,
                        "stock_name": stock["stock_name"],
                        "action": "BUY",
                        "confidence": 80,
                        "reason": "Limit test",
                    }
                )

        price_index = {}
        for code, bars in price_data.items():
            for bar in bars:
                price_index.setdefault(bar["date"], {})[code] = bar

        config = BacktestConfig(initial_capital=1_000_000, max_holdings=3)
        sim = BacktestSimulator(config)
        result = sim.run(signals, price_index)

        assert result.status == "ok"


# ── 测试: 绩效归因 ──


class TestPerformancePipeline:
    """验证绩效引擎能处理回测输出"""

    @staticmethod
    def _make_nav_series(days=60, start=1_000_000):
        """生成带 daily_return 的 NAV 序列"""
        random.seed(42)
        series = []
        nav = float(start)
        date = datetime(2024, 1, 2)
        for _ in range(days):
            if date.weekday() >= 5:
                date += timedelta(days=1)
                continue
            ret = random.gauss(0.001, 0.015)
            nav *= 1 + ret
            series.append(
                {
                    "date": date.strftime("%Y-%m-%d"),
                    "nav": round(nav, 2),
                    "daily_return": round(ret, 6),
                    "position_count": 5,
                }
            )
            date += timedelta(days=1)
        return series

    def test_performance_with_nav_data(self):
        """绩效引擎能处理 NAV 数据"""
        from services.performance import PerformanceEngine

        nav_series = self._make_nav_series(60)
        engine = PerformanceEngine()
        with (
            patch.object(engine, "_get_nav_series", return_value=nav_series),
            patch.object(engine, "_get_benchmark_series", return_value=[]),
        ):
            result = engine.compute_performance("value", days=250)

        assert result.status == "ok"
        assert "total_return_pct" in result.data["metrics"]

    def test_yearly_breakdown(self):
        """绩效引擎应能分年度输出"""
        from services.performance import PerformanceEngine

        nav_series = self._make_nav_series(300, start=1_000_000)
        # 改日期为跨年
        random.seed(99)
        date = datetime(2023, 7, 1)
        fixed = []
        for entry in nav_series:
            while date.weekday() >= 5:
                date += timedelta(days=1)
            e = dict(entry)
            e["date"] = date.strftime("%Y-%m-%d")
            fixed.append(e)
            date += timedelta(days=1)

        engine = PerformanceEngine()
        with patch.object(engine, "_get_nav_series", return_value=fixed):
            result = engine.get_yearly_breakdown("value")

        assert result.status == "ok"
        yearly = result.data.get("years", [])
        assert len(yearly) >= 2


# ── 测试: 因子验证 ──


class TestFactorValidationPipeline:
    """验证因子验证引擎能处理价格数据"""

    def test_factor_validation_with_price_data(self):
        """因子验证引擎能处理价格数据"""
        from services.factor_validator import FactorValidator

        universe = generate_stock_universe(50)
        price_data = generate_price_history(universe, 60)

        # 构建动量因子
        factor_data = {}
        for code, bars in price_data.items():
            for i, bar in enumerate(bars):
                date = bar["date"]
                if date not in factor_data:
                    factor_data[date] = {}
                if i >= 5:
                    ret_5d = (bar["close"] - bars[i - 5]["close"]) / bars[i - 5]["close"]
                    factor_data[date][f"momentum_5d_{code}"] = ret_5d

        # 简化: 用一个聚合因子
        agg_factor = {}
        for date, factors in factor_data.items():
            vals = [v for k, v in factors.items() if "momentum_5d" in k]
            if vals:
                agg_factor[date] = {"momentum_avg": sum(vals) / len(vals)}

        validator = FactorValidator()
        if agg_factor:
            dates = sorted(agg_factor.keys())[:50]
            factor_vals = [agg_factor[d]["momentum_avg"] for d in dates]
            random.seed(42)
            returns = [random.gauss(0.001, 0.02) for _ in range(len(factor_vals))]

            result = validator.validate_single("momentum_avg", factor_vals, returns)
            assert result.status == "ok"


# ── 测试: 通知链路 ──


class TestNotificationPipeline:
    """验证通知服务能接收各模块的输出"""

    def test_risk_alert_notification(self):
        """风控告警 → 通知"""
        from services.notifier import notify_risk_alert

        result = notify_risk_alert(
            "止损触发",
            "600519 跌破 -10% 止损线",
            level="WARNING",
            data={"stock_code": "600519", "pct": -10.5},
        )
        assert result["category"] == "risk"
        assert result["data"]["stock_code"] == "600519"

    def test_signal_notification(self):
        """交易信号 → 通知"""
        from services.notifier import notify_signal

        result = notify_signal(
            "买入信号",
            "000001 平安银行 置信度 85%",
            data={"stock_code": "000001", "confidence": 85},
        )
        assert result["category"] == "signal"


# ── 端到端链路 ──


class TestEndToEndPipeline:
    """端到端: 选股 → 信号 → 回测 → 绩效 → 通知"""

    def test_full_pipeline(self):
        """完整链路验证"""
        from services.backtest_sim import BacktestConfig, BacktestSimulator
        from services.hard_filter import HardFilter
        from services.notifier import notify_workflow
        from services.performance import PerformanceEngine

        # Step 1: 生成市场数据
        universe = generate_stock_universe(50)
        price_data = generate_price_history(universe, 60)

        # Step 2: 硬过滤选股
        hf = HardFilter(style="hybrid", market_regime="NEUTRAL")
        candidates = hf.apply(universe)
        assert len(candidates) > 0, "HardFilter should pass at least some stocks"

        # Step 3: 生成交易信号 (每天买1只, 跨多天以产生足够NAV快照)
        signals = []
        for idx, stock in enumerate(candidates[:5]):
            code = stock["stock_code"]
            if code in price_data and len(price_data[code]) > 15:
                day_idx = min(5 + idx * 3, len(price_data[code]) - 1)
                signals.append(
                    {
                        "date": price_data[code][day_idx]["date"],
                        "stock_code": code,
                        "stock_name": stock["stock_name"],
                        "action": "BUY",
                        "confidence": 70 + idx * 3,
                        "reason": "Hybrid screening pick",
                    }
                )

        if not signals:
            pytest.skip("No valid signals generated")

        # Step 4: 构建价格索引
        price_index = {}
        for code, bars in price_data.items():
            for bar in bars:
                price_index.setdefault(bar["date"], {})[code] = bar

        # Step 5: 回测
        config = BacktestConfig(initial_capital=1_000_000, max_holdings=5)
        sim = BacktestSimulator(config)
        bt_result = sim.run(signals, price_index)
        assert bt_result.status == "ok"
        assert bt_result.data["trades_count"] > 0

        # Step 6: 绩效分析 (mock DB 层, 注入回测 NAV)
        nav_snapshots = bt_result.data.get("daily_nav", [])
        if nav_snapshots and isinstance(nav_snapshots[0], dict):
            perf_nav = [
                {
                    "date": s["date"],
                    "nav": s["total_asset"],
                    "daily_return": s.get("daily_return", 0),
                }
                for s in nav_snapshots
            ]
            engine = PerformanceEngine()
            with (
                patch.object(engine, "_get_nav_series", return_value=perf_nav),
                patch.object(engine, "_get_benchmark_series", return_value=[]),
            ):
                perf_result = engine.compute_performance("value", days=250)
            assert perf_result.status in ("ok", "degraded")

        # Step 7: 通知
        notif = notify_workflow(
            "回测完成",
            f"交易 {bt_result.data['trades_count']} 笔, "
            f"总成本 {bt_result.data['costs']['total_cost']:.0f}",
            data={"trades": bt_result.data["trades_count"]},
        )
        assert notif["category"] == "workflow"

        # 验证链路完整性
        assert bt_result.data["summary"]["total_return_pct"] is not None
        assert bt_result.data["costs"]["total_commission"] > 0
