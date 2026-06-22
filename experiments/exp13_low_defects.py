# -*- coding: utf-8 -*-
"""
实验13: LOW缺陷验证
目标: 回测引擎/压力测试/前端适配
"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import sqlite3
import pandas as pd
import numpy as np
import time
from pathlib import Path
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP

print("=" * 60)
print("实验13: LOW缺陷验证")
print("=" * 60)

# ========== 实验13.1: 回测引擎核心逻辑 ==========
print("\n" + "=" * 60)
print("实验13.1: 回测引擎核心逻辑")
print("=" * 60)

try:
    class SimpleBacktester:
        """简化版回测引擎"""

        def __init__(self, initial_capital: float = 1_000_000):
            self.initial_capital = initial_capital
            self.cash = initial_capital
            self.positions = {}
            self.trades = []
            self.daily_nav = []

        def buy(self, code: str, price: float, quantity: int, date: str):
            """买入"""
            cost = price * quantity
            commission = max(cost * 0.00025, 5)  # 佣金万2.5，最低5元
            transfer_fee = cost * 0.00001
            total_cost = cost + commission + transfer_fee

            if total_cost > self.cash:
                return False

            self.cash -= total_cost
            self.positions[code] = {
                "price": price, "quantity": quantity, "date": date
            }
            self.trades.append({
                "date": date, "code": code, "action": "BUY",
                "price": price, "quantity": quantity, "cost": total_cost
            })
            return True

        def sell(self, code: str, price: float, date: str):
            """卖出"""
            if code not in self.positions:
                return False

            pos = self.positions[code]
            revenue = price * pos["quantity"]
            commission = max(revenue * 0.00025, 5)
            stamp_tax = revenue * 0.001  # 印花税千1
            transfer_fee = revenue * 0.00001
            net_revenue = revenue - commission - stamp_tax - transfer_fee

            profit = net_revenue - pos["price"] * pos["quantity"]
            self.cash += net_revenue
            self.trades.append({
                "date": date, "code": code, "action": "SELL",
                "price": price, "quantity": pos["quantity"],
                "revenue": net_revenue, "profit": profit
            })
            del self.positions[code]
            return True

        def record_nav(self, date: str, prices: dict):
            """记录每日净值"""
            stock_value = sum(
                prices.get(code, pos["price"]) * pos["quantity"]
                for code, pos in self.positions.items()
            )
            total = self.cash + stock_value
            self.daily_nav.append({
                "date": date, "total": total, "cash": self.cash,
                "stock_value": stock_value
            })

        def get_metrics(self) -> dict:
            """计算回测指标"""
            if not self.daily_nav:
                return {}

            navs = [d["total"] for d in self.daily_nav]
            returns = [(navs[i] - navs[i-1]) / navs[i-1] for i in range(1, len(navs))]

            total_return = (navs[-1] - navs[0]) / navs[0]
            max_drawdown = 0
            peak = navs[0]
            for nav in navs:
                if nav > peak:
                    peak = nav
                drawdown = (peak - nav) / peak
                if drawdown > max_drawdown:
                    max_drawdown = drawdown

            win_trades = [t for t in self.trades if t["action"] == "SELL" and t.get("profit", 0) > 0]
            lose_trades = [t for t in self.trades if t["action"] == "SELL" and t.get("profit", 0) <= 0]

            return {
                "total_return": f"{total_return*100:.2f}%",
                "max_drawdown": f"{max_drawdown*100:.2f}%",
                "total_trades": len(self.trades),
                "win_trades": len(win_trades),
                "lose_trades": len(lose_trades),
                "win_rate": f"{len(win_trades)/(len(win_trades)+len(lose_trades))*100:.1f}%" if (win_trades or lose_trades) else "N/A",
                "final_nav": navs[-1],
            }

    # 模拟回测
    bt = SimpleBacktester(initial_capital=1_000_000)

    # 生成模拟价格数据
    np.random.seed(42)
    dates = pd.date_range("2026-01-01", "2026-06-30", freq="B")
    prices = {"600519": 1500}
    for date in dates:
        prices["600519"] *= (1 + np.random.normal(0, 0.02))

    # 简单策略: 买入持有
    for i, date in enumerate(dates):
        date_str = date.strftime("%Y-%m-%d")
        price = prices["600519"]

        # 第1天买入
        if i == 0:
            bt.buy("600519", price, 100, date_str)

        # 记录净值
        bt.record_nav(date_str, prices)

    # 最后一天卖出
    bt.sell("600519", prices["600519"], dates[-1].strftime("%Y-%m-%d"))

    metrics = bt.get_metrics()
    print(f"回测结果:")
    for k, v in metrics.items():
        print(f"  {k}: {v}")
    print(f"交易记录: {len(bt.trades)}笔")
    for t in bt.trades:
        print(f"  {t['date']} {t['action']} {t['code']} @ {t['price']:.2f}")

    print("[PASS] 回测引擎核心逻辑成功")
except Exception as e:
    print(f"[FAIL] {e}")

# ========== 实验13.2: Decimal精确计算 ==========
print("\n" + "=" * 60)
print("实验13.2: Decimal精确计算（AlphaAnalyst模式）")
print("=" * 60)

try:
    # AlphaAnalyst: "valuation is pure Python (decimal.Decimal everywhere)"

    def calculate_position_size(
        total_capital: Decimal,
        target_pct: Decimal,
        price: Decimal,
        lot_size: int = 100
    ) -> int:
        """计算仓位（精确到手）"""
        target_amount = total_capital * target_pct / Decimal("100")
        shares = int(target_amount / price)
        lots = shares // lot_size
        return lots * lot_size

    def calculate_stop_loss(
        entry_price: Decimal,
        risk_pct: Decimal = Decimal("5")
    ) -> Decimal:
        """计算止损价"""
        stop = entry_price * (1 - risk_pct / Decimal("100"))
        return stop.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    def calculate_take_profit(
        entry_price: Decimal,
        reward_pct: Decimal = Decimal("15")
    ) -> Decimal:
        """计算止盈价"""
        tp = entry_price * (1 + reward_pct / Decimal("100"))
        return tp.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    # 测试
    capital = Decimal("1000000")
    price = Decimal("1525.50")
    target_pct = Decimal("5")

    shares = calculate_position_size(capital, target_pct, price)
    stop = calculate_stop_loss(price)
    tp = calculate_take_profit(price)

    print(f"总资金: {capital}元")
    print(f"目标仓位: {target_pct}%")
    print(f"股价: {price}元")
    print(f"可买股数: {shares}股 ({shares//100}手)")
    print(f"止损价: {stop}元 ({(price-stop)/price*100:.1f}%下行)")
    print(f"止盈价: {tp}元 ({(tp-price)/price*100:.1f}%上行)")

    # 验证精度
    assert shares % 100 == 0, "股数必须是100的整数倍"
    assert stop < price, "止损价必须低于入场价"
    assert tp > price, "止盈价必须高于入场价"

    print("[PASS] Decimal精确计算成功")
except Exception as e:
    print(f"[FAIL] {e}")

# ========== 实验13.3: 压力测试模拟 ==========
print("\n" + "=" * 60)
print("实验13.3: 压力测试模拟")
print("=" * 60)

try:
    def stress_test_concurrent_analysis(num_stocks: int = 50):
        """模拟并发分析压力测试"""
        results = []

        for i in range(num_stocks):
            start = time.time()
            # 模拟分析流程
            stock_data = {"code": f"60000{i:02d}", "price": np.random.uniform(10, 100)}

            # 模拟技术指标计算
            indicators = {
                "ma20": np.random.uniform(10, 100),
                "rsi": np.random.uniform(20, 80),
                "macd": np.random.uniform(-5, 5),
            }

            # 模拟评分
            score = np.random.uniform(50, 100)

            elapsed = time.time() - start
            results.append({
                "code": stock_data["code"],
                "elapsed_ms": elapsed * 1000,
                "score": score,
            })

        return results

    # 执行压力测试
    start = time.time()
    results = stress_test_concurrent_analysis(50)
    total_time = time.time() - start

    print(f"压力测试: 50只股票")
    print(f"总耗时: {total_time*1000:.1f}ms")
    print(f"平均每只: {total_time/50*1000:.1f}ms")
    print(f"最大单只: {max(r['elapsed_ms'] for r in results):.1f}ms")

    # 模拟极端情况
    extreme_cases = [
        {"name": "全部成功", "success_rate": 1.0},
        {"name": "30%失败", "success_rate": 0.7},
        {"name": "50%失败", "success_rate": 0.5},
        {"name": "90%失败", "success_rate": 0.1},
    ]

    print(f"\n极端情况模拟:")
    for case in extreme_cases:
        success = int(50 * case["success_rate"])
        fail = 50 - success
        print(f"  {case['name']}: {success}成功, {fail}失败, 降级率{fail/50*100:.0f}%")

    print("[PASS] 压力测试模拟成功")
except Exception as e:
    print(f"[FAIL] {e}")

# ========== 实验13.4: 响应式布局断点 ==========
print("\n" + "=" * 60)
print("实验13.4: 响应式布局断点（桌面+平板）")
print("=" * 60)

try:
    # Electron桌面应用不需要移动端，但需要支持不同窗口大小

    BREAKPOINTS = {
        "sm": {"width": 640, "cols": 1, "sidebar": False},
        "md": {"width": 768, "cols": 2, "sidebar": True},
        "lg": {"width": 1024, "cols": 3, "sidebar": True},
        "xl": {"width": 1280, "cols": 4, "sidebar": True},
        "2xl": {"width": 1536, "cols": 4, "sidebar": True},
    }

    # Electron默认窗口: 1400x900
    default_window = {"width": 1400, "height": 900}

    # 匹配断点
    matched = None
    for name, bp in BREAKPOINTS.items():
        if default_window["width"] >= bp["width"]:
            matched = (name, bp)

    print(f"Electron默认窗口: {default_window['width']}x{default_window['height']}")
    print(f"匹配断点: {matched[0]} (>{matched[1]['width']}px)")
    print(f"布局: {matched[1]['cols']}列, 侧边栏{'显示' if matched[1]['sidebar'] else '隐藏'}")

    # 最小窗口
    min_window = {"width": 1000, "height": 700}
    for name, bp in BREAKPOINTS.items():
        if min_window["width"] >= bp["width"]:
            matched_min = (name, bp)

    print(f"\n最小窗口: {min_window['width']}x{min_window['height']}")
    print(f"匹配断点: {matched_min[0]} (>{matched_min[1]['width']}px)")
    print(f"布局: {matched_min[1]['cols']}列, 侧边栏{'显示' if matched_min[1]['sidebar'] else '隐藏'}")

    print("[PASS] 响应式布局断点成功")
except Exception as e:
    print(f"[FAIL] {e}")

print("\n" + "=" * 60)
print("实验13完成")
print("=" * 60)
