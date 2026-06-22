"""数据库会话管理(向后兼容层 — 实际实现在 shared.models)"""

import logging
import os
from contextlib import contextmanager

from shared.models import get_session as _get_session
from shared.models import init_db as _init_db

logger = logging.getLogger(__name__)
_DEFAULT_DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "investment.db",
)


def init_db(db_path: str | None = None):
    path = db_path or _DEFAULT_DB_PATH
    return _init_db(path)


def get_session():
    return _get_session()


_engine = None


def get_engine():
    global _engine  # noqa: PLW0603
    try:
        if _engine is None:
            init_db()
    except NameError:
        _engine = None
        init_db()
    return _engine


@contextmanager
def db_session():
    """auto close session"""
    session = get_session()
    try:
        yield session
    finally:
        try:
            session.close()
        except Exception as _e:
            logger.warning("Suppressed: %s", _e)


def health_check() -> dict:
    """database health check"""
    try:
        from shared.models import StockInfo

        session = get_session()
        total = session.query(StockInfo).count()
        kline = 0
        try:
            from shared.models import KlineCache

            kline = session.query(KlineCache).count()
        except Exception as _e:
            logger.warning("Suppressed: %s", _e)
        session.close()

        import os

        db_file = _DEFAULT_DB_PATH
        size_mb = (
            round(os.path.getsize(db_file) / (1024 * 1024), 1) if os.path.exists(db_file) else 0
        )

        return {
            "status": "healthy",
            "table_count": total,
            "kline_records": kline,
            "disk_mb": size_mb,
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}
