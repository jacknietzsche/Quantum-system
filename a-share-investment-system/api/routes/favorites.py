"""自选股API — CRUD管理"""

from fastapi import APIRouter

from api.schemas.routes import (
    AddFavoriteIn,
    FavoriteCheckOut,
    FavoriteListOut,
    OkResponse,
)
from services.watchlist import WatchlistService
from shared.db_session import db_session
from shared.models import StockInfo, Watchlist, get_session

router = APIRouter()


@router.get("", response_model=FavoriteListOut)
def list_favorites():
    """获取自选股列表"""
    try:
        service = WatchlistService(get_session)
        result = service.get_all()
        if result["status"] == "ok":
            # Convert to expected format for FavoriteListOut
            favorite_items = []
            for item in result["data"]:
                favorite_items.append(
                    {
                        "stock_code": item["stock_code"],
                        "stock_name": item["stock_name"],
                        "created_at": item["created_at"],
                        "current_price": item.get("latest_price", 0.0),
                        "pe_ratio": item.get("pe_ratio"),
                        "pb_ratio": item.get("pb_ratio"),
                        "industry": item.get("industry", ""),
                        "trend": item.get("trend", ""),
                        "change_pct": item.get("change_pct", 0.0),
                    }
                )
            return FavoriteListOut(data=favorite_items)
        return FavoriteListOut(data=[], error=result.get("message", "Unknown error"))
    except Exception as e:
        return FavoriteListOut(data=[], error=str(e))


@router.post("", response_model=OkResponse)
def add_favorite(data: AddFavoriteIn):
    """添加自选股"""
    code = data.stock_code.strip()
    if not code:
        return OkResponse(ok=False, error="stock_code required")
    try:
        service = WatchlistService(get_session)
        # 如果前端未提供名称,尝试从数据库获取真实名称
        name = data.stock_name
        if not name:
            # 尝试从StockInfo获取真实名称
            with db_session() as session:
                info = session.query(StockInfo).filter_by(stock_code=code).first()
                if info and info.stock_name:
                    name = info.stock_name
        # 如果仍然没有名称,使用代码作为备选
        if not name:
            name = code
        result = service.add(code=code, name=name)
        if result["status"] == "ok":
            # 自动触发数据填充
            try:
                from services.data_initializer import DataInitializer

                di = DataInitializer()
                di.populate_stock_list([code])
            except Exception as e:
                # 数据填充失败不影响添加成功
                from shared.logging import emit_log

                emit_log("WARNING", "favorites", f"添加后自动填充数据失败: {e}")
            return OkResponse(ok=True)
        return OkResponse(ok=False, error=result.get("message", "添加失败"))
    except Exception as e:
        return OkResponse(ok=False, error=str(e))


@router.delete("/{stock_code}", response_model=OkResponse)
def remove_favorite(stock_code: str):
    """删除自选股"""
    try:
        with db_session() as session:
            session.query(Watchlist).filter_by(stock_code=stock_code).delete()
        return OkResponse(ok=True)
    except Exception as e:
        return OkResponse(ok=False, error=str(e))


@router.get("/{stock_code}", response_model=FavoriteCheckOut)
def check_favorite(stock_code: str):
    """检查是否为自选股"""
    try:
        with db_session() as session:
            exists = session.query(Watchlist).filter_by(stock_code=stock_code).first() is not None
        return FavoriteCheckOut(is_favorite=exists, stock_code=stock_code)
    except Exception as e:
        return FavoriteCheckOut(is_favorite=False, error=str(e))
