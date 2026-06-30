"""数据管理路由。

通过DatabaseFirstDataBus获取数据（数据库优先 → API → 存库 → 返回）。
数据刷新为异步job模式，避免长耗时HTTP超时。
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger("ashare-x.api.data")

router = APIRouter(prefix="/api/data", tags=["data"])

# ── 异步job存储 ───────────────────────────────────────────────────────
_refresh_jobs: dict[str, dict] = {}
_refresh_tasks: set[asyncio.Task] = set()


class KlineItem(BaseModel):
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: float


class KlineResponse(BaseModel):
    code: str
    kline: list[KlineItem]
    total: int


class DataSourceStatus(BaseModel):
    name: str
    status: str  # healthy / warning / error
    last_update: str
    record_count: int


class DataStats(BaseModel):
    kline_count: int
    stock_count: int
    db_size: str


class DataHealthResponse(BaseModel):
    status: str
    message: str
    sources: list[DataSourceStatus]


@router.get("/kline", response_model=KlineResponse)
async def get_kline(code: str, days: int = 30):
    """查询K线数据（数据库优先 → API → 存库 → 返回）。

    加 8s 超时保护，避免数据过期时网络回源卡死。
    超时后降级返回数据库中的旧数据。
    """
    from providers.data_bus import DatabaseFirstDataBus

    loop = asyncio.get_event_loop()
    bus = DatabaseFirstDataBus()

    # 主路径：带超时的完整查询（DB → 增量更新 → 返回）
    kline_data = None
    try:
        kline_data = await asyncio.wait_for(
            loop.run_in_executor(None, bus.get_kline, code, days),
            timeout=8.0,
        )
    except (asyncio.TimeoutError, TimeoutError):
        logger.warning("K线查询超时 code=%s, 降级返回数据库旧数据", code)
        # 降级：直接查 DB，不触发网络回源
        try:
            kline_data = bus._query_kline(code, days)
        except Exception:
            kline_data = None
    except Exception as e:
        logger.error("获取K线失败: %s", e)
        raise HTTPException(500, str(e)) from e

    if not kline_data:
        return KlineResponse(code=code, kline=[], total=0)

    kline = [
        KlineItem(
            date=r["trade_date"],
            open=r.get("open", 0),
            high=r.get("high", 0),
            low=r.get("low", 0),
            close=r.get("close", 0),
            volume=r.get("volume", 0),
        )
        for r in kline_data
    ]
    return KlineResponse(code=code, kline=kline, total=len(kline))


@router.post("/refresh")
async def refresh_data(source: str | None = None, code: str | None = None):
    """启动数据刷新（异步job，立即返回job_id）。"""
    job_id = str(uuid.uuid4())[:8]
    _refresh_jobs[job_id] = {
        "job_id": job_id,
        "status": "running",
        "code": code,
        "result": None,
        "error": None,
    }
    task = asyncio.create_task(_run_refresh(job_id, code))
    _refresh_tasks.add(task)
    task.add_done_callback(_refresh_tasks.discard)
    return {"job_id": job_id, "status": "running", "code": code}


@router.get("/refresh/{job_id}")
async def get_refresh_status(job_id: str):
    """查询数据刷新job状态。"""
    if job_id not in _refresh_jobs:
        raise HTTPException(404, "Job not found")
    return _refresh_jobs[job_id]


async def _run_refresh(job_id: str, code: str | None):
    """后台执行数据刷新。"""
    job = _refresh_jobs[job_id]
    try:
        from services.updater import DailyUpdater

        loop = asyncio.get_event_loop()
        updater = DailyUpdater()
        if code:
            stats = await loop.run_in_executor(None, updater.update_single_stock, code)
        else:
            stats = dict(await loop.run_in_executor(None, updater.run_daily_update))
        job["status"] = "completed"
        job["result"] = stats
    except Exception as e:
        logger.error("数据刷新失败: %s", e)
        job["status"] = "failed"
        job["error"] = str(e)


@router.post("/incremental-refresh")
async def incremental_refresh(days: int = 60):
    """启动增量刷新（异步job，立即返回job_id）。"""
    job_id = str(uuid.uuid4())[:8]
    _refresh_jobs[job_id] = {
        "job_id": job_id,
        "status": "running",
        "code": None,
        "result": None,
        "error": None,
    }
    task = asyncio.create_task(_run_incremental(job_id, days))
    _refresh_tasks.add(task)
    task.add_done_callback(_refresh_tasks.discard)
    return {"job_id": job_id, "status": "running"}


async def _run_incremental(job_id: str, days: int):
    """后台执行增量刷新。"""
    job = _refresh_jobs[job_id]
    try:
        from services.updater import DailyUpdater

        loop = asyncio.get_event_loop()
        updater = DailyUpdater()
        stats = await loop.run_in_executor(None, updater.incremental_refresh, days)
        job["status"] = "completed"
        job["result"] = stats
    except Exception as e:
        logger.error("增量刷新失败: %s", e)
        job["status"] = "failed"
        job["error"] = str(e)


@router.get("/stats", response_model=DataStats)
async def get_data_stats():
    """获取数据统计。"""
    try:
        import sqlite3

        from providers.data_bus import DatabaseFirstDataBus

        bus = DatabaseFirstDataBus()
        db_path = Path(bus.db_path)

        if not db_path.exists():
            return DataStats(kline_count=0, stock_count=0, db_size="0 MB")

        conn = sqlite3.connect(str(db_path))
        try:
            kline_count = conn.execute("SELECT COUNT(*) FROM kline_daily").fetchone()[0]
            stock_count = conn.execute(
                "SELECT COUNT(DISTINCT stock_code) FROM kline_daily"
            ).fetchone()[0]
        except Exception:
            kline_count = 0
            stock_count = 0
        finally:
            conn.close()

        db_size_bytes = db_path.stat().st_size
        db_size = f"{db_size_bytes / 1024 / 1024:.1f} MB"

        return DataStats(kline_count=kline_count, stock_count=stock_count, db_size=db_size)
    except Exception as e:
        logger.error("获取数据统计失败: %s", e)
        return DataStats(kline_count=0, stock_count=0, db_size="0 MB")


@router.get("/health", response_model=DataHealthResponse)
async def check_data_health():
    """检查数据源健康状态。"""
    sources: list[DataSourceStatus] = []

    # 检查数据库
    try:
        from providers.data_bus import DatabaseFirstDataBus

        bus = DatabaseFirstDataBus()
        db_path = Path(bus.db_path)
        db_healthy = db_path.exists()

        import sqlite3

        if db_healthy:
            conn = sqlite3.connect(str(db_path))
            try:
                kline_count = conn.execute("SELECT COUNT(*) FROM kline_daily").fetchone()[0]
                stock_count = conn.execute(
                    "SELECT COUNT(*) FROM stock_info"
                ).fetchone()[0]
            except Exception:
                kline_count = 0
                stock_count = 0
            finally:
                conn.close()
        else:
            kline_count = 0
            stock_count = 0

        sources.append(
            DataSourceStatus(
                name="SQLite数据库",
                status="healthy" if db_healthy else "error",
                last_update="N/A",
                record_count=kline_count + stock_count,
            )
        )
    except Exception:
        sources.append(
            DataSourceStatus(
                name="SQLite数据库", status="error", last_update="N/A", record_count=0
            )
        )

    # 检查数据源适配器（并行 + 超时，避免长时间阻塞）
    import importlib

    adapter_configs = [
        ("腾讯行情", "providers.sources.tencent", "TencentAdapter"),
        ("新浪行情", "providers.sources.sina", "SinaAdapter"),
        ("AKShare", "providers.sources.akshare_src", "AKShareAdapter"),
        ("yfinance", "providers.sources.yfinance_src", "YFinanceAdapter"),
    ]

    async def _check_adapter(
        name: str, module_path: str, class_name: str
    ) -> DataSourceStatus:
        """单个 adapter 健康检查，初始化+测试总超时 3s。"""
        loop = asyncio.get_event_loop()

        def _init_and_test() -> bool:
            mod = importlib.import_module(module_path)
            adapter_cls = getattr(mod, class_name)
            adapter = adapter_cls()
            return adapter.test_connect()

        try:
            healthy = await asyncio.wait_for(
                loop.run_in_executor(None, _init_and_test),
                timeout=3.0,
            )
        except (asyncio.TimeoutError, TimeoutError):
            return DataSourceStatus(
                name=name, status="warning", last_update="N/A", record_count=0
            )
        except Exception:
            return DataSourceStatus(
                name=name, status="error", last_update="N/A", record_count=0
            )
        return DataSourceStatus(
            name=name,
            status="healthy" if healthy else "warning",
            last_update="N/A",
            record_count=0,
        )

    adapter_results = await asyncio.gather(
        *[_check_adapter(n, mp, cn) for n, mp, cn in adapter_configs]
    )
    sources.extend(adapter_results)

    overall_status = "healthy" if all(s.status == "healthy" for s in sources) else "warning"
    message = "数据源连接正常" if overall_status == "healthy" else "部分数据源不可用"

    return DataHealthResponse(status=overall_status, message=message, sources=sources)
