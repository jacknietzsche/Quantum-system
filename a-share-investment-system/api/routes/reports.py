"""报告API — 历史分析报告管理"""

import io
import json

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from api.schemas.routes import (
    LatestBySymbolsIn,
    LatestBySymbolsOut,
    OkResponse,
    ReportDetailOut,
    ReportListOut,
)
from shared.db_session import db_session
from shared.models import AnalysisTask, ScreenResult

router = APIRouter()


@router.get("", response_model=ReportListOut)
def list_reports(stock_code: str = "", limit: int = 50, offset: int = 0):
    """报告列表(前端Reports页面使用)"""
    try:
        with db_session() as session:
            query = session.query(AnalysisTask).filter(AnalysisTask.status == "completed")
            if stock_code:
                query = query.filter(AnalysisTask.stock_code == stock_code)
            total = query.count()
            tasks = (
                query.order_by(AnalysisTask.finished_at.desc()).offset(offset).limit(limit).all()
            )
            # Extract data while session is open to avoid detached instance errors
            reports = [
                {
                    "id": t.task_id,
                    "stock_code": t.stock_code,
                    "stock_name": t.stock_name,
                    "analysis_date": str(t.finish_time or t.created_at)[:10],
                    "signal": t.signal,
                    "confidence": t.confidence,
                }
                for t in tasks
            ]
        return ReportListOut(reports=reports, total=total)  # type: ignore[arg-type]
    except Exception as e:
        return ReportListOut(reports=[], total=0, error=str(e))


@router.post("/latest-by-symbols", response_model=LatestBySymbolsOut)
def latest_by_symbols(data: LatestBySymbolsIn):
    """按股票代码批量获取最新报告(前端TrackingBoard使用)"""
    try:
        symbols = data.symbols
        if not symbols:
            return LatestBySymbolsOut(reports=[])
        with db_session() as session:
            results = []
            for sym in symbols:
                t = (
                    session.query(AnalysisTask)
                    .filter(AnalysisTask.stock_code == sym, AnalysisTask.status == "completed")
                    .order_by(AnalysisTask.finished_at.desc())
                    .first()
                )
                if t:
                    results.append(
                        {
                            "id": t.task_id,
                            "stock_code": t.stock_code,
                            "signal": t.signal,
                            "confidence": t.confidence,
                            "analysis_date": str(t.finish_time or t.created_at)[:10],
                        }
                    )
        return LatestBySymbolsOut(reports=results)  # type: ignore[arg-type]
    except Exception as e:
        return LatestBySymbolsOut(reports=[], error=str(e))


@router.get("/{report_id}", response_model=ReportDetailOut)
def get_report(report_id: str):
    """报告详情(前端ReportDetail页面使用)"""
    try:
        with db_session() as session:
            t = session.query(AnalysisTask).filter_by(task_id=report_id).first()
            if not t:
                return ReportDetailOut(error="not found")
            result = json.loads(t.result_json) if t.result_json else {}
            # Extract data while session is open
            task_id = t.task_id
            stock_code = t.stock_code
            stock_name = t.stock_name
            analysis_date = str(t.finish_time or t.created_at)[:10]
            signal = t.signal
            confidence = t.confidence
        return ReportDetailOut(
            id=task_id,
            stock_code=stock_code,
            stock_name=stock_name,
            analysis_date=analysis_date,
            signal=signal,
            confidence=confidence,
            content=json.dumps(result, ensure_ascii=False, indent=2),
            result=result,
        )
    except Exception as e:
        return ReportDetailOut(error=str(e))


@router.delete("/{report_id}", response_model=OkResponse)
def delete_report(report_id: str):
    """删除报告"""
    try:
        with db_session() as session:
            session.query(AnalysisTask).filter_by(task_id=report_id).delete()
        return OkResponse(ok=True)
    except Exception as e:
        return OkResponse(ok=False, error=str(e))


@router.get("/{report_id}/download")
def download_report(report_id: str, format: str = "markdown"):
    """下载报告文件"""
    try:
        with db_session() as session:
            t = session.query(AnalysisTask).filter_by(task_id=report_id).first()
            if not t or not t.result_json:
                return {"error": "not found"}
            result = json.loads(t.result_json)
            # Extract data while session is open
            stock_name = t.stock_name or t.stock_code
            stock_code = t.stock_code
            finish_time = t.finish_time or t.created_at
            signal = t.signal or "-"
            confidence = t.confidence or 0

        content = f"# {stock_name}({stock_code}) \u5206\u6790\u62a5\u544a\n\n"
        content += f"**\u65e5\u671f**: {str(finish_time)[:10]}\n"
        content += f"**\u4fe1\u53f7**: {signal} | **\u7f6e\u4fe1\u5ea6**: {confidence}%\n\n"
        content += "## 完整数据\n\n```json\n"
        content += json.dumps(result, ensure_ascii=False, indent=2)
        content += "\n```"

        return StreamingResponse(
            io.BytesIO(content.encode("utf-8")),
            media_type="text/markdown; charset=utf-8",
            headers={"Content-Disposition": f"attachment; filename={stock_code}_report.md"},
        )
    except Exception as e:
        return {"error": str(e)}


