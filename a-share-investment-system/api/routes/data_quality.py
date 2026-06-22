"""数据质量检查API"""

from fastapi import APIRouter

from shared.db_session import db_session
from shared.logging import emit_log
from shared.models import StockInfo

router = APIRouter()


@router.get("/quality-report")
def get_quality_report():
    """获取数据库数据质量报告"""
    try:
        with db_session() as session:
            total = session.query(StockInfo).count()
            if total == 0:
                return {"ok": True, "total": 0, "columns": []}

            columns = [c.name for c in StockInfo.__table__.columns]
            report = []

            for col in columns:
                if col in ("id", "created_at", "updated_at"):
                    continue

                col_obj = getattr(StockInfo, col)

                # Count non-null
                non_null = session.query(StockInfo).filter(col_obj.isnot(None)).count()

                # Count non-empty (for string/numeric columns)
                non_empty = (
                    session.query(StockInfo)
                    .filter(col_obj.isnot(None), col_obj != "", col_obj != 0)
                    .count()
                )

                null_count = total - non_null
                empty_count = total - non_empty
                null_pct = round(null_count / total * 100, 1)
                empty_pct = round(empty_count / total * 100, 1)

                # Determine quality level
                if null_pct == 0 and empty_pct < 10:
                    quality = "excellent"
                elif null_pct < 10 and empty_pct < 30:
                    quality = "good"
                elif null_pct < 30 and empty_pct < 50:
                    quality = "fair"
                else:
                    quality = "poor"

                report.append(
                    {
                        "column": col,
                        "total": total,
                        "non_null": non_null,
                        "non_empty": non_empty,
                        "null_count": null_count,
                        "empty_count": empty_count,
                        "null_pct": null_pct,
                        "empty_pct": empty_pct,
                        "quality": quality,
                    }
                )

            # Sort by empty_pct descending
            report.sort(key=lambda x: x["empty_pct"], reverse=True)

            # Summary
            excellent = sum(1 for r in report if r["quality"] == "excellent")
            good = sum(1 for r in report if r["quality"] == "good")
            fair = sum(1 for r in report if r["quality"] == "fair")
            poor = sum(1 for r in report if r["quality"] == "poor")

            return {
                "ok": True,
                "total": total,
                "summary": {
                    "excellent": excellent,
                    "good": good,
                    "fair": fair,
                    "poor": poor,
                    "total_columns": len(report),
                },
                "columns": report,
            }
    except Exception as e:
        emit_log("ERROR", "data_quality", f"质量报告生成失败: {str(e)[:100]}")
        return {"ok": False, "error": str(e)}


@router.get("/empty-stocks")
def get_empty_stocks(limit: int = 50):
    """获取数据最空的股票列表"""
    try:
        with db_session() as session:
            stocks = session.query(StockInfo).limit(500).all()

            result = []
            for s in stocks:
                # Count empty fields
                empty_count = 0
                total_fields = 0
                for col in StockInfo.__table__.columns:
                    if col.name in ("id", "stock_code", "stock_name", "created_at", "updated_at"):
                        continue
                    total_fields += 1
                    val = getattr(s, col.name)
                    if val is None or val in {"", 0}:
                        empty_count += 1

                empty_pct = round(empty_count / total_fields * 100, 1) if total_fields > 0 else 0

                if empty_pct > 50:
                    result.append(
                        {
                            "stock_code": s.stock_code,
                            "stock_name": s.stock_name,
                            "empty_count": empty_count,
                            "total_fields": total_fields,
                            "empty_pct": empty_pct,
                        }
                    )

            # Sort by empty_pct descending
            result.sort(key=lambda x: x["empty_pct"], reverse=True)

            return {
                "ok": True,
                "total": len(result),
                "stocks": result[:limit],
            }
    except Exception as e:
        emit_log("ERROR", "data_quality", f"空股票查询失败: {str(e)[:100]}")
        return {"ok": False, "error": str(e)}
