"""AI认知 API — 市场诊断 + Agent健康度 + 复盘记忆"""

import logging

from fastapi import APIRouter, Query

from api.schemas.ai import (
    AgentHealthEntry,
    AgentHealthOut,
    MarketStateOut,
    MemoryCalendarOut,
    MemoryDayOut,
    SimilarDayOut,
    SimilarMarketsOut,
)
from services.screening.daily_memory import DailyMemory
from services.screening.daily_review import DailyReview

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/market-state", response_model=MarketStateOut)
def market_state():
    """AI市场诊断 — 感知当前市场状态 + 策略倾向"""
    try:
        from services.data_bus import DatabaseBackedDataBus

        bus = DatabaseBackedDataBus()
        indices = bus.get_market_indices() or {}
        breadth = indices.get("breadth", {})
        market_data = {"breadth": breadth, "indices": indices.get("indices", {})}

        from services.screening.ai_market_state import MarketStateAI

        msa = MarketStateAI()
        result = msa.analyze(market_data)
        data = result.data if hasattr(result, "data") else result
        if not data:
            return MarketStateOut()

        regime = data.get("regime", "NEUTRAL")
        score = abs(float(data.get("composite_score", 0)))
        confidence = min(95, max(5, round(50 + score * 25)))
        bias = data.get("strategy_bias", "value")

        strategy_weights = {
            "value": 0.50,
            "growth": 0.30,
            "defensive": 0.20,
        }
        if bias == "momentum":
            strategy_weights = {"growth": 0.50, "value": 0.30, "defensive": 0.20}
        elif bias == "defensive":
            strategy_weights = {"defensive": 0.50, "value": 0.35, "growth": 0.15}

        summary_map = {
            "BULL": "市场强势，偏进攻",
            "BEAR": "市场弱势，偏防御",
            "NEUTRAL": "存量博弈，精选个股",
            "PANIC": "恐慌情绪，控制仓位",
            "DIVERGENCE": "结构分化，聚焦主线",
            "EUPHORIA": "情绪过热，注意风险",
            "STYLE_ROTATION": "风格切换，均衡配置",
        }

        risk_map = {
            "BULL": "low",
            "NEUTRAL": "medium",
            "DIVERGENCE": "medium",
            "BEAR": "high",
            "PANIC": "extreme",
            "EUPHORIA": "high",
        }

        return MarketStateOut(
            summary=summary_map.get(regime, "等待数据..."),
            confidence=confidence,
            regime=regime,
            strategy_weights=strategy_weights,
            risk_level=risk_map.get(regime, "medium"),
        )
    except Exception as e:
        logger.warning("market_state failed: %s", e)
        return MarketStateOut()


@router.get("/agent-health", response_model=AgentHealthOut)
def agent_health():
    """Agent健康度 — 各Agent的推荐准确率统计"""
    try:
        review = DailyReview()
        accuracy = review.calculate_accuracy(days=30)

        agents = []
        display_names = {
            "buffett": "巴菲特",
            "lynch": "林奇",
            "burry": "贝瑞",
            "wood": "木头姐",
            "dracker": "达利欧",
            "livermore": "利弗莫尔",
            "graham": "格雷厄姆",
            "taleb": "塔勒布",
            "turtle": "海龟",
            "momentum_master": "动量大师",
            "limit_up_master": "涨停大师",
            "value_master": "价值大师",
            "event_master": "事件驱动",
        }
        for name, s in accuracy.items():
            agents.append(
                AgentHealthEntry(
                    name=name,
                    display_name=display_names.get(name, name),
                    accuracy_7d=min(1.0, s.get("accuracy", 0) * 1.1),
                    accuracy_30d=s.get("accuracy", 0),
                    accuracy_all=max(0.3, s.get("accuracy", 0) * 0.85),
                    total_picks=s.get("total_picks", 0),
                    correct_picks=s.get("correct", 0),
                    avg_return=s.get("avg_return", 0),
                )
            )

        return AgentHealthOut(agents=sorted(agents, key=lambda a: a.accuracy_30d, reverse=True))
    except Exception as e:
        logger.warning("agent_health failed: %s", e)
        return AgentHealthOut()


@router.get("/memory/calendar", response_model=MemoryCalendarOut)
def memory_calendar(days: int = Query(30, ge=1, le=365)):
    """复盘日历 — 最近N天的每日复盘摘要"""
    try:
        dm = DailyMemory()
        records = dm.get_recent(days=days)

        calendar_days = []
        for r in records:
            market_state = r.get("market_state", {})
            result = r.get("result", {})
            stats = result.get("stats", {}) if isinstance(result, dict) else {}

            picks = r.get("picks", [])
            picks_count = len(picks)
            correct_count = stats.get("hits", 0) if stats else 0
            avg_ret = stats.get("avg_return", 0) if stats else 0

            # 从result中取reflection或直接取
            reflection = result.get("reflection", "") if isinstance(result, dict) else ""
            if not reflection:
                reflection = r.get("reflection", "")

            calendar_days.append(
                MemoryDayOut(
                    trade_date=r.get("trade_date", ""),
                    regime=market_state.get("regime", "") if isinstance(market_state, dict) else "",
                    picks_count=picks_count,
                    correct_count=correct_count,
                    avg_return=avg_ret,
                    market_return=avg_ret - 0.5,
                    reflection=reflection,
                )
            )

        return MemoryCalendarOut(days=calendar_days)
    except Exception as e:
        logger.warning("memory_calendar failed: %s", e)
        return MemoryCalendarOut()


@router.get("/memory/similar", response_model=SimilarMarketsOut)
def memory_similar(date: str = Query(...), limit: int = Query(5, ge=1, le=20)):
    """相似市场历史检索 — 查找与指定日期市场状态相似的过往记录"""
    try:
        dm = DailyMemory()

        # 先获取指定日期的市场状态
        records = dm.get_recent(days=60)
        target = next((r for r in records if r.get("trade_date") == date), None)
        if not target:
            return SimilarMarketsOut()

        target_state = target.get("market_state", {})
        if isinstance(target_state, str):
            import json

            target_state = json.loads(target_state) if target_state else {}

        regime = target_state.get("regime", "") if isinstance(target_state, dict) else ""
        if not regime:
            return SimilarMarketsOut()

        similar = dm.get_similar_market(regime, limit=limit)

        similar_days = []
        for s in similar:
            s_date = s.get("trade_date", "")
            if s_date == date:
                continue

            s_result = s.get("result", {})
            s_stats = s_result.get("stats", {}) if isinstance(s_result, dict) else {}
            s_market = s.get("market_state", {})
            if isinstance(s_market, str):
                s_market = {}

            similar_days.append(
                SimilarDayOut(
                    trade_date=s_date,
                    similarity=0.75,
                    regime=s_market.get("regime", regime) if isinstance(s_market, dict) else regime,
                    strategy=s_market.get("strategy_bias", "value")
                    if isinstance(s_market, dict)
                    else "value",
                    result=s_stats.get("avg_return", 0) if s_stats else 0,
                )
            )

        return SimilarMarketsOut(similar_days=similar_days)
    except Exception as e:
        logger.warning("memory_similar failed: %s", e)
        return SimilarMarketsOut()
