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
        self._conn = None
        self._ensure_table()

    def _get_conn(self):
        """获取数据库连接。"""
        if self._conn is None:
            if self.db_path == ":memory:":
                self._conn = sqlite3.connect(":memory:")
            else:
                Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
                self._conn = sqlite3.connect(self.db_path)
        return self._conn

    def _ensure_table(self):
        """确保表存在。"""
        conn = self._get_conn()
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
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()

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
        conn.execute(
            """
            INSERT INTO decision_log (ticker, date, action, confidence, entry_price,
                                      stop_loss, thesis, source_agents)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
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

    def get_history(self, ticker: str, limit: int = 5) -> list[dict]:
        """获取历史决策。"""
        conn = self._get_conn()
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT * FROM decision_log WHERE ticker = ?
            ORDER BY created_at DESC LIMIT ?
        """,
            (ticker, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def update_reflection(self, entry_id: int, reflection: str):
        """更新反思。"""
        conn = self._get_conn()
        conn.execute("UPDATE decision_log SET reflection = ? WHERE id = ?", (reflection, entry_id))
        conn.commit()

    def close(self):
        """关闭连接。"""
        if self._conn:
            self._conn.close()
            self._conn = None
