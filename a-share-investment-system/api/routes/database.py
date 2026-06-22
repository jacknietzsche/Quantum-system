"""数据库管理API"""

import logging
import os
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query

from services.data_explorer import DataExplorer
from services.data_initializer import DataInitializer
from services.trading_calendar import TradingCalendar
from shared.db_session import db_session
from shared.models import KlineCache, MarketSnapshot, StockInfo

logger = logging.getLogger(__name__)
from sqlalchemy import func, or_

from api.deps import get_db
from api.schemas.database import (
    AddStockIn,
    DbStatsOut,
    EditStockIn,
    HotStocksOut,
    IndustryDistOut,
    KlineOut,
    OkResponse,
    StockInfoListOut,
)
from providers.market_data import MarketDataProvider
from shared.logging import emit_log

router = APIRouter()

_DATA_SOURCES = [
    "tencent",
    "sina",
    "akshare",
    "tushare",
    "baostock",
    "efinance",
    "tickflow",
    "yfinance",
    "adata",
    "zzshare",
]


@router.get("/source-test")
def source_test():
    """逐一测试所有数据源连接 — 返回延迟+状态"""
    try:
        p = MarketDataProvider()
        results = p.test_all_sources()
        ok_count = sum(1 for r in results.values() if r["ok"])
        return {
            "sources": results,
            "ok": ok_count,
            "total": len(results),
            "chain": " -> ".join(_DATA_SOURCES),
        }
    except Exception as e:
        return {"error": str(e)}


@router.get("/source-status")
def source_status():
    """各数据源健康状态(断路器+可用性)"""
    try:
        p = MarketDataProvider()
        return {"sources": p.get_source_status(), "chain": " -> ".join(_DATA_SOURCES)}
    except Exception as e:
        return {"error": str(e), "chain": " -> ".join(_DATA_SOURCES)}


@router.get("/db-session-check")
def check_db_session(db=Depends(get_db)):  # noqa: B008
    """验证 DI 注入的 DB session 正常工作"""
    from shared.models import StockInfo

    count = db.query(StockInfo).count()
    return {"status": "ok", "session_active": True, "stock_count": count}


@router.get("/stats", response_model=DbStatsOut)
def db_stats():
    """数据库统计:总股票数、最新更新、数据源链 + 源健康状态"""
    start = __import__("time").time()
    try:
        with db_session() as session:
            stock_count = session.query(StockInfo).filter(StockInfo.latest_price > 0).count()
            kline_count = session.query(KlineCache).count()
            snap_count = session.query(MarketSnapshot).count()
            latest = (
                session.query(StockInfo.updated_at).order_by(StockInfo.updated_at.desc()).first()
            )
            last_kline = session.query(func.max(KlineCache.trade_date)).scalar()

        p = MarketDataProvider()
        src_status = p.get_source_status()

        # 计算数据新鲜度
        needs_refresh = False
        refresh_hint = ""
        if stock_count == 0:
            needs_refresh = True
            refresh_hint = "数据库为空, 需要初始化"
        elif latest and latest[0]:
            try:
                latest_time = datetime.strptime(str(latest[0])[:19], "%Y-%m-%d %H:%M:%S")
                hours_old = (datetime.now() - latest_time).total_seconds() / 3600
                if hours_old > 24:  # 超过24小时未更新
                    needs_refresh = True
                    refresh_hint = f"数据已过时({int(hours_old)}小时), 建议刷新"
            except Exception as _e:
                logger.warning("Suppressed: %s", _e)

        # 计算数据库文件大小
        db_size_mb = 0.0
        try:
            db_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                "data",
                "investment.db",
            )
            if os.path.exists(db_path):
                db_size_mb = round(os.path.getsize(db_path) / (1024 * 1024), 2)
        except Exception as e:
            emit_log("WARNING", "database", f"读取 DB 体积失败: {e}")

        elapsed = round((__import__("time").time() - start) * 1000)
        logger.info(
            f"[DB] stats: {stock_count} stocks, {kline_count} klines, {db_size_mb}MB ({elapsed}ms)"
        )

        return {
            "stock_count": stock_count,
            "kline_count": kline_count,
            "last_kline_date": last_kline,
            "snapshot_count": snap_count,
            "latest_update": str(latest[0])[:19] if latest and latest[0] else "never",
            "data_sources": _DATA_SOURCES,
            "source_chain": " -> ".join(_DATA_SOURCES),
            "source_status": src_status,
            "needs_refresh": needs_refresh,
            "refresh_hint": refresh_hint,
            "db_size_mb": db_size_mb,
            "startup_time_ms": elapsed,
        }
    except Exception as e:
        logger.error(f"[DB] stats failed: {e}")
        return {"error": str(e), "stock_count": 0}


