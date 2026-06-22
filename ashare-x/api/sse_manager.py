"""SSE连接管理。

设计依据: S14 §14.3, experiments exp8.2-exp8.4。
心跳机制 + 断线重连 + Last-Event-ID恢复。
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from collections.abc import AsyncGenerator
from datetime import datetime


class SSEManager:
    """SSE连接管理器。"""

    def __init__(self):
        self.connections: dict[str, list[asyncio.Queue]] = {}
        self.events: dict[str, list[dict]] = {}  # job_id → events
        self.counter = 0

    def connect(self, job_id: str) -> AsyncGenerator[str, None]:
        """注册SSE连接。"""
        if job_id not in self.connections:
            self.connections[job_id] = []
            self.events[job_id] = []

        queue: asyncio.Queue = asyncio.Queue()
        self.connections[job_id].append(queue)

        async def stream():
            try:
                while True:
                    try:
                        event = await asyncio.wait_for(queue.get(), timeout=30)
                        if event is None:
                            break
                        yield self._format_event(event)
                    except asyncio.TimeoutError:
                        # 心跳
                        yield f": heartbeat {datetime.now().isoformat()}\n\n"
            finally:
                if queue in self.connections.get(job_id, []):
                    self.connections[job_id].remove(queue)

        return stream()

    def send(self, job_id: str, event: dict):
        """发送事件到所有连接。"""
        # 存储事件
        if job_id not in self.events:
            self.events[job_id] = []
        self.counter += 1
        event["_id"] = self.counter
        self.events[job_id].append(event)

        # 发送到所有连接
        if job_id in self.connections:
            for queue in self.connections[job_id]:
                with contextlib.suppress(asyncio.QueueFull):
                    queue.put_nowait(event)

    def get_events_after(self, job_id: str, last_event_id: int = 0) -> list[dict]:
        """获取指定ID之后的事件（用于断线恢复）。"""
        events = self.events.get(job_id, [])
        return [e for e in events if e.get("_id", 0) > last_event_id]

    def disconnect(self, job_id: str):
        """断开连接。"""
        if job_id in self.connections:
            for queue in self.connections[job_id]:
                queue.put_nowait(None)
            del self.connections[job_id]

    def _format_event(self, event: dict) -> str:
        """格式化为SSE格式。"""
        event_type = event.get("type", "message")
        data = json.dumps({k: v for k, v in event.items() if k != "_id"}, ensure_ascii=False)
        return f"event: {event_type}\ndata: {data}\n\n"
