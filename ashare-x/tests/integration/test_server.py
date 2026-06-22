"""Server test script."""

import json
import subprocess
import sys
import time
import urllib.request


def main():
    # Start server
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "server:app",
            "--host",
            "127.0.0.1",
            "--port",
            "8765",
            "--log-level",
            "info",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    time.sleep(3)

    print("=" * 60)
    print("AShare-X Server Test")
    print("=" * 60)
    print()

    # Test endpoints
    endpoints = [
        ("GET", "http://127.0.0.1:8765/api/health"),
        ("GET", "http://127.0.0.1:8765/api/settings"),
        ("GET", "http://127.0.0.1:8765/api/portfolio"),
        ("GET", "http://127.0.0.1:8765/api/screening?style=value"),
        ("GET", "http://127.0.0.1:8765/api/reports"),
    ]

    for method, url in endpoints:
        try:
            req = urllib.request.Request(url)
            r = urllib.request.urlopen(req)
            body = r.read().decode()
            endpoint = url.split("/")[-1].split("?")[0]
            print(f"[{r.status}] {method} /{endpoint}")
            print(f"    {body[:150]}")
        except Exception as e:
            print(f"[ERROR] {url}: {e}")
        print()

    # Test analysis POST
    print("--- Analysis POST ---")
    data = json.dumps({"ticker": "600519", "fast_mode": False}).encode()
    req = urllib.request.Request(
        "http://127.0.0.1:8765/api/analysis",
        data=data,
        headers={"Content-Type": "application/json"},
    )
    r = urllib.request.urlopen(req)
    body = json.loads(r.read().decode())
    print(f"Job created: {body}")

    if body.get("job_id"):
        job_id = body["job_id"]
        r2 = urllib.request.urlopen(f"http://127.0.0.1:8765/api/analysis/{job_id}")
        status = json.loads(r2.read().decode())
        print(f"Job status: {status}")

    print()
    print("=" * 60)
    print("All endpoints tested!")
    print("=" * 60)

    proc.terminate()


if __name__ == "__main__":
    main()