@router.get("/stockinfo", response_model=StockInfoListOut)
def list_stocks(
    search: str = "",
    sort: str = "stock_code",
    order: str = "asc",
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=500),
):
    """StockInfo列表(搜索+排序+分页)"""
    try:
        with db_session() as session:
            q = session.query(StockInfo)
            if search:
                q = q.filter(
                    (StockInfo.stock_code.contains(search))
                    | (StockInfo.stock_name.contains(search))
                )
            col = getattr(StockInfo, sort, StockInfo.stock_code)
            q = q.order_by(col.asc() if order == "asc" else col.desc())
            total = q.count()
            rows = q.offset((page - 1) * limit).limit(limit).all()
            return {
                "total": total,
                "page": page,
                "limit": limit,
                "stocks": [{c.name: getattr(r, c.name) for c in r.__table__.columns} for r in rows],
            }
    except Exception as e:
        return {"error": str(e), "stocks": [], "total": 0}


@router.post("/stockinfo", response_model=OkResponse)
def add_stock(data: AddStockIn):
    """手动添加股票"""
    try:
        code = data.stock_code.strip()
        if not code:
            return {"ok": False, "error": "stock_code required"}
        with db_session() as session:
            existing = session.query(StockInfo).filter_by(stock_code=code).first()
            if existing:
                return {"ok": False, "error": f"{code} already exists"}
            info = StockInfo(
                stock_code=code,
                stock_name=data.stock_name or code,
                latest_price=float(data.price or 0),
                pe_ratio=float(data.pe or 0),
                pb_ratio=float(data.pb or 0),
                roe=float(data.roe or 0),
                industry=data.industry or "",
                updated_at=datetime.now(),
            )
            session.add(info)
        emit_log("INFO", "db", f"手动添加: {code} {data.stock_name or ''}")
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.put("/stockinfo/{code}", response_model=OkResponse)
def edit_stock(code: str, data: EditStockIn):
    """编辑股票信息"""
    try:
        with db_session() as session:
            info = session.query(StockInfo).filter_by(stock_code=code).first()
            if not info:
                return {"ok": False, "error": f"{code} not found"}
            for field in ["stock_name", "industry", "trend"]:
                val = getattr(data, field, None)
                if val is not None:
                    setattr(info, field, val)
            for field in [
                "latest_price",
                "pe_ratio",
                "pb_ratio",
                "roe",
                "gross_margin",
                "eps",
                "bvps",
                "debt_to_equity",
                "net_income",
            ]:
                val = getattr(data, field, None)
                if val is not None:
                    setattr(info, field, float(val or 0))
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.delete("/stockinfo/{code}")
def delete_stock(code: str):
    """删除股票"""
    try:
        with db_session() as session:
            session.query(StockInfo).filter_by(stock_code=code).delete()
        emit_log("INFO", "db", f"删除: {code}")
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.post("/refresh")
def refresh_stocks(data: dict):
    """触发数据刷新 — mode: 'hot'(热榜100) / 'full'(全市场500) / codes指定"""
    import time as _time

    t0 = _time.time()
    mode = data.get("mode", "hot")
    codes = data.get("codes", [])
    try:
        di = DataInitializer()

        # 检查数据源状态
        from providers.market_data import MarketDataProvider

        md = MarketDataProvider()
        src_status = md.get_source_status()
        available = [n for n, s in src_status.items() if s.get("available")]
        emit_log("INFO", "db", f"[刷新] 数据源可用: {available} / 全部: {list(src_status.keys())}")

        if codes:
            emit_log("INFO", "db", f"[刷新] 手动刷新指定 {len(codes)} 只: {codes[:5]}...")
            result = di.populate_stock_list(codes)
        elif mode == "full":
            max_n = data.get("max_stocks", 10000)
            emit_log("INFO", "db", f"[刷新] 全市场刷新开始 (最多{max_n}只)...")
            result = di.refresh_full_universe(max_stocks=max_n, force_refresh=True)
        else:
            emit_log("INFO", "db", "[刷新] 热榜刷新开始 Top 100...")
            result = di.refresh_hot_stocks()

        elapsed = round(_time.time() - t0, 1)
        result_data = result.data if hasattr(result, "data") else result
        emit_log("INFO", "db", f"[刷新] 完成! 耗时{elapsed}s | {result_data}")
        return {"ok": True, "result": result_data}
    except Exception as e:
        elapsed = round(_time.time() - t0, 1)
        emit_log("ERROR", "db", f"[刷新] 失败(耗时{elapsed}s): {e}")
        return {"ok": False, "error": str(e)}


