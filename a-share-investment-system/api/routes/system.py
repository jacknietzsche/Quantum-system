"""系统状态API"""

from fastapi import APIRouter

from api.schemas.routes import SourceHealthOut, SystemStatusOut
from shared.version import VERSION

router = APIRouter()


@router.get("/status", response_model=SystemStatusOut)
def system_status():
    """系统运行状态 — DB连接+数据规模+版本+数据源健康"""
    try:
        from providers.database import health_check

        db = health_check()
        from shared.db_session import db_session

        with db_session() as session:
            from shared.models import KlineCache, StockInfo

            kline_count = session.query(KlineCache).count() if session else 0
            total_stocks = db.get("table_count", 0) or session.query(StockInfo).count()
            stocks_with_data = (
                session.query(StockInfo).filter(StockInfo.latest_price > 0).count()
                if total_stocks > 0
                else 0
            )

        completeness_pct = round(stocks_with_data / max(total_stocks, 1) * 100, 1)

        from providers.market_data import MarketDataProvider

        provider = MarketDataProvider()
        data_sources = provider.get_source_status()
        if data_sources is None:
            data_sources = {}

        return SystemStatusOut(
            status="running",
            version=VERSION,
            database={
                "total_stocks": total_stocks,
                "kline_records": kline_count,
                "disk_mb": db.get("disk_mb", 0),
                "healthy": db.get("status") == "healthy",
                "completeness_pct": completeness_pct,
            },
            data_sources=data_sources,
        )
    except Exception as e:
        return SystemStatusOut(status="error", version=VERSION, error=str(e))


@router.get("/cache-stats")
def cache_stats():
    """数据总线缓存命中统计 — 命中率/API调用/陈旧数据次数"""
    try:
        from services.data_bus import DatabaseBackedDataBus

        bus = DatabaseBackedDataBus()
        return bus.get_stats().data
    except Exception as e:
        return {"error": str(e)}


@router.get("/sources", response_model=SourceHealthOut)
def source_health():
    """数据源健康状态 — 断路器状态 + 延迟测试"""
    from providers.market_data import MarketDataProvider

    provider = MarketDataProvider()

    # Latency test (active probe)
    latency_test = provider.test_all_sources()

    # 断路器状态
    circuit_status = provider.get_source_status()

    working = sum(1 for v in circuit_status.values() if v.get("available", False))
    total = len(circuit_status)

    from providers.source_base import HttpClientPool

    http_pools = HttpClientPool.pool_stats()

    return SourceHealthOut(
        total_sources=total,
        working_sources=working,
        circuit_breakers=circuit_status,
        latency=latency_test,
        http_pools=http_pools,
    )


@router.get("/health")
def health_check():
    """?????? ? ? Docker/Load Balancer ??"""
    from services.monitor import get_monitor

    monitor = get_monitor()
    return monitor.get_health_summary()


@router.get("/monitor/metrics")
def monitor_metrics():
    """??????? ? ???/LLM/?????"""
    from services.monitor import get_monitor

    monitor = get_monitor()
    return monitor.get_health_summary()


@router.get("/monitor/alerts")
def monitor_alerts(limit: int = 50):
    """??????"""
    from services.monitor import get_monitor

    monitor = get_monitor()
    return {"alerts": monitor.get_alerts(limit)}
