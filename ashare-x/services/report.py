"""报告生成。

设计依据: S08, experiments exp11.1。
生成分析报告（SQLite结构化 + Markdown）。
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path


class ReportGenerator:
    """报告生成器。"""

    def __init__(self, db_path: str = "runtime/investment.db"):
        self.db_path = db_path
        self._persistent_conn: sqlite3.Connection | None = None
        if db_path == ":memory:":
            # In-memory DB needs a persistent connection to survive across calls
            self._persistent_conn = sqlite3.connect(":memory:")
            self._persistent_conn.row_factory = sqlite3.Row
            self._ensure_tables()

    def _get_conn(self) -> sqlite3.Connection:
        if self._persistent_conn is not None:
            return self._persistent_conn
        conn = sqlite3.connect(self.db_path, timeout=5.0)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    def _ensure_tables(self):
        if self.db_path != ":memory:":
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        conn = self._get_conn()
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS reports (
                    id TEXT PRIMARY KEY,
                    ticker TEXT NOT NULL,
                    stock_name TEXT,
                    date TEXT,
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
            conn.commit()
        finally:
            if self._persistent_conn is None:
                conn.close()

    def save_report(
        self,
        report_id: str,
        plan: dict,
        token_usage: int = 0,
        execution_time: float = 0,
        agents: list[str] | None = None,
    ):
        conn = self._get_conn()
        try:
            conn.execute(
                """
                INSERT OR REPLACE INTO reports
                (id, ticker, stock_name, date, action, confidence, entry_price,
                 stop_loss, take_profit, position_pct, token_usage,
                 execution_time_seconds, agents_executed, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
                (
                    report_id,
                    plan.get("ticker", ""),
                    plan.get("stock_name", ""),
                    datetime.now().strftime("%Y-%m-%d"),
                    plan.get("action", "Hold"),
                    plan.get("confidence", 0),
                    plan.get("entry_price", 0),
                    plan.get("stop_loss", 0),
                    plan.get("take_profit", 0),
                    plan.get("position_pct", 0),
                    token_usage,
                    execution_time,
                    json.dumps(agents or []),
                ),
            )
            conn.commit()
        finally:
            if self._persistent_conn is None:
                conn.close()

    def get_recent_reports(self, limit: int = 10) -> list[dict]:
        conn = self._get_conn()
        try:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM reports ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            if self._persistent_conn is None:
                conn.close()

    def generate_markdown(self, plan: dict) -> str:
        md = f"# {plan.get('ticker', '')} {plan.get('stock_name', '')} 分析报告\n\n"
        md += f"**日期**: {datetime.now().strftime('%Y-%m-%d')}\n\n"
        md += "## 决策\n"
        md += f"- **操作**: {plan.get('action', 'Hold')}\n"
        md += f"- **置信度**: {plan.get('confidence', 0)}%\n"
        md += f"- **入场价**: ¥{plan.get('entry_price', 0):.2f}\n"
        md += f"- **止损价**: ¥{plan.get('stop_loss', 0):.2f}\n"
        md += f"- **止盈价**: ¥{plan.get('take_profit', 0):.2f}\n"
        md += f"- **仓位**: {plan.get('position_pct', 0)}%\n\n"
        md += f"## 论据\n{plan.get('thesis', 'N/A')}\n"
        return md

    def close(self):
        if self._persistent_conn:
            self._persistent_conn.close()
            self._persistent_conn = None