@router.get("/kline/{code}", response_model=KlineOut)
def get_kline(code: str, days: int = Query(30, ge=5, le=365)):
    """K线数据查询"""
    try:
        with db_session() as session:
            rows = (
                session.query(KlineCache)
                .filter_by(stock_code=code)
                .order_by(KlineCache.trade_date.desc())
                .limit(days)
                .all()
            )
            return {
                "code": code,
                "count": len(rows),
                "klines": [
                    {
                        "date": r.trade_date,
                        "open": r.open,
                        "close": r.close,
                        "high": r.high,
                        "low": r.low,
                        "volume": r.volume,
                    }
                    for r in rows
                ],
            }
    except Exception as e:
        return {"error": str(e)}


@router.get("/snapshots")
def list_snapshots():
    """MarketSnapshot列表"""
    try:
        with db_session() as session:
            rows = (
                session.query(MarketSnapshot)
                .order_by(MarketSnapshot.updated_at.desc())
                .limit(50)
                .all()
            )
            return {
                "count": len(rows),
                "snapshots": [
                    {"type": r.snapshot_type, "updated": str(r.updated_at)[:19]} for r in rows
                ],
            }
    except Exception as e:
        return {"error": str(e)}


@router.get("/hot-stocks", response_model=HotStocksOut)
def hot_stocks(limit: int = Query(50, ge=1, le=200)):
    """热榜股票 — DB优先 + 空库自动填充"""
    import time as _time

    t0 = _time.time()
    try:
        with db_session() as session:
            valid_count = session.query(StockInfo).filter(StockInfo.latest_price > 0).count()
        emit_log("INFO", "db", f"[热榜] StockInfo表有效数据: {valid_count}只")

        if valid_count == 0:
            emit_log("INFO", "db-hot-stocks", "StockInfo表为空, 触发自动填充热榜股票...")
            di = DataInitializer()
            result = di.populate_stock_list()
            if result.data.get("success", 0) > 0:
                emit_log(
                    "INFO", "db-hot-stocks", f"自动填充成功: {result.data.get('success')} 只股票"
                )
            else:
                emit_log("WARNING", "db-hot-stocks", "自动填充失败, 返回空数据")

        with db_session() as session:
            rows = (
                session.query(StockInfo)
                .filter(StockInfo.latest_price > 0)
                .order_by(StockInfo.amount.desc())
                .limit(limit)
                .all()
            )
            stocks = [
                {
                    "code": r.stock_code,
                    "name": r.stock_name or r.stock_code,
                    "price": r.latest_price or 0,
                    "change_pct": r.change_pct or 0,
                    "turnover_rate": r.turnover_rate or 0,
                    "market_cap": r.total_market_cap or 0,
                }
                for r in rows
            ]

        missing = sum(1 for s in stocks if s["price"] == 0)
        elapsed = round(_time.time() - t0, 1)
        emit_log("INFO", "db", f"[热榜] 返回{len(stocks)}只, 其中{missing}只无价格, 耗时{elapsed}s")
        return {
            "stocks": stocks,
            "count": len(stocks),
            "source": "db+datainitializer",
            "missing_data": missing,
            "hint": "数据已自动填充"
            if valid_count == 0 and missing == 0
            else ("点刷新热榜填充数据" if missing > 0 else ""),
        }
    except Exception as e:
        elapsed = round(_time.time() - t0, 1)
        emit_log("ERROR", "db", f"[热榜] 失败(耗时{elapsed}s): {e}")
        return {"error": str(e), "stocks": [], "count": 0}


