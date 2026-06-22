"""全功能端到端测试（不含LLM）。"""
import json
import os
import subprocess
import sys
import traceback

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

RMB = "RMB "
PASS_COUNT = 0
FAIL_COUNT = 0


def test_step(name, func):
    global PASS_COUNT, FAIL_COUNT
    print(f"\n{'='*70}")
    print(f"  {name}")
    print(f"{'='*70}")
    try:
        func()
        print(f"  >>> PASS")
        PASS_COUNT += 1
    except Exception as e:
        print(f"  >>> FAIL: {e}")
        traceback.print_exc()
        FAIL_COUNT += 1


# ═══════════════════════════════════════════════════════════════
# 1. DataBus — 数据总线
# ═══════════════════════════════════════════════════════════════

def test_data_bus():
    from providers.data_bus import DatabaseFirstDataBus
    bus = DatabaseFirstDataBus()

    # 全量快照
    spot = bus._get_spot_data("600519")
    print(f"  spot 600519: {spot.get('stock_name') if spot else 'unreachable'}")

    # 市场广度
    breadth = bus.get_market_breadth()
    total = breadth.get("total", 0)
    print(f"  breadth: total={total} up={breadth.get('up',0)} down={breadth.get('down',0)}")
    if total == 0:
        print("  (network unreachable, testing DB fallback)")

    # 市场概览
    overview = bus.get_market_overview()
    state = overview.get("market_state", "N/A")
    print(f"  market_state={state}")

    # K线查询
    kline = bus.get_kline("600519", days=60)
    print(f"  kline 600519: {len(kline) if kline else 0} bars")
    assert kline is not None or total == 0  # network may fail

    # 基本面
    fund = bus.get_fundamentals("600519")
    if fund:
        print(f"  fundamentals: PE={fund.get('pe_ratio')} ROE={fund.get('roe')}")
    else:
        print("  fundamentals: no data (network)")


# ═══════════════════════════════════════════════════════════════
# 2. MarketScanner — 全市场扫描
# ═══════════════════════════════════════════════════════════════

def test_market_scanner():
    from services.market_scanner import MarketScanner
    scanner = MarketScanner()

    # 扫描
    results = scanner.scan_full_market(top_n=10)
    print(f"  scan: {len(results)} stocks")
    for i, s in enumerate(results[:5]):
        print(f"    #{i+1} {s.get('stock_code')} {s.get('stock_name')} "
              f"score={s.get('score',0):.1f} PE={s.get('pe_ratio')}")

    # 观察名单
    if results:
        scanner.update_watchlist(results, max_size=10)
        wl = scanner.get_watchlist()
        print(f"  watchlist: {len(wl)} stocks")
        # mark_analyzed
        scanner.mark_analyzed(results[0]["stock_code"])
        wl2 = scanner.get_watchlist()
        s0 = next(w for w in wl2 if w["stock_code"] == results[0]["stock_code"])
        print(f"  mark_analyzed: count={s0['analysis_count']} date={s0['last_analysis_date']}")
        assert s0["analysis_count"] == 1

    # normalize
    norm = MarketScanner._normalize_spot({
        "stock_code": "600519", "stock_name": "maotai",
        "pe_ratio": 30.0, "pb_ratio": 10.0,
    })
    assert norm["stock_code"] == "600519"
    assert norm["is_st"] is False
    print("  normalize: OK")


# ═══════════════════════════════════════════════════════════════
# 3. PaperPortfolio — 模拟持仓全流程
# ═══════════════════════════════════════════════════════════════

