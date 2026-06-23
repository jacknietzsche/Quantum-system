"""邮件发送服务。

支持 QQ 邮箱 SMTP(SSL), 用于手动推送交易计划到指定邮箱。
"""

from __future__ import annotations

import logging
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

from core.config import Config

logger = logging.getLogger("ashare-x.services.email_sender")


class EmailSender:
    """基于 SMTP 的邮件发送器, 默认适配 QQ 邮箱。"""

    DEFAULT_HOST = "smtp.qq.com"
    DEFAULT_PORT = 465
    DEFAULT_USE_SSL = True

    def __init__(self, config: Config | None = None) -> None:
        self.config = config or Config()

    def _cfg(self, key: str, default: Any = None) -> Any:
        """读取 email.* 配置。"""
        return self.config.get(f"email.{key}", default)

    def _get_credentials(self) -> tuple[str | None, str | None, str | None]:
        """返回 (sender, password, default_recipient)。

        优先从配置读取; 若未配置则尝试环境变量。
        """
        import os

        sender = self._cfg("sender") or os.getenv("ASHARE_X_EMAIL_SENDER")
        password = self._cfg("password") or os.getenv("ASHARE_X_EMAIL_PASSWORD")
        recipient = self._cfg("recipient") or os.getenv("ASHARE_X_EMAIL_RECIPIENT")
        return sender, password, recipient

    def is_configured(self) -> bool:
        """检查是否已配置发件邮箱和授权码。"""
        sender, password, _ = self._get_credentials()
        return bool(sender and password)

    def _send(
        self,
        recipient: str,
        subject: str,
        html_body: str,
        log_label: str,
    ) -> dict[str, Any]:
        """通用 SMTP 发送逻辑。"""
        sender, password, _ = self._get_credentials()
        if not sender or not password:
            return {"ok": False, "error": "未配置发件邮箱或授权码"}

        host = self._cfg("smtp_host") or self.DEFAULT_HOST
        port = int(self._cfg("smtp_port") or self.DEFAULT_PORT)
        use_ssl = bool(self._cfg("use_ssl", self.DEFAULT_USE_SSL))

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = sender
        msg["To"] = recipient
        msg.attach(MIMEText(html_body, "html", "utf-8"))

        try:
            server: Any
            if use_ssl:
                server = smtplib.SMTP_SSL(host, port, timeout=30)
            else:
                server = smtplib.SMTP(host, port, timeout=30)
                server.starttls()
            with server:
                server.login(sender, password)
                server.sendmail(sender, [recipient], msg.as_string())
            logger.info("%s已发送至 %s", log_label, recipient)
            return {"ok": True, "message": f"邮件已发送至 {recipient}"}
        except smtplib.SMTPAuthenticationError as e:
            logger.error("邮箱认证失败: %s", e)
            return {"ok": False, "error": "邮箱认证失败, 请检查发件邮箱和授权码"}
        except smtplib.SMTPException as e:
            logger.error("SMTP 发送失败: %s", e)
            return {"ok": False, "error": f"SMTP 发送失败: {e}"}
        except OSError as e:
            logger.error("网络连接失败: %s", e)
            return {"ok": False, "error": f"网络连接失败: {e}"}

    def send_test_email(self, recipient: str | None = None) -> dict[str, Any]:
        """发送一封测试邮件, 用于验证邮箱配置是否正确。"""
        _, _, default_recipient = self._get_credentials()
        recipient = recipient or default_recipient
        if not recipient:
            return {"ok": False, "error": "未指定收件人"}

        subject = "AShare-X 邮件配置测试"
        html_body = """
        <html>
        <body style="font-family:sans-serif;background:#0f172a;color:#e2e8f0;
                    padding:20px">
            <div style="max-width:600px;margin:0 auto;background:#1e293b;
                        border-radius:12px;padding:24px">
                <h2 style="color:#38bdf8">AShare-X 邮件配置测试</h2>
                <p>如果您收到这封邮件, 说明 QQ 邮箱推送配置正确。</p>
                <p style="color:#64748b;font-size:12px">
                    由 AShare-X 投研系统自动发送
                </p>
            </div>
        </body>
        </html>
        """
        return self._send(recipient, subject, html_body, "测试邮件")

    def send_plan(
        self,
        plan: dict[str, Any],
        recipient: str | None = None,
        holdings: list[dict] | None = None,
        trades: list[dict] | None = None,
    ) -> dict[str, Any]:
        """发送交易计划邮件。

        Args:
            plan: 交易计划字典(来自 DailyPlanGenerator)
            recipient: 收件人, 为空时使用配置中的默认收件人
            holdings: 当前持仓, 用于展示
            trades: 最近交易记录, 用于展示

        Returns:
            {"ok": True, "message": "..."} 或 {"ok": False, "error": "..."}
        """
        _, _, default_recipient = self._get_credentials()
        recipient = recipient or default_recipient
        if not recipient:
            return {"ok": False, "error": "未指定收件人"}

        subject, html_body = self._build_message(plan, holdings, trades)
        return self._send(recipient, subject, html_body, "交易计划邮件")

    def _build_message(
        self,
        plan: dict[str, Any],
        holdings: list[dict] | None,
        trades: list[dict] | None,
    ) -> tuple[str, str]:
        """构建邮件主题和 HTML 正文。"""
        date = plan.get("date", datetime.now().strftime("%Y-%m-%d"))
        market_state = plan.get("market_state", "NEUTRAL")
        actions = plan.get("actions", [])
        summary = plan.get("summary", "")

        state_map = {
            "BULL": ("牛市", "#34d399"),
            "BEAR": ("熊市", "#f87171"),
            "PANIC": ("恐慌", "#dc2626"),
            "OVERHEAT": ("过热", "#fbbf24"),
            "NEUTRAL": ("中性", "#60a5fa"),
        }
        state_text, state_color = state_map.get(market_state, (market_state, "#94a3b8"))

        subject = f"AShare-X 交易计划 [{date}] {state_text}"

        action_rows = []
        if actions:
            for a in actions:
                action = a.get("action", "HOLD")
                code = a.get("stock_code", "")
                name = a.get("stock_name", "")
                conf = a.get("confidence", 0)
                reason = a.get("reasoning", "")
                target = a.get("target_price")
                stop = a.get("stop_loss")
                tp = a.get("take_profit")
                target_td = f"<td>¥{target:.2f}</td>" if target else "<td>-</td>"
                stop_td = f"<td>¥{stop:.2f}</td>" if stop else "<td>-</td>"
                tp_td = f"<td>¥{tp:.2f}</td>" if tp else "<td>-</td>"
                action_rows.append(
                    f"<tr>"
                    f"<td><strong>{action}</strong></td>"
                    f"<td>{code} {name}</td>"
                    f"<td>{conf}%</td>"
                    f"{target_td}"
                    f"{stop_td}"
                    f"{tp_td}"
                    f"<td>{reason}</td>"
                    f"</tr>"
                )
        action_html = (
            "".join(action_rows)
            if action_rows
            else "<tr><td colspan='7'>今日无操作建议</td></tr>"
        )

        holding_rows = []
        if holdings:
            for h in holdings:
                pnl = h.get("pnl", 0)
                pnl_pct = h.get("pnl_pct", 0)
                color = "#34d399" if pnl >= 0 else "#f87171"
                holding_rows.append(
                    f"<tr>"
                    f"<td>{h.get('stock_code', '')} {h.get('stock_name', '')}</td>"
                    f"<td>{h.get('shares', 0)}</td>"
                    f"<td>¥{h.get('avg_cost', 0):.2f}</td>"
                    f"<td>¥{h.get('current_price', 0):.2f}</td>"
                    f"<td>¥{h.get('market_value', 0):,.0f}</td>"
                    f"<td style='color:{color}'>{pnl:+.0f} ({pnl_pct:+.1f}%)</td>"
                    f"</tr>"
                )
        holding_html = (
            "".join(holding_rows)
            if holding_rows
            else "<tr><td colspan='6'>暂无持仓</td></tr>"
        )

        trade_rows = []
        if trades:
            for t in trades[:10]:
                trade_rows.append(
                    f"<tr>"
                    f"<td>{t.get('trade_date', '')}</td>"
                    f"<td>{t.get('stock_code', '')} {t.get('stock_name', '')}</td>"
                    f"<td>{t.get('action', '')}</td>"
                    f"<td>{t.get('shares', 0)}</td>"
                    f"<td>¥{t.get('price', 0):.2f}</td>"
                    f"<td>{t.get('reasoning', '')}</td>"
                    f"</tr>"
                )
        trade_html = (
            "".join(trade_rows)
            if trade_rows
            else "<tr><td colspan='6'>暂无交易记录</td></tr>"
        )

        html = f"""
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                body {{
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
                    background: #0f172a; color: #e2e8f0; padding: 20px;
                }}
                .container {{
                    max-width: 800px; margin: 0 auto; background: #1e293b;
                    border-radius: 12px; padding: 24px;
                }}
                h1 {{ color: #38bdf8; font-size: 20px; margin-bottom: 8px; }}
                .subtitle {{ color: #64748b; font-size: 13px; margin-bottom: 20px; }}
                .badge {{
                    display: inline-block; padding: 4px 12px; border-radius: 12px;
                    font-size: 13px; font-weight: 600; background: {state_color};
                    color: #0f172a;
                }}
                h2 {{
                    color: #94a3b8; font-size: 15px; margin-top: 24px;
                    margin-bottom: 12px; border-bottom: 1px solid #334155;
                    padding-bottom: 8px;
                }}
                table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
                th {{
                    text-align: left; padding: 10px; background: #0f172a;
                    color: #64748b; border-bottom: 1px solid #334155;
                }}
                td {{ padding: 10px; border-bottom: 1px solid #334155; }}
                .summary {{
                    background: #0f172a; border-left: 3px solid #3b82f6;
                    padding: 12px; border-radius: 6px;
                    line-height: 1.6; white-space: pre-wrap;
                }}
                .footer {{
                    margin-top: 30px; padding-top: 16px;
                    border-top: 1px solid #334155; color: #475569; font-size: 12px;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>AShare-X 每日交易计划</h1>
                <div class="subtitle">
                    生成日期: {date} <span class="badge">{state_text}</span>
                </div>
                {f'<div class="summary">{summary}</div>' if summary else ''}

                <h2>今日操作建议</h2>
                <table>
                    <tr>
                        <th>操作</th><th>股票</th><th>置信度</th>
                        <th>目标价</th><th>止损</th><th>止盈</th><th>理由</th>
                    </tr>
                    {action_html}
                </table>

                <h2>当前持仓</h2>
                <table>
                    <tr>
                        <th>股票</th><th>持仓</th><th>成本</th>
                        <th>现价</th><th>市值</th><th>盈亏</th>
                    </tr>
                    {holding_html}
                </table>

                <h2>最近交易</h2>
                <table>
                    <tr>
                        <th>日期</th><th>股票</th><th>操作</th>
                        <th>股数</th><th>价格</th><th>理由</th>
                    </tr>
                    {trade_html}
                </table>

                <div class="footer">由 AShare-X AI 投研系统自动生成, 仅供参考。</div>
            </div>
        </body>
        </html>
        """
        return subject, html