@router.get("/lhb")
def lhb_list(date: str | None = None, limit: int = Query(50, ge=10, le=200)):
    """龙虎榜真实数据 — DB优先, LHBAdapter降级"""
    import time as _lhb_t

    t0 = _lhb_t.time()
    try:
        tc = TradingCalendar()
        data_date = date or tc.effective_data_date()
        if data_date is None:
            data_date = datetime.now().strftime("%Y-%m-%d")
        # DB 缓存优先
        try:
            from shared.models import DragonTiger, get_session

            session = get_session()
            try:
                rows = session.query(DragonTiger).filter_by(trade_date=data_date).limit(limit).all()
                if rows:
                    stocks = [
                        {
                            "code": r.stock_code,
                            "name": r.stock_name,
                            "total_buy": r.total_buy,
                            "total_sell": r.total_sell,
                            "net_inflow": r.net_inflow,
                        }
                        for r in rows
                    ]
                    session.close()
                    emit_log("INFO", "db", f"[LHB] DB命中 {len(stocks)}条 ({data_date})")
                    return {
                        "stocks": stocks,
                        "count": len(stocks),
                        "date": data_date,
                        "source": "db",
                    }
            except Exception as e:
                emit_log("WARNING", "database", f"LHB DB error: {str(e)[:100]}")
                session.close()
        except Exception:
            pass

        # 降级: 通过 LHBAdapter 实时拉取 (带超时, 最多等8秒)
        emit_log("INFO", "db", f"[LHB] 尝试实时拉取 ({data_date})...")
        import threading as _lhb_th

        lhb_result = []
        lhb_done = _lhb_th.Event()

        def _fetch_lhb():
            try:
                from providers.sources.lhb import LHBAdapter

                adapter = LHBAdapter()
                df = adapter.fetch_lhb_detail(data_date.replace("-", ""))
                if df is not None and not df.empty:
                    for _, row in df.iterrows():
                        lhb_result.append(
                            {
                                "code": str(row.get("代码", "")),
                                "name": str(row.get("名称", "")),
                                "total_buy": float(row.get("龙虎榜买入额", 0) or 0),
                                "total_sell": float(row.get("龙虎榜卖出额", 0) or 0),
                                "net_inflow": float(row.get("龙虎榜净买额", 0) or 0),
                            }
                        )
            except Exception as e:
                emit_log("WARNING", "db", f"[LHB] 获取失败: {type(e).__name__}: {str(e)[:80]}")
            finally:
                lhb_done.set()

        _lhb_th.Thread(target=_fetch_lhb, daemon=True).start()
        lhb_done.wait(timeout=8)

        if lhb_result:
            emit_log("INFO", "db", f"[LHB] 实时获取 {len(lhb_result)}条")
            return {
                "stocks": lhb_result[:limit],
                "count": len(lhb_result[:limit]),
                "date": data_date,
                "source": "lhb_adapter",
            }

        elapsed = round(_lhb_t.time() - t0, 1)
        emit_log("INFO", "db", f"[LHB] 无数据 ({elapsed}s)")
        return {"stocks": [], "count": 0, "date": data_date, "source": "none"}
    except Exception as e:
        logger.exception("lhb_list error")
        return {"error": str(e), "stocks": [], "count": 0}


@router.get("/hot-rank")
def hot_rank(limit: int = Query(50, ge=10, le=200)):
    """人气榜 TOP N — 基于 HotRankAdapter"""
    try:
        from providers.sources import get_adapter

        adapter = get_adapter("hot_rank")
        if adapter and adapter.cb.try_acquire():
            fetch = getattr(adapter, "fetch_hot_rank", None)
            data = fetch() if callable(fetch) else None
            if data:
                adapter.cb.record_success()
                return {"stocks": data[:limit], "count": min(len(data), limit)}
            adapter.cb.record_failure()
        return {"stocks": [], "count": 0, "note": "数据源不可用"}
    except Exception as e:
        return {"error": str(e), "stocks": []}


@router.get("/zt-pool")
def zt_pool(date: str | None = None, limit: int = Query(50, ge=10, le=200)):
    """涨停股池 — 基于 ZTPoolAdapter"""
    try:
        tc = TradingCalendar()
        d = (date or tc.effective_data_date() or datetime.now().strftime("%Y-%m-%d")).replace(
            "-", ""
        )
        from providers.sources import get_adapter

        adapter = get_adapter("zt_pool")
        if adapter and adapter.cb.try_acquire():
            fetch = getattr(adapter, "fetch_zt_pool", None)
            df = fetch(d) if callable(fetch) else None
            if df is not None and not df.empty:
                adapter.cb.record_success()
                stocks = df.head(limit).to_dict("records") if hasattr(df, "to_dict") else []
                return {"stocks": stocks, "count": len(stocks), "date": d}
            adapter.cb.record_failure()
        # 降级:直接调用 akshare
        import akshare as ak

        df = ak.stock_zt_pool_em(d)
        if df is None or df.empty:
            return {"stocks": [], "count": 0, "date": d}
        stocks = df.head(limit).to_dict("records") if hasattr(df, "to_dict") else []
        return {"stocks": stocks, "count": len(stocks), "date": d}
    except Exception as e:
        return {"error": str(e), "stocks": []}


