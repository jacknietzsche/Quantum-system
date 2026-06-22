# -*- coding: utf-8 -*-
"""
实验11: 报告存储 + 数据源版本兼容
目标: 验证报告存储格式、数据源API变动应对
"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import json
import sqlite3
from pathlib import Path
from datetime import datetime

print("=" * 60)
print("实验11: 报告存储 + 数据源版本兼容")
print("=" * 60)

# ========== 实验11.1: 报告存储格式 ==========
print("\n" + "=" * 60)
print("实验11.1: 报告存储格式（JSON + Markdown）")
print("=" * 60)

try:
    # 报告存储方案: SQLite存结构化数据 + 文件系统存Markdown报告

    db_path = Path("experiments/test_reports.db")
    conn = sqlite3.connect(str(db_path))

    # 创建报告表
    conn.execute("""
        CREATE TABLE IF NOT EXISTS reports (
            id TEXT PRIMARY KEY,
            ticker TEXT NOT NULL,
            stock_name TEXT,
            date TEXT NOT NULL,
            action TEXT,
            confidence REAL,
            entry_price REAL,
            stop_loss REAL,
            take_profit REAL,
            position_pct REAL,
            token_usage INTEGER,
            execution_time_seconds REAL,
            agents_executed TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS report_content (
            report_id TEXT PRIMARY KEY,
            market_report TEXT,
            fundamentals_report TEXT,
            news_report TEXT,
            sentiment_report TEXT,
            debate_summary TEXT,
            full_report_md TEXT,
            FOREIGN KEY (report_id) REFERENCES reports(id)
        )
    """)

    # 插入测试报告
    report_id = "rpt-2026-06-14-600519"
    conn.execute("""
        INSERT INTO reports (id, ticker, stock_name, date, action, confidence,
            entry_price, stop_loss, take_profit, position_pct,
            token_usage, execution_time_seconds, agents_executed)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (report_id, "600519", "贵州茅台", "2026-06-14", "Buy", 80.0,
          1500.0, 1425.0, 1650.0, 5.0, 17500, 180.0,
          json.dumps(["market", "fundamentals", "news", "sentiment",
                       "bull", "bear", "research_mgr", "trader",
                       "aggressive", "conservative", "neutral", "portfolio_mgr"])))

    conn.execute("""
        INSERT INTO report_content (report_id, market_report, full_report_md)
        VALUES (?, ?, ?)
    """, (report_id, "技术面看涨，MA5>MA20", "# 600519 贵州茅台 分析报告\n\n## 技术面\n..."))

    conn.commit()

    # 查询报告
    report = pd.read_sql_query("""
        SELECT r.*, rc.full_report_md
        FROM reports r
        LEFT JOIN report_content rc ON r.id = rc.report_id
        WHERE r.id = ?
    """, conn, params=(report_id,))

    print(f"报告存储:")
    print(f"  ID: {report['id'].iloc[0]}")
    print(f"  股票: {report['ticker'].iloc[0]} {report['stock_name'].iloc[0]}")
    print(f"  决策: {report['action'].iloc[0]} (置信度{report['confidence'].iloc[0]}%)")
    print(f"  入场价: {report['entry_price'].iloc[0]}")
    print(f"  止损: {report['stop_loss'].iloc[0]}")
    print(f"  止盈: {report['take_profit'].iloc[0]}")
    print(f"  仓位: {report['position_pct'].iloc[0]}%")
    print(f"  Token: {report['token_usage'].iloc[0]}")
    print(f"  耗时: {report['execution_time_seconds'].iloc[0]}秒")

    # 查询最近报告列表
    recent = pd.read_sql_query("""
        SELECT id, ticker, stock_name, date, action, confidence
        FROM reports
        ORDER BY created_at DESC
        LIMIT 10
    """, conn)
    print(f"\n最近报告: {len(recent)}条")
    print(recent.to_string())

    conn.close()
    db_path.unlink()
    print("\n[PASS] 报告存储格式成功")
