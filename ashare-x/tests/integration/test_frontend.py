"""Quick server test."""

import subprocess
import sys
import time
import urllib.request

proc = subprocess.Popen(
    [sys.executable, "-m", "uvicorn", "server:app", "--host", "127.0.0.1", "--port", "8765"],
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
)
time.sleep(5)

try:
    r = urllib.request.urlopen("http://127.0.0.1:8765/api/health")
    print("Server:", r.read().decode())

    r2 = urllib.request.urlopen("http://127.0.0.1:8765/")
    html = r2.read().decode()
    print(f"Frontend: {len(html)} bytes")

    # Check pages
    pages = ["dashboard", "analysis", "screening", "portfolio", "reports", "settings"]
    for p in pages:
        if f'id="page-{p}"' in html:
            print(f"  Page: {p} OK")
        else:
            print(f"  Page: {p} MISSING")

except Exception as e:
    print(f"Error: {e}")
finally:
    proc.terminate()