@router.get("/board-rank")
def board_rank(
    board_type: str = Query("industry", pattern="^(industry|concept)$"),
    limit: int = Query(20, ge=5, le=100),
):
    """板块排行 — industry=行业板块, concept=概念板块"""
    try:
        from providers.sources import get_adapter

        adapter = get_adapter("board_rank")
        if adapter and adapter.cb.try_acquire():
            fetch_name = "fetch_industry_rank" if board_type == "industry" else "fetch_concept_rank"
            fetch = getattr(adapter, fetch_name, None)
            data = fetch() if callable(fetch) else None
            if data:
                adapter.cb.record_success()
                return {
                    "board_type": board_type,
                    "boards": data[:limit],
                    "count": min(len(data), limit),
                }
            adapter.cb.record_failure()
        return {"board_type": board_type, "boards": [], "count": 0, "note": "数据源不可用"}
    except Exception as e:
        return {"error": str(e), "boards": []}


@router.get("/industry-distribution", response_model=IndustryDistOut)
def industry_distribution(limit: int = Query(30, ge=1, le=100)):
    """行业分布统计 — 从StockInfo表聚合"""
    try:
        with db_session() as session:
            rows = (
                session.query(
                    StockInfo.industry,
                    func.count(StockInfo.stock_code).label("count"),
                    func.avg(StockInfo.pe_ratio).label("avg_pe"),
                    func.avg(StockInfo.roe).label("avg_roe"),
                    func.sum(StockInfo.total_market_cap).label("total_market_cap_yi"),
                )
                .filter(StockInfo.industry.isnot(None), StockInfo.industry != "")
                .group_by(StockInfo.industry)
                .order_by(func.count(StockInfo.stock_code).desc())
                .limit(limit)
                .all()
            )
            industries = []
            for r in rows:
                industries.append(
                    {
                        "name": r.industry or "未知",
                        "count": r.count,
                        "avg_pe": float(r.avg_pe or 0),
                        "avg_roe": float(r.avg_roe or 0),
                        "total_market_cap_yi": float(r.total_market_cap_yi or 0),
                    }
                )
            total_with = sum([r.count for r in rows])  # type: ignore
            total_no = (
                session.query(func.count(StockInfo.stock_code))
                .filter(or_(StockInfo.industry.is_(None), StockInfo.industry == ""))
                .scalar()
                or 0
            )
            return {
                "industries": industries,
                "total_with_industry": total_with,
                "total_no_industry": total_no,
            }
    except Exception as e:
        return {"error": str(e), "industries": []}


@router.get("/data-quality")
def data_quality():
    """数据质量评估 — 各字段填充率"""
    try:
        with db_session() as session:
            total = (
                session.query(func.count(StockInfo.stock_code))
                .filter(StockInfo.latest_price > 0)
                .scalar()
                or 0
            )
            fields = {}
            for col, name in [
                ("stock_name", "stock_name"),
                ("latest_price", "latest_price"),
                ("pe_ratio", "pe_ratio"),
                ("roe", "roe"),
                ("industry", "industry"),
                ("total_market_cap", "total_market_cap"),
                ("eps", "eps"),
                ("bvps", "bvps"),
                ("gross_margin", "gross_margin"),
                ("debt_to_equity", "debt_to_equity"),
                ("free_cash_flow", "free_cash_flow"),
                ("dividend_yield", "dividend_yield"),
                ("ma5", "ma5"),
                ("rsi_14", "rsi_14"),
                ("trend", "trend"),
            ]:
                filled = (
                    session.query(func.count(getattr(StockInfo, col)))
                    .filter(
                        StockInfo.latest_price > 0,
                        getattr(StockInfo, col).isnot(None),
                        getattr(StockInfo, col) != 0,
                    )
                    .scalar()
                    or 0
                )
                fields[name] = {
                    "filled": filled,
                    "total": total,
                    "pct": int(filled / total * 100) if total > 0 else 0,
                    "missing": total - filled,
                }
            return {"fields": fields, "total": total}
    except Exception as e:
        return {"error": str(e), "fields": {}}


