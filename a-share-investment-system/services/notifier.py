"""统一通知推送服务 — 风控信号 → WebSocket + 邮件 + DB 记录

通知链路:
  风控引擎检测到异常 → create_notification() →
    1. 写入 SystemLog 表 (持久化)
    2. WebSocket 推送到前端 (实时)
    3. 邮件通知 (高优先级)

使用方式:
    from services.notifier import notify, notify_risk_alert, notify_signal

    notify_risk_alert("止损触发", "600519 跌破止损线 -10%", level="WARNING")
    notify_signal("买入信号", "000001 平安银行 置信度 85%")
"""

import json
from datetime import datetime
from enum import Enum

from shared.logging import emit_log


class NotificationLevel(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class NotificationChannel(str, Enum):
    WEBSOCKET = "websocket"
    EMAIL = "email"
    DB = "db"


# ── WebSocket 广播 ──

_ws_clients: set = set()


def register_ws_client(ws):
    """注册 WebSocket 客户端 (由 server.py 调用)"""
    _ws_clients.add(ws)


def unregister_ws_client(ws):
    """注销 WebSocket 客户端"""
    _ws_clients.discard(ws)


async def _broadcast_ws(notification: dict):
    """广播到所有 WebSocket 客户端"""
    if not _ws_clients:
        return
    data = json.dumps(notification, ensure_ascii=False, default=str)
    dead = set()
    for ws in _ws_clients:
        try:
            await ws.send_text(data)
        except Exception:
            dead.add(ws)
    _ws_clients.difference_update(dead)


# ── 核心通知函数 ──


def create_notification(
    title: str,
    message: str,
    level: NotificationLevel = NotificationLevel.INFO,
    category: str = "system",
    channels: list[NotificationChannel] | None = None,
    data: dict | None = None,
) -> dict:
    """创建通知 — 写DB + 推WebSocket + 邮件(高优先级)

    Args:
        title: 通知标题 (简短)
        message: 通知内容 (详细)
        level: 通知级别
        category: 分类 (risk/signal/system/workflow)
        channels: 推送渠道, 默认 [DB, WEBSOCKET]
        data: 附加数据 (如股票代码、指标值等)

    Returns:
        通知字典
    """
    if channels is None:
        channels = [NotificationChannel.DB, NotificationChannel.WEBSOCKET]

    notification = {
        "id": f"notif_{datetime.now().strftime('%Y%m%d%H%M%S%f')}",
        "title": title,
        "message": message,
        "level": level.value if isinstance(level, NotificationLevel) else level,
        "category": category,
        "data": data or {},
        "timestamp": datetime.now().isoformat(),
        "channels": [c.value if isinstance(c, NotificationChannel) else c for c in channels],
    }

    # 1. 写入 DB
    if NotificationChannel.DB in channels:
        _persist_to_db(notification)

    # 2. 记录日志
    log_level = level.value if isinstance(level, NotificationLevel) else level
    emit_log(log_level, f"notify:{category}", f"{title}: {message[:100]}")

    # 3. 邮件 (仅 WARNING 以上)
    if NotificationChannel.EMAIL in channels:
        _send_email_notification(notification)

    return notification


def _persist_to_db(notification: dict):
    """持久化到 SystemLog 表"""
    try:
        from shared.models import SystemLog, get_session

        session = get_session()
        try:
            log = SystemLog(
                module=f"notify:{notification['category']}",
                level=notification["level"],
                message=f"{notification['title']}: {notification['message']}",
            )
            session.add(log)
            session.commit()
        except Exception:
            session.rollback()
        finally:
            session.close()
    except Exception as e:
        emit_log("WARNING", "notifier", f"DB persist failed: {e}")


def _send_email_notification(notification: dict):
    """发送邮件通知"""
    try:
        from providers.email_sender import EmailSender

        sender = EmailSender()
        subject = f"[{notification['level']}] {notification['title']}"
        body = (
            f"时间: {notification['timestamp']}\n"
            f"级别: {notification['level']}\n"
            f"分类: {notification['category']}\n\n"
            f"{notification['message']}\n"
        )
        if notification.get("data"):
            body += f"\n附加数据:\n{json.dumps(notification['data'], ensure_ascii=False, indent=2)}"
        sender.send(subject, body)
    except Exception as e:
        emit_log("WARNING", "notifier", f"Email send failed: {e}")


# ── 便捷通知函数 ──


def notify_risk_alert(title: str, message: str, level: str = "WARNING", data: dict | None = None):
    """风控告警通知"""
    notif_level = (
        NotificationLevel(level)
        if level in NotificationLevel.__members__
        else NotificationLevel.WARNING
    )
    channels = [NotificationChannel.DB, NotificationChannel.WEBSOCKET]
    if notif_level in (NotificationLevel.ERROR, NotificationLevel.CRITICAL):
        channels.append(NotificationChannel.EMAIL)
    return create_notification(
        title=title,
        message=message,
        level=notif_level,
        category="risk",
        channels=channels,
        data=data,
    )


def notify_signal(title: str, message: str, data: dict | None = None):
    """交易信号通知"""
    return create_notification(
        title=title,
        message=message,
        level=NotificationLevel.INFO,
        category="signal",
        data=data,
    )


def notify_workflow(title: str, message: str, data: dict | None = None):
    """工作流状态通知"""
    return create_notification(
        title=title,
        message=message,
        level=NotificationLevel.INFO,
        category="workflow",
        data=data,
    )


# ── 通知历史查询 ──


def get_recent_notifications(limit: int = 50, category: str | None = None) -> list[dict]:
    """查询最近通知 (从 SystemLog 中读取 notify: 前缀的记录)"""
    try:
        from shared.models import SystemLog, get_session

        session = get_session()
        try:
            query = session.query(SystemLog).filter(SystemLog.module.like("notify:%"))
            if category:
                query = query.filter(SystemLog.module == f"notify:{category}")
            rows = query.order_by(SystemLog.created_at.desc()).limit(limit).all()
            return [
                {
                    "module": r.module,
                    "level": r.level,
                    "message": r.message,
                    "time": r.created_at.isoformat() if r.created_at else "",
                }
                for r in rows
            ]
        finally:
            session.close()
    except Exception as e:
        emit_log("WARNING", "notifier", f"Query failed: {e}")
        return []
