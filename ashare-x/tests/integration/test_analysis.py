"""Analysis layer complete test - real data flow from fetch to trading plan."""

import sys
import time
from datetime import datetime
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

import contextlib

from providers.data_bus import DatabaseFirstDataBus
from services.portfolio import optimize_positions
from services.report import ReportGenerator
from services.risk_engine import assess_market_risk, assess_stock_risk
from services.screening import compute_stock_score, rank_stocks
from services.trading_plan import generate_trading_plan
from tools.market_state import detect_market_state, get_position_cap
from tools.technical_indicators import get_latest_indicators


def test_single_stock_analysis():
    """Test: Complete single stock analysis pipeline."""
    print("=" * 60)
    print("Test 1: Single Stock Analysis (600519)")
    print("=" * 60)

    bus = DatabaseFirstDataBus("runtime/analysis_test.db")

    # Step 1: Fetch data
    print("  [1] Fetching K-line data...")
    kline = bus.get_kline("600519", days=100)
    if kline and len(kline) > 20:
        print(f"      Got {len(kline)} rows from API")
    else:
        print("      API data insufficient, using mock data")
        kline = [
            {
                "stock_code": "600519",
                "trade_date": f"2026-01-{i:02d}",
                "open": 1500 + i * 2,
                "high": 1510 + i * 2,
                "low": 1490 + i * 2,
                "close": 1505 + i * 2,
                "volume": 1000000 + i * 10000,
                "amount": 1.5e9,
            }
            for i in range(1, 61)
        ]
        bus._save_kline("600519", kline)
        print(f"      Inserted {len(kline)} mock rows")

    # Step 2: Technical indicators
    print("  [2] Computing technical indicators...")
    import pandas as pd

    df = pd.DataFrame(kline)
    indicators = get_latest_indicators(df)
    print(f"      Close: {indicators['close']:.2f}")
    print(f"      MA5: {indicators['ma5']:.2f}")
    print(f"      MA20: {indicators['ma20']:.2f}")
    print(f"      MACD: {indicators['macd']:.4f}")
    print(f"      RSI: {indicators['rsi_14']:.2f}")
    print(f"      BB Upper: {indicators['bb_upper']:.2f}")
    print(f"      BB Lower: {indicators['bb_lower']:.2f}")

    # Step 3: Stock info
    print("  [3] Fetching stock info...")
    info = bus.get_stock_info("600519")
    if info:
        print(f"      Name: {info.get('stock_name', 'N/A')}")
        print(f"      PE: {info.get('pe_ratio', 'N/A')}")
        print(f"      PB: {info.get('pb_ratio', 'N/A')}")

    # Step 4: Market state
    print("  [4] Detecting market state...")
    market_data = {
        "sh_change_20d": 0.02,
        "advance_count": 2200,
        "decline_count": 1800,
        "volume": 3500,
        "volume_ma20": 3000,
        "north_flow_5d": 30,
    }
    market_state = detect_market_state(market_data)
    position_cap = get_position_cap(market_state)
    print(f"      Market: {market_state}, Position cap: {position_cap * 100:.0f}%")

    # Step 5: Stock scoring
    print("  [5] Computing stock score...")
    stock_profile = {
        "code": "600519",
        "name": "贵州茅台",
        "pe_ratio": info.get("pe_ratio", 25) if info else 25,
        "roe": 0.30,
        "revenue_growth": 0.15,
        "rsi_14": indicators.get("rsi_14", 50),
        "change_pct_20d": 0.05,
        "amount": 10_000_000,
        "listing_days": 5000,
    }
    score = compute_stock_score(stock_profile)
    print(f"      Score: {score:.1f}")

    # Step 6: Risk assessment
    print("  [6] Risk assessment...")
    market_risk = assess_market_risk(market_data)
    stock_risk = assess_stock_risk({"volatility": 0.25, "volume": 1000000, "avg_volume": 1200000})
    print(f"      Market risk: {market_risk['market_state']}")
    print(f"      Stock risk: {stock_risk['risk_level']}")

    # Step 7: Trading plan
    print("  [7] Generating trading plan...")
    current_price = indicators.get("close", 1500)
    plan = generate_trading_plan(
        ticker="600519",
        stock_name="贵州茅台",
        action="Buy" if score > 60 else "Hold",
        confidence=min(score, 100),
        current_price=current_price,
        thesis=f"技术面RSI={indicators.get('rsi_14', 0):.0f}, MA趋势{'上升' if indicators.get('ma5', 0) > indicators.get('ma20', 0) else '下降'}",
        key_factors=[
            f"MA5>{'>' if indicators.get('ma5', 0) > indicators.get('ma20', 0) else '<'}MA20",
            f"RSI={indicators.get('rsi_14', 0):.0f}",
        ],
        risks=["估值偏高"] if info and info.get("pe_ratio", 0) > 30 else ["正常风险"],
    )
    print(f"      Action: {plan['action']}")
    print(f"      Entry: {plan['entry_price']:.2f}")
    print(f"      Stop Loss: {plan['stop_loss']:.2f}")
    print(f"      Take Profit: {plan['take_profit']:.2f}")
    print(f"      Position: {plan['position_pct']}%")

    # Step 8: Generate report
    print("  [8] Generating report...")
    report_gen = ReportGenerator(db_path="runtime/analysis_test.db")
    report_id = f"rpt-{datetime.now().strftime('%Y%m%d%H%M%S')}-600519"
    report_gen.save_report(report_id, plan, token_usage=0, execution_time=0)
    reports = report_gen.get_recent_reports(1)
    print(f"      Report saved: {report_id}")
    print(f"      Reports in DB: {len(reports)}")

    # Cleanup
    with contextlib.suppress(Exception):
        Path("runtime/analysis_test.db").unlink(missing_ok=True)
    print("  [PASS] Single stock analysis complete\n")


