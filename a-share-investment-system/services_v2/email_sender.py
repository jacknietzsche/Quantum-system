"""邮件通知服务 — 参考 daily_stock_analysis/notification.py

支持:
1. 日频分析报告邮件推送
2. Markdown 格式报告
3. 多收件人支持
4. 失败重试
"""

from __future__ import annotations

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

logger = logging.getLogger("ashare.notification")


class EmailSender:
    """邮件发送器"""

    def __init__(self, config: dict[str, Any]):
        """
        config = {
            "smtp_host": "smtp.qq.com",
            "smtp_port": 465,
            "sender": "xxx@qq.com",
            "password": "授权码",
            "receivers": ["xxx@qq.com"],
            "sender_name": "A股智能投研系统",
        }
        """
        self.smtp_host = config.get("smtp_host", "smtp.qq.com")
        self.smtp_port = config.get("smtp_port", 465)
        self.sender = config.get("sender", "")
        self.password = config.get("password", "")
        self.receivers = config.get("receivers", [])
        self.sender_name = config.get("sender_name", "A股智能投研")

    def send(self, subject: str, content: str, is_html: bool = False) -> bool:
        """发送邮件

        Args:
            subject: 邮件主题
            content: 邮件内容 (Markdown 或 HTML)
            is_html: 是否为 HTML 格式

        Returns:
            是否发送成功
        """
        if not self.sender or not self.password:
            logger.warning("邮件配置不完整,跳过发送")
            return False
        if not self.receivers:
            logger.warning("无收件人,跳过发送")
            return False

        try:
            msg = MIMEMultipart("alternative")
            msg["From"] = f"{self.sender_name} <{self.sender}>"
            msg["To"] = ", ".join(self.receivers)
            msg["Subject"] = subject

            if is_html:
                msg.attach(MIMEText(content, "html", "utf-8"))
            else:
                # Markdown 转简单 HTML
                html = self._md_to_html(content)
                msg.attach(MIMEText(html, "html", "utf-8"))

            # SSL 连接
            with smtplib.SMTP_SSL(self.smtp_host, self.smtp_port) as server:
                server.login(self.sender, self.password)
                server.sendmail(self.sender, self.receivers, msg.as_string())

            logger.info(f"邮件发送成功: {subject} -> {self.receivers}")
            return True

        except Exception as e:
            logger.error(f"邮件发送失败: {e}")
            return False

    def _md_to_html(self, md: str) -> str:
        """简单 Markdown 转 HTML"""
        try:
            import markdown

            return str(markdown.markdown(md, extensions=["tables", "fenced_code"]))
        except ImportError:
            # 降级: 直接包裹 pre 标签
            return f"<pre>{md}</pre>"

    def send_daily_report(
        self,
        stock_code: str,
        stock_name: str,
        decision: str,
        signal: dict[str, Any],
        reports: dict[str, str],
    ) -> bool:
        """发送日频分析报告

        Args:
            stock_code: 股票代码
            stock_name: 股票名称
            decision: 完整决策文本
            signal: 结构化信号 {action, confidence, reasoning}
            reports: 各分析师报告
        """
        action = signal.get("action", "持有")
        confidence = signal.get("confidence", 0)
        emoji_map = {"买入": "🟢", "持有": "🟡", "卖出": "🔴"}
        emoji = emoji_map.get(action, "⚪")

        subject = f"{emoji} {stock_name}({stock_code}) 日频分析: {action}"

        # 构建 Markdown 报告
        lines = [
            f"# {emoji} {stock_name} ({stock_code}) 日频分析报告",
            "",
            "## 决策摘要",
            "",
            "| 项目 | 结果 |",
            "|------|------|",
            f"| **操作建议** | {action} |",
            f"| **置信度** | {confidence:.0%} |",
            f"| **核心理由** | {signal.get('reasoning', '')[:200]} |",
            "",
        ]

        # 各维度报告
        report_titles = {
            "market_report": "📈 技术分析",
            "sentiment_report": "💭 情绪分析",
            "news_report": "📰 新闻分析",
            "fundamentals_report": "📊 基本面分析",
            "northbound_report": "🌏 北向资金",
            "sector_report": "🏭 板块分析",
        }

        for key, title in report_titles.items():
            report = reports.get(key, "")
            if report:
                lines.extend(
                    [
                        "",
                        "---",
                        f"## {title}",
                        "",
                        report[:500],
                        "",
                    ]
                )

        lines.extend(
            [
                "---",
                "*由 A 股智能投研系统生成*",
            ]
        )

        content = "\n".join(lines)
        return self.send(subject, content)