except Exception as e:
    print(f"[FAIL] {e}")

# ========== 实验11.2: 数据源版本兼容层 ==========
print("\n" + "=" * 60)
print("实验11.2: 数据源版本兼容层")
print("=" * 60)

try:
    # AKShare经常更新API，需要版本兼容层

    class DataProviderAdapter:
        """数据源适配器基类（带版本兼容）"""

        def __init__(self, name: str):
            self.name = name
            self.version = "1.0.0"
            self._function_map = {}  # 旧函数名 → 新函数名

        def register_compat(self, old_name: str, new_name: str):
            """注册兼容映射"""
            self._function_map[old_name] = new_name

        def call(self, func_name: str, *args, **kwargs):
            """调用函数（自动兼容旧版本）"""
            # 检查兼容映射
            actual_name = self._function_map.get(func_name, func_name)

            # 模拟调用
            return {
                "provider": self.name,
                "version": self.version,
                "function": actual_name,
                "original": func_name,
                "compat_used": func_name != actual_name,
                "status": "ok"
            }

    # 测试
    adapter = DataProviderAdapter("akshare")
    adapter.version = "1.15.0"

    # 注册兼容映射（旧函数名→新函数名）
    adapter.register_compat("stock_zh_a_spot_em", "stock_zh_a_spot")
    adapter.register_compat("stock_hsgt_north_net_flow_in", "stock_hsgt_north_net_flow_in_em")

    # 调用新函数
    result1 = adapter.call("stock_zh_a_spot")
    print(f"调用新函数: {result1}")
    assert not result1["compat_used"]

    # 调用旧函数（自动兼容）
    result2 = adapter.call("stock_zh_a_spot_em")
    print(f"调用旧函数: {result2}")
    assert result2["compat_used"]
    assert result2["function"] == "stock_zh_a_spot"

    print("[PASS] 数据源版本兼容层成功")
except Exception as e:
    print(f"[FAIL] {e}")

# ========== 实验11.3: 数据源健康检查 ==========
print("\n" + "=" * 60)
print("实验11.3: 数据源健康检查")
print("=" * 60)

try:
    import time

    class DataProviderHealth:
        """数据源健康检查"""

        def __init__(self):
            self.providers = {}

        def check(self, name: str, check_fn) -> dict:
            """检查数据源健康状态"""
            start = time.time()
            try:
                result = check_fn()
                latency = (time.time() - start) * 1000
                self.providers[name] = {
                    "status": "healthy",
                    "latency_ms": round(latency, 1),
                    "last_check": datetime.now().isoformat(),
                    "error": None
                }
            except Exception as e:
                latency = (time.time() - start) * 1000
                self.providers[name] = {
                    "status": "unhealthy",
                    "latency_ms": round(latency, 1),
                    "last_check": datetime.now().isoformat(),
                    "error": str(e)
                }
            return self.providers[name]

        def get_status(self) -> dict:
            """获取所有数据源状态"""
            return self.providers

        def get_healthy_providers(self) -> list[str]:
            """获取健康的数据源列表"""
            return [name for name, info in self.providers.items()
                    if info["status"] == "healthy"]

    # 测试
    health = DataProviderHealth()

    # 模拟健康检查
    health.check("tencent", lambda: "ok")
    health.check("sina", lambda: "ok")
    health.check("akshare", lambda: 1/0)  # 模拟失败

    status = health.get_status()
    print("数据源状态:")
    for name, info in status.items():
        print(f"  {name}: {info['status']} ({info['latency_ms']}ms)")

    healthy = health.get_healthy_providers()
    print(f"\n健康数据源: {healthy}")

    print("[PASS] 数据源健康检查成功")
except Exception as e:
    print(f"[FAIL] {e}")

print("\n" + "=" * 60)
print("实验11完成")
print("=" * 60)
