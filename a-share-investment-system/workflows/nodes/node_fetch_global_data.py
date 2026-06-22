"""Node 1: Fetch global market data — 全局数据总线"""

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

from workflows.nodes._shared import _log, create_data_bus, logger
from workflows.state import AShareSuperState
from workflows.stubs import get_services


def node_fetch_global_data(state: AShareSuperState) -> dict:
    """第一层:全局数据总线 — 唯一数据入口"""
    from shared.models import Portfolio, TradeStatus, get_session

    logs = list(state.get("logs", []))
    errors = list(state.get("errors", []))
    logs.append(_log(state, "📡 [第一层] 全局数据总线启动..."))

    data_bus = create_data_bus()
    data_source = "unknown"

    try:
        # 并行获取所有数据
        def fetch_indices():
            return data_bus.get_market_indices()

        def fetch_breadth():
            return data_bus.get_market_breadth()

        def fetch_sectors():
            return data_bus.get_sector_ranking(10)

        def fetch_north():
            return data_bus.get_north_flow()

        with ThreadPoolExecutor(max_workers=4) as executor:
            f_indices = executor.submit(fetch_indices)
            f_breadth = executor.submit(fetch_breadth)
            f_sectors = executor.submit(fetch_sectors)
            f_north = executor.submit(fetch_north)

            indices = f_indices.result()
            breadth = f_breadth.result()
            sectors = f_sectors.result()
            north_flow = f_north.result()

        data_source = "akshare"  # 主数据源

        # 更新持仓行情
        session = get_session()
        holdings = session.query(Portfolio).filter_by(status=TradeStatus.HOLDING).all()
        portfolio = []
        for h in holdings:
            quote = data_bus.get_stock_quote(h.stock_code)
            if quote and quote["price"] > 0:
                h.current_price = quote["price"]
            portfolio.append(
                {
                    "stock_code": h.stock_code,
                    "stock_name": h.stock_name,
                    "buy_price": h.buy_price,
                    "quantity": h.quantity,
                    "current_price": h.current_price or 0,
                    "cost_value": h.cost_value,
                    "current_value": h.current_value,
                    "profit_loss": h.profit_loss,
                    "profit_loss_pct": h.profit_loss_pct,
                }
            )
        session.commit()
        session.close()

        # 获取自选股 + 同步最新行情到 StockInfo 表
        watchlist = []
        all_codes_to_refresh = []  # 需要更新 StockInfo 的股票代码
        try:
            from shared.models import StockInfo as _StockInfo
            from shared.models import Watchlist, get_session

            session = get_session()
            wl_items = session.query(Watchlist).all()
            for w in wl_items:
                quote = data_bus.get_stock_quote(w.stock_code)
                price = quote["price"] if quote else 0
                change_pct = quote["change_pct"] if quote else 0
                watchlist.append(
                    {
                        "stock_code": w.stock_code,
                        "stock_name": w.stock_name,
                        "category": w.category or "自选",
                        "price": price,
                        "change_pct": change_pct,
                    }
                )
                all_codes_to_refresh.append((w.stock_code, price, change_pct))

            # 同步持仓的最新价格到 StockInfo
            for h_item in portfolio:
                code = h_item["stock_code"]
                price = h_item.get("current_price", 0)
                all_codes_to_refresh.append((code, price, 0))

            # 批量更新 StockInfo.latest_price / change_pct(行级快照)
            updated_count = 0
            for code, price, pct in all_codes_to_refresh:
                if not price or price <= 0:
                    continue
                info = session.query(_StockInfo).filter_by(stock_code=code).first()
                if info:
                    info.latest_price = price
                    if pct:
                        info.change_pct = pct
                    info.updated_at = datetime.now()
                    updated_count += 1
            session.commit()
            session.close()
            if updated_count:
                logs.append(_log(state, f"📊 StockInfo 已同步 {updated_count} 只股票最新价格"))
        except Exception as e:
            logs.append(_log(state, f"⚠️ StockInfo 同步失败: {e}"))
            try:
                session.close()
            except Exception as _e:
                logger.warning("Suppressed: %s", _e)

        # 检查 StockInfo 技术指标是否过期(>24h),自动触发后台刷新
        try:
            from shared.models import StockInfo as _SI
            from shared.models import get_session

            _s = get_session()
            stale_info = (
                _s.query(_SI)
                .filter(
                    (_SI.updated_at is None)
                    | (_SI.updated_at < datetime.now() - timedelta(hours=24))
                )
                .count()
            )
            _s.close()
            if stale_info > 0:
                logs.append(_log(state, f"🔄 发现 {stale_info} 只股票技术指标过期,自动触发刷新..."))

                def _bg_refresh():
                    try:
                        from services.data_initializer import DataInitializer

                        DataInitializer().refresh_full_universe(max_stocks=2000)
                        logs.append(_log(state, "✅ 后台技术指标刷新完成"))
                    except Exception as e:
                        logs.append(_log(state, f"⚠️ 后台刷新失败: {e}"))

                threading.Thread(target=_bg_refresh, daemon=True).start()
            else:
                logs.append(_log(state, "✅ StockInfo 技术指标均为最新,无需刷新"))
        except Exception as _e:
            logger.warning("Suppressed: %s", _e)

        market_data = {
            "indices": indices,
            "breadth": breadth,
            "sectors": sectors.to_dict("records")
            if hasattr(sectors, "empty") and not sectors.empty
            else [],
            "north_flow": north_flow,
        }

        # 注入MarketPerception — AShare-X增强
        services = get_services()
        if services.market_perception:
            perception_result = services.market_perception.perceive(market_data)
            if perception_result.status == "ok":
                market_data["_perception"] = perception_result.data
                logs.append(
                    _log(
                        state,
                        f"📊 市场感知: {perception_result.data['regime']} "
                        f"(总分{perception_result.data['total_score']}, "
                        f"目标仓位{perception_result.data['adaptive_params']['target_position_pct']:.0%})",
                    )
                )

        logs.append(
            _log(
                state,
                f"✅ 数据获取完成: 持仓{len(portfolio)}只, 自选{len(watchlist)}只, 数据源={data_source}",
            )
        )

        return {
            "market_data": market_data,
            "portfolio": portfolio,
            "watchlist": watchlist,
            "data_source": data_source,
            "logs": logs,
        }
    except Exception as e:
        errors.append(f"数据获取失败: {e}")
        logs.append(_log(state, f"❌ 数据获取失败: {e}"))
        return {
            "market_data": {},
            "portfolio": [],
            "watchlist": [],
            "data_source": "failed",
            "errors": errors,
            "logs": logs,
        }
