# -*- coding: utf-8 -*-
"""
实验10: 交易日历 + SSE连接生命周期
目标: 验证交易日判断、断线重连、心跳机制
"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import asyncio
import json
import time
from datetime import datetime, timedelta

print("=" * 60)
print("实验10: 交易日历 + SSE连接生命周期")
print("=" * 60)

# ========== 实验10.1: 交易日判断 ==========
print("\n" + "=" * 60)
print("实验10.1: 交易日判断算法")
print("=" * 60)

try:
    # 中国节假日（2026年示例）
    CHINA_HOLIDAYS_2026 = {
        "2026-01-01",  # 元旦
        "2026-01-26", "2026-01-27", "2026-01-28", "2026-01-29", "2026-01-30",  # 春节
        "2026-04-05", "2026-04-06", "2026-04-07",  # 清明
        "2026-05-01", "2026-05-02", "2026-05-03", "2026-05-04", "2026-05-05",  # 劳动节
        "2026-06-19", "2026-06-20", "2026-06-21",  # 端午
        "2026-10-01", "2026-10-02", "2026-10-03", "2026-10-04", "2026-10-05",
        "2026-10-06", "2026-10-07",  # 国庆
    }

    # 调休补班日（周末但开市）
    CHINA_WORKDAYS_2026 = {
        "2026-01-24", "2026-02-07",  # 春节调休
        "2026-04-04",  # 清明调休
        "2026-10-10",  # 国庆调休
    }

    def is_trading_day(date_str: str) -> bool:
        """判断是否为交易日"""
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        weekday = dt.weekday()

        # 调休补班日（周末开市）
        if date_str in CHINA_WORKDAYS_2026:
            return True

        # 法定节假日（不开市）
        if date_str in CHINA_HOLIDAYS_2026:
            return False

        # 周末（不开市）
        if weekday >= 5:
            return False

        return True

    def get_next_trading_day(date_str: str) -> str:
        """获取下一个交易日"""
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        for i in range(1, 10):
            next_dt = dt + timedelta(days=i)
            next_str = next_dt.strftime("%Y-%m-%d")
            if is_trading_day(next_str):
                return next_str
        return date_str

    def get_trading_days_between(start: str, end: str) -> list[str]:
        """获取两个日期之间的所有交易日"""
        days = []
        dt = datetime.strptime(start, "%Y-%m-%d")
        end_dt = datetime.strptime(end, "%Y-%m-%d")
        while dt <= end_dt:
            if is_trading_day(dt.strftime("%Y-%m-%d")):
                days.append(dt.strftime("%Y-%m-%d"))
            dt += timedelta(days=1)
        return days

    # 测试
    test_dates = ["2026-06-13", "2026-06-14", "2026-06-15", "2026-01-26", "2026-01-24"]
    for d in test_dates:
        result = is_trading_day(d)
        weekday = datetime.strptime(d, "%Y-%m-%d").strftime("%A")
        print(f"  {d} ({weekday}): {'交易日' if result else '非交易日'}")

    # 获取一段时间的交易日
    trading_days = get_trading_days_between("2026-06-10", "2026-06-20")
    print(f"\n2026-06-10 ~ 2026-06-20 交易日: {len(trading_days)}天")
    print(f"  {trading_days}")

    print("[PASS] 交易日判断算法成功")
except Exception as e:
    print(f"[FAIL] {e}")

# ========== 实验10.2: SSE心跳机制 ==========
print("\n" + "=" * 60)
print("实验10.2: SSE心跳机制")
print("=" * 60)

try:
    class SSEHeartbeat:
        """SSE心跳管理器"""

        def __init__(self, interval: int = 15):
            self.interval = interval  # 心跳间隔（秒）
            self.last_heartbeat = time.time()

        def should_send_heartbeat(self) -> bool:
            """检查是否应该发送心跳"""
            if time.time() - self.last_heartbeat >= self.interval:
                self.last_heartbeat = time.time()
                return True
            return False

        def format_heartbeat(self) -> str:
            """格式化心跳事件"""
            return f": heartbeat {datetime.now().isoformat()}\n\n"

    # 测试
    heartbeat = SSEHeartbeat(interval=0.1)  # 实验用短间隔

    # 模拟发送
    events_sent = 0
    for i in range(5):
        time.sleep(0.05)
        if heartbeat.should_send_heartbeat():
            events_sent += 1

    print(f"心跳间隔: {heartbeat.interval}秒")
    print(f"发送心跳: {events_sent}次")
    print("[PASS] SSE心跳机制成功")
except Exception as e:
    print(f"[FAIL] {e}")

# ========== 实验10.3: SSE断线重连 ==========
print("\n" + "=" * 60)
print("实验10.3: SSE断线重连")
print("=" * 60)

try:
    class SSEReconnect:
        """SSE断线重连管理"""

        def __init__(self, max_retries: int = 5, base_delay: float = 1.0):
            self.max_retries = max_retries
            self.base_delay = base_delay
            self.retry_count = 0
            self.last_event_id = None

        def get_retry_delay(self) -> float:
            """计算重试延迟（指数退避）"""
            delay = self.base_delay * (2 ** self.retry_count)
            return min(delay, 30.0)

        def on_connect(self):
            """连接成功"""
            self.retry_count = 0

        def on_disconnect(self):
            """连接断开"""
            self.retry_count += 1

        def should_retry(self) -> bool:
            """是否应该重试"""
            return self.retry_count <= self.max_retries

        def get_reconnect_headers(self) -> dict:
            """获取重连请求头"""
            headers = {}
            if self.last_event_id:
                headers["Last-Event-ID"] = self.last_event_id
            return headers

        def on_event(self, event_id: str):
            """收到事件时更新last_event_id"""
            self.last_event_id = event_id

    # 测试
    reconnect = SSEReconnect(max_retries=5, base_delay=0.01)

    # 模拟连接成功
    reconnect.on_connect()
    print(f"连接成功, retry_count={reconnect.retry_count}")

    # 模拟事件
    for i in range(3):
        reconnect.on_event(f"event-{i}")
    print(f"收到事件, last_event_id={reconnect.last_event_id}")

    # 模拟断线
    reconnect.on_disconnect()
    print(f"断线, retry_count={reconnect.retry_count}, should_retry={reconnect.should_retry()}")

    # 模拟重连延迟
    delays = []
    for i in range(5):
        reconnect.on_disconnect()
        delay = reconnect.get_retry_delay()
        delays.append(delay)
        print(f"  重试{i+1}: 延迟{delay:.2f}秒")

    print(f"重连延迟: {delays}")
    print("[PASS] SSE断线重连成功")
except Exception as e:
    print(f"[FAIL] {e}")

# ========== 实验10.4: SSE Last-Event-ID恢复 ==========
print("\n" + "=" * 60)
print("实验10.4: SSE Last-Event-ID恢复")
print("=" * 60)

try:
    class SSEEventStore:
        """事件存储，支持Last-Event-ID恢复"""

        def __init__(self, max_events: int = 1000):
            self.events = {}
            self.max_events = max_events
            self.counter = 0

        def store(self, job_id: str, event: dict) -> str:
            """存储事件，返回事件ID"""
            self.counter += 1
            event_id = f"{job_id}:{self.counter}"
            self.events[event_id] = event

            # 清理旧事件
            if len(self.events) > self.max_events:
                oldest_keys = list(self.events.keys())[:len(self.events) - self.max_events]
                for k in oldest_keys:
                    del self.events[k]

            return event_id

        def get_events_after(self, job_id: str, last_event_id: str = None) -> list[dict]:
            """获取指定ID之后的事件"""
            if not last_event_id:
                return []

            events = []
            found = False
            for event_id, event in self.events.items():
                if found:
                    events.append(event)
                if event_id == last_event_id:
                    found = True

            return events

    # 测试
    store = SSEEventStore()

    # 存储事件
    for i in range(5):
        event_id = store.store("job-1", {"type": "test", "data": f"event-{i}"})
        print(f"  存储: {event_id}")

    # 模拟断线恢复（从event-3之后恢复）
    recovered = store.get_events_after("job-1", "job-1:3")
    print(f"\n从job-1:3恢复: {len(recovered)}个事件")
    for e in recovered:
        print(f"  {e}")

    print("[PASS] SSE Last-Event-ID恢复成功")
except Exception as e:
    print(f"[FAIL] {e}")

# ========== 实验10.5: 重复分析保护 ==========
print("\n" + "=" * 60)
print("实验10.5: 重复分析保护")
print("=" * 60)

try:
    class AnalysisLock:
        """分析任务锁，防止重复提交"""

        def __init__(self):
            self.locks = {}  # ticker → job_id
            self.jobs = {}   # job_id → status

        def try_lock(self, ticker: str, job_id: str) -> tuple[bool, str]:
            """
            尝试锁定股票
            返回: (成功, 消息)
            """
            if ticker in self.locks:
                existing_job = self.locks[ticker]
                status = self.jobs.get(existing_job, "unknown")
                if status in ("pending", "running"):
                    return False, f"股票{ticker}正在分析中(job_id={existing_job})"

            self.locks[ticker] = job_id
            self.jobs[job_id] = "running"
            return True, "锁定成功"

        def release(self, ticker: str, job_id: str):
            """释放锁"""
            if self.locks.get(ticker) == job_id:
                del self.locks[ticker]
            self.jobs[job_id] = "completed"

        def get_status(self, ticker: str) -> str | None:
            """获取股票当前分析状态"""
            job_id = self.locks.get(ticker)
            return self.jobs.get(job_id) if job_id else None

    # 测试
    lock = AnalysisLock()

    # 首次提交
    ok, msg = lock.try_lock("600519", "job-001")
    print(f"首次提交600519: ok={ok}, msg={msg}")

    # 重复提交
    ok, msg = lock.try_lock("600519", "job-002")
    print(f"重复提交600519: ok={ok}, msg={msg}")

    # 其他股票
    ok, msg = lock.try_lock("000858", "job-003")
    print(f"提交000858: ok={ok}, msg={msg}")

    # 完成后释放
    lock.release("600519", "job-001")
    status = lock.get_status("600519")
    print(f"释放后状态: {status}")

    # 再次提交
    ok, msg = lock.try_lock("600519", "job-004")
    print(f"释放后再次提交: ok={ok}, msg={msg}")

    print("[PASS] 重复分析保护成功")
except Exception as e:
    print(f"[FAIL] {e}")

print("\n" + "=" * 60)
print("实验10完成")
print("=" * 60)
