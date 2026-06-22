"""通知 API — 查询通知历史 + WebSocket 实时推送"""

from fastapi import APIRouter, Query

from services.notifier import get_recent_notifications
from shared.logging import emit_log

router = APIRouter()


@router.get("/recent")
def recent_notifications(
    limit: int = Query(50, ge=1, le=200),
    category: str = Query(None),
):
    """查询最近通知"""
    try:
        notifications = get_recent_notifications(limit=limit, category=category)
        return {"notifications": notifications, "count": len(notifications)}
    except Exception as e:
        emit_log("ERROR", "notifications", f"recent: {e}")
        return {"notifications": [], "error": str(e)}
