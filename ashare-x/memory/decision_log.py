"""决策日志。

设计依据: S09 §9.1, experiments exp11.1。
每次分析自动记录决策。
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path


class DecisionLog:
    """决策日志，支持自动轮转。"""

    def __init__(self, db_path: str = "runtime/investment.db", max_entries: int = 100):
        self.db_path = db_path
        self.max_entries = max_entries
        self._persistent_conn: sqlite3.Connection | None = None
        if db_path == ":memory:":
            self._persistent_conn = sqlite3.connect(":memory:")
        self._ensure_table()

    def _get_conn(self) -> sqlite3.Connection:
        """获取数据库连接（WAL模式）。"""
        if self._persistent_conn is not None:
            return self._persistent_conn
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path, timeout=5.0)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    def _ensure_table(self):
        """确保表存在（含outcome列，与ORM对齐）。"""
        conn = self._get_conn()
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS decision_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ticker TEXT NOT NULL,
                    date TEXT,
                    action TEXT,
                    confidence REAL,
                    entry_price REAL,
                    stop_loss REAL,
                    thesis TEXT,
                    reflection TEXT,
                    source_agents TEXT,
                    outcome_profit REAL,
                    outcome_return_pct REAL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            # Add missing columns if table was created by older version
            try:
                conn.execute("ALTER TABLE decision_log ADD COLUMN outcome_profit REAL")
            except sqlite3.OperationalError:
                pass  # Column already exists
            try:
                conn.execute("ALTER TABLE decision_log ADD COLUMN outcome_return_pct REAL")
            except sqlite3.OperationalError:
                pass
            conn.commit()
        finally:
            if self._persistent_conn is None:
                conn.close()

    def add_entry(
        self,
        ticker: str,
        date: str,
        action: str,
        confidence: float,
        entry_price: float = 0,
        stop_loss: float = 0,
        thesis: str = "",
        source_agents: list[str] | None = None,
    ):
        """添加新条目。"""
        conn = self._get_conn()
        try:
            conn.execute(
                """
                INSERT INTO decision_log (ticker, date, action, confidence, entry_price,
                                          stop_loss, thesis, source_agents, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
                (
                    ticker,
                    date,
                    action,
                    confidence,
                    entry_price,
                    stop_loss,
                    thesis,
                    json.dumps(source_agents or []),
                ),
            )
            conn.commit()

            # 轮转
            if self.max_entries:
                count = conn.execute("SELECT COUNT(*) FROM decision_log").fetchone()[0]
                if count > self.max_entries:
                    conn.execute(
                        """
                        DELETE FROM decision_log WHERE id IN (
                            SELECT id FROM decision_log ORDER BY created_at ASC LIMIT ?
                        )
                    """,
                        (count - self.max_entries,),
                    )
                    conn.commit()
        finally:
            if self._persistent_conn is None:
                conn.close()

    def get_history(self, ticker: str, limit: int = 5) -> list[dict]:
        """获取历史决策。"""
        conn = self._get_conn()
        try:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT * FROM decision_log WHERE ticker = ?
                ORDER BY created_at DESC LIMIT ?
            """,
                (ticker, limit),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            if self._persistent_conn is None:
                conn.close()

    def update_reflection(self, entry_id: int, reflection: str):
        """更新反思。"""
        conn = self._get_conn()
        try:
            conn.execute(
                "UPDATE decision_log SET reflection = ? WHERE id = ?",
                (reflection, entry_id),
            )
            conn.commit()
        finally:
            if self._persistent_conn is None:
                conn.close()

    def update_outcome(self, entry_id: int, profit: float, return_pct: float):
        """更新决策结果（用于反思引擎评估历史决策）。"""
        conn = self._get_conn()
        try:
            conn.execute(
                "UPDATE decision_log SET outcome_profit = ?, outcome_return_pct = ? WHERE id = ?",
                (profit, return_pct, entry_id),
            )
            conn.commit()
        finally:
            if self._persistent_conn is None:
                conn.close()

    def get_unreflected(self, limit: int = 10) -> list[dict]:
        """获取尚未有反思结果的决策（用于反思引擎批量处理）。"""
        conn = self._get_conn()
        try:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT * FROM decision_log
                WHERE reflection IS NULL OR reflection = ''
                ORDER BY created_at ASC LIMIT ?
                """,
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            if self._persistent_conn is None:
                conn.close()

    def close(self):
        """关闭连接。"""
        if self._persistent_conn:
            self._persistent_conn.close()
            self._persistent_conn = None
