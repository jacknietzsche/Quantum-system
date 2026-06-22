"""DB Session 上下文管理器 — 统一会话生命周期管理"""

from collections.abc import Generator
from contextlib import contextmanager

from shared.models import get_session


@contextmanager
def db_session() -> Generator:
    """数据库会话上下文管理器 — 自动提交/回滚/关闭

    用法:
        with db_session() as session:
            rows = session.query(StockInfo).all()
            # 自动提交
        # 自动关闭
    """
    session = get_session()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
