"""检查点恢复系统 — 参考 TradingAgents/graph/checkpointer.py

Per-stock SQLite 数据库,支持:
- 并发股票分析不冲突
- 崩溃后从最后成功步骤恢复
- 完成后自动清理检查点
"""

from __future__ import annotations

import hashlib
import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from shared.logging import emit_log


def _safe_stock_code(stock_code: str) -> str:
    """净化股票代码,防止路径穿越"""
    safe = "".join(c for c in stock_code if c.isalnum() or c in ("_", "-"))
    return safe.upper()[:10] or "UNKNOWN"


def _db_path(data_dir: str | Path, stock_code: str) -> Path:
    """返回 per-stock 检查点数据库路径"""
    safe = _safe_stock_code(stock_code)
    p = Path(data_dir) / "checkpoints"
    p.mkdir(parents=True, exist_ok=True)
    return p / f"{safe}.db"


def thread_id(stock_code: str, date: str) -> str:
    """确定性 thread_id (stock_code + date)"""
    return hashlib.sha256(f"{stock_code.upper()}:{date}".encode()).hexdigest()[:16]


@contextmanager
def get_checkpointer(data_dir: str | Path, stock_code: str) -> Generator:
    """Context manager: 返回 SqliteSaver (per-stock)"""
    from langgraph.checkpoint.sqlite import SqliteSaver

    db = _db_path(data_dir, stock_code)
    conn = sqlite3.connect(str(db), check_same_thread=False)
    try:
        saver = SqliteSaver(conn)
        saver.setup()
        yield saver
    finally:
        conn.close()


def has_checkpoint(data_dir: str | Path, stock_code: str, date: str) -> bool:
    """检查是否存在可恢复的检查点"""
    return checkpoint_step(data_dir, stock_code, date) is not None


def checkpoint_step(data_dir: str | Path, stock_code: str, date: str) -> int | None:
    """返回最新检查点步骤号,或 None"""
    db = _db_path(data_dir, stock_code)
    if not db.exists():
        return None
    tid = thread_id(stock_code, date)
    try:
        with get_checkpointer(data_dir, stock_code) as saver:
            config = {"configurable": {"thread_id": tid}}
            cp = saver.get_tuple(config)
            if cp is None:
                return None
            return cp.metadata.get("step")
    except Exception:
        return None


def clear_all_checkpoints(data_dir: str | Path) -> int:
    """清除所有检查点数据库,返回删除文件数"""
    cp_dir = Path(data_dir) / "checkpoints"
    if not cp_dir.exists():
        return 0
    dbs = list(cp_dir.glob("*.db"))
    for db in dbs:
        db.unlink()
    emit_log("INFO", "checkpoint", f"Cleared {len(dbs)} checkpoint databases")
    return len(dbs)


def clear_checkpoint(data_dir: str | Path, stock_code: str, date: str) -> None:
    """清除特定 stock+date 的检查点"""
    db = _db_path(data_dir, stock_code)
    if not db.exists():
        return
    tid = thread_id(stock_code, date)
    try:
        conn = sqlite3.connect(str(db))
        for table in ("writes", "checkpoints"):
            if table not in {"writes", "checkpoints"}:
                continue
            conn.execute(f"DELETE FROM {table} WHERE thread_id = ?", (tid,))  # noqa: S608
        conn.commit()
        conn.close()
    except sqlite3.OperationalError:
        pass