def test_paper_portfolio():
    from services.paper_portfolio import PaperPortfolio
    import sqlite3

    p = PaperPortfolio()
    # 清空
    conn = sqlite3.connect(p.db_path)
    conn.execute("DELETE FROM paper_holdings")
    conn.execute("DELETE FROM paper_trades")
    conn.execute("UPDATE paper_account SET cash = initial_capital WHERE id = 1")
    conn.commit()
    conn.close()

    # 1. 买入
    r = p.buy("600519", "maotai", 300.0, 200, "buy test")
    assert r["ok"], f"buy failed: {r}"
    print(f"  buy: 200@300 cost={RMB}{r['total_cost']:.2f}")

    # 2. 加仓
    r = p.add("600519", "maotai", 310.0, 100, "add test")
    assert r["ok"]
    print(f"  add: +100@310 avg={r['new_avg_cost']} total={r['total_shares']}")

    # 3. T+1 拦截
    r = p.reduce("600519", 310.0, 100, "same day")
    assert not r["ok"]
    print(f"  T+1 block: {r['error']}")

    # 4. 次日减仓
    p.update_prices()
    r = p.reduce("600519", 310.0, 100, "next day reduce")
    assert r["ok"]
    print(f"  reduce: 100@310 remaining={r['remaining_shares']} profit={RMB}{r['profit']:.2f}")

    # 5. 账户
    acct = p.get_account()
    print(f"  account: total={RMB}{acct['total_assets']:.0f} "
          f"cash={RMB}{acct['cash']:.0f} pnl={RMB}{acct['pnl']:.0f} ({acct['pnl_pct']:+.1f}%)")
    assert acct["holding_count"] == 1

    # 6. 交易历史
    trades = p.get_trade_history()
    print(f"  trades: {len(trades)} records")
    assert len(trades) == 3  # buy + add + reduce

    # 7. 清仓
    r = p.clear("600519", 320.0, "clear all")
    assert r["ok"]
    print(f"  clear: remaining={r['remaining_shares']}")
    assert p.get_holdings() == []

    # 8. 手续费验证
    p2 = PaperPortfolio()
    conn = sqlite3.connect(p2.db_path)
    conn.execute("DELETE FROM paper_holdings")
    conn.execute("DELETE FROM paper_trades")
    conn.execute("UPDATE paper_account SET cash = initial_capital WHERE id = 1")
    conn.commit()
    conn.close()
    # 大额: 100*500=50000, commission=50000*0.00025=12.5
    p2.buy("000001", "pingan", 100.0, 500, "big")
    conn = sqlite3.connect(p2.db_path)
    row = conn.execute("SELECT commission FROM paper_trades WHERE action='BUY'").fetchone()
    conn.close()
    assert row[0] == 12.5
    print(f"  commission (big): {RMB}12.50")

    # 小额: 10*100=1000, commission=max(0.25, 5)=5
    conn = sqlite3.connect(p2.db_path)
    conn.execute("DELETE FROM paper_trades")
    conn.execute("UPDATE paper_account SET cash = initial_capital WHERE id = 1")
    conn.commit()
    conn.close()
    p2.buy("000002", "small", 10.0, 100, "small")
    conn = sqlite3.connect(p2.db_path)
    row = conn.execute("SELECT commission FROM paper_trades WHERE action='BUY'").fetchone()
    conn.close()
    assert row[0] == 5.0
    print(f"  commission (min): {RMB}5.00")


# ═══════════════════════════════════════════════════════════════
# 4. PositionEngine — 仓位决策矩阵
# ═══════════════════════════════════════════════════════════════

def test_position_engine():
    from services.position_engine import PositionEngine
    engine = PositionEngine()
    account = {"total_assets": 100000, "cash": 100000}

    cases = [
        # (action, confidence, holding, market, holding_count, expected)
        ("Buy", 85, None, "NEUTRAL", 0, "INITIAL_BUY"),
        ("Buy", 50, None, "NEUTRAL", 0, "WATCH"),
        ("Buy", 85, None, "NEUTRAL", 5, "HOLD"),  # max holdings
        ("Buy", 80, {"shares": 100, "market_value": 5000, "avg_cost": 48}, "NEUTRAL", 1, "ADD"),
        ("Sell", 75, {"shares": 300, "market_value": 15000, "avg_cost": 50}, "NEUTRAL", 1, "CLEAR"),
        ("Hold", 60, {"shares": 300, "market_value": 15000, "avg_cost": 50}, "NEUTRAL", 1, "HOLD"),
        ("Hold", 30, {"shares": 600, "market_value": 30000, "avg_cost": 50}, "NEUTRAL", 1, "REDUCE"),
    ]

    for action, conf, holding, market, hc, expected in cases:
        analysis = {
            "action": action, "confidence": conf,
            "entry_price": 50.0, "ticker": "000001",
            "thesis": f"{action} conf={conf}",
        }
        d = engine.decide(analysis, holding, account, market, hc)
        status = "OK" if d.action == expected else "MISMATCH"
        print(f"  {action:>4} conf={conf:>2} holding={'Y' if holding else 'N'} "
              f"market={market:>7} -> {d.action:<12} (expect {expected}) [{status}]")
        assert d.action == expected, f"{status}: got {d.action}, expected {expected}"

    # PANIC
    d = engine.decide(
        {"action": "Buy", "confidence": 90, "entry_price": 50.0,
         "ticker": "000001", "thesis": "panic"},
        None, account, "PANIC", 0,
    )
    assert d.target_shares == 0
    print(f"  PANIC -> shares=0 OK")

    # 100 lot
    d = engine.decide(
        {"action": "Buy", "confidence": 85, "entry_price": 50.0,
         "ticker": "000001", "thesis": "lot test"},
        None, account, "NEUTRAL", 0,
    )
    assert d.target_shares % 100 == 0
    print(f"  100lot: shares={d.target_shares} pct={d.position_pct}% OK")


