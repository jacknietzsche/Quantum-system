"""日频复盘记忆 — 盘后自动运行

每天存储:
  1. 当日市场状态 + 策略选择
  2. 推荐结果 + 次日表现
  3. AI反思与经验教训
"""

import json
import logging
import sqlite3
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

DB_PATH = "data/daily_memory.db"


def _init_db():
    """初始化记忆数据库"""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS daily_memory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trade_date TEXT UNIQUE NOT NULL,
            market_state TEXT,
            picks TEXT,
            result TEXT,
            reflection TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS agent_stats (
            agent_name TEXT NOT NULL,
            trade_date TEXT NOT NULL,
            picks_count INTEGER DEFAULT 0,
            correct_count INTEGER DEFAULT 0,
            avg_return REAL DEFAULT 0,
            PRIMARY KEY (agent_name, trade_date)
        )
    """)
    conn.commit()
    conn.close()


class DailyMemory:
    """日频复盘记忆系统"""

    def __init__(self):
        _init_db()
        self._today = datetime.now().strftime("%Y-%m-%d")

    def save_daily(
        self,
        market_state: dict,
        picks: list[dict],
        reflection: str = "",
    ) -> bool:
        """保存当日记录"""
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.execute(
                """INSERT OR REPLACE INTO daily_memory
                   (trade_date, market_state, picks, reflection)
                   VALUES (?, ?, ?, ?)""",
                (
                    self._today,
                    json.dumps(market_state, ensure_ascii=False),
                    json.dumps(picks, ensure_ascii=False),
                    reflection,
                ),
            )
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logger.warning("DailyMemory save failed: %s", e)
            return False

    def update_result(self, trade_date: str, result: dict) -> bool:
        """更新指定日期的实际表现"""
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.execute(
                "UPDATE daily_memory SET result=? WHERE trade_date=?",
                (json.dumps(result, ensure_ascii=False), trade_date),
            )
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logger.warning("DailyMemory update failed: %s", e)
            return False

    def get_recent(self, days: int = 30) -> list[dict]:
        """获取最近N天的记忆"""
        try:
            conn = sqlite3.connect(DB_PATH)
            cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
            rows = conn.execute(
                "SELECT trade_date, market_state, picks, result, reflection FROM daily_memory WHERE trade_date >= ? ORDER BY trade_date DESC",
                (cutoff,),
            ).fetchall()
            conn.close()
            result = []
            for row in rows:
                item = {"trade_date": row[0]}
                try:
                    item["market_state"] = json.loads(row[1]) if row[1] else {}
                except json.JSONDecodeError:
                    item["market_state"] = {}
                try:
                    item["picks"] = json.loads(row[2]) if row[2] else []
                except json.JSONDecodeError:
                    item["picks"] = []
                try:
                    item["result"] = json.loads(row[3]) if row[3] else {}
                except json.JSONDecodeError:
                    item["result"] = {}
                item["reflection"] = row[4] or ""
                result.append(item)
            return result
        except Exception as e:
            logger.warning("DailyMemory get_recent failed: %s", e)
            return []

    def get_similar_market(self, regime: str, limit: int = 5) -> list[dict]:
        """查找相似市场状态的过往记录"""
        try:
            conn = sqlite3.connect(DB_PATH)
            rows = conn.execute(
                """SELECT trade_date, market_state, picks, result, reflection FROM daily_memory
                   WHERE market_state LIKE ? AND result IS NOT NULL
                   ORDER BY trade_date DESC LIMIT ?""",
                (f"%{regime}%", limit),
            ).fetchall()
            conn.close()
            result = []
            for row in rows:
                item = {"trade_date": row[0]}
                try:
                    item["result"] = json.loads(row[3]) if row[3] else {}
                except json.JSONDecodeError:
                    item["result"] = {}
                item["reflection"] = row[4] or ""
                result.append(item)
            return result
        except Exception as e:
            logger.warning("DailyMemory get_similar failed: %s", e)
            return []

    def get_agent_stats(self, agent_name: str | None = None) -> list[dict]:
        """获取Agent历史统计"""
        try:
            conn = sqlite3.connect(DB_PATH)
            if agent_name:
                rows = conn.execute(
                    "SELECT * FROM agent_stats WHERE agent_name=? ORDER BY trade_date DESC LIMIT 30",
                    (agent_name,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT agent_name, SUM(picks_count), SUM(correct_count) FROM agent_stats GROUP BY agent_name"
                ).fetchall()
            conn.close()
            return [{"agent_name": r[0], "total_picks": r[1], "correct": r[2]} for r in rows]
        except Exception as e:
            logger.warning("DailyMemory get_agent_stats failed: %s", e)
            return []
