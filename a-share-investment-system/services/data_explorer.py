"""数据探测引擎 - 源可用性探针 + 数据质量扫描 + 智能降级"""

import logging
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from datetime import datetime
from typing import ClassVar

from services.base import BaseService, ServiceResult
from shared.logging import emit_log

logger = logging.getLogger(__name__)


class DataExplorer(BaseService):
    """数据探测引擎
    职责:
      1. 探针模式: 逐一测试所有数据源各接口是否可用
      2. 质量扫描: 检查 DB 中各字段填充率
      3. 智能降级: 当某数据源不可用时自动切换可用源
      4. 与 DataInitializer 集成:提供 fallback 数据源排序
    """

    DATA_TYPES: ClassVar[list[str]] = [
        "indices",
        "kline",
        "basic",
        "spot",
        "north_flow",
        "hot_stocks",
    ]
    SOURCE_NAMES: ClassVar[list[str]] = [
        "tencent",
        "sina",
        "baostock",
        "efinance",
        "tickflow",
        "akshare",
    ]

    def __init__(self):
        super().__init__()
        self._provider = None
        self._probe_cache = {}  # data_type -> {source: ok/None}
        self._last_probe = 0

    @property
    def provider(self):
        if self._provider is None:
            from providers.market_data import MarketDataProvider

            self._provider = MarketDataProvider()
        return self._provider

    def probe_all(self, force: bool = False) -> ServiceResult:
        """全量探针 - 测试所有数据源连接状态"""
        elapsed = time.perf_counter()
        results = self.provider.test_all_sources()
        elapsed = (time.perf_counter() - elapsed) * 1000

        working = [n for n, r in results.items() if r.get("ok")]
        return self._track(
            ServiceResult.ok(
                data={
                    "probe_time": datetime.now().isoformat(),
                    "sources": results,
                    "working": working,
                    "primary": working[0] if working else "none",
                    "available_count": len(working),
                    "total_count": len(results),
                }
            ),
            elapsed,
        )

    def find_working_source(self, data_type: str) -> str | None:
        """找到第一个可用的数据源"""
        try:
            status = self.provider.get_source_status()
            for name in self.SOURCE_NAMES:
                if name in status and status[name].get("available"):
                    return name
        except Exception as _e:
            logger.debug("find_working_source failed: %s", _e)
        return None

    def get_available_sources(self) -> dict[str, list[str]]:
        """按数据类型返回可用源列表"""
        try:
            raw = self.provider.get_source_status()
            result = {}
            for dtype in self.DATA_TYPES:
                result[dtype] = [
                    n
                    for n, s in raw.items()
                    if s.get("available") and dtype in s.get("methods", [dtype])
                ]
            return result
        except Exception as _e:
            logger.debug("get_available_sources failed: %s", _e)
            return {}

    def scan_data_quality(self) -> ServiceResult:
        """扫描 StockInfo 表各字段填充率"""
        elapsed = time.perf_counter()
        try:
            from sqlalchemy import func

            from shared.models import StockInfo, get_session

            session = get_session()
            total = session.query(func.count(StockInfo.stock_code)).scalar() or 1

            checks = [
                ("latest_price", StockInfo.latest_price, lambda v: v is not None and v > 0),
                ("pe_ratio", StockInfo.pe_ratio, lambda v: v is not None and v != 0),
                ("pb_ratio", StockInfo.pb_ratio, lambda v: v is not None and v != 0),
                ("industry", StockInfo.industry, lambda v: v is not None and v != ""),
                ("total_market_cap", StockInfo.total_market_cap, lambda v: v is not None and v > 0),
                ("ma5", StockInfo.ma5, lambda v: v is not None and v > 0),
                ("rsi_14", StockInfo.rsi_14, lambda v: v is not None and v != 0),
                ("turnover_rate", StockInfo.turnover_rate, lambda v: v is not None and v > 0),
                ("gross_margin", StockInfo.gross_margin, lambda v: v is not None and v != 0),
                ("trend", StockInfo.trend, lambda v: v is not None and v != ""),
            ]
            fields = {}
            for name, col, is_filled in checks:
                try:
                    filled = session.query(func.count(col)).filter(is_filled(col)).scalar() or 0
                except Exception as e:
                    emit_log("WARNING", "data_explorer", f"Error: {str(e)[:100]}")
                    filled = 0
                fields[name] = {
                    "filled": filled,
                    "total": total,
                    "pct": int(filled / total * 100),
                    "missing": total - filled,
                }
            session.close()

            avg_completeness = sum(f["pct"] for f in fields.values()) / len(fields) if fields else 0

            elapsed = (time.perf_counter() - elapsed) * 1000
            return self._track(
                ServiceResult.ok(
                    data={
                        "total_stocks": total,
                        "fields": fields,
                        "avg_completeness": round(avg_completeness, 1),
                        "status": "good"
                        if avg_completeness > 70
                        else ("degraded" if avg_completeness > 30 else "poor"),
                        "scan_time": datetime.now().isoformat(),
                    }
                ),
                elapsed,
            )
        except Exception as e:
            elapsed = (time.perf_counter() - elapsed) * 1000
            return self._track(ServiceResult.error(errors=[str(e)[:200]]), elapsed)

    def scan_cache_status(self) -> ServiceResult:
        """扫描 MarketSnapshot 缓存状态"""
        elapsed = time.perf_counter()
        try:
            from shared.models import MarketSnapshot, get_session

            session = get_session()
            rows = session.query(MarketSnapshot).all()
            session.close()

            snapshots = []
            for r in rows:
                age_hours = (datetime.now() - r.updated_at).total_seconds() / 3600
                snapshots.append(
                    {
                        "type": r.snapshot_type,
                        "updated": r.updated_at.isoformat()[:19],
                        "age_hours": round(age_hours, 1),
                        "stale": age_hours > 24,
                    }
                )
            elapsed = (time.perf_counter() - elapsed) * 1000
            return self._track(
                ServiceResult.ok(
                    data={
                        "snapshots": snapshots,
                        "total": len(snapshots),
                        "stale_count": sum(1 for s in snapshots if s["stale"]),
                    }
                ),
                elapsed,
            )
        except Exception as e:
            elapsed = (time.perf_counter() - elapsed) * 1000
            return self._track(ServiceResult.error(errors=[str(e)[:200]]), elapsed)

    def get_source_chain(self) -> ServiceResult:
        """获取数据源链及健康状态(探针结果缓存30秒)"""
        if time.time() - self._last_probe < 30 and self._probe_cache:
            return ServiceResult.ok(data=self._probe_cache)

        try:
            raw = self.provider.get_source_status()
            chain = []
            for name in self.SOURCE_NAMES:
                info = raw.get(name, {})
                chain.append(
                    {
                        "name": name,
                        "available": info.get("available", False),
                        "latency": round(info.get("latency_ms", 0), 1),
                        "error": info.get("last_error", ""),
                        "methods": list(info.get("methods", set()))
                        if isinstance(info.get("methods"), (set, list))
                        else [],
                    }
                )

            available = [s["name"] for s in chain if s["available"]]
            self._probe_cache = {
                "chain": chain,
                "available_sources": available,
                "primary": available[0] if available else "none",
                "probe_time": datetime.now().isoformat(),
            }
            self._last_probe = time.time()
            return ServiceResult.ok(data=self._probe_cache)
        except Exception as e:
            return ServiceResult.error(errors=[str(e)[:200]])

    def estimate_refresh_time(self, stock_count: int) -> ServiceResult:
        """预估全市场刷新耗时"""
        from services.data_initializer import DataInitializer

        di = DataInitializer()
        test_codes = di.get_hot_stock_pool()[:5]
        if not test_codes:
            return ServiceResult.ok(
                data={
                    "stock_count": stock_count,
                    "estimated_seconds": stock_count * 3,
                    "estimated_minutes": round(stock_count * 3 / 60, 1),
                }
            )

        start = time.perf_counter()
        ok = 0
        from services.trading_calendar import TradingCalendar

        tc = TradingCalendar()

        def _probe_sample():
            nonlocal ok
            for code in test_codes:
                try:
                    basic = self.provider.get_stock_basic(code)
                    df = self.provider.get_stock_kline(code, days=60)
                    if basic or (df is not None and not df.empty):
                        ok += 1
                except Exception as _e:
                    logger.debug("Stock test failed: %s", _e)

        # 采样探针整体限时 5 秒，避免网络不可用时拖垮接口/测试
        try:
            with ThreadPoolExecutor(max_workers=1) as executor:
                executor.submit(_probe_sample).result(timeout=5)
        except FutureTimeoutError:
            logger.warning("estimate_refresh_time probe timed out, using default estimate")

        elapsed = time.perf_counter() - start
        per_stock = elapsed / max(len(test_codes), 1) if ok > 0 else 3.0
        success_rate = ok / max(len(test_codes), 1)

        return ServiceResult.ok(
            data={
                "stock_count": stock_count,
                "estimated_seconds": round(stock_count * per_stock, 1),
                "estimated_minutes": round(stock_count * per_stock / 60, 1),
                "test_sample": len(test_codes),
                "test_success_rate": round(success_rate, 2),
                "per_stock_seconds": round(per_stock, 2),
                "is_trading_day": tc.is_trading_day() if hasattr(tc, "is_trading_day") else False,
            }
        )

    def suggest_fallback_chain(self, data_type: str) -> list[str]:
        """建议某数据类型的最佳降级顺序"""
        preferred = {
            "indices": ["tencent", "akshare", "sina"],
            "kline": ["baostock", "akshare", "efinance", "tickflow"],
            "basic": ["efinance", "akshare", "tickflow"],
            "spot": ["akshare", "efinance"],
            "hot_stocks": ["akshare", "efinance"],
            "north_flow": ["akshare"],
        }
        status = (
            self.provider.get_source_status() if hasattr(self.provider, "get_source_status") else {}
        )
        chain = preferred.get(data_type, self.SOURCE_NAMES)
        result = []
        for name in chain:
            if name in status and status[name].get("available", False):
                result.append(name)
        result.extend(n for n in self.SOURCE_NAMES if n not in result)
        return result
