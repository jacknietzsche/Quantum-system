"""Phase 6 API层测试。"""

from __future__ import annotations

from api.sse_manager import SSEManager


class TestSSEManager:
    def test_send_and_get_events(self):
        mgr = SSEManager()
        mgr.send("job-1", {"type": "test", "data": "hello"})
        events = mgr.get_events_after("job-1")
        assert len(events) == 1
        assert events[0]["type"] == "test"

    def test_get_events_after_id(self):
        mgr = SSEManager()
        mgr.send("job-1", {"type": "a"})
        mgr.send("job-1", {"type": "b"})
        mgr.send("job-1", {"type": "c"})
        events = mgr.get_events_after("job-1", last_event_id=1)
        assert len(events) == 2

    def test_format_event(self):
        mgr = SSEManager()
        event = {"type": "agent.status", "agent": "market_analyst", "status": "completed"}
        formatted = mgr._format_event(event)
        assert "event: agent.status" in formatted
        assert "data:" in formatted
