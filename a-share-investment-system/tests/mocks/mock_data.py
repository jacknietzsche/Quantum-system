"""Mock 数据源 — 用于测试和 CI 环境, 零外部依赖"""

from datetime import datetime
from typing import Any, cast


class MockMarketDataProvider:
    """Mock 市场数据提供器 — 返回合理的模拟数据"""

    def __init__(self, overrides: dict | None = None):
        self._overrides = overrides or {}

    def get_indices(self) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            self._overrides.get(
                "indices",
                {
                    "shanghai": {
                        "code": "000001",
                        "name": "上证指数",
                        "price": 3150.5,
                        "change_pct": 0.35,
                    },
                    "shenzhen": {
                        "code": "399001",
                        "name": "深证成指",
                        "price": 10200.8,
                        "change_pct": 0.42,
                    },
                    "chinext": {
                        "code": "399006",
                        "name": "创业板指",
                        "price": 2050.3,
                        "change_pct": -0.15,
                    },
                    "csi300": {
                        "code": "000300",
                        "name": "沪深300",
                        "price": 3750.2,
                        "change_pct": 0.28,
                    },
                    "breadth": {
                        "up": 2800,
                        "down": 2000,
                        "total": 5000,
                        "limit_up": 45,
                        "limit_down": 12,
                    },
                },
            ),
        )

    def get_north_flow(self) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            self._overrides.get(
                "north_flow",
                {
                    "total_net": 5230_000_000,
                    "sh_net": 3100_000_000,
                    "sz_net": 2130_000_000,
                    "date": datetime.now().strftime("%Y-%m-%d"),
                },
            ),
        )

    def get_sector_ranking(self) -> list[dict[str, Any]]:
        return cast(
            list[dict[str, Any]],
            self._overrides.get(
                "sectors",
                [
                    {"name": "半导体", "change_pct": 2.35, "lead_stock": "中芯国际"},
                    {"name": "新能源", "change_pct": 1.82, "lead_stock": "宁德时代"},
                    {"name": "白酒", "change_pct": 1.15, "lead_stock": "贵州茅台"},
                    {"name": "医药", "change_pct": -0.45, "lead_stock": "恒瑞医药"},
                    {"name": "房地产", "change_pct": -1.23, "lead_stock": "万科A"},
                ],
            ),
        )

    def get_stock_quote(self, stock_code: str) -> dict[str, Any]:
        defaults: dict[str, dict[str, Any]] = {
            "600519": {
                "stock_code": "600519",
                "stock_name": "贵州茅台",
                "price": 1680.0,
                "change_pct": 0.52,
                "volume": 3500000,
                "amount": 5880000000,
                "industry": "白酒",
            },
            "000001": {
                "stock_code": "000001",
                "stock_name": "平安银行",
                "price": 11.25,
                "change_pct": -0.35,
                "volume": 45000000,
                "amount": 506250000,
                "industry": "银行",
            },
        }
        return cast(
            dict[str, Any],
            self._overrides.get(
                f"quote_{stock_code}",
                defaults.get(
                    stock_code,
                    {
                        "stock_code": stock_code,
                        "stock_name": f"Mock_{stock_code}",
                        "price": 50.0,
                        "change_pct": 0.0,
                        "volume": 1000000,
                        "amount": 50000000,
                        "industry": "未知",
                    },
                ),
            ),
        )

    def test_all_sources(self) -> dict:
        return {
            "tencent": {"latency_ms": 45, "status": "ok"},
            "sina": {"latency_ms": 62, "status": "ok"},
        }

    def get_source_status(self) -> dict:
        return {
            "tencent": {"state": "closed", "available": True, "failures": 0, "total_calls": 100},
            "sina": {"state": "closed", "available": True, "failures": 0, "total_calls": 50},
        }
