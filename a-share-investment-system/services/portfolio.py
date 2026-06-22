"""持仓管理服务"""

from shared.logging import emit_log
from shared.models import Portfolio, StockInfo, TradeRecord, TradeStatus


class PortfolioService:
    def __init__(self, db_session_factory):
        self._get_db = db_session_factory

    def get_holdings(self, portfolio_type: str | None = None) -> dict:
        db = self._get_db()
        emit_log("DEBUG", "portfolio", f"get_holdings(type={portfolio_type})")
        try:
            query = db.query(Portfolio).filter_by(status=TradeStatus.HOLDING)
            if portfolio_type:
                query = query.filter_by(portfolio_type=portfolio_type)
            holdings = query.all()
            result = []
            for h in holdings:
                info = db.query(StockInfo).filter_by(stock_code=h.stock_code).first()
                result.append(
                    {
                        "stock_code": h.stock_code,
                        "stock_name": h.stock_name,
                        "buy_date": h.buy_date,
                        "buy_price": h.buy_price,
                        "quantity": h.quantity,
                        "current_price": h.current_price or 0,
                        "cost_value": h.cost_value,
                        "current_value": h.current_value,
                        "profit_loss": round(h.profit_loss, 2),
                        "profit_loss_pct": round(h.profit_loss_pct, 2),
                        "industry": info.industry if info else "",
                        "trend": info.trend if info else "",
                    }
                )
            total_value = sum(h.current_value or 0 for h in holdings)
            _total_cost = sum(h.cost_value or 0 for h in holdings)
            emit_log("INFO", "portfolio", f"????: {len(result)}?, ???{total_value:.0f}")
            return {
                "status": "ok",
                "positions": result,
                "total": len(result),
                "total_asset": round(total_value, 2),
                "cash": 0,
                "position_count": len(result),
                "portfolio_type": portfolio_type or "value",
            }
        finally:
            db.close()

    def get_holdings_map(self, portfolio_type: str | None = None) -> dict:
        """Return holdings as {stock_code: holding_dict} for portfolio-aware screening."""
        result = self.get_holdings(portfolio_type)
        if isinstance(result, dict) and "positions" in result:
            holdings_list = result["positions"]
        elif isinstance(result, dict) and "data" in result:
            data = result["data"]
            holdings_list = data if isinstance(data, list) else data.get("holdings", [])
        elif isinstance(result, list):
            holdings_list = result
        else:
            return {}
        return {
            h["stock_code"]: h for h in holdings_list if isinstance(h, dict) and "stock_code" in h
        }

    def get_trades(self, limit: int = 50, portfolio_type: str | None = None) -> dict:
        db = self._get_db()
        emit_log("DEBUG", "portfolio", f"get_trades(limit={limit}, type={portfolio_type})")
        try:
            query = db.query(TradeRecord)
            if portfolio_type:
                query = query.filter_by(portfolio_type=portfolio_type)
            trades = query.order_by(TradeRecord.id.desc()).limit(limit).all()
            result = [
                {
                    "stock_code": t.stock_code,
                    "stock_name": t.stock_name,
                    "trade_date": t.trade_date,
                    "trade_type": t.trade_type.value
                    if hasattr(t.trade_type, "value")
                    else str(t.trade_type),
                    "price": t.price,
                    "quantity": t.quantity,
                    "amount": t.amount,
                    "reason": t.reason,
                }
                for t in trades
            ]
            return {"status": "ok", "data": result}
        finally:
            db.close()

    def get_stock_info(self, code: str) -> dict:
        db = self._get_db()
        try:
            info = db.query(StockInfo).filter_by(stock_code=code).first()
            if not info:
                return {"status": "error", "message": f"未找到 {code}"}
            return {
                "status": "ok",
                "data": {
                    "stock_code": info.stock_code,
                    "stock_name": info.stock_name,
                    "category": info.category,
                    "industry": info.industry,
                    "pe_ratio": round(info.pe_ratio, 1) if info.pe_ratio else None,
                    "pb_ratio": round(info.pb_ratio, 2) if info.pb_ratio else None,
                    "latest_price": round(info.latest_price, 2) if info.latest_price else None,
                    "change_pct": round(info.change_pct, 2) if info.change_pct else None,
                    "trend": info.trend,
                    "rsi_14": round(info.rsi_14, 1) if info.rsi_14 else None,
                    "kline_count": info.kline_count,
                    "ma_alignment": info.ma_alignment,
                },
            }
        finally:
            db.close()

    def get_all_stock_info(self) -> dict:
        db = self._get_db()
        try:
            items = db.query(StockInfo).order_by(StockInfo.trend, StockInfo.rsi_14.desc()).all()
            result = [
                {
                    "stock_code": s.stock_code,
                    "stock_name": s.stock_name,
                    "industry": s.industry,
                    "pe_ratio": round(s.pe_ratio, 1) if s.pe_ratio else None,
                    "latest_price": round(s.latest_price, 2) if s.latest_price else None,
                    "change_pct": round(s.change_pct, 2) if s.change_pct else None,
                    "trend": s.trend,
                    "rsi_14": round(s.rsi_14, 1) if s.rsi_14 else None,
                }
                for s in items
            ]
            return {"status": "ok", "positions": result, "total": len(result)}
        finally:
            db.close()

    def search_stocks(self, query: str = "", limit: int = 20) -> dict:
        db = self._get_db()
        try:
            if query:
                items = (
                    db.query(StockInfo)
                    .filter(
                        (StockInfo.stock_code.contains(query))
                        | (StockInfo.stock_name.contains(query))
                    )
                    .limit(limit)
                    .all()
                )
            else:
                items = db.query(StockInfo).order_by(StockInfo.trend).limit(limit).all()
            result = [
                {
                    "stock_code": s.stock_code,
                    "stock_name": s.stock_name,
                    "industry": s.industry,
                    "latest_price": round(s.latest_price, 2) if s.latest_price else None,
                    "change_pct": round(s.change_pct, 2) if s.change_pct else None,
                    "trend": s.trend,
                    "pe_ratio": round(s.pe_ratio, 1) if s.pe_ratio else None,
                }
                for s in items
            ]
            return {"status": "ok", "positions": result, "total": len(result)}
        finally:
            db.close()

    def add_position(
        self,
        portfolio_type: str,
        stock_code: str,
        stock_name: str,
        buy_price: float,
        quantity: int,
        buy_date: str | None = None,
        buy_reason: str = "",
    ) -> dict:
        db = self._get_db()
        try:
            from datetime import datetime

            existing = (
                db.query(Portfolio)
                .filter_by(
                    stock_code=stock_code, portfolio_type=portfolio_type, status=TradeStatus.HOLDING
                )
                .first()
            )
            if existing:
                return {
                    "status": "error",
                    "message": f"{stock_name}({stock_code}) already in portfolio",
                }

            holding = Portfolio(
                stock_code=stock_code,
                stock_name=stock_name,
                buy_date=buy_date or datetime.now().strftime("%Y-%m-%d"),
                buy_price=buy_price,
                quantity=quantity,
                current_price=buy_price,
                status=TradeStatus.HOLDING,
                buy_reason=buy_reason,
                portfolio_type=portfolio_type,
            )
            db.add(holding)

            trade = TradeRecord(
                stock_code=stock_code,
                stock_name=stock_name,
                trade_date=buy_date or datetime.now().strftime("%Y-%m-%d"),
                trade_type="BUY",
                price=buy_price,
                quantity=quantity,
                amount=buy_price * quantity,
                reason=buy_reason,
                portfolio_type=portfolio_type,
            )
            db.add(trade)
            db.commit()
            return {"status": "ok", "message": f"Added {stock_name}({stock_code})"}
        except Exception as e:
            db.rollback()
            return {"status": "error", "message": str(e)}
        finally:
            db.close()

    def sell_position(
        self,
        portfolio_type: str,
        stock_code: str,
        sell_price: float,
        sell_date: str | None = None,
        sell_reason: str = "",
    ) -> dict:
        db = self._get_db()
        try:
            from datetime import datetime

            holding = (
                db.query(Portfolio)
                .filter_by(
                    stock_code=stock_code, portfolio_type=portfolio_type, status=TradeStatus.HOLDING
                )
                .first()
            )
            if not holding:
                return {"status": "error", "message": f"{stock_code} not found in portfolio"}

            holding.status = TradeStatus.SOLD
            holding.sell_price = sell_price
            holding.sell_date = sell_date or datetime.now().strftime("%Y-%m-%d")
            holding.sell_reason = sell_reason

            trade = TradeRecord(
                stock_code=stock_code,
                stock_name=holding.stock_name,
                trade_date=sell_date or datetime.now().strftime("%Y-%m-%d"),
                trade_type="SELL",
                price=sell_price,
                quantity=holding.quantity,
                amount=sell_price * holding.quantity,
                reason=sell_reason,
                portfolio_type=portfolio_type,
            )
            db.add(trade)
            db.commit()

            pnl_pct = (sell_price - holding.buy_price) / holding.buy_price * 100
            return {
                "status": "ok",
                "message": f"Sold {holding.stock_name}({stock_code})",
                "pnl_pct": round(pnl_pct, 2),
            }
        except Exception as e:
            db.rollback()
            return {"status": "error", "message": str(e)}
        finally:
            db.close()

    def get_portfolio_summary(self, portfolio_type: str) -> dict:
        db = self._get_db()
        try:
            holdings = (
                db.query(Portfolio)
                .filter_by(portfolio_type=portfolio_type, status=TradeStatus.HOLDING)
                .all()
            )
            total_cost = sum(h.buy_price * h.quantity for h in holdings)
            total_value = sum((h.current_price or h.buy_price) * h.quantity for h in holdings)
            total_pnl = total_value - total_cost
            pnl_pct = (total_pnl / total_cost * 100) if total_cost > 0 else 0

            trades = db.query(TradeRecord).filter_by(portfolio_type=portfolio_type).all()
            _win_trades = [t for t in trades if t.trade_type == "SELL" and t.price > 0]
            sold_positions = (
                db.query(Portfolio)
                .filter_by(portfolio_type=portfolio_type, status=TradeStatus.SOLD)
                .all()
            )
            win_count = sum(
                1 for p in sold_positions if p.sell_price and p.sell_price > p.buy_price
            )
            total_sold = len(sold_positions)
            win_rate = (win_count / total_sold * 100) if total_sold > 0 else 0

            return {
                "status": "ok",
                "portfolio_type": portfolio_type,
                "position_count": len(holdings),
                "total_cost": round(total_cost, 2),
                "total_value": round(total_value, 2),
                "total_asset": round(total_value, 2),
                "cash": 0,
                "total_pnl": round(total_pnl, 2),
                "pnl_pct": round(pnl_pct, 2),
                "total_return_pct": round(pnl_pct, 2),
                "win_rate": round(win_rate, 1),
                "total_trades": len(trades),
            }
        finally:
            db.close()

    def get_all_portfolios_summary(self) -> dict:
        results = {}
        for ptype in ["limit_up", "momentum", "value"]:
            results[ptype] = self.get_portfolio_summary(ptype)
        return {"status": "ok", "summaries": results}

    def reset_portfolio(self, portfolio_type: str | None = None) -> dict:
        db = self._get_db()
        try:
            query = db.query(Portfolio)
            if portfolio_type:
                query = query.filter_by(portfolio_type=portfolio_type)
            query.delete()

            trade_query = db.query(TradeRecord)
            if portfolio_type:
                trade_query = trade_query.filter_by(portfolio_type=portfolio_type)
            trade_query.delete()

            db.commit()
            return {"status": "ok", "message": f"Reset portfolio {portfolio_type or 'all'}"}
        except Exception as e:
            db.rollback()
            return {"status": "error", "message": str(e)}
        finally:
            db.close()

    def get_nav(self, portfolio_type: str, limit: int = 30) -> dict:
        from shared.models import DailyNAV

        db = self._get_db()
        try:
            rows = (
                db.query(DailyNAV)
                .filter_by(portfolio_type=portfolio_type)
                .order_by(DailyNAV.date.desc())
                .limit(limit)
                .all()
            )
            nav = [
                {
                    "date": r.date,
                    "total_asset": r.total_asset or 0,
                    "cash": r.cash or 0,
                    "stock_value": r.stock_value or 0,
                    "daily_return_pct": r.daily_return_pct or 0,
                    "cumulative_return_pct": r.cumulative_return_pct or 0,
                    "position_count": r.position_count or 0,
                }
                for r in reversed(rows)
            ]
            return {"status": "ok", "nav": nav}
        finally:
            db.close()

    def record_nav(self, portfolio_type: str, date: str | None = None, notes: str = "") -> dict:
        from datetime import datetime

        from shared.models import DailyNAV

        db = self._get_db()
        try:
            date = date or datetime.now().strftime("%Y-%m-%d")
            holdings = (
                db.query(Portfolio)
                .filter_by(portfolio_type=portfolio_type, status=TradeStatus.HOLDING)
                .all()
            )
            total_cost = sum(h.buy_price * h.quantity for h in holdings)
            total_value = sum((h.current_price or h.buy_price) * h.quantity for h in holdings)

            # Get previous NAV for cumulative calculation
            prev = (
                db.query(DailyNAV)
                .filter_by(portfolio_type=portfolio_type)
                .order_by(DailyNAV.date.desc())
                .first()
            )

            daily_return = 0
            if prev and prev.total_asset and prev.total_asset > 0:
                daily_return = (total_value - prev.total_asset) / prev.total_asset * 100
            cumulative_return = 0
            if total_cost > 0:
                cumulative_return = (total_value - total_cost) / total_cost * 100

            # Check if entry for this date already exists
            existing = (
                db.query(DailyNAV).filter_by(portfolio_type=portfolio_type, date=date).first()
            )
            if existing:
                existing.total_asset = total_value
                existing.cash = 0
                existing.stock_value = total_value
                existing.daily_return_pct = round(daily_return, 4)
                existing.cumulative_return_pct = round(cumulative_return, 4)
                existing.position_count = len(holdings)
                existing.notes = notes
            else:
                nav = DailyNAV(
                    date=date,
                    total_asset=total_value,
                    cash=0,
                    stock_value=total_value,
                    daily_return_pct=round(daily_return, 4),
                    cumulative_return_pct=round(cumulative_return, 4),
                    position_count=len(holdings),
                    portfolio_type=portfolio_type,
                    notes=notes,
                )
                db.add(nav)
            db.commit()
            return {"status": "ok", "date": date, "total_asset": round(total_value, 2)}
        except Exception as e:
            db.rollback()
            return {"status": "error", "message": str(e)}
        finally:
            db.close()

    def update_prices(self) -> dict:
        db = self._get_db()
        try:
            holdings = db.query(Portfolio).filter_by(status=TradeStatus.HOLDING).all()
            updated = 0
            for h in holdings:
                info = db.query(StockInfo).filter_by(stock_code=h.stock_code).first()
                if info and info.latest_price:
                    h.current_price = info.latest_price
                    updated += 1
            db.commit()
            return {"status": "ok", "updated": updated}
        except Exception as e:
            db.rollback()
            return {"status": "error", "message": str(e)}
        finally:
            db.close()