def test_batch_analysis():
    """Test: Batch stock analysis."""
    print("=" * 60)
    print("Test 2: Batch Analysis (5 stocks)")
    print("=" * 60)

    stocks = [
        {
            "code": "600519",
            "name": "贵州茅台",
            "pe_ratio": 25,
            "roe": 30,
            "revenue_growth": 0.15,
            "rsi_14": 55,
            "change_pct_20d": 0.05,
            "amount": 10_000_000,
            "listing_days": 5000,
            "industry": "白酒",
            "close": 1500,
        },
        {
            "code": "000858",
            "name": "五粮液",
            "pe_ratio": 20,
            "roe": 25,
            "revenue_growth": 0.12,
            "rsi_14": 48,
            "change_pct_20d": 0.03,
            "amount": 8_000_000,
            "listing_days": 4000,
            "industry": "白酒",
            "close": 135,
        },
        {
            "code": "601318",
            "name": "中国平安",
            "pe_ratio": 8,
            "roe": 15,
            "revenue_growth": 0.05,
            "rsi_14": 42,
            "change_pct_20d": -0.02,
            "amount": 15_000_000,
            "listing_days": 3000,
            "industry": "保险",
            "close": 52,
        },
        {
            "code": "000001",
            "name": "平安银行",
            "pe_ratio": 5,
            "roe": 12,
            "revenue_growth": 0.03,
            "rsi_14": 38,
            "change_pct_20d": -0.01,
            "amount": 12_000_000,
            "listing_days": 3000,
            "industry": "银行",
            "close": 12,
        },
        {
            "code": "002594",
            "name": "比亚迪",
            "pe_ratio": 35,
            "roe": 18,
            "revenue_growth": 0.25,
            "rsi_14": 62,
            "change_pct_20d": 0.08,
            "amount": 20_000_000,
            "listing_days": 2000,
            "industry": "汽车",
            "close": 280,
        },
    ]

    # Step 1: Score and rank
    print("  [1] Scoring and ranking...")
    ranked = rank_stocks(stocks, top_n=5)
    for i, s in enumerate(ranked):
        print(f"      {i + 1}. {s['code']} {s['name']}: {s['score']:.1f}")

    # Step 2: Market state
    print("  [2] Market state...")
    market_data = {
        "sh_change_20d": 0.02,
        "advance_count": 2200,
        "decline_count": 1800,
        "volume": 3500,
        "volume_ma20": 3000,
        "north_flow_5d": 30,
    }
    market_state = detect_market_state(market_data)
    print(f"      Market: {market_state}")

    # Step 3: Portfolio optimization
    print("  [3] Portfolio optimization...")
    portfolio = optimize_positions(ranked, 1_000_000, market_state=market_state)
    total_pct = 0
    for p in portfolio:
        print(f"      {p['code']} {p['name']}: {p['position_pct']}% = {p['position_amount']:.0f}")
        total_pct += p["position_pct"]
    print(f"      Total: {total_pct:.1f}%")

    # Step 4: Generate plans for top 3
    print("  [4] Generating trading plans...")
    for p in portfolio[:3]:
        plan = generate_trading_plan(
            ticker=p["code"],
            stock_name=p["name"],
            action="Buy" if p.get("score", 0) > 60 else "Hold",
            confidence=min(p.get("score", 50), 100),
            current_price=p.get("close", 100),
            thesis=f"评分{p.get('score', 0):.1f}",
        )
        print(
            f"      {p['code']}: {plan['action']} @ {plan['entry_price']:.2f}, SL={plan['stop_loss']:.2f}, TP={plan['take_profit']:.2f}"
        )

    print("  [PASS] Batch analysis complete\n")


