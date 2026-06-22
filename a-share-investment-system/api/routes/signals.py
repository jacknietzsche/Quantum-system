"""信号推送API"""

from fastapi import APIRouter

from shared.logging import emit_log

router = APIRouter()


@router.get("/today")
def today_signals():
    try:
        from services.data_bus import DatabaseBackedDataBus
        from services.factor_farm import FactorFarm
        from services.market_perception import MarketPerception

        mp = MarketPerception()
        ff = FactorFarm()
        data_bus = DatabaseBackedDataBus()

        # 从DataBus获取实时市场宽度和指数数据
        breadth = data_bus.get_market_breadth()
        indices = data_bus.get_market_indices()

        if not breadth:
            emit_log("WARNING", "signals", "市场宽度数据为空, 使用默认值")
            breadth = {"up": 1500, "down": 1500, "total": 5000, "limit_up": 15, "limit_down": 10}
        if not indices:
            emit_log("WARNING", "signals", "指数数据为空")
            indices = {}

        regime = mp.perceive(
            {
                "breadth": breadth,
                "indices": indices,
            }
        ).data
        factors = ff.get_top_factors(5).data
        return {
            "regime": regime.get("regime", "NEUTRAL"),
            "position_advice": regime.get("adaptive_params", {}),
            "top_factors": factors.get("factors", []),
        }
    except Exception as e:
        emit_log("ERROR", "signals", f"信号生成失败: {e}")
        return {"error": str(e)}
