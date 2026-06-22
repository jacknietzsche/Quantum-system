"""单元测试 — db_session 上下文管理器"""

from unittest.mock import MagicMock, patch

from shared.db_session import db_session


@patch("shared.db_session.get_session")
def test_session_commit_on_success(mock_get_session):
    """正常退出时自动提交并关闭"""
    mock_session = MagicMock()
    mock_get_session.return_value = mock_session

    with db_session():
        pass

    mock_session.commit.assert_called_once()
    mock_session.close.assert_called_once()


@patch("shared.db_session.get_session")
def test_session_rollback_on_error(mock_get_session):
    """异常时回滚并关闭"""
    mock_session = MagicMock()
    mock_get_session.return_value = mock_session

    try:
        with db_session():
            raise ValueError("test error")
    except ValueError:
        pass

    mock_session.rollback.assert_called_once()
    mock_session.close.assert_called_once()


@patch("shared.db_session.get_session")
def test_session_close_on_any_exit(mock_get_session):
    """退出时总执行close(无论成功或失败)"""
    mock_session = MagicMock()
    mock_get_session.return_value = mock_session

    with db_session():
        pass

    mock_session.close.assert_called_once()
