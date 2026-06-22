"""E2E tests for multi-style screening API"""

import pytest
import requests

BASE = "http://127.0.0.1:8765"


def _server_online() -> bool:
    try:
        requests.get(f"{BASE}/docs", timeout=2)
        return True
    except Exception:
        return False


@pytest.mark.skipif(not _server_online(), reason="API server not running on 127.0.0.1:8765")
@pytest.mark.parametrize("style", ["limit_up", "momentum", "value", "hybrid"])
def test_each_style_returns_started(style):
    r = requests.get(f"{BASE}/api/screening/run?style={style}", timeout=10)
    data = r.json()
    assert data.get("status") in ("started", "already_running")
    if data.get("status") == "started":
        assert data.get("style") == style


@pytest.mark.skipif(not _server_online(), reason="API server not running on 127.0.0.1:8765")
def test_styles_endpoint():
    r = requests.get(f"{BASE}/api/screening/styles", timeout=10)
    data = r.json()
    assert "styles" in data
    for s in ["limit_up", "momentum", "value", "hybrid"]:
        assert s in data["styles"], f"Missing style: {s}"


@pytest.mark.skipif(not _server_online(), reason="API server not running on 127.0.0.1:8765")
def test_history_endpoint():
    r = requests.get(f"{BASE}/api/screening/history?limit=5", timeout=10)
    data = r.json()
    assert "history" in data
    assert isinstance(data["history"], list)


@pytest.mark.skipif(not _server_online(), reason="API server not running on 127.0.0.1:8765")
def test_hybrid_via_sse():
    r = requests.get(f"{BASE}/api/screening/run/stream?style=hybrid", timeout=10, stream=True)
    assert r.status_code == 200
    assert "text/event-stream" in r.headers.get("content-type", "")
    r.close()
