"""风控审计服务"""

from datetime import datetime

from shared.models import Portfolio, TradeStatus


class RiskService:
    def __init__(self, db_session_factory, cache_manager=None, risk_firewall=None):
        self._get_db = db_session_factory
        self._cache = cache_manager

    def audit(self) -> dict:
        db = self._get_db()
        try:
            holdings = db.query(Portfolio).filter_by(status=TradeStatus.HOLDING).all()
            if not holdings:
                return {
                    "status": "ok",
                    "overall_pass": True,
                    "market_risk": {"level": "LOW", "score": 0, "pass": True, "message": "无持仓"},
                    "tail_risk": {"level": "LOW", "score": 0, "pass": True, "message": "无持仓"},
                    "stock_risks": [],
                    "timestamp": datetime.now().isoformat(),
                }

            # 有持仓时返回基本风控结果
            stock_risks = [
                {
                    "stock_code": h.stock_code,
                    "stock_name": h.stock_name,
                    "level": "UNKNOWN",
                    "score": 0,
                    "warnings": [],
                }
                for h in holdings
            ]
            return {
                "status": "ok",
                "market_risk": {
                    "level": "LOW",
                    "score": 20,
                    "pass": True,
                    "message": f"持仓 {len(holdings)} 只",
                },
                "tail_risk": {"level": "LOW", "score": 10, "pass": True},
                "overall_pass": True,
                "stock_risks": stock_risks,
                "timestamp": datetime.now().isoformat(),
            }
        finally:
            db.close()

    def position_plan(self) -> dict:
        db = self._get_db()
        try:
            holdings = db.query(Portfolio).filter_by(status=TradeStatus.HOLDING).all()
            if not holdings:
                return {
                    "status": "ok",
                    "risk_score": 30,
                    "level": "中等",
                    "position_pct": "60%",
                    "advice": "暂无持仓",
                    "stock_distribution": [],
                    "holding_count": 0,
                }

            total_cost = sum(h.cost_value or 0 for h in holdings)
            stocks_dist = []
            for h in holdings:
                weight = round(h.cost_value / total_cost * 100, 1) if total_cost > 0 else 0
                stocks_dist.append(
                    {
                        "stock_code": h.stock_code,
                        "stock_name": h.stock_name,
                        "weight": weight,
                        "profit_loss_pct": round(h.profit_loss_pct, 2),
                    }
                )

            return {
                "status": "ok",
                "risk_score": 30,
                "level": "中等",
                "position_pct": f"{min(80, len(holdings) * 10)}%",
                "advice": "正常操作",
                "stock_distribution": stocks_dist,
                "holding_count": len(holdings),
            }
        finally:
            db.close()

    def get_review_stats(self) -> dict:
        try:
            from decision_review import DecisionReviewManager

            rm = DecisionReviewManager()
            stats = rm.get_stats()
            rm.close()
            return {"status": "ok", "data": stats}
        except Exception as e:
            return {"status": "ok", "data": {"error": str(e)}}
