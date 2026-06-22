"""Stage 0: 市场感知模块 — 看天吃饭, 随市而动

在每次筛股前运行, 采集当前市场数据, 判断市场状态 (BULL/BEAR/SHOCK/VOLATILE),
并输出四维评分的动态权重建议。结果当日缓存, 重复调用复用。

数据来源: 现有行情数据, 无新增外部依赖。
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)

# ── 规则降级默认权重 ──
_RULE_WEIGHTS: dict[str, dict[str, float]] = {
    "BULL": {"trend": 0.40, "capital": 0.30, "fundamental": 0.20, "defensive": 0.10},
    "BEAR": {"trend": 0.15, "capital": 0.20, "fundamental": 0.25, "defensive": 0.40},
    "SHOCK": {"trend": 0.25, "capital": 0.30, "fundamental": 0.25, "defensive": 0.20},
    "VOLATILE": {"trend": 0.20, "capital": 0.30, "fundamental": 0.15, "defensive": 0.35},
}

_NEUTRAL_WEIGHTS = {"trend": 0.25, "capital": 0.25, "fundamental": 0.25, "defensive": 0.25}


@dataclass
class MarketDiagnosis:
    """市场诊断结果

    state:       BULL / BEAR / SHOCK / VOLATILE
    confidence:  0.0 - 1.0
    weights:     四维评分权重 (总和1.0)
    summary:     一句话市场总结 (用于前端AI认知简报)
    details:     完整指标+理由 (用于Dashboard展示)
    """

    state: str = "SHOCK"
    confidence: float = 0.5
    weights: dict[str, float] = field(default_factory=lambda: dict(_NEUTRAL_WEIGHTS))
    summary: str = "市场状态未知"
    details: dict[str, Any] = field(default_factory=dict)
    timestamp: str = ""


class MarketCollector:
    """采集市场数据, 不依赖外部API, 从 DB + MarketSnapshot 读取"""

    @staticmethod
    def collect() -> dict:
        """采集当前市场指标"""
        data = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "indices": {},
            "breadth": {"up": 0, "down": 0, "limit_up": 0, "limit_down": 0, "total": 0},
            "sectors": {"top": [], "bottom": []},
            "volume": {"total_amount": 0, "amount_vs_5d": 0},
            "volatility": 0,
            "limit_up_count": 0,
            "max_continuous_boards": 0,
            "hot_concepts": [],
        }

        try:
            # 1. 从 StockInfo 获取市场涨跌分布
            from shared.models import StockInfo, get_session

            s = get_session()
            total = s.query(StockInfo).filter(StockInfo.latest_price > 0).count()
            up = s.query(StockInfo).filter(StockInfo.change_pct > 2).count()
            down = s.query(StockInfo).filter(StockInfo.change_pct < -2).count()
            limit_up_stocks = s.query(StockInfo).filter(StockInfo.change_pct >= 9.5).count()
            limit_down_stocks = s.query(StockInfo).filter(StockInfo.change_pct <= -9.5).count()
            s.close()

            data["breadth"] = {
                "up": up,
                "down": down,
                "limit_up": limit_up_stocks,
                "limit_down": limit_down_stocks,
                "total": total,
            }
        except Exception as e:
            logger.debug("[MarketPerception] breadth collect: %s", e)

        try:
            # 2. 从 MarketSnapshot 获取板块热度
            from shared.models import MarketSnapshot, get_session

            s = get_session()
            snap = s.query(MarketSnapshot).filter_by(snapshot_type="sector_rank_industry").first()
            if snap and snap.data_json:
                sectors = json.loads(snap.data_json)
                if sectors:
                    data["sectors"]["top"] = [
                        {"name": sec.get("plate_name", ""), "change": sec.get("rate", 0)}
                        for sec in sectors[:5]
                        if sec.get("rate", 0)
                    ]
                    data["sectors"]["bottom"] = [
                        {"name": sec.get("plate_name", ""), "change": sec.get("rate", 0)}
                        for sec in sectors[-3:]
                        if sec.get("rate", 0)
                    ]
            s.close()
        except Exception as e:
            logger.debug("[MarketPerception] sectors collect: %s", e)

        try:
            # 3. 从 zzshare MarketSnapshot 获取涨停数据
            from shared.models import MarketSnapshot, get_session

            s = get_session()
            snap = s.query(MarketSnapshot).filter_by(snapshot_type="uplimit_stocks").first()
            if snap and snap.data_json:
                up_list = json.loads(snap.data_json)
                data["limit_up_count"] = len(up_list)
            snap2 = s.query(MarketSnapshot).filter_by(snapshot_type="hot_stocks_ths").first()
            if snap2 and snap2.data_json:
                hot = json.loads(snap2.data_json)
                data["hot_concepts"] = [
                    {"name": h.get("symbol_name", ""), "rank": h.get("rank", 0)} for h in hot[:10]
                ]
            s.close()
        except Exception as e:
            logger.debug("[MarketPerception] limit_up collect: %s", e)

        # 4. 从 StockInfo 计算波动率代理
        try:
            from shared.models import StockInfo, get_session

            s = get_session()
            avg_vol = (
                s.query(StockInfo.volatility_20d)
                .filter(StockInfo.volatility_20d > 0)
                .order_by(StockInfo.volatility_20d.desc())
                .limit(100)
                .all()
            )
            if avg_vol:
                data["volatility"] = round(sum(v[0] for v in avg_vol) / len(avg_vol), 3)
            s.close()
        except Exception as e:
            logger.debug("[MarketPerception] vol collect: %s", e)

        return data


class MarketPerception:
    """市场感知 — Stage 0

    用法:
        mp = MarketPerception()
        diagnosis = mp.diagnose()  # 当日缓存, 重复调用复用
    """

    def __init__(self, llm_client=None):
        self._llm = llm_client
        self._cache: MarketDiagnosis | None = None
        self._cache_date: str = ""

    def diagnose(self, force_refresh: bool = False) -> MarketDiagnosis:
        """执行市场诊断 — 当日缓存"""
        today = datetime.now().strftime("%Y-%m-%d")
        if self._cache and self._cache_date == today and not force_refresh:
            logger.debug("[MarketPerception] using cached: %s", self._cache.state)
            return self._cache

        # 采集数据
        data = MarketCollector.collect()

        # LLM 诊断 (优先)
        diagnosis = self._llm_diagnose(data) if self._llm is not None else self._rule_diagnose(data)

        diagnosis.timestamp = data["timestamp"]
        diagnosis.details = data

        # 缓存
        self._cache = diagnosis
        self._cache_date = today

        logger.info(
            "[MarketPerception] %s (conf=%.2f) weights=%s summary=%s",
            diagnosis.state,
            diagnosis.confidence,
            diagnosis.weights,
            diagnosis.summary,
        )
        return diagnosis

    def _llm_diagnose(self, data: dict) -> MarketDiagnosis:
        """LLM 市场诊断"""
        try:
            prompt = self._build_prompt(data)
            text = self._llm.invoke(prompt, temperature=0.3, max_tokens=300, timeout=10)
            if text:
                # 清理可能的 markdown 代码块标记
                clean = text.strip()
                if clean.startswith("```"):
                    clean = clean.split("\n", 1)[-1]
                    clean = clean.rsplit("```", 1)[0]
                result = json.loads(clean)
                return MarketDiagnosis(
                    state=result.get("state", "SHOCK"),
                    confidence=float(result.get("confidence", 0.5)),
                    weights=result.get("weights", dict(_NEUTRAL_WEIGHTS)),
                    summary=result.get("reason", "")[:80],
                )
        except Exception as e:
            logger.warning("[MarketPerception] LLM diagnosis failed, fallback to rules: %s", e)

        return self._rule_diagnose(data)

    def _rule_diagnose(self, data: dict) -> MarketDiagnosis:
        """规则降级诊断 (无需LLM)"""
        b = data.get("breadth", {})
        up = b.get("up", 0) or 1
        down = b.get("down", 0) or 1
        total = b.get("total", 1) or 1
        limit_up_n = b.get("limit_up", 0) or 0
        limit_down_n = b.get("limit_down", 0) or 0
        vol = data.get("volatility", 0)
        up_ratio = up / max(total, 1)
        down_ratio = down / max(total, 1)
        limit_up_ratio = limit_up_n / max(total, 1)

        signals = []

        # 判断状态
        if limit_up_ratio > 0.03 and limit_up_n > limit_down_n * 3:
            state = "BULL"
            signals.append(f"涨停{limit_up_n}家远多于跌停{limit_down_n}")
        elif up_ratio > 0.3 and down_ratio < 0.1:
            state = "BULL"
            signals.append(f"上涨占比{up_ratio:.0%}")
        elif down_ratio > 0.3 and up_ratio < 0.1:
            state = "BEAR"
            signals.append(f"下跌占比{down_ratio:.0%}")
        elif limit_up_n > 20 and limit_down_n > 20 and vol > 0.5:
            state = "VOLATILE"
            signals.append(f"涨停{limit_up_n}+跌停{limit_down_n}+高波")
        elif 0.1 <= up_ratio <= 0.3 and 0.1 <= down_ratio <= 0.3:
            state = "SHOCK"
            signals.append("涨跌均衡, 结构分化")
        elif vol > 0.6:
            state = "VOLATILE"
            signals.append("高波动率")
        else:
            state = "SHOCK"
            signals.append("无明显方向")

        # 置信度
        if up_ratio > 0.4 or down_ratio > 0.4:
            confidence = 0.8
        elif limit_up_ratio > 0.02:
            confidence = 0.7
        else:
            confidence = 0.5

        weights = dict(_RULE_WEIGHTS.get(state, _NEUTRAL_WEIGHTS))
        summary = f"{signals[0] if signals else '震荡格局'}, {state}"

        return MarketDiagnosis(
            state=state,
            confidence=confidence,
            weights=weights,
            summary=summary,
        )

    @staticmethod
    def _build_prompt(data: dict) -> str:
        """构建LLM提示词"""
        b = data.get("breadth", {})
        sec_top = data.get("sectors", {}).get("top", [])
        sec_bottom = data.get("sectors", {}).get("bottom", [])
        top_str = ", ".join(f"{s.get('name', '?')}+{s.get('change', 0):.1f}%" for s in sec_top[:3])
        bottom_str = ", ".join(
            f"{s.get('name', '?')}{s.get('change', 0):.1f}%" for s in sec_bottom[:3]
        )

        return f"""你是一位A股市场分析师。根据今日市场数据判断市场状态, 输出JSON。