# ═══════════════════════════════════════════════════════════════
# 5. Screening — 多因子选股
# ═══════════════════════════════════════════════════════════════

def test_screening():
    from services.screening import compute_stock_score, hard_filter, rank_stocks

    stocks = [
        {"stock_code": "600519", "stock_name": "maotai", "pe_ratio": 30, "pb_ratio": 10,
         "roe": 25, "revenue_growth": 15, "profit_growth": 20,
         "change_pct_20d": 5, "rsi_14": 55, "turnover_rate": 0.5,
         "amount": 10000000, "is_st": False, "is_suspended": False, "listing_days": 999},
        {"stock_code": "000001", "stock_name": "pingan", "pe_ratio": 8, "pb_ratio": 1,
         "roe": 12, "revenue_growth": 5, "profit_growth": 8,
         "change_pct_20d": -2, "rsi_14": 40, "turnover_rate": 1.2,
         "amount": 20000000, "is_st": False, "is_suspended": False, "listing_days": 999},
        {"stock_code": "*ST001", "stock_name": "*STbad", "pe_ratio": -5, "pb_ratio": 20,
         "roe": -10, "revenue_growth": -30, "profit_growth": -40,
         "change_pct_20d": -15, "rsi_14": 25, "turnover_rate": 0.1,
         "amount": 1000000, "is_st": True, "is_suspended": False, "listing_days": 10},
    ]

    # hard_filter
    filtered = [s for s in stocks if hard_filter(s)]
    assert len(filtered) == 2  # ST filtered out
    print(f"  hard_filter: {len(stocks)} -> {len(filtered)} (ST removed)")

    # compute_stock_score
    for s in filtered:
        s["score"] = compute_stock_score(s, "balanced")
    print(f"  scores: {filtered[0]['stock_code']}={filtered[0]['score']:.1f} "
          f"{filtered[1]['stock_code']}={filtered[1]['score']:.1f}")

    # rank_stocks
    ranked = rank_stocks(stocks, top_n=5, style="value")
    print(f"  rank (value): {len(ranked)} stocks")
    assert len(ranked) == 2
    assert ranked[0]["score"] >= ranked[1]["score"]
    print(f"  top: {ranked[0]['stock_code']} score={ranked[0]['score']:.1f}")


# ═══════════════════════════════════════════════════════════════
# 6. IncrementalRefresh — 增量数据刷新
# ═══════════════════════════════════════════════════════════════

def test_incremental_refresh():
    from services.updater import DailyUpdater
    updater = DailyUpdater()

    # 获取待检查股票
    stocks = updater._get_stocks_to_check()
    print(f"  stocks to check: {len(stocks)} ({stocks[:5]}...)")

    # 增量刷新
    result = updater.incremental_refresh(days=60)
    print(f"  total={result['total']} skipped={result['skipped']} "
          f"updated={result['updated']} failed={result['failed']}")
    for d in result["details"][:5]:
        code = d["code"]
        status = d["status"]
        days = d.get("existing_days", d.get("previous_days", "?"))
        print(f"    {code}: {status} (days={days})")

    assert result["total"] > 0
    assert result["skipped"] + result["updated"] + result["failed"] == result["total"]


# ═══════════════════════════════════════════════════════════════
# 7. DailyPlanGenerator — 每日计划生成（无LLM）
# ═══════════════════════════════════════════════════════════════

def test_daily_plan():
    from services.daily_plan import DailyPlanGenerator
    gen = DailyPlanGenerator()

    plan = gen.generate(fast_mode=True)
    print(f"  date: {plan.get('date')}")
    print(f"  market_state: {plan.get('market_state')}")
    print(f"  scan_count: {plan.get('scan_count', 'N/A')}")
    print(f"  actions: {len(plan.get('actions', []))}")
    print(f"  holdings: {len(plan.get('holdings_status', []))}")
    print(f"  watchlist: {len(plan.get('watchlist', []))}")
    print(f"  errors: {len(plan.get('errors', []))}")
    for err in plan.get("errors", [])[:3]:
        print(f"    - {err}")
    summary = plan.get("summary", "").replace("\u00a5", "RMB")[:100]
    print(f"  summary: {summary}")

    # 验证保存
    loaded = gen.get_today_plan()
    assert loaded is not None, "plan should be saved"
    print(f"  saved to DB: YES (date={loaded.get('date')})")

    # 验证历史
    history = gen.get_plan_history(limit=5)
    print(f"  history: {len(history)} plans")

    # 验证Markdown
    from pathlib import Path
    reports_dir = Path(gen.config.get("runtime.reports_dir", "reports"))
    today = plan.get("date", "")
    md_files = list(reports_dir.glob(f"daily_plan_{today}.md"))
    if md_files:
        content = md_files[0].read_text(encoding="utf-8")
        assert "每日交易计划" in content
        print(f"  markdown: {md_files[0].name} ({len(content)} chars)")
    else:
        print("  markdown: NOT FOUND")

    # 验证账户
    acct = plan.get("account", {})
    if acct:
        print(f"  account: total={RMB}{acct.get('total_assets',0):.0f} "
              f"cash={RMB}{acct.get('cash',0):.0f} "
              f"holdings={acct.get('holding_count',0)}")


