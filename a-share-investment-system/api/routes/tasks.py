"""任务中心API — 分析任务CRUD"""

import json
import logging

from fastapi import APIRouter

logger = logging.getLogger(__name__)
from datetime import datetime

from api.schemas.routes import (
    OkResponse,
    TaskDetailOut,
    TaskListOut,
    TaskQueueOut,
)
from shared.db_session import db_session
from shared.models import AnalysisTask

router = APIRouter()


@router.post("", response_model=OkResponse)
def create_task(params: dict | None = None):
    """创建分析任务(前端可通过此接口发起分析)"""
    if params is None:
        params = {}
    try:
        stock_code = params.get("stock_code", "")
        stock_name = params.get("stock_name", "")
        if not stock_code:
            return OkResponse(ok=False, error="stock_code required")
        with db_session() as session:
            import uuid

            # Look up stock_name from database if not provided
            if not stock_name:
                from shared.models import StockInfo

                info = session.query(StockInfo).filter_by(stock_code=stock_code).first()
                stock_name = info.stock_name if info and info.stock_name else stock_code
            task = AnalysisTask(
                task_id=str(uuid.uuid4())[:8],
                stock_code=stock_code,
                stock_name=stock_name,
                status="pending",
            )
            session.add(task)
            task_id = task.task_id
        return OkResponse(ok=True, data={"task_id": task_id})
    except Exception as e:
        return OkResponse(ok=False, error=str(e))


@router.get("", response_model=TaskListOut)
def list_tasks(status: str = "", limit: int = 50, offset: int = 0):
    """任务列表"""
    try:
        with db_session() as session:
            q = session.query(AnalysisTask)
            if status:
                q = q.filter(AnalysisTask.status == status)
            total = q.count()
            rows = q.order_by(AnalysisTask.created_at.desc()).offset(offset).limit(limit).all()
            # Extract data while session is open
            tasks = []
            for r in rows:
                tasks.append(
                    {
                        "id": r.task_id or "",
                        "task_id": r.task_id or "",
                        "stock_code": r.stock_code or "",
                        "stock_name": r.stock_name or "",
                        "status": r.status or "",
                        "signal": r.signal or "",
                        "confidence": r.confidence or 0,
                        "progress": r.progress or 0,
                        "error": r.error or "",
                        "created_at": str(r.created_at)[:19] if r.created_at else "",
                        "finish_time": str(r.finish_time)[:19] if r.finish_time else "",
                    }
                )
        return TaskListOut(tasks=tasks, total=total)  # type: ignore[arg-type]
    except Exception as e:
        return TaskListOut(tasks=[], total=0, error=str(e))


@router.get("/{task_id}", response_model=TaskDetailOut)
def task_detail(task_id: str):
    """任务详情"""
    try:
        with db_session() as session:
            r = session.query(AnalysisTask).filter_by(task_id=task_id).first()
            if not r:
                return TaskDetailOut(error="task not found")
            # Extract data while session is open
            result = {}
            if r.result_json:
                try:
                    result = json.loads(r.result_json)
                except Exception as _e:
                    logger.warning("Suppressed: %s", _e)
            return TaskDetailOut(
                id=r.task_id,
                task_id=r.task_id,
                stock_code=r.stock_code,
                stock_name=r.stock_name,
                status=r.status,
                signal=r.signal,
                confidence=r.confidence,
                progress=r.progress,
                result=result,
                error=r.error,
                created_at=str(r.created_at)[:19] if r.created_at else "",
                finish_time=str(r.finish_time)[:19] if r.finish_time else "",
            )
    except Exception as e:
        return TaskDetailOut(error=str(e))


@router.post("/{task_id}/cancel", response_model=OkResponse)
def cancel_task(task_id: str):
    """取消任务"""
    try:
        with db_session() as session:
            task = session.query(AnalysisTask).filter_by(task_id=task_id).first()
            if task:
                task.status = "cancelled"
                task.finish_time = datetime.now()
        return OkResponse(ok=True)
    except Exception as e:
        return OkResponse(ok=False, error=str(e))


@router.delete("/{task_id}", response_model=OkResponse)
def delete_task(task_id: str):
    """删除任务"""
    try:
        with db_session() as session:
            session.query(AnalysisTask).filter_by(task_id=task_id).delete()
        return OkResponse(ok=True)
    except Exception as e:
        return OkResponse(ok=False, error=str(e))


@router.get("/queue", response_model=TaskQueueOut)
def task_queue():
    """队列状态"""
    try:
        with db_session() as session:
            running = session.query(AnalysisTask).filter_by(status="running").count()
            queued = session.query(AnalysisTask).filter_by(status="pending").count()
            total = session.query(AnalysisTask).count()
        return TaskQueueOut(running=running, queued=queued, total=total)
    except Exception as _e:
        logger.warning("Suppressed: %s", _e)
        return TaskQueueOut(running=0, queued=0, total=0)