@router.post("/batch-repair")
def batch_repair():
    """批量修复 — 重新填充latest_price=0的股票"""
    import time as _time

    t0 = _time.time()
    try:
        with db_session() as session:
            broken = (
                session.query(StockInfo.stock_code)
                .filter(or_(StockInfo.latest_price.is_(None), StockInfo.latest_price == 0))
                .limit(200)
                .all()
            )
            codes = [r[0] for r in broken]

        if not codes:
            emit_log("INFO", "db", "[修复] 无需要修复的股票 (latest_price=0)")
            return {"ok": True, "repaired": 0, "still_broken": 0}

        emit_log("INFO", "db", f"[修复] 发现 {len(codes)} 只最新价为0的股票: {codes[:10]}...")
        di = DataInitializer()
        result = di.populate_stock_list(codes)
        repaired = result.data.get("success", 0) if hasattr(result, "data") else 0

        with db_session() as session:
            still = (
                session.query(StockInfo.stock_code)
                .filter(or_(StockInfo.latest_price.is_(None), StockInfo.latest_price == 0))
                .count()
            )

        elapsed = round(_time.time() - t0, 1)
        emit_log("INFO", "db", f"[修复] 完成: 修复{repaired}, 仍有{still}只异常, 耗时{elapsed}s")
        return {"ok": True, "repaired": repaired, "still_broken": still}
    except Exception as e:
        elapsed = round(_time.time() - t0, 1)
        emit_log("ERROR", "db", f"[修复] 失败(耗时{elapsed}s): {e}")
        return {"ok": False, "error": str(e)}


@router.post("/clean-stale")
def clean_stale():
    """清理空壳数据 — 删除latest_price=0且无K线记录的股票"""
    import time as _time

    t0 = _time.time()
    try:
        with db_session() as session:
            stale_codes = (
                session.query(StockInfo.stock_code).filter(StockInfo.latest_price == 0).all()
            )
            deleted = 0
            kept_with_klines = 0
            for (code,) in stale_codes:
                has_klines = session.query(KlineCache).filter_by(stock_code=code).count() > 0
                if not has_klines:
                    session.query(StockInfo).filter_by(stock_code=code).delete()
                    deleted += 1
                else:
                    kept_with_klines += 1

        elapsed = round(_time.time() - t0, 1)
        emit_log(
            "INFO",
            "db",
            f"[清理] 删除{deleted}条空壳, {kept_with_klines}条有K线保留, 耗时{elapsed}s",
        )
        return {"ok": True, "deleted": deleted, "kept_with_klines": kept_with_klines}
    except Exception as e:
        emit_log("ERROR", "db", f"[清理] 失败: {e}")
        return {"ok": False, "error": str(e)}


@router.get("/lhb/list")
def lhb_full_list(date: str | None = None, limit: int = Query(100, ge=1, le=500)):
    """龙虎榜全量列表 — 东财LHB API"""
    try:
        tc = TradingCalendar()
        data_date = date or tc.effective_data_date()
        import akshare as ak

        d = data_date.replace("-", "")
        df = ak.stock_lhb_detail_em(start_date=d, end_date=d)
        if df is None or df.empty:
            return {"date": data_date, "stocks": [], "total": 0}
        rows = []
        for _, r in df.iterrows():
            code = str(r.get("代码", ""))
            name = str(r.get("名称", ""))
            if code and name:
                rows.append(
                    {
                        "code": code,
                        "name": name,
                        "buy_amount": float(r.get("买入额", 0) or 0),
                        "sell_amount": float(r.get("卖出额", 0) or 0),
                        "net_amount": float(r.get("净买额", r.get("龙虎榜净买额", 0)) or 0),
                    }
                )
        return {"date": data_date, "stocks": rows[:limit], "total": len(rows)}
    except Exception as e:
        return {"error": str(e), "stocks": []}


@router.get("/data-quality/scan")
def quality_scan():
    """全量数据质量扫描 — 各字段填充率 + 综合评分"""
    try:
        de = DataExplorer()
        result = de.scan_data_quality()
        return result.data if hasattr(result, "data") else result
    except Exception as e:
        return {"error": str(e)}


@router.get("/cache-status")
def cache_status():
    """MarketSnapshot缓存状态 — 类型/年龄/过期"""
    try:
        de = DataExplorer()
        result = de.scan_cache_status()
        return result.data if hasattr(result, "data") else result
    except Exception as e:
        return {"error": str(e)}


