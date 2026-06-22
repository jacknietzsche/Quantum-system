"""Notifier 单元测试 — 通知创建、持久化、查询"""

from unittest.mock import MagicMock, patch

import pytest

from services.notifier import (
    NotificationLevel,
    _persist_to_db,
    create_notification,
    get_recent_notifications,
    notify_risk_alert,
    notify_signal,
    notify_workflow,
)


@pytest.fixture(autouse=True)
def clean_state():
    from services.notifier import _ws_clients

    _ws_clients.clear()
    yield
    _ws_clients.clear()


class TestCreateNotification:
    def test_basic_notification(self):
        result = create_notification("Test", "Hello", level=NotificationLevel.INFO)
        assert result["title"] == "Test"
        assert result["message"] == "Hello"
        assert result["level"] == "INFO"
        assert "id" in result
        assert "timestamp" in result

    def test_notification_with_data(self):
        data = {"stock_code": "600519", "price": 1680}
        result = create_notification("Signal", "Buy", data=data)
        assert result["data"]["stock_code"] == "600519"

    def test_notification_category(self):
        result = create_notification("Risk", "Alert", category="risk")
        assert result["category"] == "risk"

    def test_notification_channels_default(self):
        result = create_notification("Test", "Msg")
        assert "db" in result["channels"]
        assert "websocket" in result["channels"]

    def test_notification_level_warning(self):
        result = create_notification("Warn", "Msg", level=NotificationLevel.WARNING)
        assert result["level"] == "WARNING"


class TestConvenienceFunctions:
    def test_notify_risk_alert(self):
        result = notify_risk_alert("Stop Loss", "600519 hit -10%", level="WARNING")
        assert result["category"] == "risk"
        assert result["level"] == "WARNING"

    def test_notify_risk_alert_critical_includes_email(self):
        result = notify_risk_alert("Critical", "System down", level="CRITICAL")
        assert "email" in result["channels"]

    def test_notify_signal(self):
        result = notify_signal("Buy Signal", "600519 bullish")
        assert result["category"] == "signal"
        assert result["level"] == "INFO"

    def test_notify_workflow(self):
        result = notify_workflow("Daily Complete", "Screening done")
        assert result["category"] == "workflow"


class TestPersistence:
    @patch("shared.models.get_session")
    def test_persist_to_db(self, mock_get_session):
        mock_session = MagicMock()
        mock_get_session.return_value = mock_session
        _persist_to_db({"category": "test", "level": "INFO", "title": "T", "message": "M"})
        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()
        mock_session.close.assert_called_once()

    @patch("shared.models.get_session")
    def test_persist_handles_error(self, mock_get_session):
        mock_get_session.side_effect = Exception("DB down")
        _persist_to_db({"category": "test", "level": "INFO", "title": "T", "message": "M"})


class TestQuery:
    @patch("shared.models.get_session")
    def test_get_recent_notifications(self, mock_get_session):
        mock_log = MagicMock()
        mock_log.module = "notify:risk"
        mock_log.level = "WARNING"
        mock_log.message = "Test alert"
        mock_log.created_at.isoformat.return_value = "2024-01-15T10:00:00"
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [
            mock_log
        ]
        mock_get_session.return_value = mock_session
        result = get_recent_notifications(limit=10)
        assert len(result) == 1
        assert result[0]["module"] == "notify:risk"

    @patch("shared.models.get_session")
    def test_get_recent_empty(self, mock_get_session):
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []
        mock_get_session.return_value = mock_session
        result = get_recent_notifications()
        assert result == []

    @patch("shared.models.get_session")
    def test_get_recent_handles_error(self, mock_get_session):
        mock_get_session.side_effect = Exception("DB error")
        result = get_recent_notifications()
        assert result == []
