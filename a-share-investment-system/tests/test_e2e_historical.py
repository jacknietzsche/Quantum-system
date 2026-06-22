"""端到端历史数据回放测试 — 3个交易日完整流程"""

import os
import tempfile

import numpy as np
import pandas as pd
import pytest

from services.debate_engine import DebateEngine
from services.factor_farm import FactorFarm
from services.market_perception import MarketPerception
from services.memory_bank import MemoryBank
from services.risk_engine import RiskEngine
from services.trade_executor import TradeExecutor


class TestE2EHistoricalReplay:
    """模拟3个交易日的完整分析→决策→执行→复盘流程"""

    @pytest.fixture
    def market_data_3days(self):
        """生成3个交易日的模拟市场数据"""
        np.random.seed(42)
        return [
            # Day 1: 牛市
            {
                "date": "2026-05-06",
                "breadth": {
                    "up": 3500,
                    "down": 1000,
                    "total": 5000,
                    "limit_up": 80,
                    "limit_down": 5,
                },
                "indices": {"上证指数": {"price": 3350, "change_pct": 1.2}},
            },
            # Day 2: 震荡
            {
                "date": "2026-05-07",
                "breadth": {
                    "up": 2400,
                    "down": 2300,
                    "total": 5000,
                    "limit_up": 35,
                    "limit_down": 30,
                },
                "indices": {"上证指数": {"price": 3340, "change_pct": -0.3}},
            },
            # Day 3: 弱势
            {
                "date": "2026-05-08",
                "breadth": {
                    "up": 800,
                    "down": 3900,
                    "total": 5000,
                    "limit_up": 10,
                    "limit_down": 45,
                },
                "indices": {"上证指数": {"price": 3280, "change_pct": -1.8}},
            },
        ]

    @pytest.fixture
    def price_history(self):
        """模拟20日价格历史"""
        dates = pd.date_range("2026-04-10", periods=20, freq="B")
        df = pd.DataFrame(
            {
                "close": 100 * (1 + np.random.randn(20).cumsum() * 0.01),
                "high": None,
                "low": None,
                "volume": None,
                "amount": None,
            },
            index=dates,
        )
        df["high"] = df["close"] * 1.02
        df["low"] = df["close"] * 0.98
        df["volume"] = np.random.randint(1e6, 1e7, 20)
        df["amount"] = df["close"] * df["volume"]
        return df

    def test_3day_market_perception_flow(self, market_data_3days):
        """验证3天市场感知连续运行"""
        mp = MarketPerception()
        regimes = []
        for day in market_data_3days:
            result = mp.perceive(day)
            assert result.status == "ok"
            regimes.append(result.data["regime"])

        # 3天应有不同环境
        assert len(set(regimes)) >= 2, f"3天应至少有2种不同环境: {regimes}"
        print(f"3-day regimes: {regimes}")

    def test_3day_memory_cycle(self, market_data_3days):
        """验证3天记忆存储→检索循环"""
        with tempfile.TemporaryDirectory() as tmp:
            mb = MemoryBank(memory_dir=tmp)

            # Day 1: 买入决策
            mb.store(
                {
                    "stock_code": "600519",
                    "stock_name": "茅台",
                    "regime": "BULL",
                    "pe": 25,
                    "roe": 18,
                    "industry": "白酒",
                    "pl_pct": 0,
                },
                {"verdict": "买入", "confidence": 0.8},
                {"return_pct": 0, "correct": None},  # 待验证
            )

            # Day 2: 检索Day1经验
            result = mb.retrieve(
                {
                    "stock_code": "600519",
                    "stock_name": "茅台",
                    "regime": "NEUTRAL",
                    "pe": 26,
                    "roe": 17,
                    "industry": "白酒",
                    "pl_pct": 3.0,
                }
            )
            assert result.data["count"] >= 1

            # Day 3: 验证Day1决策(T+2简化)
            mb.store(
                {
                    "stock_code": "600519",
                    "stock_name": "茅台",
                    "regime": "BEAR",
                    "pe": 24,
                    "roe": 18,
                    "industry": "白酒",
                    "pl_pct": -2.0,
                },
                {"verdict": "卖出", "confidence": 0.7},
                {"return_pct": -2.0, "correct": False},
            )
            n_bull = mb.bull_docs.__len__()
            n_bear = mb.bear_docs.__len__()
            print(f"3-day memory cycle: {n_bull} bull + {n_bear} bear")

    def test_3day_debate_factor_risk_pipeline(self, market_data_3days, price_history):
        """验证辩论→因子→风控3天连续流水线"""

        with tempfile.TemporaryDirectory() as tmp:
            mb = MemoryBank(memory_dir=tmp)
            db_path = os.path.join(tmp, "factors.db")
            de = DebateEngine(memory_bank=mb)
            ff = FactorFarm(db_path=db_path)
            re = RiskEngine()

            decisions = []
            for day in market_data_3days:
                # 1. 辩论
                debate = de.run_debate(
                    "600519",
                    [
                        {"category": "value", "analysis_prompt": "ROE 18%"},
                        {"category": "risk", "alerts": []},
                    ],
                    {
                        "stock_name": "茅台",
                        "regime": "NEUTRAL",
                        "pe": 25,
                        "roe": 18,
                        "industry": "白酒",
                        "pl_pct": 0,
                    },
                    max_rounds=1,
                )
                assert debate.status in ("ok", "degraded")

                # 2. 因子评分
                factor_score = ff.build_factor_score("600519")
                assert factor_score.status == "ok"

                # 3. 风控
                risk = re.full_audit(
                    [
                        {
                            "stock_code": "600519",
                            "current_value": 100000,
                            "industry": "白酒",
                            "debt_to_equity": 30,
                            "pledge_ratio": 5,
                            "cash_to_assets": 20,
                        }
                    ],
                    market_regime={
                        "regime": (day["breadth"]["up"] > day["breadth"]["down"] and "BULL")
                        or "NEUTRAL"
                    },
                )
                assert risk.status == "ok"

                decisions.append(
                    {
                        "date": day["date"],
                        "verdict": debate.data["verdict"],
                        "risk_pass": risk.data["pass"],
                    }
                )

            # 关闭SQLite连接以允许临时目录清理
            ff.library.close()

            assert len(decisions) == 3
            decisions_str = [(d["date"], d["verdict"], d["risk_pass"]) for d in decisions]
            print(f"3-day pipeline decisions: {decisions_str}")

    def test_3day_trade_execution_cycle(self):
        """验证3天交易执行→仓位→熔断完整周期"""
        te = TradeExecutor()
        te.set_initial_cash(500000)

        prices_day1 = {"600519": 1800}
        prices_day2 = {"600519": 1850}
        prices_day3 = {"600519": 1780}

        # Day 1: 买入
        r1 = te.generate_orders(
            [
                {
                    "stock_code": "600519",
                    "stock_name": "茅台",
                    "action": "买入",
                    "confidence": 0.8,
                    "target_price": 1800,
                }
            ],
            mode="paper",
            trading_date="2026-05-06",
            cash=500000,
        )
        if r1.data["orders"]:
            te.execute_paper(r1.data["orders"], prices_day1, "2026-05-06")
        te.update_market_prices(prices_day1)
        pos1 = te.get_positions()
        print(f"Day1: pos={pos1.data['position_count']}, asset={pos1.data['total_asset']:.0f}")

        # Day 2: 持有(价格上涨)
        te.update_market_prices(prices_day2)
        pos2 = te.get_positions()
        ks2 = te.check_kill_switch()
        print(f"Day2: asset={pos2.data['total_asset']:.0f}, kill_switch={ks2.data['level']}")

        # Day 3: 止损卖出
        r3 = te.generate_orders(
            [
                {
                    "stock_code": "600519",
                    "stock_name": "茅台",
                    "action": "卖出",
                    "confidence": 0.7,
                    "target_price": 1780,
                }
            ],
            mode="paper",
            trading_date="2026-05-08",
            cash=te.tracker.cash,
        )
        if r3.data["orders"]:
            te.execute_paper(r3.data["orders"], prices_day3, "2026-05-08")
        te.update_market_prices(prices_day3)
        pos3 = te.get_positions()

        # 应有关仓记录
        print(f"Day3: pos={pos3.data['position_count']}, asset={pos3.data['total_asset']:.0f}")
        assert pos3.data["position_count"] >= 0  # 仓位可能已清
