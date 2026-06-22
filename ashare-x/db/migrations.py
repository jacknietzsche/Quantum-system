"""数据库迁移管理（版本追踪 + 幂等迁移）。

设计依据: S05 §5.9, experiments exp12.3。
迁移脚本存储在 db/migrations/ 目录，按版本号命名。
"""

from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy import text

from db.engine import get_engine

logger = logging.getLogger(__name__)

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def get_current_version() -> int:
    """获取当前数据库版本。"""
    engine = get_engine()
    with engine.connect() as conn:
        result = conn.execute(text("SELECT MAX(version) FROM _migration_version"))
        row = result.fetchone()
        return row[0] if row and row[0] else 0


def apply_migration(version: int, description: str, sql: str) -> bool:
    """
    应用迁移（幂等：已应用的跳过）。
    返回 True 表示成功应用，False 表示已存在。
    """
    current = get_current_version()
    if version <= current:
        logger.debug("迁移v%d: 跳过（已应用）", version)
        return False

    engine = get_engine()
    with engine.connect() as conn:
        conn.execute(text(sql))
        conn.execute(
            text("INSERT INTO _migration_version (version, description) VALUES (:v, :d)"),
            {"v": version, "d": description},
        )
        conn.commit()
    logger.info("迁移v%d: %s [已应用]", version, description)
    return True


def apply_pending_migrations() -> int:
    """应用所有待执行的迁移，返回应用数量。"""
    # 确保迁移表存在
    engine = get_engine()
    with engine.connect() as conn:
        conn.execute(
            text("""
            CREATE TABLE IF NOT EXISTS _migration_version (
                version INTEGER PRIMARY KEY,
                description TEXT,
                applied_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        )
        conn.commit()

    applied = 0
    # 读取迁移文件
    migration_files = sorted(MIGRATIONS_DIR.glob("v*.sql"))
    for mf in migration_files:
        # 解析版本号: v001_xxx.sql → 1
        name = mf.stem
        try:
            version = int(name.split("_")[0][1:])
        except (IndexError, ValueError):
            logger.warning("无法解析迁移文件: %s", name)
            continue

        description = "_".join(name.split("_")[1:])
        sql = mf.read_text(encoding="utf-8")

        if apply_migration(version, description, sql):
            applied += 1

    return applied