@router.get("/explorer/estimate")
def estimate_refresh(stocks: int = Query(5000, ge=1, le=20000)):
    """预估全市场刷新耗时"""
    try:
        de = DataExplorer()
        result = de.estimate_refresh_time(stocks)
        return result.data if hasattr(result, "data") else result
    except Exception as e:
        return {"error": str(e)}


@router.get("/data-by-date")
def get_data_by_date(
    table: str = Query(
        ...,
        enum=[
            "stock_info",
            "kline_cache",
            "fund_metric_hist",
            "market_snapshot",
            "daily_nav",
            "portfolio",
            "trade_records",
            "style_signal",
            "screen_result",
            "dragon_tiger",
            "orders",
            "trades",
        ],
    ),
    date: str = Query(None, description="精确日期 YYYY-MM-DD"),
    date_from: str = Query(None, description="起始日期"),
    date_to: str = Query(None, description="结束日期"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    code: str = Query(None, description="股票代码过滤"),
):
    """按日期/日期范围/股票代码查询各表数据"""
    try:
        from sqlalchemy import text

        from shared.models import get_session

        # Determine date column based on table
        date_col_map = {
            "kline_cache": "trade_date",
            "fund_metric_hist": "report_period",
            "market_snapshot": "trade_date",
            "daily_nav": "date",
            "dragon_tiger": "trade_date",
            "portfolio": "buy_date",
            "trade_records": "trade_date",
            "style_signal": "created_at",
            "screen_result": "created_at",
            "stock_info": "updated_at",
            "orders": "created_at",
            "trades": "trade_date",
        }

        date_col = date_col_map.get(table, "date")

        # Build query
        conditions = []
        params: dict[str, Any] = {}

        if date:
            if table in ("style_signal", "screen_result", "orders", "stock_info"):
                # These use datetime columns, compare as date string
                conditions.append(f"date({date_col}) = :date_val")
            else:
                conditions.append(f"{date_col} = :date_val")
            params["date_val"] = date

        if date_from and not date:
            if table in ("style_signal", "screen_result", "orders", "stock_info"):
                conditions.append(f"date({date_col}) >= :date_from")
            else:
                conditions.append(f"{date_col} >= :date_from")
            params["date_from"] = date_from

        if date_to and not date:
            if table in ("style_signal", "screen_result", "orders", "stock_info"):
                conditions.append(f"date({date_col}) <= :date_to")
            else:
                conditions.append(f"{date_col} <= :date_to")
            params["date_to"] = date_to

        if code and table in (
            "stock_info",
            "kline_cache",
            "fund_metric_hist",
            "portfolio",
            "trade_records",
            "dragon_tiger",
            "style_signal",
            "orders",
            "trades",
        ):
            conditions.append("stock_code = :code")
            params["code"] = code

        where_clause = " AND ".join(conditions) if conditions else "1=1"

        # Count and fetch
        session = get_session()
        try:
            count_sql = f'SELECT COUNT(*) FROM "{table}" WHERE {where_clause}'  # noqa: S608
            total = session.execute(text(count_sql), params).scalar() or 0

            data_sql = f'SELECT * FROM "{table}" WHERE {where_clause} ORDER BY rowid DESC LIMIT :lim OFFSET :off'  # noqa: S608
            params["lim"] = limit
            params["off"] = offset
            rows = session.execute(text(data_sql), params).fetchall()

            # Convert to dict
            columns = rows[0]._fields if rows else []
            result = [dict(zip(columns, row, strict=False)) for row in rows]

            # Convert datetime/Decimal to string/float
            import datetime as _dt
            import decimal

            serializable = []
            for row in result:
                clean: dict[str, Any] = {}
                for k, v in row.items():
                    if isinstance(v, (_dt.datetime, _dt.date)):
                        clean[k] = v.isoformat() if hasattr(v, "isoformat") else str(v)
                    elif isinstance(v, decimal.Decimal):
                        clean[k] = float(v)
                    elif isinstance(v, bytes):
                        clean[k] = v.decode("utf-8", errors="replace")
                    else:
                        clean[k] = v
                serializable.append(clean)

            return {
                "status": "ok",
                "table": table,
                "total": total,
                "offset": offset,
                "limit": limit,
                "columns": columns,
                "rows": serializable,
            }
        finally:
            session.close()
    except Exception as e:
        emit_log("ERROR", "database", f"data_by_date failed: {e}")
        return {"error": str(e), "rows": [], "total": 0}


@router.get("/table-info")
def get_table_info(
    table: str = Query(
        ...,
        enum=[
            "stock_info",
            "kline_cache",
            "fund_metric_hist",
            "market_snapshot",
            "daily_nav",
            "portfolio",
            "trade_records",
            "style_signal",
            "screen_result",
            "dragon_tiger",
            "orders",
            "trades",
        ],
    ),
):
    """返回指定表的列信息"""
    try:
        from sqlalchemy import inspect, text

        from shared.models import get_engine

        engine = get_engine()
        insp = inspect(engine)
        columns = insp.get_columns(table)
        cols = [{"name": c["name"], "type": str(c["type"])} for c in columns]

        # Get sample row
        session = get_engine().connect()
        try:
            sample = session.execute(text(f'SELECT * FROM "{table}" LIMIT 3')).fetchall()  # noqa: S608
            sample_data = (
                [dict(zip(sample[0]._fields, row, strict=False)) for row in sample]
                if sample
                else []
            )
        finally:
            session.close()

        return {"status": "ok", "table": table, "columns": cols, "sample": sample_data}
    except Exception as e:
        return {"error": str(e)}


@router.post("/refresh-financials")
def refresh_financials(max_stocks: int = Query(9999, ge=1, le=99999)):
    """批量刷新财务数据 (roe, gross_margin, eps等)"""
    try:
        from services.data_initializer import DataInitializer

        di = DataInitializer()
        result_data = di.enrich_financial_data(max_stocks)
        return {"status": "ok", **result_data}

    except Exception as e:
        emit_log("ERROR", "database", f"refresh_financials: {e}")
        return {"error": str(e)}


@router.post("/zzshare-snapshots")
def refresh_zzshare_snapshots():
    """获取 zzshare 热门/涨停/板块排行数据, 存入 MarketSnapshot"""
    try:
        from services.data_initializer import DataInitializer

        di = DataInitializer()
        result = di.refresh_zzshare_snapshots()
        return {"status": "ok", "results": result}
    except Exception as e:
        emit_log("ERROR", "database", f"zzshare_snapshots: {e}")
        return {"error": str(e)}


@router.post("/fix-stock-names")
def fix_stock_names(max_stocks: int = Query(500, ge=1, le=99999)):
    """批量修正英文股票名为中文名"""
    try:
        from services.data_initializer import DataInitializer

        di = DataInitializer()
        result = di.fix_english_names(max_stocks)
        return {"status": "ok", **result}
    except Exception as e:
        emit_log("ERROR", "database", f"fix_stock_names: {e}")
        return {"error": str(e)}


@router.post("/tushare-batch-fill")
def tushare_batch_fill():
    """Tushare daily_basic 批量填充 PE/PB/换手率/市值/股息 (一次调用~7s, 覆盖5514只)"""
    try:
        from services.data_initializer import DataInitializer

        di = DataInitializer()
        result = di.batch_enrich_from_tushare()
        return {"status": "ok", **result}
    except Exception as e:
        emit_log("ERROR", "database", f"tushare_batch_fill: {e}")
        return {"error": str(e)}


@router.post("/full-enrich")
def full_enrich(max_stocks: int = Query(99999, ge=1, le=99999)):
    """全量财务填充: Tushare daily_basic + AKShare 深度财务"""
    try:
        from services.data_initializer import DataInitializer

        di = DataInitializer()
        results = {}
        # Phase 1: Tushare batch (fast)
        r1 = di.batch_enrich_from_tushare()
        results["tushare_batch"] = r1
        # Phase 2: AKShare deep financials
        r2 = di.enrich_financial_data(max_stocks)
        results["akshare_deep"] = r2
        return {"status": "ok", "results": results}
    except Exception as e:
        emit_log("ERROR", "database", f"full_enrich: {e}")
        return {"error": str(e)}


@router.post("/refresh-industry")
def refresh_industry():
    """刷新行业数据 (从东方财富获取)"""
    try:
        from services.data_initializer import DataInitializer

        di = DataInitializer()
        result = di.refresh_industry_data()
        return result if isinstance(result, dict) else {"status": "ok"}
    except Exception as e:
        emit_log("ERROR", "database", f"refresh_industry: {e}")
        return {"error": str(e)}
