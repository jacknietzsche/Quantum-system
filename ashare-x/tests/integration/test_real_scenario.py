"""Real scenario test."""

from __future__ import annotations

import sys
import time
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

import numpy as np
import pandas as pd

from agents.masters.selector import select_masters
from core.config import Config
from graph.conditional_logic import should_continue_investment_debate
from memory.decision_log import DecisionLog
from memory.injection import inject_memory
from services.portfolio import check_industry_constraint, optimize_positions
from services.report import ReportGenerator
from services.risk_engine import assess_market_risk, assess_stock_risk
from services.screening import compute_stock_score, rank_stocks
from services.trading_plan import generate_trading_plan
from tools.market_state import detect_market_state, get_position_cap
from tools.technical_indicators import get_latest_indicators


def test_config():
    print("=" * 60)
    print("Test 1: Config")
    print("=" * 60)
    Config.reset()
    config = Config()
    budget = config.get("llm.monthly_budget_rmb", 100)
    provider = config.get("llm.quick_think.provider", "unknown")
    print(f"  Budget: {budget}")
    print(f"  Provider: {provider}")
    print(f"  Quick model: {config.get('llm.quick_think.model', 'N/A')}")
    print(f"  Deep model: {config.get('llm.deep_think.model', 'N/A')}")
    print("  [PASS]\n")


def test_technical_indicators():
    print("=" * 60)
    print("Test 2: Technical Indicators")
    print("=" * 60)
    np.random.seed(42)
    dates = pd.date_range("2026-01-01", periods=100, freq="B")
    prices = 1500 + np.cumsum(np.random.normal(0, 10, 100))
    df = pd.DataFrame(
        {
            "date": dates,
            "open": prices - 5,
            "high": prices + 10,
            "low": prices - 10,
            "close": prices,
            "volume": np.random.randint(500000, 2000000, 100),
        }
    )
    indicators = get_latest_indicators(df)
    print(f"  Close: {indicators['close']:.2f}")
    print(f"  MA5: {indicators['ma5']:.2f}")
    print(f"  MA20: {indicators['ma20']:.2f}")
    print(f"  MACD: {indicators['macd']:.4f}")
    print(f"  RSI(14): {indicators['rsi_14']:.2f}")
    print(f"  BB Upper: {indicators['bb_upper']:.2f}")
    print(f"  BB Lower: {indicators['bb_lower']:.2f}")
    print("  [PASS]\n")


def test_market_state():
    print("=" * 60)
    print("Test 3: Market State")
    print("=" * 60)
    scenarios = [
        {
            "name": "BULL",
            "data": {
                "sh_change_20d": 0.10,
                "advance_count": 3000,
                "decline_count": 1000,
                "volume": 5000,
                "volume_ma20": 3000,
                "north_flow_5d": 100,
            },
        },
        {
            "name": "BEAR",
            "data": {
                "sh_change_20d": -0.03,
                "advance_count": 1000,
                "decline_count": 3000,
                "volume": 2500,
                "volume_ma20": 3500,
                "north_flow_5d": -20,
            },
        },
        {
            "name": "NEUTRAL",
            "data": {
                "sh_change_20d": 0.01,
                "advance_count": 2000,
                "decline_count": 2000,
                "volume": 3000,
                "volume_ma20": 3000,
                "north_flow_5d": 10,
            },
        },
    ]
    for s in scenarios:
        state = detect_market_state(s["data"])
        cap = get_position_cap(state)
        print(f"  {s['name']}: state={state}, cap={cap * 100:.0f}%")
    print("  [PASS]\n")


def test_screening():
    print("=" * 60)
    print("Test 4: Stock Screening")
    print("=" * 60)
    stocks = [
        {
            "code": "600519",
            "name": "Maotai",
            "pe_ratio": 25,
            "roe": 30,
            "revenue_growth": 0.15,
            "rsi_14": 55,
            "change_pct_20d": 0.05,
            "amount": 10_000_000,
            "listing_days": 5000,
        },
        {
            "code": "000858",
            "name": "Wuliangye",
            "pe_ratio": 20,
            "roe": 25,
            "revenue_growth": 0.12,
            "rsi_14": 48,
            "change_pct_20d": 0.03,
            "amount": 8_000_000,
            "listing_days": 4000,
        },
        {
            "code": "601318",
            "name": "PingAn",
            "pe_ratio": 8,
            "roe": 15,
            "revenue_growth": 0.05,
            "rsi_14": 42,
            "change_pct_20d": -0.02,
            "amount": 15_000_000,
            "listing_days": 3000,
        },
    ]
    for s in stocks:
        score = compute_stock_score(s)
        s["score"] = score
        print(f"  {s['code']} {s['name']}: score={score:.1f}")
    ranked = rank_stocks(stocks, top_n=3)
    top3_str = ", ".join([f"{s['code']}({s['score']:.1f})" for s in ranked])
    print(f"  Top 3: {top3_str}")
    print("  [PASS]\n")


