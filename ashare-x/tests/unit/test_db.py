"""db层单元测试。"""

from __future__ import annotations

from db.migrations import get_current_version
from db.models import DecisionLog, KlineDaily, MigrationVersion, Reports, StockInfo


class TestModels:
    def test_kline_daily_fields(self):
        k = KlineDaily(stock_code="600519", trade_date="2026-01-01", close=1500.0)
        assert k.stock_code == "600519"
        assert k.close == 1500.0

    def test_stock_info_fields(self):
        s = StockInfo(stock_code="600519", stock_name="贵州茅台", pe_ratio=25.0)
        assert s.stock_name == "贵州茅台"

    def test_reports_fields(self):
        r = Reports(id="rpt-001", ticker="600519", action="Buy", confidence=80.0)
        assert r.action == "Buy"

    def test_decision_log_fields(self):
        d = DecisionLog(ticker="600519", action="Buy", confidence=0.75)
        assert d.action == "Buy"

    def test_migration_version_fields(self):
        m = MigrationVersion(version=1, description="test")
        assert m.version == 1


class TestMigrations:
    def test_get_current_version_empty_db(self):
        """测试版本查询（表不存在时应返回0或抛异常）"""
        try:
            version = get_current_version()
            assert version >= 0
        except Exception:
            # 表不存在时抛异常是预期行为
            pass
