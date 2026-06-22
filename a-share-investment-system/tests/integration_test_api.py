#!/usr/bin/env python
"""集成测试 — 验证所有前后端API端点"""

import time

import requests

BASE = "http://127.0.0.1:8765"
PASS = 0
FAIL = 0


def test(name, method="GET", path="/", data=None, check=lambda r: 200 <= r.status_code < 300):
    global PASS, FAIL
    url = f"{BASE}{path}"
    try:
        if method == "GET":
            r = requests.get(url, timeout=5)
        elif method == "POST":
            r = requests.post(url, json=data, timeout=10)
        elif method == "DELETE":
            r = requests.delete(url, timeout=5)
        ok = check(r)
        if ok:
            print(f"  OK {method} {path}")
            PASS += 1
        else:
            msg = f"status={r.status_code}, body={r.text[:200]}"
            print(f"  FAIL {method} {path} -> {msg}")
            FAIL += 1
    except Exception as e:
        print(f"  FAIL {method} {path} -> ERROR: {e}")
        FAIL += 1


print("=" * 50)
print("前后端API集成测试")
print("=" * 50)

# ── Part 0: Quick fixes ──
print("\n--- Part 0: 快速修复 ---")
test("Health", "GET", "/api/health", check=lambda r: r.json().get("version") == "5.1.0")
test("StockInfo列表", "GET", "/api/db/stockinfo?limit=3", check=lambda r: "stocks" in r.json())
test(
    "分析格式",
    "GET",
    "/api/analysis/600519",
    check=lambda r: r.json().get("confidence") is not None,
)
test("市场态势", "GET", "/api/market/regime")
test("系统状态", "GET", "/api/system/status")

# ── Part 1: Analysis API ──
print("\n--- Part 1: Analysis API ---")
test(
    "分析师列表",
    "GET",
    "/api/analysis/analysts",
    check=lambda r: len(r.json().get("analysts", [])) > 0,
)
test(
    "提交分析任务",
    "POST",
    "/api/analysis/run",
    {"stock_code": "600519"},
    check=lambda r: r.json().get("task_id") is not None,
)
time.sleep(3)
test("任务列表", "GET", "/api/analysis/tasks", check=lambda r: r.json().get("total", 0) > 0)
r_task = requests.get(f"{BASE}/api/analysis/tasks", timeout=10)
tasks = r_task.json().get("tasks", [])
if tasks:
    tid = tasks[0]["task_id"]
    test("任务详情", "GET", f"/api/analysis/tasks/{tid}")
    test(
        "任务结果",
        "GET",
        f"/api/analysis/result/{tid}",
        check=lambda r: r.json().get("stock_code") is not None,
    )

# ── Part 2: Reports API ──
print("\n--- Part 2: Reports API ---")
test("报告列表", "GET", "/api/reports", check=lambda r: "reports" in r.json())
r_reports = requests.get(f"{BASE}/api/reports", timeout=10)
reports = r_reports.json().get("reports", [])
if reports:
    rid = reports[0]["id"]
    test("报告详情", "GET", f"/api/reports/{rid}")

# ── Part 3: Favorites API ──
print("\n--- Part 3: Favorites API ---")
test("自选股列表", "GET", "/api/favorites")
test("添加自选股", "POST", "/api/favorites", {"stock_code": "000001", "stock_name": "平安银行"})
test("添加后再查", "GET", "/api/favorites", check=lambda r: len(r.json().get("data", [])) > 0)
test(
    "检查自选股",
    "GET",
    "/api/favorites/000001",
    check=lambda r: r.json().get("is_favorite") is True,
)
test("删除自选股", "DELETE", "/api/favorites/000001")

# ── Part 4: Tasks API ──
print("\n--- Part 4: Tasks API ---")
test("任务中心列表", "GET", "/api/tasks", check=lambda r: "total" in r.json())
test("任务队列", "GET", "/api/tasks/queue")
if tasks:
    tid = tasks[0]["task_id"]
    test("任务中心详情", "GET", f"/api/tasks/{tid}")

# ── 总结 ──
print("\n" + "=" * 50)
TOTAL = PASS + FAIL
print(f"结果: {PASS}/{TOTAL} 通过, {FAIL}/{TOTAL} 失败")
if FAIL == 0:
    print("✅ 所有端点测试通过!")
else:
    print(f"⚠️  {FAIL} 个端点失败,需检查")
print("=" * 50)
