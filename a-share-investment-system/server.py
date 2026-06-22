"""AShare-X FastAPI 后端入口 — API + WebSocket + 静态前端 + 自动打开浏览器"""

import os
import sys
import warnings

from shared.version import VERSION

# 全局: 抑制第三方库噪音(baostock未关闭的socket / akshare tqdm进度条)
warnings.filterwarnings("ignore", category=ResourceWarning)
os.environ.setdefault("TQDM_DISABLE", "1")

# SOCKS proxy 清理: 如果未安装 socksio, 清除 PROXY 环境变量防止网络请求阻塞
try:
    import socksio  # noqa: F401
except ImportError:
    for _key in (
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "http_proxy",
        "https_proxy",
        "PROXY_URL",
        "ALL_PROXY",
    ):
        os.environ.pop(_key, None)

# Force IPv4 for outbound connections (Chinese financial APIs reject IPv6)
import socket as _socket

_old_gai = _socket.getaddrinfo


def _prefer_ipv4(host, port, family=0, type=0, proto=0, flags=0):
    results = _old_gai(host, port, _socket.AF_INET, type, proto, flags)
    if not results:
        results = _old_gai(host, port, family, type, proto, flags)
    return results


_socket.getaddrinfo = _prefer_ipv4

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import time as _time

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

app = FastAPI(title="AShare-X API", version=VERSION)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# ── 请求日志中间件 ──
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """记录所有 API 请求的耗时和状态码"""
    path = request.url.path
    if path.startswith("/ws/"):
        return await call_next(request)
    start = _time.time()
    response = await call_next(request)
    elapsed = (_time.time() - start) * 1000
    if elapsed > 1000:
        from shared.logging import emit_log

        emit_log(
            "WARNING", "api", f"{request.method} {path} → {response.status_code} ({elapsed:.0f}ms)"
        )
    return response


# ── 全局异常处理器 ──
class AppError(Exception):
    """业务逻辑异常 — 返回带可读message的4xx响应"""

    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError):
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.message, "ok": False},
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """全局兜底 — 所有未捕获异常的最终处理器"""
    from shared.logging import emit_log

    emit_log("ERROR", "server", f"Unhandled: {exc}")
    return JSONResponse(
        status_code=500,
        content={"error": f"Internal error: {exc}", "ok": False},
    )


# ── 注册 API 路由(必须在静态文件之前)──
from api.routes import (
    ai,
    analysis,
    data_quality,
    database,
    favorites,
    logs,
    market,
    portfolio,
    quant_agent,
    reports,
    risk,
    screening,
    settings,
    signals,
    system,
    tasks,
    workflow,
)

app.include_router(portfolio.router, prefix="/api/portfolio")
app.include_router(risk.router, prefix="/api/risk")
app.include_router(reports.router, prefix="/api/reports")
app.include_router(signals.router, prefix="/api/signals")
app.include_router(screening.router, prefix="/api/screening")
app.include_router(quant_agent.router, prefix="/api/quant-agent")
app.include_router(analysis.router, prefix="/api/analysis")
app.include_router(tasks.router, prefix="/api/tasks")
app.include_router(favorites.router, prefix="/api/favorites")

app.include_router(logs.router, prefix="/api/logs")
app.include_router(database.router, prefix="/api/db")
app.include_router(market.router, prefix="/api/market")
app.include_router(system.router, prefix="/api/system")

app.include_router(workflow.router, prefix="/api/workflow")
app.include_router(settings.router, prefix="/api/settings")
app.include_router(ai.router, prefix="/api/ai")
app.include_router(data_quality.router, prefix="/api/data-quality")

# ── 日志 ──
from shared.logging import emit_log


