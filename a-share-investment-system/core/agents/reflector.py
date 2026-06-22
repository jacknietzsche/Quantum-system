"""反思循环 — SQLite轻量记忆"""

import json
import os
import sqlite3
from datetime import datetime

_MEMORY_DB = "data/memory.db"


class Reflector:
    def __init__(self):
        os.makedirs("data", exist_ok=True)
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(_MEMORY_DB) as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS reflections "
                "(id INTEGER PRIMARY KEY, date TEXT, code TEXT, decision TEXT, "
                "outcome TEXT, reflection TEXT, created_at TEXT)"
            )

    def record(self, code: str, decision: dict, outcome: str = ""):
        with sqlite3.connect(_MEMORY_DB) as conn:
            conn.execute(
                "INSERT INTO reflections (date, code, decision, outcome, reflection, created_at) "
                "VALUES (?,?,?,?,?,?)",
                (
                    datetime.now().strftime("%Y-%m-%d"),
                    code,
                    json.dumps(decision),
                    outcome,
                    "",
                    datetime.now().isoformat(),
                ),
            )

    def get_history(self, code: str, limit: int = 10) -> list:
        with sqlite3.connect(_MEMORY_DB) as conn:
            return conn.execute(
                "SELECT * FROM reflections WHERE code=? ORDER BY id DESC LIMIT ?",
                (code, limit),
            ).fetchall()