市场状态定义:
- BULL 强势上行: 指数多头, 放量上攻, 主线清晰, 亏钱效应弱
- BEAR 弱势下行: 指数空头, 缩量下跌, 全线溃败
- SHOCK 震荡分化: 指数盘整, 板块轮动, 无持续主线
- VOLATILE 高波动: 大起大落, 涨停跌停均多, 日内反转

今日数据:
上涨>2%: {b.get("up", 0)}家 | 下跌>2%: {b.get("down", 0)}家
涨停: {b.get("limit_up", 0)}家 | 跌停: {b.get("limit_down", 0)}家
最强板块: {top_str}
最弱板块: {bottom_str}
波动率: {data.get("volatility", 0)}
连板高度: {data.get("max_continuous_boards", 0)}板
热点概念: {data.get("hot_concepts", [])[:3]}

输出JSON格式(不要包含其他文字):
{{"state": "BULL/BEAR/SHOCK/VOLATILE", "confidence": 0.8,
 "weights": {{"trend": 0.35, "capital": 0.25, "fundamental": 0.25, "defensive": 0.15}},
 "reason": "一句话总结市场状态(20字以内)"}}"""


def diagnose(force_refresh: bool = False) -> MarketDiagnosis:
    """快捷入口: 使用默认配置执行市场诊断"""
    return MarketPerception().diagnose(force_refresh)