def test_analysis_report_generation():
    """Test: Full analysis with report generation."""
    print("=" * 60)
    print("Test 3: Analysis Report Generation")
    print("=" * 60)

    report_gen = ReportGenerator(db_path="runtime/analysis_report_test.db")

    plans = [
        {
            "ticker": "600519",
            "stock_name": "贵州茅台",
            "action": "Buy",
            "confidence": 80,
            "entry_price": 1500,
            "stop_loss": 1425,
            "take_profit": 1725,
            "position_pct": 5,
            "thesis": "技术面看涨，基本面良好",
            "key_factors": ["MA5>MA20", "RSI=55"],
            "risks": ["估值偏高"],
        },
        {
            "ticker": "000858",
            "stock_name": "五粮液",
            "action": "Hold",
            "confidence": 60,
            "entry_price": 135,
            "stop_loss": 128,
            "take_profit": 155,
            "position_pct": 4,
            "thesis": "中性观望",
            "key_factors": ["RSI=48"],
            "risks": ["正常风险"],
        },
    ]

    for i, plan in enumerate(plans):
        report_id = f"rpt-{datetime.now().strftime('%Y%m%d%H%M%S')}-{i}"
        report_gen.save_report(report_id, plan)

    reports = report_gen.get_recent_reports(10)
    print(f"  Reports saved: {len(reports)}")
    for r in reports:
        print(f"    {r['ticker']}: {r['action']} (confidence={r['confidence']})")

    # Generate markdown for first report
    md = report_gen.generate_markdown(plans[0])
    print(f"\n  Markdown report ({len(md)} chars):")
    md_clean = md.replace("¥", "")
    print("  " + md_clean[:200] + "...")

    with contextlib.suppress(Exception):
        Path("runtime/analysis_report_test.db").unlink(missing_ok=True)
    print("  [PASS] Report generation complete\n")


if __name__ == "__main__":
    print("=" * 60)
    print("AShare-X Analysis Layer Test")
    print("=" * 60)
    print()

    start = time.time()

    test_single_stock_analysis()
    test_batch_analysis()
    test_analysis_report_generation()

    elapsed = time.time() - start
    print("=" * 60)
    print(f"All analysis tests completed! Time: {elapsed:.2f}s")
    print("=" * 60)
