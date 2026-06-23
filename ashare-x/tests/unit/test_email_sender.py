"""邮件发送服务与接口测试。"""

from __future__ import annotations

import smtplib
from unittest.mock import MagicMock, patch

import pytest

from services.email_sender import EmailSender


@pytest.fixture()
def configured_email_sender(monkeypatch: pytest.MonkeyPatch) -> EmailSender:
    """构造一个已配置发件邮箱和授权码的 EmailSender。"""
    monkeypatch.setenv("ASHARE_X_EMAIL_SENDER", "test@qq.com")
    monkeypatch.setenv("ASHARE_X_EMAIL_PASSWORD", "secret")
    monkeypatch.setenv("ASHARE_X_EMAIL_RECIPIENT", "to@qq.com")

    from core.config import Config

    Config.reset()
    return EmailSender()


@pytest.fixture()
def empty_email_sender(monkeypatch: pytest.MonkeyPatch) -> EmailSender:
    """构造一个未配置邮箱的 EmailSender。"""
    monkeypatch.delenv("ASHARE_X_EMAIL_SENDER", raising=False)
    monkeypatch.delenv("ASHARE_X_EMAIL_PASSWORD", raising=False)
    monkeypatch.delenv("ASHARE_X_EMAIL_RECIPIENT", raising=False)

    from core.config import Config

    Config.reset()
    return EmailSender()


class TestEmailSender:
    """EmailSender 服务单元测试。"""

    def test_is_configured_false(self, empty_email_sender: EmailSender):
        assert empty_email_sender.is_configured() is False

    def test_is_configured_true(self, configured_email_sender: EmailSender):
        assert configured_email_sender.is_configured() is True

    def test_send_plan_not_configured(self, empty_email_sender: EmailSender):
        result = empty_email_sender.send_plan(
            {"date": "2026-06-22"}, recipient="to@qq.com"
        )
        assert result["ok"] is False
        assert "发件邮箱" in result["error"]

    def test_send_plan_missing_recipient(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("ASHARE_X_EMAIL_SENDER", "test@qq.com")
        monkeypatch.setenv("ASHARE_X_EMAIL_PASSWORD", "secret")
        monkeypatch.delenv("ASHARE_X_EMAIL_RECIPIENT", raising=False)

        from core.config import Config

        Config.reset()
        sender = EmailSender()

        result = sender.send_plan({"date": "2026-06-22"})
        assert result["ok"] is False
        assert "收件人" in result["error"]

    def test_send_test_email_not_configured(self, empty_email_sender: EmailSender):
        result = empty_email_sender.send_test_email(recipient="to@qq.com")
        assert result["ok"] is False
        assert "发件邮箱" in result["error"]

    @patch("services.email_sender.smtplib.SMTP_SSL")
    def test_send_plan_success(
        self, mock_smtp_ssl: MagicMock, configured_email_sender: EmailSender
    ):
        mock_server = mock_smtp_ssl.return_value
        mock_server.__enter__ = MagicMock(return_value=mock_server)
        mock_server.__exit__ = MagicMock(return_value=False)

        plan = {
            "date": "2026-06-22",
            "market_state": "BULL",
            "summary": "test summary",
            "actions": [
                {
                    "action": "BUY",
                    "stock_code": "600519",
                    "stock_name": "贵州茅台",
                    "confidence": 85,
                    "reasoning": "估值合理",
                }
            ],
        }
        result = configured_email_sender.send_plan(plan)

        assert result["ok"] is True
        assert "to@qq.com" in result["message"]
        mock_smtp_ssl.assert_called_once()
        mock_server.login.assert_called_once_with("test@qq.com", "secret")
        mock_server.sendmail.assert_called_once()

    @patch("services.email_sender.smtplib.SMTP_SSL")
    def test_send_test_email_success(
        self, mock_smtp_ssl: MagicMock, configured_email_sender: EmailSender
    ):
        mock_server = mock_smtp_ssl.return_value
        mock_server.__enter__ = MagicMock(return_value=mock_server)
        mock_server.__exit__ = MagicMock(return_value=False)

        result = configured_email_sender.send_test_email()

        assert result["ok"] is True
        assert "to@qq.com" in result["message"]
        mock_server.login.assert_called_once()
        mock_server.sendmail.assert_called_once()

    @patch(
        "services.email_sender.smtplib.SMTP_SSL",
        side_effect=smtplib.SMTPException("network error"),
    )
    def test_send_plan_smtp_error(
        self, _mock_smtp_ssl: MagicMock, configured_email_sender: EmailSender
    ):
        result = configured_email_sender.send_plan({"date": "2026-06-22"})

        assert result["ok"] is False
        assert "SMTP" in result["error"]

    def test_build_message_contains_plan_data(
        self, configured_email_sender: EmailSender
    ):
        plan = {
            "date": "2026-06-22",
            "market_state": "BULL",
            "summary": "test summary",
            "actions": [
                {
                    "action": "BUY",
                    "stock_code": "600519",
                    "stock_name": "贵州茅台",
                    "confidence": 85,
                    "reasoning": "估值合理",
                }
            ],
        }
        subject, html = configured_email_sender._build_message(plan, [], [])
        assert "2026-06-22" in subject
        assert "600519" in html
        assert "贵州茅台" in html
        assert "估值合理" in html


class TestEmailAPI:
    """邮件相关 API 路由测试。"""

    def test_send_email_no_plan(self):
        from fastapi.testclient import TestClient

        from server import app

        with patch("services.daily_plan.DailyPlanGenerator") as mock_gen_cls:
            mock_gen = MagicMock()
            mock_gen.get_today_plan.return_value = None
            mock_gen_cls.return_value = mock_gen

            client = TestClient(app)
            r = client.post("/api/trading-plan/send-email", json={})

        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is False
        assert "尚未生成" in data["error"]

    @patch("services.daily_plan.DailyPlanGenerator")
    @patch("services.paper_portfolio.PaperPortfolio")
    @patch("services.email_sender.EmailSender")
    def test_send_email_success(
        self,
        mock_sender_cls: MagicMock,
        mock_portfolio_cls: MagicMock,
        mock_gen_cls: MagicMock,
    ):
        from fastapi.testclient import TestClient

        from server import app

        mock_gen = MagicMock()
        mock_gen.get_today_plan.return_value = {"date": "2026-06-22"}
        mock_gen_cls.return_value = mock_gen

        mock_portfolio = MagicMock()
        mock_portfolio.get_holdings.return_value = []
        mock_portfolio.get_trade_history.return_value = []
        mock_portfolio_cls.return_value = mock_portfolio

        mock_sender = MagicMock()
        mock_sender.send_plan.return_value = {"ok": True, "message": "已发送"}
        mock_sender_cls.return_value = mock_sender

        client = TestClient(app)
        r = client.post("/api/trading-plan/send-email", json={"recipient": "to@qq.com"})

        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert data["message"] == "已发送"
        mock_sender.send_plan.assert_called_once()

    @patch("services.email_sender.EmailSender")
    def test_send_test_email_success(self, mock_sender_cls: MagicMock):
        from fastapi.testclient import TestClient

        from server import app

        mock_sender = MagicMock()
        mock_sender.send_test_email.return_value = {"ok": True, "message": "测试已发送"}
        mock_sender_cls.return_value = mock_sender

        client = TestClient(app)
        r = client.post("/api/settings/send-test-email", json={"recipient": "to@qq.com"})

        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert data["message"] == "测试已发送"
        mock_sender.send_test_email.assert_called_once_with(recipient="to@qq.com")