@app.on_event("startup")
async def startup():
    emit_log("INFO", "server", "Initializing database...")
    try:
        from shared.models import init_db, run_db_maintenance

        init_db()
        run_db_maintenance()
        emit_log("INFO", "server", "Database initialized + maintenance")
    except Exception as e:
        emit_log("ERROR", "server", f"DB init failed: {e}")

    try:
        from providers.cache import CacheManager

        CacheManager().invalidate()
        emit_log("INFO", "server", "Cache invalidated")
    except Exception as e:
        emit_log("INFO", "server", f"Cache skip: {e}")

    emit_log("INFO", "server", "Startup complete — warming cache in background")
    _preload_cache()

    try:
        from services.skill_engine import get_skill_engine

        se = get_skill_engine()
        emit_log("INFO", "server", f"SkillEngine: {len(se.skills)} skills discovered")
    except Exception as e:
        emit_log("INFO", "server", f"SkillEngine init: {e}")

    try:
        from services.master_agents import get_master_agents

        ma = get_master_agents()
        emit_log("INFO", "server", f"MasterAgents: {len(ma.get_all_names())} registered")
    except Exception as e:
        emit_log("INFO", "server", f"MasterAgents init: {e}")


@app.get("/api/health")
def health():
    emit_log("INFO", "server", "Health check")
    return {"status": "ok", "version": VERSION}


# ── WebSocket: 实时日志 ──

from fastapi import WebSocket, WebSocketDisconnect

_ws_clients = set()


@app.websocket("/ws/logs")
async def ws_logs(ws: WebSocket):
    """实时日志WebSocket — 推送内存缓冲区新增日志"""
    import asyncio
    import contextlib

    from shared.logging import get_logs_since

    await ws.accept()
    _ws_clients.add(ws)
    last_index = 0
    try:
        while True:
            logs, last_index = get_logs_since(last_index)
            for entry in logs:
                await ws.send_json(entry)
            # 等待客户端消息或1秒超时,保持连接并定期推送
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(ws.receive_text(), timeout=1.0)
    except WebSocketDisconnect:
        pass
    finally:
        _ws_clients.discard(ws)


# ── 静态前端(必须在所有 API 路由之后)──
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
STATIC_INDEX = os.path.join(STATIC_DIR, "index.html")
_HAS_STATIC = os.path.isdir(STATIC_DIR) and os.path.isfile(STATIC_INDEX)


@app.get("/{full_path:path}", include_in_schema=False)
async def serve_frontend(full_path: str = ""):
    """SPA catch-all — 静态文件服务 + 前端路由降级

    优先服务 static/ 目录下的已有文件(JS/CSS/图片等),
    非API路径且无对应文件时返回 index.html(SPA 路由降级)。
    """
    if not _HAS_STATIC:
        if full_path.startswith(("api/", "ws/")):
            return JSONResponse({"error": "Not found"}, status_code=404)
        from fastapi.responses import HTMLResponse

        return HTMLResponse(
            "<h1>AShare-X API Running</h1><p>Frontend not built. Run 'npm run build' in frontend/</p>"
        )

    # API / WebSocket 路径: 返回 JSON 404(已有路由定义不会走到这里,兜底)
    if full_path.startswith(("api/", "ws/")):
        return JSONResponse({"error": "Not found"}, status_code=404)

    # 尝试 static/ 目录下的确切文件
    safe_path = os.path.normpath(os.path.join(STATIC_DIR, full_path))
    if safe_path.startswith(os.path.normpath(STATIC_DIR)) and os.path.isfile(safe_path):
        return FileResponse(
            safe_path, headers={"Cache-Control": "no-cache, no-store, must-revalidate"}
        )

    # SPA 降级: 所有非 API 路径返回 index.html
    return FileResponse(
        STATIC_INDEX, headers={"Cache-Control": "no-cache, no-store, must-revalidate"}
    )


emit_log("INFO", "server", "AShare-X API starting on http://127.0.0.1:8765")


def _preload_cache():
    """warm up cache (indices + sectors) in background thread"""
    import threading

    def _run():
        try:
            from services.data_bus import DatabaseBackedDataBus

            db_path = os.path.join(os.path.dirname(__file__), "data", "investment.db")
            bus = DatabaseBackedDataBus(db_path=db_path)
            bus.get_market_indices()
            bus.get_sector_ranking()
            emit_log("INFO", "server", "cache warmed: indices + sectors")
        except Exception as e:
            emit_log("DEBUG", "server", f"cache warmup skipped: {e}")

    threading.Thread(target=_run, daemon=True).start()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8765)
