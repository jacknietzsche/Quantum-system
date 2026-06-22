"""市场数据服务 - SQLite优先 + 日频数据 (v5.2)"""

import json
import threading
from datetime import datetime

from providers.market_data import _SECTOR_FIELD_MAP, MarketDataProvider, _latest_trade_date
from shared.logging import emit_log
from shared.models import MarketSnapshot


def _norm_sectors(raw: list) -> list:
    return [{_SECTOR_FIELD_MAP.get(k, k): v for k, v in s.items()} for s in (raw or [])]


class MarketService:
    def __init__(self, db_session_factory, market_provider=None, cache=None):
        self._get_db = db_session_factory
        self._provider = market_provider or MarketDataProvider()
        self._cache = cache

    # ═══════════════════════════════════════════
    #  市场指数
    # ═══════════════════════════════════════════

    def get_indices(self) -> dict:
        target_date = _latest_trade_date()
        db = self._get_db()
        try:
            # Step 1: 查今天/昨天的数据
            snap = (
                db.query(MarketSnapshot)
                .filter_by(snapshot_type="indices", trade_date=target_date)
                .first()
            )
            if snap and snap.data_json:
                c = json.loads(snap.data_json)
                # If breadth missing (all zeros), trigger background refresh
                b = c.get("breadth", {})
                if b.get("total", 0) == 0:
                    threading.Thread(target=self._fetch_and_save_indices, daemon=True).start()
                return self._format_indices_response(c, "cached")

            # Step 2: 查最近的数据
            snap = (
                db.query(MarketSnapshot)
                .filter_by(snapshot_type="indices")
                .order_by(MarketSnapshot.trade_date.desc())
                .first()
            )
            if snap and snap.data_json:
                c = json.loads(snap.data_json)
                # Trigger background refresh
                threading.Thread(target=self._fetch_and_save_indices, daemon=True).start()
                return self._format_indices_response(c, "stale", f"使用 {snap.trade_date} 数据")

            # Step 3: 无本地数据,立即返回空 + 后台获取
            threading.Thread(target=self._fetch_and_save_indices, daemon=True).start()
            return self._empty_indices_response()
        finally:
            db.close()

    def _fetch_and_save_indices(self):
        """后台线程:从外部源获取指数+广度+板块"""
        try:
            data = self._provider.get_indices()
            if data and data.get("indices"):
                breadth = self._fetch_breadth_from_spot()
                if breadth:
                    data["breadth"] = breadth
                db = self._get_db()
                try:
                    self._save_snapshot(db, "indices", _latest_trade_date(), data)
                finally:
                    db.close()
        except Exception as e:
            print(f"[BG] indices fetch err: {e}")

    def _fetch_breadth_from_spot(self) -> dict:
        """全市场广度 ~5500只A股 - 东方财富分页(56页x100,约15s)"""
        import json
        import urllib.request
        from concurrent.futures import ThreadPoolExecutor, as_completed

        def _fetch_page(page: int):
            try:
                url = (
                    "https://push2.eastmoney.com/api/qt/clist/get?"
                    f"pn={page}&pz=100&po=1&np=1&fltt=2&invt=2&fid=f3"
                    "&fs=m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23&fields=f3"
                )
                req = urllib.request.Request(  # noqa: S310
                    url,
                    headers={
                        "User-Agent": "Mozilla/5.0",
                        "Referer": "https://quote.eastmoney.com/",
                    },
                )
                resp = urllib.request.urlopen(req, timeout=5)  # noqa: S310
                data = json.loads(resp.read().decode("utf-8"))
                items = data.get("data", {}).get("diff", [])
                return [float(item.get("f3", 0) or 0) for item in items] if items else []
            except Exception as e:
                emit_log("ERROR", "market", f"Operation failed: {str(e)[:100]}")
                return []

        all_pct = []
        # Fetch 4 pages at a time in parallel, up to 60 pages
        with ThreadPoolExecutor(max_workers=4) as executor:
            for batch_start in range(1, 61, 4):
                futures = {
                    executor.submit(_fetch_page, p): p
                    for p in range(batch_start, min(batch_start + 4, 61))
                }
                for f in as_completed(futures):
                    result = f.result()
                    if not result:
                        continue
                    all_pct.extend(result)

        if all_pct and len(all_pct) > 1000:
            total = len(all_pct)
            up = sum(1 for p in all_pct if p > 0)
            down = sum(1 for p in all_pct if p < 0)
            return {
                "total": total,
                "up": up,
                "down": down,
                "flat": total - up - down,
                "limit_up": sum(1 for p in all_pct if p >= 9.5),
                "limit_down": sum(1 for p in all_pct if p <= -9.5),
                "up_ratio": round(up / total * 100, 1),
            }
        return None

    def _format_indices_response(self, data: dict, freshness: str, note: str | None = None) -> dict:
        resp = {
            "status": "ok",
            "indices": data.get("indices", {}),
            "breadth": data.get("breadth", {}),
            "sectors": _norm_sectors(data.get("sectors", [])),
            "data_freshness": freshness,
            "data_time": data.get("data_time", ""),
        }
        if note:
            resp["note"] = note
        return resp

    def _empty_indices_response(self) -> dict:
        return {
            "status": "ok",
            "indices": {},
            "breadth": {
                "total": 0,
                "up": 0,
                "down": 0,
                "flat": 0,
                "limit_up": 0,
                "limit_down": 0,
                "up_ratio": 0,
            },
            "sectors": [],
            "data_freshness": "unavailable",
            "note": "数据暂不可用,请稍后刷新",
            "data_time": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }

    # ═══════════════════════════════════════════
    #  北向资金
    # ═══════════════════════════════════════════

    def get_north_flow(self) -> dict:
        target_date = _latest_trade_date()
        db = self._get_db()
        try:
            snap = (
                db.query(MarketSnapshot)
                .filter_by(snapshot_type="north_flow", trade_date=target_date)
                .first()
            )
            if snap and snap.data_json:
                return {
                    "status": "ok",
                    "data": json.loads(snap.data_json),
                    "data_freshness": "cached",
                }

            snap = (
                db.query(MarketSnapshot)
                .filter_by(snapshot_type="north_flow")
                .order_by(MarketSnapshot.trade_date.desc())
                .first()
            )
            if snap and snap.data_json:
                threading.Thread(target=self._fetch_and_save_north_flow, daemon=True).start()
                return {
                    "status": "ok",
                    "data": json.loads(snap.data_json),
                    "data_freshness": "stale",
                }

            threading.Thread(target=self._fetch_and_save_north_flow, daemon=True).start()
            return {"status": "ok", "data": {}, "data_freshness": "unavailable"}
        finally:
            db.close()

    def _fetch_and_save_north_flow(self):
        try:
            db = self._get_db()
            try:
                data = self._provider.get_north_flow()
                if data:
                    self._save_snapshot(db, "north_flow", _latest_trade_date(), data)
            finally:
                db.close()
        except Exception as e:
            print(f"[BG] nflow fetch err: {e}")

    # ═══════════════════════════════════════════
    #  热门股票
    # ═══════════════════════════════════════════

    def get_hot_stocks(self, sort: str = "turnover", limit: int = 100) -> dict:
        target_date = _latest_trade_date()
        snap_type = f"hot_stocks_{sort}"

        # Step 1: 读缓存 (per sort type)
        db = self._get_db()
        try:
            snap = db.query(MarketSnapshot).filter_by(snapshot_type=snap_type).first()
            if snap and snap.data_json:
                cached = json.loads(snap.data_json)
                return {
                    "status": "ok",
                    "data": cached.get("data", []),
                    "total": cached.get("total", 0),
                    "sort": sort,
                    "updated_at": str(snap.updated_at or ""),
                    "data_freshness": "cached" if snap.trade_date == target_date else "stale",
                }
        finally:
            db.close()

        # Step 2: 从外部获取
        data = self._provider.get_hot_stocks(sort, limit)
        if data:
            threading.Thread(
                target=self._save_hot_stocks_cache,
                args=(snap_type, target_date, sort, data),
                daemon=True,
            ).start()
            return {
                "status": "ok",
                "data": data,
                "total": len(data),
                "sort": sort,
                "updated_at": datetime.now().isoformat(),
                "data_freshness": "fresh",
            }

        return {
            "status": "ok",
            "data": [],
            "total": 0,
            "sort": sort,
            "note": "数据暂不可用",
            "data_freshness": "unavailable",
        }

    def _save_hot_stocks_cache(self, snap_type: str, trade_date: str, sort: str, data: list):
        try:
            db = self._get_db()
            try:
                snap = db.query(MarketSnapshot).filter_by(snapshot_type=snap_type).first()
                if not snap:
                    snap = MarketSnapshot(snapshot_type=snap_type)
                    db.add(snap)
                snap.trade_date = trade_date
                snap.data_json = json.dumps(
                    {"sort": sort, "data": data, "total": len(data)}, ensure_ascii=False
                )
                snap.updated_at = datetime.now()
                db.commit()
            finally:
                db.close()
        except Exception as e:
            print(f"[BG] save hot stocks err: {e}")

    def get_sectors(self) -> list:
        return self._provider.get_indices().get("sectors", [])

    # ═══════════════════════════════════════════
    #  内部
    # ═══════════════════════════════════════════

    def _save_snapshot(self, db, snap_type: str, trade_date: str, data: dict):
        try:
            snap = db.query(MarketSnapshot).filter_by(snapshot_type=snap_type).first()
            if not snap:
                snap = MarketSnapshot(snapshot_type=snap_type)
                db.add(snap)
            snap.trade_date = trade_date
            snap.data_json = json.dumps(
                data
                if snap_type == "north_flow"
                else {
                    "indices": data.get("indices", {}),
                    "breadth": data.get("breadth", {}),
                    "sectors": _norm_sectors(data.get("sectors", [])),
                },
                ensure_ascii=False,
                default=str,
            )
            snap.updated_at = datetime.now()
            db.commit()
        except Exception as e:
            db.rollback()
            print(f"[MarketService] save snapshot err: {e}")

    def refresh_all(self):
        """强制刷新所有市场数据"""

        def _run():
            db = self._get_db()
            try:
                target_date = _latest_trade_date()
                data = self._provider.get_indices()
                if data and data.get("indices"):
                    self._save_snapshot(db, "indices", target_date, data)
                flow = self._provider.get_north_flow()
                if flow:
                    self._save_snapshot(db, "north_flow", target_date, flow)
            finally:
                db.close()

        threading.Thread(target=_run, daemon=True).start()
