"""执行日志API — 实时排查错误(统一使用 shared.logging 作为日志源)"""

import glob
import os

from fastapi import APIRouter, Query

from shared.logging import get_log_buffer

router = APIRouter()


@router.get("/recent")
def recent_logs(limit: int = Query(100, ge=1, le=500), level: str = Query("all")):
    """获取最近N条日志,可按级别过滤"""
    all_logs = get_log_buffer()
    if level != "all":
        filtered = [entry for entry in all_logs if entry["level"] == level.upper()]
    else:
        filtered = all_logs
    return {
        "total": len(all_logs),
        "filtered": len(filtered),
        "logs": filtered[-limit:],
    }


@router.get("/server-log")
def server_log(lines: int = Query(200, ge=10, le=1000)):
    """读取 Python 后端最近的 print/stderr 输出(通过临时日志文件)"""
    log_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
    server_logs = []

    if os.path.isdir(log_dir):
        log_files = sorted(
            glob.glob(os.path.join(log_dir, "*.log")),
            key=os.path.getmtime,
            reverse=True,
        )
        for lf in log_files[:3]:
            try:
                with open(lf, encoding="utf-8", errors="replace") as f:
                    content = f.read()
                server_logs.append({"file": os.path.basename(lf), "content": content[-5000:]})
            except Exception:
                pass

    # 如果logs目录为空,返回内存日志
    if not server_logs:
        all_logs = get_log_buffer()
        server_logs.append(
            {
                "file": "memory_buffer",
                "content": "\n".join(
                    f"[{entry['ts']}] [{entry['level']}] {entry['module']}: {entry['msg']}"
                    for entry in all_logs[-lines:]
                ),
            }
        )

    all_logs = get_log_buffer()
    return {"files": server_logs, "memory_buffer_size": len(all_logs)}


@router.get("/errors")
def error_summary():
    """返回最近的错误摘要"""
    all_logs = get_log_buffer()
    errors = [entry for entry in all_logs if entry["level"] in ("ERROR", "CRITICAL")]
    by_module: dict[str, list] = {}
    for e in errors[-200:]:
        by_module.setdefault(e["module"], []).append(e)

    return {
        "total_errors": len(errors),
        "recent_errors": errors[-20:],
        "by_module": {k: len(v) for k, v in by_module.items()},
    }


@router.delete("/clear")
def clear_logs():
    """清空共享内存日志缓冲区"""
    buf = get_log_buffer()
    count = len(buf)
    buf.clear()
    return {"cleared": count}