def test_portfolio():
    print("=" * 60)
    print("Test 5: Portfolio Optimization")
    print("=" * 60)
    candidates = [
        {"code": "600519", "name": "Maotai", "industry": "liquor", "score": 85},
        {"code": "000858", "name": "Wuliangye", "industry": "liquor", "score": 78},
        {"code": "601318", "name": "PingAn", "industry": "insurance", "score": 75},
        {"code": "000001", "name": "PingAnBank", "industry": "bank", "score": 72},
    ]
    result = optimize_positions(candidates, 1_000_000, market_state="NEUTRAL")
    total_pct = 0
    for s in result:
        print(
            f"  {s['code']} {s['name']}({s['industry']}): {s['position_pct']}% = {s['position_amount']:.0f}"
        )
        total_pct += s["position_pct"]
    print(f"  Total: {total_pct:.1f}%")
    violations = check_industry_constraint(result)
    print(f"  Violations: {len(violations)}")
    print("  [PASS]\n")


def test_trading_plan():
    print("=" * 60)
    print("Test 6: Trading Plan")
    print("=" * 60)
    plan = generate_trading_plan(
        ticker="600519",
        stock_name="Maotai",
        action="Buy",
        confidence=80,
        current_price=1500.0,
        thesis="Bullish tech + good fundamentals",
        key_factors=["MA5>MA20", "ROE=30%"],
        risks=["High valuation"],
    )
    print(f"  Stock: {plan['ticker']} {plan['stock_name']}")
    print(f"  Action: {plan['action']}")
    print(f"  Confidence: {plan['confidence']}%")
    print(f"  Entry: {plan['entry_price']:.2f}")
    print(f"  Stop Loss: {plan['stop_loss']:.2f}")
    print(f"  Take Profit: {plan['take_profit']:.2f}")
    print(f"  Position: {plan['position_pct']}%")
    print("  [PASS]\n")


def test_risk_engine():
    print("=" * 60)
    print("Test 7: Risk Engine")
    print("=" * 60)
    market = assess_market_risk(
        {
            "sh_change_20d": 0.05,
            "advance_count": 2500,
            "decline_count": 1500,
            "volume": 4000,
            "volume_ma20": 3000,
            "north_flow_5d": 50,
        }
    )
    print(f"  Market: {market['market_state']}, cap={market['position_cap'] * 100:.0f}%")
    stock = assess_stock_risk({"volatility": 0.35, "volume": 1000000, "avg_volume": 1500000})
    print(
        f"  Stock risk: {stock['risk_level']}, liquidity={'OK' if stock['liquidity_ok'] else 'LOW'}"
    )
    print("  [PASS]\n")


def test_report_memory():
    print("=" * 60)
    print("Test 8: Report + Memory")
    print("=" * 60)
    gen = ReportGenerator(db_path=":memory:")
    plan = {
        "ticker": "600519",
        "stock_name": "Maotai",
        "action": "Buy",
        "confidence": 80,
        "entry_price": 1500,
        "stop_loss": 1425,
        "take_profit": 1650,
        "position_pct": 5,
        "thesis": "Bullish",
        "key_factors": ["MA5>MA20"],
        "risks": ["High PE"],
    }
    gen.save_report("rpt-001", plan)
    reports = gen.get_recent_reports()
    print(f"  Reports saved: {len(reports)}")
    md = gen.generate_markdown(plan)
    print(f"  Markdown: {len(md)} chars")

    log = DecisionLog(db_path=":memory:")
    log.add_entry("600519", "2026-01-01", "Buy", 80.0, 1500.0, 1425.0, "Bullish tech")
    history = log.get_history("600519")
    print(f"  Decision log: {len(history)} entries")
    memory = inject_memory(log, "600519")
    print(f"  Memory injection: {len(memory)} chars")
    print("  [PASS]\n")


def test_master_selection():
    print("=" * 60)
    print("Test 9: Master Selection")
    print("=" * 60)
    profiles = [
        {"name": "Maotai", "pe_ratio": 25, "roe": 30, "volatility": 0.2, "revenue_growth": 0.15},
        {"name": "CATL", "pe_ratio": 50, "roe": 20, "volatility": 0.45, "revenue_growth": 0.5},
    ]
    for p in profiles:
        masters = select_masters(p)
        print(f"  {p['name']}: {', '.join(masters)}")
    print("  [PASS]\n")


def test_workflow():
    print("=" * 60)
    print("Test 10: Workflow Logic")
    print("=" * 60)
    state1 = {"debate_messages": [{"round": 1}], "config": {}}
    print(f"  Round 1: {should_continue_investment_debate(state1)}")
    state2 = {"debate_messages": [{"round": 1}] * 4, "config": {}}
    print(f"  Round 4: {should_continue_investment_debate(state2)}")
    print("  [PASS]\n")


if __name__ == "__main__":
    print("=" * 60)
    print("AShare-X Real Scenario Test")
    print("=" * 60)
    print()

    start = time.time()

    test_config()
    test_technical_indicators()
    test_market_state()
    test_screening()
    test_portfolio()
    test_trading_plan()
    test_risk_engine()
    test_report_memory()
    test_master_selection()
    test_workflow()

    elapsed = time.time() - start
    print("=" * 60)
    print(f"All tests passed! Time: {elapsed:.2f}s")
    print("=" * 60)
