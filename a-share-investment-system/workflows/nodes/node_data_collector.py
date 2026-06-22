"""Node 1.5: 数据预取 — 工作流开始前批量预加载全部持仓+自选数据"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

from workflows.nodes._shared import create_data_bus, logger
from workflows.state import AShareSuperState

# 每股预取字段配置
_PREFETCH_FIELDS = {
    "kline_60": {"method": "get_stock_kline", "kwargs": {"days": 60}},
    "kline_90": {"method": "get_stock_kline", "kwargs": {"days": 90}},
    "stock_basic": {"method": "get_stock_basic", "kwargs": {}},
    "stock_quote": {"method": "get_stock_quote", "kwargs": {}},
}


def node_data_collector(state: AShareSuperState) -> dict:
    """预取所有持仓+自选股的 K线/基本面/行情数据, 预热 DB 缓存"""
    logs = list(state.get("logs", []))
    logs.append(f"[{datetime.now().strftime('%H:%M:%S')}] [数据预取] 开始批量加载...")

    data_bus = create_data_bus()
    portfolio = state.get("portfolio", [])
    watchlist = state.get("watchlist", [])

    # 去重
    all_codes = {}
    for h in portfolio:
        code = h.get("stock_code", "")
        if code:
            all_codes[code] = h.get("stock_name", code)
    for w in watchlist:
        code = w.get("stock_code", "")
        if code and code not in all_codes:
            all_codes[code] = w.get("stock_name", code)

    if not all_codes:
        logs.append(f"[{datetime.now().strftime('%H:%M:%S')}] [数据预取] 无目标, 跳过")
        return {"prefetched_data": {}, "logs": logs}

    prefetched: dict = {}
    # 线程安全计数器 (list 为可变容器, 避免 nonlocal 线程竞争)
    stats = {"success": 0, "failed": 0}

    def _fetch_one(code: str, name: str) -> tuple:
        """预取单只股票所有字段, 利用 DataBus 的 SQLite 缓存层"""
        result = {"stock_code": code, "stock_name": name}
        for field, spec in _PREFETCH_FIELDS.items():
            try:
                fn = getattr(data_bus, spec["method"])
                data = fn(code, **spec["kwargs"]) if spec["kwargs"] else fn(code)
                result[field] = data
                if data is not None and data:
                    stats["success"] += 1
                else:
                    stats["failed"] += 1
            except Exception:
                result[field] = None
                stats["failed"] += 1
        return code, result

    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = {pool.submit(_fetch_one, code, name): code for code, name in all_codes.items()}
        for future in as_completed(futures):
            try:
                code, data = future.result()
                prefetched[code] = data
            except Exception as _e:
                logger.warning("Data fetch failed: %s", _e)

    logs.append(
        f"[{datetime.now().strftime('%H:%M:%S')}] "
        f"[数据预取] {len(prefetched)}只股票完成 "
        f"(成功{stats['success']}, 失败{stats['failed']})"
    )

    return {
        "prefetched_data": prefetched,
        "logs": logs,
    }
