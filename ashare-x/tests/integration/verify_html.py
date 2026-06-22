"""Verify frontend HTML."""

with open("static/index.html", encoding="utf-8") as f:
    content = f.read()

lines = content.split("\n")
print(f"Total lines: {len(lines)}")

# Check for duplicate function definitions
show_results_count = content.count("function showResults")
print(f"showResults definitions: {show_results_count}")

# Check for leftover code patterns
leftover_patterns = ['document.getElementById("ag-"+p)', "clearInterval(iv)"]
for p in leftover_patterns:
    if p in content:
        print(f"WARNING: Leftover pattern found: {p}")
    else:
        print(f"OK: No leftover: {p}")

# Check key features exist
features = {
    "toast-container": "Toast notifications",
    "skeleton": "Loading skeleton",
    "@media": "Responsive layout",
    "kline-chart": "K-line chart",
    "EventSource": "SSE streaming",
    "showToast": "Toast function",
    "initKlineChart": "K-line init function",
}

for key, desc in features.items():
    status = "OK" if key in content else "MISSING"
    print(f"{status}: {desc}")
