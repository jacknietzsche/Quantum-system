"""报告路由。

从数据库查询分析报告。
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

logger = logging.getLogger("ashare-x.api.reports")

router = APIRouter(prefix="/api", tags=["reports"])


@router.get("/reports")
async def get_reports(limit: int = 20, ticker: str | None = None):
    """获取报告列表。"""
    try:
        from services.report import ReportGenerator

        gen = ReportGenerator()
        reports = gen.get_recent_reports(limit=limit)

        # 按ticker过滤
        if ticker:
            reports = [r for r in reports if r.get("ticker") == ticker]

        return {"reports": reports, "total": len(reports)}
    except Exception as e:
        logger.error("获取报告失败: %s", e)
        return {"reports": [], "total": 0, "error": str(e)}


@router.get("/reports/{report_id}")
async def get_report(report_id: str):
    """获取报告详情。"""
    try:
        from services.report import ReportGenerator

        gen = ReportGenerator()
        reports = gen.get_recent_reports(limit=100)

        for r in reports:
            if r.get("id") == report_id:
                return r

        raise HTTPException(404, f"报告 {report_id} 不存在")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("获取报告详情失败: %s", e)
        raise HTTPException(500, str(e)) from e
