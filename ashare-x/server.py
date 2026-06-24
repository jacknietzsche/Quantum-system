"""FastAPI服务器入口。

启动时初始化数据库、预编译工作流图。
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from api.routes.analysis import router as analysis_router
from api.routes.backtest import router as backtest_router
from api.routes.data import router as data_router
from api.routes.portfolio import router as portfolio_router
from api.routes.reports import router as reports_router
from api.routes.screening import router as screening_router
from api.routes.settings import router as settings_router
from api.routes.trading_plan import router as trading_plan_router

logger = logging.getLogger("ashare-x.server")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期: 启动时初始化，关闭时清理。"""
    # 启动
    logger.info("AShare-X 服务器启动中...")

    # 初始化数据库
    try:
        from db.engine import init_db

        init_db()
        logger.info("数据库初始化完成")
    except Exception as e:
        logger.warning("数据库初始化失败: %s", e)

    # 初始化数据总线（确保表存在）
    try:
        from providers.data_bus import DatabaseFirstDataBus

        DatabaseFirstDataBus()
        logger.info("数据总线初始化完成")
    except Exception as e:
        logger.warning("数据总线初始化失败: %s", e)

    logger.info("AShare-X 服务器就绪")

    yield

    # 关闭
    logger.info("AShare-X 服务器关闭")


app = FastAPI(title="AShare-X", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(analysis_router)
app.include_router(backtest_router)
app.include_router(portfolio_router)
app.include_router(screening_router)
app.include_router(reports_router)
app.include_router(settings_router)
app.include_router(trading_plan_router)
app.include_router(data_router)


@app.get("/api/health")
async def health():
    return {"status": "ok"}


# Serve static frontend
static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    @app.get("/")
    async def index():
        return FileResponse(
            str(static_dir / "index.html"),
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0",
            },
        )
