# -*- coding: utf-8 -*-
"""
实验11.1: 报告存储格式
"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import json
import sqlite3
import pandas as pd
from pathlib import Path

print("=" * 60)
print("实验11.1: 报告存储格式（JSON + Markdown）")
print("=" * 60)

db_path = Path("experiments/test_reports.db")
if db_path.exists():
    db_path.unlink()
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
