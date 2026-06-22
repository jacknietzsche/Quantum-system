"""数据管理路由。

通过DatabaseFirstDataBus获取数据（数据库优先 → API → 存库 → 返回）。
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger("ashare-x.api.data")

router = APIRouter(prefix="/api/data", tags=["data"])


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
    """查询K线数据（数据库优先 → API → 存库 → 返回）。"""
    try:
        from providers.data_bus import DatabaseFirstDataBus

        bus = DatabaseFirstDataBus()
        kline_data = bus.get_kline(code, days=days)

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
    except Exception as e:
        logger.error("获取K线失败: %s", e)
        raise HTTPException(500, str(e)) from e


@router.post("/refresh")
async def refresh_data(source: str | None = None, code: str | None = None):
    """触发数据刷新（调用updater更新数据库）。"""
    try:
        from services.updater import DailyUpdater

        updater = DailyUpdater()
        if code:
            # 更新单只股票
            stats = updater.update_single_stock(code)
            return {"status": "ok", "code": code, "stats": stats}
        # 更新所有活跃股票
        stats = dict(updater.run_daily_update())
        return {"status": "ok", "stats": stats}
    except Exception as e:
        logger.error("数据刷新失败: %s", e)
        return {"status": "error", "message": str(e)}


@router.post("/incremental-refresh")
async def incremental_refresh(days: int = 60):
    """
    增量刷新近N日数据。

    逐股检查K线数据完整性:
    - 数据完整的跳过（已有交易日数 >= 预期的80%）
    - 不完整的补充获取
    """
    try:
        from services.updater import DailyUpdater

        updater = DailyUpdater()
        stats = updater.incremental_refresh(days=days)
        return {"status": "ok", "stats": stats}
    except Exception as e:
        logger.error("增量刷新失败: %s", e)
        return {"status": "error", "message": str(e)}


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

    # 检查数据源适配器
    adapter_configs = [
        ("腾讯行情", "providers.sources.tencent", "TencentAdapter"),
        ("新浪行情", "providers.sources.sina", "SinaAdapter"),
        ("AKShare", "providers.sources.akshare_src", "AKShareAdapter"),
        ("yfinance", "providers.sources.yfinance_src", "YFinanceAdapter"),
    ]

    for name, module_path, class_name in adapter_configs:
        try:
            import importlib

            mod = importlib.import_module(module_path)
            adapter_cls = getattr(mod, class_name)
            adapter = adapter_cls()
            healthy = adapter.test_connect()
            sources.append(
                DataSourceStatus(
                    name=name,
                    status="healthy" if healthy else "warning",
                    last_update="N/A",
                    record_count=0,
                )
            )
        except Exception:
            sources.append(
                DataSourceStatus(
                    name=name, status="error", last_update="N/A", record_count=0
                )
            )

    overall_status = "healthy" if all(s.status == "healthy" for s in sources) else "warning"
    message = "数据源连接正常" if overall_status == "healthy" else "部分数据源不可用"

    return DataHealthResponse(status=overall_status, message=message, sources=sources)
