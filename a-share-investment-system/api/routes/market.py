"""市场态势API"""

from fastapi import APIRouter

router = APIRouter()


@router.get("/regime")
def market_regime():
    """市场态势判断 — 从 DataBus 获取指数和广度数据,通过 MarketPerception 感知"""
    try:
        from services.data_bus import DatabaseBackedDataBus

        data_bus = DatabaseBackedDataBus()
        indices = data_bus.get_market_indices()
        breadth = indices.get("breadth", {})
        market_data = {"breadth": breadth, "indices": indices.get("indices", {})}

        from services.market_perception import MarketPerception

        mp = MarketPerception()
        result = mp.perceive(market_data)
        return result.data if hasattr(result, "data") else result
    except Exception as e:
        return {
            "regime": "unknown",
            "confidence": 0,
            "total_score": 0,
            "dimension_scores": {},
            "adaptive_params": {"target_position_pct": 0.5, "max_holdings": 5},
            "error": str(e),
        }
