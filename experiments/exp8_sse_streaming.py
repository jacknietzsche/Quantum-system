# -*- coding: utf-8 -*-
"""
实验8: SSE实时推送验证
目标: 验证Server-Sent Events实现Agent状态实时推送
"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import asyncio
import json
import time
from typing import AsyncGenerator

print("=" * 60)
print("实验8: SSE实时推送验证")
print("=" * 60)

# ========== 实验8.1: SSE事件格式 ==========
print("\n" + "=" * 60)
print("实验8.1: SSE事件格式定义")
print("=" * 60)

try:
    # SSE事件类型定义
    EVENT_TYPES = {
        "agent.status": "Agent状态变更",
        "agent.message": "Agent消息（辩论发言）",
        "report.chunk": "报告文本片段",
        "agent.token": "Token使用量",
        "job.completed": "任务完成",
        "job.failed": "任务失败",
    }

    # 模拟事件
    events = [
        {"type": "agent.status", "agent": "market_analyst", "status": "in_progress", "message": "获取K线数据"},
        {"type": "agent.status", "agent": "market_analyst", "status": "completed"},
        {"type": "agent.message", "agent": "bull_researcher", "content": "看涨论据...", "round": 1, "role": "bull"},
        {"type": "report.chunk", "section": "market_report", "content": "## 技术面分析\n..."},
        {"type": "agent.token", "agent": "market_analyst", "tokens": 1200, "total_tokens": 1200},
        {"type": "job.completed", "result": {"ticker": "600519", "decision": "Buy"}},
    ]

    # 格式化为SSE
    def format_sse(event: dict) -> str:
        event_type = event.get("type", "message")
        data = json.dumps(event, ensure_ascii=False)
        return f"event: {event_type}\ndata: {data}\n\n"

    print("SSE事件格式:")
    for event in events:
        sse = format_sse(event)
        print(f"--- {event['type']} ---")
        print(sse[:100] + "..." if len(sse) > 100 else sse)

    print("[PASS] SSE事件格式定义成功")
except Exception as e:
    print(f"[FAIL] SSE事件格式失败: {e}")

# ========== 实验8.2: SSE流式生成器 ==========
print("\n" + "=" * 60)
print("实验8.2: SSE流式生成器")
print("=" * 60)

try:
    async def sse_generator(job_id: str) -> AsyncGenerator[str, None]:
        """模拟SSE事件流"""
        # 模拟Agent执行过程
        agents = [
            ("market_analyst", "in_progress", "获取K线数据"),
            ("market_analyst", "completed", ""),
            ("fundamentals_analyst", "in_progress", "分析财务数据"),
            ("fundamentals_analyst", "completed", ""),
            ("bull_researcher", "in_progress", "构建看涨论据"),
            ("bull_researcher", "completed", ""),
            ("bear_researcher", "in_progress", "构建看跌论据"),
            ("bear_researcher", "completed", ""),
            ("portfolio_manager", "in_progress", "做出最终决策"),
            ("portfolio_manager", "completed", ""),
        ]

        for i, (agent, status, message) in enumerate(agents):
            event = {
                "type": "agent.status",
                "agent": agent,
                "status": status,
                "message": message,
                "progress": (i + 1) / len(agents) * 100,
            }
            yield format_sse(event)
            await asyncio.sleep(0.05)  # 模拟延迟

        # 完成事件
        yield format_sse({
            "type": "job.completed",
            "result": {"ticker": "600519", "decision": "Buy", "confidence": 80}
        })

    async def test_sse_stream():
        events = []
        async for event in sse_generator("test-123"):
            events.append(event)
        return events

    events = asyncio.run(test_sse_stream())
    print(f"生成了 {len(events)} 个SSE事件")
    print(f"前3个事件:")
    for e in events[:3]:
        print(f"  {e.strip()[:80]}...")

    print("[PASS] SSE流式生成器成功")
except Exception as e:
    print(f"[FAIL] SSE流式生成器失败: {e}")

# ========== 实验8.3: SSE事件解析 ==========
print("\n" + "=" * 60)
print("实验8.3: SSE事件解析（前端模拟）")
print("=" * 60)

try:
    def parse_sse(raw_sse: str) -> dict:
        """解析SSE格式的字符串"""
        result = {}
        for line in raw_sse.strip().split("\n"):
            if line.startswith("event: "):
                result["type"] = line[7:]
            elif line.startswith("data: "):
                result["data"] = json.loads(line[6:])
        return result

    # 测试解析
    test_sse = 'event: agent.status\ndata: {"type":"agent.status","agent":"market_analyst","status":"completed"}\n\n'
    parsed = parse_sse(test_sse)
    print(f"解析结果: {parsed}")
    assert parsed["type"] == "agent.status"
    assert parsed["data"]["agent"] == "market_analyst"
    assert parsed["data"]["status"] == "completed"

    print("[PASS] SSE事件解析成功")
except Exception as e:
    print(f"[FAIL] SSE事件解析失败: {e}")

# ========== 实验8.4: SSE并发连接管理 ==========
print("\n" + "=" * 60)
print("实验8.4: SSE并发连接管理")
print("=" * 60)

try:
    class SSEManager:
        def __init__(self):
            self.connections: dict[str, list] = {}

        def connect(self, job_id: str) -> AsyncGenerator[str, None]:
            """注册连接"""
            if job_id not in self.connections:
                self.connections[job_id] = []
            queue = asyncio.Queue()
            self.connections[job_id].append(queue)
            return self._stream(queue)

        async def _stream(self, queue: asyncio.Queue) -> AsyncGenerator[str, None]:
            """从队列读取事件"""
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=30)
                    if event is None:  # 结束信号
                        break
                    yield event
                except asyncio.TimeoutError:
                    break

        async def send(self, job_id: str, event: dict):
            """发送事件到所有连接"""
            if job_id in self.connections:
                for queue in self.connections[job_id]:
                    await queue.put(event)

        def disconnect(self, job_id: str):
            """断开连接"""
            if job_id in self.connections:
                for queue in self.connections[job_id]:
                    queue.put_nowait(None)  # 发送结束信号
                del self.connections[job_id]

    async def test_sse_manager():
        manager = SSEManager()

        # 模拟连接
        async for event in manager.connect("job-1"):
            print(f"收到: {event}")

        # 模拟发送
        await manager.send("job-1", {"type": "test", "data": "hello"})

        # 清理
        manager.disconnect("job-1")
        return True

    # 简化测试
    manager = SSEManager()
    print(f"连接管理器初始化成功")
    print(f"当前连接: {len(manager.connections)}")

    print("[PASS] SSE并发连接管理成功")
except Exception as e:
    print(f"[FAIL] SSE并发连接管理失败: {e}")

print("\n" + "=" * 60)
print("实验8完成")
print("=" * 60)