@router.get("/screening/{run_id}/download")
def download_screening_report(run_id: str, format: str = "markdown"):
    """Download category-based screening report."""
    try:
        with db_session() as session:
            row = session.query(ScreenResult).filter_by(run_id=run_id).first()
            if not row or not row.recommendations_json:
                return {"error": "Screening result not found"}
            data = json.loads(row.recommendations_json)
        style = data.get("style", "unknown")
        categories = data.get("categories", {})
        total = data.get("total_screened", 0)
        created = str(row.created_at)[:10] if row and row.created_at else "unknown"
        cat_names = {
            "star": "STAR",
            "chinext": "ChiNext",
            "main": "Main",
            "etf": "ETF",
            "lof": "LOF",
        }
        lines = ["# AShare-X Screening Report", ""]
        lines.append("Date: " + created)
        lines.append("Universe: " + str(total) + " stocks")
        lines.append("Style: " + style)
        lines.append("")
        for cat_key, cat_data in categories.items():
            cat_name = cat_data.get("category_name", cat_names.get(cat_key, cat_key))
            recs = cat_data.get("recommendations", [])
            cat_total = cat_data.get("total", 0)
            lines.append("## " + cat_name + " (" + str(len(recs)) + "/" + str(cat_total) + ")")
            lines.append("")
            if not recs:
                lines.append("*No recommendations*")
                lines.append("")
                continue
            lines.append("| # | Code | Name | Industry | Score | Signal |")
            lines.append("|---|------|------|----------|-------|--------|")
            for rec in recs:
                r = str(rec.get("rank", "-"))
                cd = rec.get("stock_code", "-")
                nm = rec.get("stock_name", "-")
                ind = rec.get("industry", "-")
                sc = str(rec.get("score", 0))
                sg = rec.get("signal", "-")
                lines.append(
                    "| "
                    + r
                    + " | "
                    + cd
                    + " | "
                    + nm
                    + " | "
                    + ind
                    + " | "
                    + sc
                    + " | "
                    + sg
                    + " |"
                )
            lines.append("")
        total_recs = sum(len(v.get("recommendations", [])) for v in categories.values())
        lines.append(
            "Total: "
            + str(total_recs)
            + " recommendations, "
            + str(len(categories))
            + " categories"
        )
        content_md = chr(10).join(lines)
        return StreamingResponse(
            io.BytesIO(content_md.encode("utf-8")),
            media_type="text/markdown; charset=utf-8",
            headers={
                "Content-Disposition": "attachment; filename=screening_"
                + style
                + "_"
                + created
                + ".md"
            },
        )
    except Exception as e:
        return {"error": str(e)}


@router.post("/{report_id}/send-email")
def send_report_email(report_id: str):
    """????????"""
    try:
        with db_session() as session:
            t = session.query(AnalysisTask).filter_by(task_id=report_id).first()
            if not t or not t.result_json:
                return {"ok": False, "error": "report not found"}
            _result = json.loads(t.result_json)
            # Extract data while session is open
            stock_name = t.stock_name or t.stock_code
            stock_code = t.stock_code
            finish_time = str(t.finish_time or t.created_at)[:10]
            signal = t.signal or "-"
            confidence = t.confidence or 0

        # Build email content
        subject = f"📊 {stock_name}({stock_code}) 投研报告 - {finish_time[:10]}"

        # Professional report format
        signal = signal or "-"
        confidence = confidence or 0
        html_body = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"></head>
<body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI','PingFang SC',sans-serif;
     line-height:1.7;color:#24292e;max-width:800px;margin:0 auto;padding:20px;">
<div style="background:linear-gradient(135deg,#1a5276,#2e86c1);color:white;padding:24px
    30px;border-radius:12px;margin-bottom:20px;">
  <h1 style="margin:0 0 8px;">{stock_name} ({stock_code})</h1>
  <p style="opacity:0.85;margin:0;">投研报告 | {finish_time[:10]}</p>
</div>
<div style="background:white;border:1px solid #e1e4e8;border-radius:8px;
     padding:20px;margin-bottom:16px;">
  <h2 style="color:#1a5276;border-bottom:2px solid #2e86c1;padding-bottom:6px;">交易信号</h2>
  <table style="width:100%;border-collapse:collapse;">
    <tr><td style="padding:8px;font-weight:600;">信号</td>
        <td style="padding:8px;">{signal}</td></tr>
    <tr><td style="padding:8px;font-weight:600;">置信度</td>
        <td style="padding:8px;">{confidence}%</td></tr>
  </table>
</div>
<div style="background:#f8f9fa;border-radius:8px;padding:16px;font-size:13px;color:#666;">
  <p>本报告由 A股智能投研系统 自动生成，仅供参考，不构成投资建议。</p>
</div>
</body></html>"""

        plain_body = f"{stock_name}({stock_code}) 投研报告\n信号: {signal}\n置信度: {confidence}%"

        # Send via EmailSender
        from providers.email_sender import EmailSender

        sender = EmailSender()
        ok = sender.send(subject, plain_body, html=html_body)

        return {"ok": ok, "message": "email sent" if ok else "email send failed"}
    except Exception as e:
        return {"ok": False, "error": str(e)}