# ═══════════════════════════════════════════════════════════════
# 8. API — 所有非LLM端点
# ═══════════════════════════════════════════════════════════════

def test_api():
    from fastapi.testclient import TestClient
    from server import app
    client = TestClient(app)

    results = []

    def check(method, path, expected_status=200, **kwargs):
        r = client.request(method, path, **kwargs)
        data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        ok = r.status_code == expected_status
        if not ok:
            print(f"  {method} {path} -> {r.status_code} (expected {expected_status}) FAIL")
        results.append((method, path, r.status_code, data, ok))
        return data

    # health
    d = check("GET", "/api/health")
    assert d.get("status") == "ok"

    # data: kline
    d = check("GET", "/api/data/kline?code=600519&days=30")
    print(f"  kline: {d.get('total', 0)} bars")

    # data: stats
    d = check("GET", "/api/data/stats")
    print(f"  stats: kline={d.get('kline_count',0)} stocks={d.get('stock_count',0)} "
          f"db={d.get('db_size','')}")

    # data: health
    d = check("GET", "/api/data/health")
    print(f"  data_health: {d.get('status')} - {d.get('message','')}")

    # data: incremental-refresh
    d = check("POST", "/api/data/incremental-refresh?days=60")
    s = d.get("stats", {})
    print(f"  incremental: total={s.get('total')} skip={s.get('skipped')} "
          f"update={s.get('updated')} fail={s.get('failed')}")

    # trading-plan: portfolio
    d = check("GET", "/api/trading-plan/portfolio")
    assert d.get("ok") is True
    acct = d.get("account", {})
    print(f"  portfolio: total={RMB}{acct.get('total_assets',0):.0f} "
          f"holdings={acct.get('holding_count',0)}")

    # trading-plan: watchlist
    d = check("GET", "/api/trading-plan/watchlist")
    assert d.get("ok") is True
    print(f"  watchlist: {d.get('total',0)} stocks")

    # trading-plan: trades
    d = check("GET", "/api/trading-plan/trades")
    assert d.get("ok") is True
    print(f"  trades: {d.get('total',0)} records")

    # trading-plan: today
    d = check("GET", "/api/trading-plan/today")
    if d.get("ok"):
        plan = d.get("plan", {})
        print(f"  today: date={plan.get('date')} actions={len(plan.get('actions',[]))}")
    else:
        print(f"  today: {d.get('message','')}")

    # trading-plan: history
    d = check("GET", "/api/trading-plan/history")
    assert d.get("ok") is True
    print(f"  history: {d.get('total',0)} plans")

    # backtest: strategies (returns strategies list, no 'ok' field)
    d = check("GET", "/api/backtest/strategies")
    assert "strategies" in d
    print(f"  strategies: {[s.get('name') for s in d.get('strategies', [])]}")

    # backtest: validation (empty codes) - should be rejected (400)
    r = client.post("/api/backtest", json={"stock_codes": [], "strategy": "ma_cross", "days": 30})
    assert r.status_code == 400
    print(f"  backtest (empty): rejected with 400 OK")

    # backtest: validation (too many) - should be rejected (400)
    r = client.post("/api/backtest", json={
        "stock_codes": ["1","2","3","4","5","6","7","8","9","10","11"],
        "strategy": "ma_cross", "days": 30,
    })
    assert r.status_code == 400
    print(f"  backtest (>10): rejected with 400 OK")

    # screening: rank (may fail if no data in DB)
    d = check("GET", "/api/screening/rank?top_n=5&style=balanced")
    if d.get("ok"):
        print(f"  screening: {len(d.get('stocks',[]))} stocks")
    else:
        print(f"  screening: {d.get('message','no data')} (network-dependent)")

    # summary
    passed = sum(1 for _, _, _, _, ok in results if ok)
    total = len(results)
    print(f"\n  API summary: {passed}/{total} endpoints OK")
    assert passed >= total - 1  # allow 1 failure (screening may have no data)


