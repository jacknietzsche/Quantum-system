"""QQ邮箱 SMTP 发送器"""

import smtplib
from email.header import Header
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from shared.config import config as _config


class EmailSender:
    """QQ邮箱 SMTP SSL 邮件发送"""

    def __init__(self, config=None):
        self._cfg = _config or config
        self._email_cfg = self._cfg.get_email_config()

    def send(
        self, subject: str, body: str, to: list[str] | None = None, html: str | None = None
    ) -> bool:
        receivers = to or self._email_cfg.get("receivers", [])
        sender = self._email_cfg.get("sender", "")
        password = self._email_cfg.get("password", "")
        sender_name = self._email_cfg.get("sender_name", "A股智能投研系统")

        if not sender or not password or not receivers:
            print("[Email] Configuration incomplete")
            return False

        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = Header(subject, "utf-8").encode()
            msg["From"] = Header(sender_name, "utf-8").encode() + f" <{sender}>"
            msg["To"] = ", ".join(receivers)
            msg.attach(MIMEText(body, "plain", "utf-8"))
            if html:
                msg.attach(MIMEText(html, "html", "utf-8"))

            with smtplib.SMTP_SSL("smtp.qq.com", 465) as server:
                server.login(sender, password)
                server.sendmail(sender, receivers, msg.as_string())
            return True
        except Exception as e:
            print(f"[Email] Send failed: {e}")
            return False

    def send_report(self, report_content: str, report_name: str = "投研报告") -> bool:
        subject = f"📊 {report_name}"
        return self.send(subject, report_content)
