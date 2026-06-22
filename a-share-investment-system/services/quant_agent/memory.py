"""记忆系统 — QuantAgent 的每日决策保存与复盘"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

DB_DIR = Path(__file__).resolve().parent.parent.parent / "data"
DB_PATH = DB_DIR / "quant_agent.db"


def _get_db() -> sqlite3.Connection:
    DB_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    _init_tables(conn)
    return conn


def _init_tables(conn: sqlite3.Connection):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS decisions (
            date TEXT PRIMARY KEY,
            state TEXT,
            weights_json TEXT,
            picks_json TEXT,
            report TEXT,
            created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS reflections (
            date TEXT PRIMARY KEY,
            summary TEXT,
            insights_json TEXT,
            mistakes_json TEXT,
            improvements_json TEXT,
            created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS thought_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            phase TEXT,
            title TEXT,
            content TEXT,
            timestamp TEXT
        );
    """)


class MemorySystem:
    """QuantAgent 的记忆系统"""

    def __init__(self):
        self._db = _get_db()

    def save_decision(self, date: str, state: str, weights: dict, picks: list[dict], report: str):
        """保存当日决策"""
        self._db.execute(
            """INSERT OR REPLACE INTO decisions (date, state, weights_json, picks_json, report, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                date,
                state,
                json.dumps(weights, ensure_ascii=False),
                json.dumps(picks, ensure_ascii=False),
                report,
                datetime.now().isoformat(),
            ),
        )
        self._db.commit()

    def save_reflection(
        self,
        date: str,
        summary: str,
        insights: list[str],
        mistakes: list[str],
        improvements: list[str],
    ):
        self._db.execute(
            """INSERT OR REPLACE INTO reflections (date, summary, insights_json, mistakes_json, improvements_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                date,
                summary,
                json.dumps(insights),
                json.dumps(mistakes),
                json.dumps(improvements),
                datetime.now().isoformat(),
            ),
        )
        self._db.commit()

    def log_thought(self, date: str, phase: str, title: str, content: str):
        self._db.execute(
            "INSERT INTO thought_logs (date, phase, title, content, timestamp) VALUES (?, ?, ?, ?, ?)",
            (date, phase, title, content, datetime.now().isoformat()),
        )
        self._db.commit()

    def get_decision(self, date: str) -> dict | None:
        row = self._db.execute("SELECT * FROM decisions WHERE date = ?", (date,)).fetchone()
        if row is None:
            return None
        return {
            "date": row["date"],
            "state": row["state"],
            "weights": json.loads(row["weights_json"] or "{}"),
            "picks": json.loads(row["picks_json"] or "[]"),
            "report": row["report"],
        }

    def get_reflection(self, date: str) -> dict | None:
        row = self._db.execute("SELECT * FROM reflections WHERE date = ?", (date,)).fetchone()
        if row is None:
            return None
        return {
            "date": row["date"],
            "summary": row["summary"],
            "insights": json.loads(row["insights_json"] or "[]"),
            "mistakes": json.loads(row["mistakes_json"] or "[]"),
            "improvements": json.loads(row["improvements_json"] or "[]"),
        }

    def get_recent_decisions(self, limit: int = 10) -> list[dict]:
        rows = self._db.execute(
            "SELECT date, state, picks_json, report, created_at FROM decisions ORDER BY date DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [
            {
                "date": r["date"],
                "state": r["state"],
                "picks_count": len(json.loads(r["picks_json"] or "[]")),
                "report": (r["report"] or "")[:100],
            }
            for r in rows
        ]

    def get_yesterday_decision(self) -> dict | None:
        from datetime import timedelta

        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        return self.get_decision(yesterday)

    def get_latest_reflection(self) -> dict | None:
        row = self._db.execute("SELECT * FROM reflections ORDER BY date DESC LIMIT 1").fetchone()
        if row is None:
            return None
        return {
            "date": row["date"],
            "summary": row["summary"],
            "insights": json.loads(row["insights_json"] or "[]"),
        }