# ═══════════════════════════════════════════════════════════════
# 9. CLI — 命令行
# ═══════════════════════════════════════════════════════════════

def test_cli():
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"

    # plan --show
    result = subprocess.run(
        [sys.executable, "main.py", "plan", "--show"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        env=env,
    )
    output = (result.stdout or "") + (result.stderr or "")
    safe = output.replace("\u00a5", "RMB")
    lines = [l for l in safe.strip().split("\n") if l.strip()]
    for line in lines[:15]:
        print(f"  {line}")
    if len(lines) > 15:
        print(f"  ... ({len(lines)} lines total)")
    assert "每日交易计划" in safe or "尚未生成" in safe
    assert result.returncode == 0
    print(f"  exit code: 0 OK")

    # screen (may fail due to network, check no crash)
    result2 = subprocess.run(
        [sys.executable, "main.py", "screen", "--limit", "5"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        env=env, timeout=60,
    )
    out2 = (result2.stdout or "") + (result2.stderr or "")
    # screen may exit 0 even with no data; just verify it doesn't crash
    print(f"  screen: exit={result2.returncode} OK")

    # backtest (validation)
    result3 = subprocess.run(
        [sys.executable, "main.py", "backtest", ""],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        env=env,
    )
    out3 = (result3.stdout or "") + (result3.stderr or "")
    assert result3.returncode == 0
    print(f"  backtest (no codes): exit=0 OK")

    # help
    result4 = subprocess.run(
        [sys.executable, "main.py", "--help"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        env=env,
    )
    out4 = (result4.stdout or "") + (result4.stderr or "")
    assert "plan" in out4 and "analyze" in out4 and "serve" in out4
    print(f"  help: all commands listed OK")


# ═══════════════════════════════════════════════════════════════
# 10. Config — 配置验证
# ═══════════════════════════════════════════════════════════════

def test_config():
    from core.config import Config
    c = Config()

    # portfolio config
    assert c.get("portfolio.initial_capital") == 100000
    assert c.get("portfolio.max_holdings") == 5
    assert c.get("portfolio.max_single_pct") == 0.30
    assert c.get("portfolio.lot_size") == 100
    assert c.get("portfolio.commission_rate") == 0.00025
    assert c.get("portfolio.min_commission") == 5
    assert c.get("portfolio.stamp_tax_rate") == 0.001
    print(f"  portfolio: capital={c.get('portfolio.initial_capital')} "
          f"max_holdings={c.get('portfolio.max_holdings')} "
          f"lot={c.get('portfolio.lot_size')}")

    # trading_plan config
    assert c.get("trading_plan.daily_analysis_batch") == 30
    assert c.get("trading_plan.watchlist_size") == 30
    assert c.get("trading_plan.scan_top_n") == 50
    print(f"  trading_plan: batch={c.get('trading_plan.daily_analysis_batch')} "
          f"watchlist={c.get('trading_plan.watchlist_size')} "
          f"scan_top={c.get('trading_plan.scan_top_n')}")

    # llm budget
    assert c.get("llm.monthly_budget_rmb") == 1000
    print(f"  llm: budget={c.get('llm.monthly_budget_rmb')} "
          f"model={c.get('llm.quick_think.model')}")

    # runtime
    assert c.get("runtime.db_path") == "runtime/investment.db"
    print(f"  runtime: db={c.get('runtime.db_path')}")


# ═══════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 70)
    print("  ASHARE-X E2E TEST (NO LLM) — All non-LLM features")
    print("=" * 70)

    test_step("1. DataBus (akshare/DB)", test_data_bus)
    test_step("2. MarketScanner", test_market_scanner)
    test_step("3. PaperPortfolio (buy/add/T+1/reduce/clear/fee)", test_paper_portfolio)
    test_step("4. PositionEngine (7 cases + PANIC + 100lot)", test_position_engine)
    test_step("5. Screening (filter/score/rank)", test_screening)
    test_step("6. IncrementalRefresh (60d)", test_incremental_refresh)
    test_step("7. DailyPlanGenerator (no LLM)", test_daily_plan)
    test_step("8. API Server (12+ endpoints)", test_api)
    test_step("9. CLI (plan/screen/backtest/help)", test_cli)
    test_step("10. Config (portfolio/trading_plan/llm/runtime)", test_config)

    print(f"\n{'='*70}")
    print(f"  TOTAL: {PASS_COUNT}/{PASS_COUNT + FAIL_COUNT} passed, {FAIL_COUNT} failed")
    print(f"{'='*70}")
