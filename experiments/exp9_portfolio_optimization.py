# -*- coding: utf-8 -*-
"""
实验9: 组合优化算法验证
目标: 验证行业分散+仓位约束的约束满足算法
"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

print("=" * 60)
print("实验9: 组合优化算法验证")
print("=" * 60)

# ========== 实验9.1: 行业分散约束 ==========
print("\n" + "=" * 60)
print("实验9.1: 行业分散约束")
print("=" * 60)

try:
    def check_industry_constraint(portfolio: list[dict], max_per_industry: int = 3) -> list[str]:
        """检查行业集中度约束"""
        industry_count = {}
        violations = []

        for stock in portfolio:
            industry = stock.get("industry", "未知")
            industry_count[industry] = industry_count.get(industry, 0) + 1

            if industry_count[industry] > max_per_industry:
                violations.append(f"{stock['code']}({stock['name']}) 超出行业上限: {industry}已有{industry_count[industry]}只")

        return violations

    # 测试数据
    portfolio = [
        {"code": "600519", "name": "贵州茅台", "industry": "白酒", "position_pct": 10},
        {"code": "000858", "name": "五粮液", "industry": "白酒", "position_pct": 8},
        {"code": "000568", "name": "泸州老窖", "industry": "白酒", "position_pct": 6},
        {"code": "600809", "name": "山西汾酒", "industry": "白酒", "position_pct": 5},
        {"code": "601318", "name": "中国平安", "industry": "保险", "position_pct": 8},
        {"code": "000001", "name": "平安银行", "industry": "银行", "position_pct": 5},
    ]

    violations = check_industry_constraint(portfolio, max_per_industry=3)
    print(f"组合: {len(portfolio)}只股票")
    print(f"行业分布:")
    industry_count = {}
    for s in portfolio:
        industry_count[s['industry']] = industry_count.get(s['industry'], 0) + 1
    for ind, count in industry_count.items():
        print(f"  {ind}: {count}只")
    print(f"违规: {len(violations)}条")
    for v in violations:
        print(f"  - {v}")

    print("[PASS] 行业分散约束检查成功")
except Exception as e:
    print(f"[FAIL] {e}")

# ========== 实验9.2: 仓位约束 ==========
print("\n" + "=" * 60)
print("实验9.2: 仓位约束优化")
print("=" * 60)

try:
    def optimize_positions(
        candidates: list[dict],
        total_capital: float,
        max_single_pct: float = 0.15,
        max_industry_pct: float = 0.30,
        market_state: str = "NEUTRAL"
    ) -> list[dict]:
        """
        仓位优化算法:
        1. 按评分排序
        2. 逐个分配仓位
        3. 检查单只上限
        4. 检查行业上限
        5. 检查总仓位上限
        """
        # 市场状态对应的总仓位上限
        market_caps = {
            "PANIC": 0.10, "BEAR": 0.30, "NEUTRAL": 0.60,
            "BULL": 0.80, "OVERHEAT": 0.50
        }
        max_total_pct = market_caps.get(market_state, 0.60)

        # 按评分排序
        sorted_candidates = sorted(candidates, key=lambda x: x["score"], reverse=True)

        result = []
        used_pct = 0.0
        industry_used = {}

        for stock in sorted_candidates:
            if len(result) >= 10:  # 最多10只
                break

            industry = stock.get("industry", "未知")

            # 计算建议仓位（按评分比例）
            base_pct = min(max_single_pct, stock["score"] / 100 * 0.2)

            # 检查单只上限
            actual_pct = min(base_pct, max_single_pct)

            # 检查行业上限
            industry_pct = industry_used.get(industry, 0) + actual_pct
            if industry_pct > max_industry_pct:
                actual_pct = max(0, max_industry_pct - industry_used.get(industry, 0))

            # 检查总仓位上限
            if used_pct + actual_pct > max_total_pct:
                actual_pct = max(0, max_total_pct - used_pct)

            if actual_pct > 0.01:  # 至少1%才有意义
                position_amount = total_capital * actual_pct
                result.append({
                    **stock,
                    "position_pct": round(actual_pct * 100, 1),
                    "position_amount": round(position_amount, 0),
                })
                used_pct += actual_pct
                industry_used[industry] = industry_used.get(industry, 0) + actual_pct

        return result

    # 测试
    candidates = [
        {"code": "600519", "name": "贵州茅台", "industry": "白酒", "score": 85},
        {"code": "000858", "name": "五粮液", "industry": "白酒", "score": 78},
        {"code": "601318", "name": "中国平安", "industry": "保险", "score": 75},
        {"code": "000001", "name": "平安银行", "industry": "银行", "score": 72},
        {"code": "002594", "name": "比亚迪", "industry": "汽车", "score": 70},
        {"code": "300750", "name": "宁德时代", "industry": "电池", "score": 68},
    ]

    result = optimize_positions(candidates, total_capital=1_000_000, market_state="NEUTRAL")
    print(f"优化结果 ({len(result)}只):")
    total_pct = 0
    for s in result:
        print(f"  {s['code']} {s['name']}({s['industry']}): {s['position_pct']}% = {s['position_amount']:.0f}元")
        total_pct += s['position_pct']
    print(f"总仓位: {total_pct:.1f}%")
    print(f"市场状态: NEUTRAL (上限60%)")

    # 验证约束
    assert total_pct <= 60, f"总仓位{total_pct}%超过60%上限"
    industry_check = {}
    for s in result:
        ind = s['industry']
        industry_check[ind] = industry_check.get(ind, 0) + s['position_pct']
    for ind, pct in industry_check.items():
        assert pct <= 30, f"行业{ind}仓位{pct}%超过30%上限"
        print(f"  行业{ind}: {pct}% <= 30% [OK]")

    print("[PASS] 仓位约束优化成功")
except Exception as e:
    print(f"[FAIL] {e}")

# ========== 实验9.3: 重新平衡计算 ==========
print("\n" + "=" * 60)
print("实验9.3: 重新平衡计算")
print("=" * 60)

try:
    def compute_rebalance(current: list[dict], target: list[dict]) -> list[dict]:
        """计算再平衡操作"""
        operations = []

        # 当前持仓的code集合
        current_codes = {s["code"]: s for s in current}
        target_codes = {s["code"]: s for s in target}

        # 需要卖出的（在当前不在目标中）
        for code, stock in current_codes.items():
            if code not in target_codes:
                operations.append({
                    "action": "SELL",
                    "code": code,
                    "name": stock["name"],
                    "reason": "目标组合中无此股票",
                })

        # 需要买入的（在目标不在当前中）
        for code, stock in target_codes.items():
            if code not in current_codes:
                operations.append({
                    "action": "BUY",
                    "code": code,
                    "name": stock["name"],
                    "target_pct": stock["position_pct"],
                    "reason": "新加入目标组合",
                })

        # 需要调整的（仓位差异超过2%）
        for code in set(current_codes.keys()) & set(target_codes.keys()):
            diff = target_codes[code]["position_pct"] - current_codes[code]["position_pct"]
            if abs(diff) > 2:
                operations.append({
                    "action": "ADJUST",
                    "code": code,
                    "name": current_codes[code]["name"],
                    "current_pct": current_codes[code]["position_pct"],
                    "target_pct": target_codes[code]["position_pct"],
                    "diff": round(diff, 1),
                    "reason": f"仓位调整{diff:+.1f}%",
                })

        return operations

    # 测试
    current = [
        {"code": "600519", "name": "贵州茅台", "position_pct": 15},
        {"code": "000858", "name": "五粮液", "position_pct": 10},
        {"code": "601318", "name": "中国平安", "position_pct": 8},
    ]
    target = [
        {"code": "600519", "name": "贵州茅台", "position_pct": 12},
        {"code": "601318", "name": "中国平安", "position_pct": 10},
        {"code": "002594", "name": "比亚迪", "position_pct": 8},
    ]

    ops = compute_rebalance(current, target)
    print(f"再平衡操作 ({len(ops)}个):")
    for op in ops:
        if op["action"] == "SELL":
            print(f"  卖出: {op['code']} {op['name']} - {op['reason']}")
        elif op["action"] == "BUY":
            print(f"  买入: {op['code']} {op['name']} {op['target_pct']}% - {op['reason']}")
        elif op["action"] == "ADJUST":
            print(f"  调整: {op['code']} {op['name']} {op['current_pct']}% -> {op['target_pct']}% ({op['diff']:+.1f}%)")

    print("[PASS] 重新平衡计算成功")
except Exception as e:
    print(f"[FAIL] {e}")

print("\n" + "=" * 60)
print("实验9完成")
print("=" * 60)
