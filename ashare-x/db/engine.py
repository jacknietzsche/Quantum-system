"""SQLAlchemy 数据库引擎（线程安全）。

设计依据: S05 §5.8, experiments exp1.3/exp6.3。
线程安全: StaticPool + check_same_thread=False。
"""

from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

logger = logging.getLogger(__name__)

_engine = None
_SessionFactory = None


def get_engine(db_path: str = "runtime/investment.db"):
    """获取SQLite引擎（单例）。"""
    global _engine  # noqa: PLW0603
    if _engine is None:
        path = Path(db_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        url = f"sqlite:///{path}"
        _engine = create_engine(
            url,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
            echo=False,
        )

        # 启用WAL模式提升并发性能
        @event.listens_for(_engine, "connect")
        def set_sqlite_pragma(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA busy_timeout=5000")
            cursor.close()

        logger.info("数据库引擎初始化: %s", path)
    return _engine


def get_session_factory():
    """获取Session工厂。"""
    global _SessionFactory  # noqa: PLW0603
    if _SessionFactory is None:
        _SessionFactory = sessionmaker(bind=get_engine())
    return _SessionFactory


def get_session() -> Session:
    """获取数据库Session。"""
    return get_session_factory()()


def init_db(db_path: str = "runtime/investment.db"):
    """初始化数据库（创建所有表）。"""
    from db.models import Base

    engine = get_engine(db_path)
    Base.metadata.create_all(engine)
    logger.info("数据库表创建完成")
