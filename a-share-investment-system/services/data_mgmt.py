"""数据管理服务"""

import logging
import os
import re
import subprocess
import sys
import threading
from datetime import datetime

from shared.logging import emit_log

logger = logging.getLogger(__name__)

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from sqlalchemy import text

from providers.cache import CacheManager
from providers.market_data import MarketDataProvider
from shared.models import KlineCache, StockInfo


class DataManagementService:
    def __init__(self, db_session_factory, cache: CacheManager = None):
        self._get_db = db_session_factory
        self._cache = cache or CacheManager()

    def get_table_stats(self) -> dict:
        db = self._get_db()
        try:
            rows = db.execute(
                text(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                )
            ).fetchall()
            tables = []
            for r in rows:
                table_name = r[0]
                # 表名来自 sqlite_master，仅允许字母数字下划线，防止 SQL 注入
                if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", table_name):
                    continue
                count = db.execute(text(f"SELECT COUNT(*) FROM [{table_name}]")).scalar()  # noqa: S608
                tables.append({"name": table_name, "row_count": count or 0})
            db_path = os.path.join(_PROJECT_ROOT, "data", "investment.db")
            db_size = (
                round(os.path.getsize(db_path) / 1024 / 1024, 2) if os.path.exists(db_path) else 0
            )
            return {
                "status": "ok",
                "tables": sorted(tables, key=lambda t: t["name"]),
                "db_size_mb": db_size,
                "total_tables": len(tables),
            }
        except Exception as e:
            return {"status": "error", "message": str(e)[:200]}
        finally:
            db.close()

    def get_provider_status(self) -> dict:
        provider = MarketDataProvider()
        try:
            result = provider.get_indices()
            available = bool(result and result.get("indices"))
        except Exception as e:
            emit_log("WARNING", "data_mgmt", f"Error: {str(e)[:100]}")
            available = False

        return {
            "status": "ok",
            "providers": [
                {"name": "akshare", "priority": 1, "available": available},
                {"name": "tencent", "priority": 2, "available": False},
                {"name": "sina", "priority": 3, "available": False},
                {"name": "efinance", "priority": 4, "available": False},
                {"name": "baostock", "priority": 5, "available": False},
                {"name": "tickflow", "priority": 6, "available": False},
            ],
            "available_count": 1 if available else 0,
            "total_count": 6,
            "recent_errors": [],
            "checked_at": datetime.now().isoformat(),
        }

    def clear_cache(self) -> dict:
        try:
            self._cache.clear_all()
            return {"status": "ok", "message": "缓存已清除"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def refresh_stock(self, code: str) -> dict:
        if not code or not code.strip():
            return {"status": "error", "message": "请输入股票代码"}

        def _fetch():
            try:
                provider = MarketDataProvider()
                basic = provider.get_stock_basic(code)
                if basic:
                    db = self._get_db()
                    try:
                        info = db.query(StockInfo).filter_by(stock_code=code).first()
                        if not info:
                            info = StockInfo(stock_code=code, stock_name=code)
                            db.add(info)
                        for k, v in basic.items():
                            if hasattr(info, k) and v is not None:
                                setattr(info, k, v)
                        db.commit()
                    except Exception as e:
                        db.rollback()
                        logger.warning("stock basic save err: %s", e)
                    finally:
                        db.close()

                kline = provider.get_stock_kline(code, days=90)
                if kline is not None and not kline.empty:
                    db = self._get_db()
                    try:
                        for _, row in kline.iterrows():
                            td = str(row.get("日期", row.get("trade_date", "")))
                            ex = (
                                db.query(KlineCache)
                                .filter_by(stock_code=code, trade_date=td)
                                .first()
                            )
                            if not ex:
                                db.add(
                                    KlineCache(
                                        stock_code=code,
                                        trade_date=td,
                                        open=float(row.get("开盘", row.get("open", 0)) or 0),
                                        high=float(row.get("最高", row.get("high", 0)) or 0),
                                        low=float(row.get("最低", row.get("low", 0)) or 0),
                                        close=float(row.get("收盘", row.get("close", 0)) or 0),
                                        volume=float(row.get("成交量", row.get("volume", 0)) or 0),
                                        amount=float(row.get("成交额", row.get("amount", 0)) or 0),
                                    )
                                )
                        db.commit()
                    except Exception as e:
                        emit_log("WARNING", "data_mgmt", f"Error: {str(e)[:100]}")
                        db.rollback()
                    finally:
                        db.close()
            except Exception as e:
                logger.warning("refresh %s err: %s", code, e)

        threading.Thread(target=_fetch, daemon=True).start()
        return {"status": "ok", "message": f"后台刷新 {code} 已启动"}

    def rebuild_db(self) -> dict:
        def _run():
            try:
                script = os.path.join(_PROJECT_ROOT, "build_stock_db.py")
                subprocess.run(  # noqa: S603
                    [sys.executable, script], cwd=_PROJECT_ROOT, timeout=900, check=False
                )
            except Exception as e:
                logger.warning("rebuild err: %s", e)

        threading.Thread(target=_run, daemon=True).start()
        return {"status": "ok", "message": "数据库重建已启动"}

    def rescreen(self) -> dict:
        def _run():
            try:
                script = os.path.join(_PROJECT_ROOT, "screen_watchlist.py")
                subprocess.run(  # noqa: S603
                    [sys.executable, script], cwd=_PROJECT_ROOT, timeout=600, check=False
                )
            except Exception as e:
                logger.warning("rescreen err: %s", e)

        threading.Thread(target=_run, daemon=True).start()
        return {"status": "ok", "message": "全量筛选已启动"}
