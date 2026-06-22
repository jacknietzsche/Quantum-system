"""自选股管理服务"""

import csv
import io

from shared.models import StockInfo, Watchlist


class WatchlistService:
    def __init__(self, db_session_factory):
        self._get_db = db_session_factory

    def get_all(self, refresh: bool = False) -> dict:
        db = self._get_db()
        try:
            items = db.query(Watchlist).order_by(Watchlist.id).all()
            result = []
            for w in items:
                info = db.query(StockInfo).filter_by(stock_code=w.stock_code).first()
                result.append(
                    {
                        "id": w.id,
                        "stock_code": w.stock_code,
                        "stock_name": w.stock_name,
                        "category": w.category or "股票",
                        "add_reason": w.add_reason or "",
                        "created_at": str(w.created_at or ""),
                        "pe_ratio": round(info.pe_ratio, 1) if info and info.pe_ratio else None,
                        "pb_ratio": round(info.pb_ratio, 2) if info and info.pb_ratio else None,
                        "industry": info.industry if info else "",
                        "trend": info.trend if info else "",
                        "rsi": round(info.rsi_14, 1) if info and info.rsi_14 else None,
                        "latest_price": round(info.latest_price, 2)
                        if info and info.latest_price
                        else None,
                        "change_pct": round(info.change_pct, 2)
                        if info and info.change_pct
                        else None,
                        "volatility": round(info.volatility_20d, 1)
                        if info and info.volatility_20d
                        else None,
                    }
                )
            return {"status": "ok", "data": result, "total": len(result)}
        finally:
            db.close()

    def add(self, code: str, name: str, category: str = "股票", reason: str = "") -> dict:
        db = self._get_db()
        try:
            existing = db.query(Watchlist).filter_by(stock_code=code).first()
            if existing:
                return {"status": "error", "message": f"{code} 已在自选股中"}
            wl = Watchlist(stock_code=code, stock_name=name, category=category, add_reason=reason)
            db.add(wl)
            db.commit()
            return {"status": "ok", "message": f"已添加 {name}({code})"}
        except Exception as e:
            db.rollback()
            return {"status": "error", "message": str(e)}
        finally:
            db.close()

    def delete(self, code: str) -> dict:
        db = self._get_db()
        try:
            deleted = db.query(Watchlist).filter_by(stock_code=code).delete()
            db.commit()
            return {
                "status": "ok" if deleted else "error",
                "message": f"已删除 {code}" if deleted else f"未找到 {code}",
            }
        finally:
            db.close()

    def clear(self) -> dict:
        db = self._get_db()
        try:
            count = db.query(Watchlist).delete()
            db.commit()
            return {"status": "ok", "message": f"已清空 {count} 只自选股"}
        finally:
            db.close()

    def export_csv(self) -> str:
        db = self._get_db()
        try:
            items = db.query(Watchlist).order_by(Watchlist.id).all()
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(["stock_code", "stock_name", "category", "add_reason", "created_at"])
            for w in items:
                writer.writerow(
                    [
                        w.stock_code,
                        w.stock_name,
                        w.category or "",
                        w.add_reason or "",
                        str(w.created_at or ""),
                    ]
                )
            return output.getvalue()
        finally:
            db.close()

    def import_csv(self, csv_text: str) -> dict:
        reader = csv.DictReader(io.StringIO(csv_text))
        added, skipped = 0, 0
        db = self._get_db()
        try:
            for row in reader:
                code = row.get("stock_code", "").strip()
                name = row.get("stock_name", "").strip()
                if not code or not name:
                    continue
                existing = db.query(Watchlist).filter_by(stock_code=code).first()
                if existing:
                    skipped += 1
                    continue
                db.add(
                    Watchlist(
                        stock_code=code,
                        stock_name=name,
                        category=row.get("category", "股票"),
                        add_reason=row.get("add_reason", ""),
                    )
                )
                added += 1
            db.commit()
        except Exception as e:
            db.rollback()
            return {"status": "error", "message": str(e)}
        finally:
            db.close()
        return {
            "status": "ok",
            "message": f"新增 {added} 只,跳过 {skipped} 只",
            "added": added,
            "skipped": skipped,
        }
