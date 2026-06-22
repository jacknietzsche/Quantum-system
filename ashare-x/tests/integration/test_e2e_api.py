"""End-to-end API tests — no running server required.

Two test modes:
  - Sync tests via FastAPI TestClient (simple CRUD, no background tasks)
  - Async tests via httpx AsyncClient + ASGITransport (analysis lifecycle, SSE)

Covers:
  1. Health check
  2. Settings CRUD
  3. Portfolio endpoints
  4. Screening endpoints
  5. Reports endpoints
  6. Data management endpoints
  7. Analysis lifecycle: POST → poll → verify result
  8. SSE stream for analysis job
  9. Error handling / validation
"""

from __future__ import annotations

import asyncio
import os
import time

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient

from server import app

# 检查是否有API Key（真实LangGraph需要）
_HAS_API_KEY = bool(os.getenv("DEEPSEEK_API_KEY", ""))

# ── Fixtures ───────────────────────────────────────────────────────────────


@pytest.fixture()
def sync_client():
    """Synchronous TestClient for simple endpoint tests."""
    return TestClient(app)


@pytest_asyncio.fixture()
async def async_client():
    """Async httpx client over the ASGI app — needed for background-task tests."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c


# ── 1. Health ──────────────────────────────────────────────────────────────


@pytest.mark.integration
class TestHealth:
    def test_health_returns_ok(self, sync_client: TestClient):
        r = sync_client.get("/api/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"


# ── 2. Settings ────────────────────────────────────────────────────────────


@pytest.mark.integration
class TestSettings:
    def test_get_settings(self, sync_client: TestClient):
        r = sync_client.get("/api/settings")
        assert r.status_code == 200
        data = r.json()
        assert data["llm_provider"] == "deepseek"
        assert "quick_think_model" in data
        assert "debate_rounds" in data

    def test_update_settings(self, sync_client: TestClient):
        r = sync_client.put("/api/settings", json={"debate_rounds": 3, "risk_rounds": 1})
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "ok"


# ── 3. Portfolio ───────────────────────────────────────────────────────────


@pytest.mark.integration
class TestPortfolio:
    def test_get_portfolio_empty(self, sync_client: TestClient):
        r = sync_client.get("/api/portfolio")
        assert r.status_code == 200
        assert isinstance(r.json()["holdings"], list)

    def test_rebalance_empty(self, sync_client: TestClient):
        r = sync_client.post("/api/portfolio/rebalance")
        assert r.status_code == 200
        assert "operations" in r.json()


# ── 4. Screening ───────────────────────────────────────────────────────────


@pytest.mark.integration
class TestScreening:
    def test_get_screening_default(self, sync_client: TestClient):
        r = sync_client.get("/api/screening")
        assert r.status_code == 200
        assert r.json()["style"] == "balanced"

    def test_get_screening_growth(self, sync_client: TestClient):
        r = sync_client.get("/api/screening?style=growth")
        assert r.status_code == 200
        assert r.json()["style"] == "growth"

    def test_run_screening(self, sync_client: TestClient):
        r = sync_client.post("/api/screening/run")
        assert r.status_code == 200
        assert "stocks" in r.json()


# ── 5. Reports ─────────────────────────────────────────────────────────────


@pytest.mark.integration
class TestReports:
    def test_get_reports(self, sync_client: TestClient):
        r = sync_client.get("/api/reports")
        assert r.status_code == 200
        assert "reports" in r.json()

    def test_get_report_by_id(self, sync_client: TestClient):
        r = sync_client.get("/api/reports/rpt-test-001")
        assert r.status_code == 404


# ── 6. Data Management ────────────────────────────────────────────────────


@pytest.mark.integration
class TestDataManagement:
    def test_get_kline_returns_data(self, sync_client: TestClient):
        """K线接口应该返回数据或空列表。"""
        r = sync_client.get("/api/data/kline?code=600519&days=5")
        assert r.status_code == 200
        data = r.json()
        assert "kline" in data
        assert "total" in data

    def test_get_kline_empty_code(self, sync_client: TestClient):
        r = sync_client.get("/api/data/kline?code=INVALID999")
        assert r.status_code == 200

    def test_get_stats(self, sync_client: TestClient):
        r = sync_client.get("/api/data/stats")
        assert r.status_code == 200
        data = r.json()
        assert "kline_count" in data
        assert "stock_count" in data
        assert "db_size" in data

    def test_refresh_data(self, sync_client: TestClient):
        r = sync_client.post("/api/data/refresh?code=600519")
        assert r.status_code == 200

    def test_health_check(self, sync_client: TestClient):
        r = sync_client.get("/api/data/health")
        assert r.status_code == 200
        data = r.json()
        assert "status" in data
        assert "sources" in data
        assert len(data["sources"]) > 0


# ── 7. Analysis Lifecycle (async — needs persistent event loop) ────────────


@pytest.mark.integration
class TestAnalysisLifecycle:
    def test_start_analysis(self, sync_client: TestClient):
        r = sync_client.post("/api/analysis", json={"ticker": "600519"})
        assert r.status_code == 200
        data = r.json()
        assert "job_id" in data
        assert data["status"] == "running"

    def test_start_analysis_fast_mode(self, sync_client: TestClient):
        r = sync_client.post("/api/analysis", json={"ticker": "000858", "fast_mode": True})
        assert r.status_code == 200
        assert r.json()["ticker"] == "000858"

    def test_get_analysis_status(self, sync_client: TestClient):
        job_id = sync_client.post("/api/analysis", json={"ticker": "600519"}).json()["job_id"]
        r = sync_client.get(f"/api/analysis/{job_id}")
        assert r.status_code == 200
        assert r.json()["job_id"] == job_id

    def test_get_analysis_not_found(self, sync_client: TestClient):
        assert sync_client.get("/api/analysis/nonexistent").status_code == 404

    def test_cancel_analysis(self, sync_client: TestClient):
        job_id = sync_client.post("/api/analysis", json={"ticker": "600519"}).json()["job_id"]
        assert sync_client.delete(f"/api/analysis/{job_id}").json()["ok"] is True
        assert sync_client.get(f"/api/analysis/{job_id}").json()["status"] == "cancelled"

    def test_cancel_not_found(self, sync_client: TestClient):
        assert sync_client.delete("/api/analysis/nonexistent").status_code == 404

    @pytest.mark.asyncio
    @pytest.mark.skipif(not _HAS_API_KEY, reason="需要DEEPSEEK_API_KEY才能执行真实分析")
    async def test_analysis_completes(self, async_client: AsyncClient):
        """Full lifecycle with async client so background task runs."""
        r1 = await async_client.post("/api/analysis", json={"ticker": "600519"})
        job_id = r1.json()["job_id"]

        result = None
        for _ in range(40):
            await asyncio.sleep(0.5)
            r = await async_client.get(f"/api/analysis/{job_id}")
            data = r.json()
            if data["status"] in ("completed", "failed"):
                result = data
                break

        assert result is not None, "Analysis did not complete within 20s"
        assert result["status"] == "completed"
        assert result["progress"] == 100
        res = result["result"]
        assert res["ticker"] == "600519"
        assert res["action"] in ("Buy", "Hold", "Sell")
        assert 0 < res["confidence"] <= 100
        assert res["entry_price"] > 0
        assert res["stop_loss"] < res["entry_price"]
        assert res["take_profit"] > res["entry_price"]

    @pytest.mark.asyncio
    @pytest.mark.skipif(not _HAS_API_KEY, reason="需要DEEPSEEK_API_KEY才能执行真实分析")
    async def test_analysis_agents_progress(self, async_client: AsyncClient):
        """Verify agents_status updates during analysis."""
        r1 = await async_client.post("/api/analysis", json={"ticker": "600519"})
        job_id = r1.json()["job_id"]

        await asyncio.sleep(2)
        r2 = await async_client.get(f"/api/analysis/{job_id}")
        data = r2.json()
        assert "agents_status" in data
        # At least some agents should have started
        assert len(data["agents_status"]) > 0


# ── 8. SSE Stream (async) ─────────────────────────────────────────────────


@pytest.mark.integration
class TestSSEStream:
    @pytest.mark.asyncio
    async def test_stream_receives_events(self, async_client: AsyncClient):
        r1 = await async_client.post("/api/analysis", json={"ticker": "600519"})
        job_id = r1.json()["job_id"]
        await asyncio.sleep(0.5)

        events: list[str] = []
        async with async_client.stream("GET", f"/api/stream/{job_id}") as stream:
            start = time.time()
            async for chunk in stream.aiter_text():
                chunk_parts = chunk.split("\n\n")
                for raw_part in chunk_parts:
                    part = raw_part.strip()
                    if part:
                        events.append(part)
                if time.time() - start > 10:
                    break
                if any("event: done" in e for e in events):
                    break

        assert len(events) > 0, "No SSE events received"
        assert any("progress" in e or "agent_status" in e or "done" in e for e in events)

    def test_stream_not_found(self, sync_client: TestClient):
        assert sync_client.get("/api/stream/nonexistent").status_code == 404


# ── 9. Error Handling ──────────────────────────────────────────────────────


@pytest.mark.integration
class TestErrorHandling:
    def test_analysis_invalid_body(self, sync_client: TestClient):
        assert sync_client.post("/api/analysis", json={}).status_code == 422

    def test_analysis_missing_ticker(self, sync_client: TestClient):
        assert sync_client.post("/api/analysis", json={"fast_mode": True}).status_code == 422
