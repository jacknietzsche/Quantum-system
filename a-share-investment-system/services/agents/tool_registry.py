"""Agent Tool 注册表 - 将 MasterAgent / SkillEngine / DataBus 包装为 AgentTool"""

from datetime import datetime, timedelta

from providers.sources import get_adapter
from services.agents.base_agent import AgentTool
from services.data_bus import DatabaseBackedDataBus
from services.master_agents import get_master_agents
from services.skill_engine import get_skill_engine
from shared.models import StockInfo, get_session


def get_master_list_tool() -> AgentTool:
    """工具: 列出所有可用大师"""
    registry = get_master_agents()
    masters = registry.get_all_names()
    master_descriptions = {
        "cathie_wood": "高增长成长股分析",
        "bill_ackman": "维权投资+管理层驱动",
        "michael_burry": "逆向价值+尾部风险",
        "stanley_druckenmiller": "宏观趋势+动量",
        "aswath_damodaran": "DCF估值+风险溢价",
        "phil_fisher": "成长型+管理层质量",
        "rakesh_jhunjhunwala": "印度式价值投资",
        "howard_marks": "市场周期+第二层思维",
        "joel_greenblatt": "魔法公式(高ROIC+低估值)",
        "peter_lynch_growth": "GARP成长+十倍股",
        "risk_sentinel": "综合风险评估",
        "limit_up_master": "短线涨停博弈",
        "turtle_master": "趋势突破+ATR仓位",
        "candlestick_master": "K线形态识别",
        "trader_vic_master": "1-2-3法则趋势分析",
        "livermore_master": "关键点+金字塔仓位",
        "momentum_master": "中期趋势+动量",
    }
    master_list = [f"{name}({master_descriptions.get(name, '')})" for name in masters]
    return AgentTool(
        name="get_master_list",
        description="获取所有可用的投资大师分析器列表, 每个大师有不同分析风格",
        parameters={},
        fn=lambda: {"masters": master_list, "count": len(master_list)},
    )


def get_master_analyze_tool() -> AgentTool:
    """工具: 调用指定大师分析股票"""
    registry = get_master_agents()

    def _analyze(stock_code: str, master_names: list, stock_data: dict | None = None) -> dict:
        sd = stock_data or {}
        # Map field names from stock_data keys (screening/HardFilter output)
        # to master_agents expected keys.
        field_map = {
            # Core fields (already had)
            "pe_ratio": sd.get("pe", 0),
            "price": sd.get("price", 0),
            "turnover_rate": sd.get("turnover_rate", 0),
            "roe": sd.get("roe", 0),
            "gross_margin": sd.get("gross_margin", 0),
            "total_market_cap": sd.get("market_cap", 0),
            "debt_to_equity": sd.get("debt_to_equity", 0),
            "eps": sd.get("eps", 0),
            "bvps": sd.get("bvps", 0),
            "earnings_growth_3y": sd.get("earnings_growth_3y", 0),
            "revenue_growth_3y": sd.get("revenue_growth_3y", 0),
            "free_cash_flow": sd.get("free_cash_flow", 0),
            "net_income": sd.get("net_income", 0),
            "change_pct": sd.get("change_pct", 0),
            "pb_ratio": sd.get("pb", 0),
            # Financial fields (in _load_universe)
            "operating_margin": sd.get("operating_margin", 0),
            "current_ratio": sd.get("current_ratio", 0),
            "cash_ratio": sd.get("cash_ratio", 0),
            # Volume/price fields
            "daily_volume_ratio": sd.get("volume_ratio", 0),
            "volume": sd.get("volume", 0),
            # MA fields
            "ma5": sd.get("ma5", 0),
            "ma10": sd.get("ma10", 0),
            "ma20": sd.get("ma20", 0),
            "ma60": sd.get("ma60", 0),
            # Trend/volatility
            "trend": sd.get("trend", ""),
            "volatility": sd.get("volatility", 0),
            "volatility_20d": sd.get("volatility", 0),
            # StockInfo fields not in _load_universe (default 0)
            "atr_14": sd.get("atr_14", 0),
            "max_drawdown_60d": sd.get("max_drawdown_60d", 0),
            "ma_alignment": sd.get("ma_alignment", ""),
            # Fields not available (always default)
            "insider_holding_pct": sd.get("insider_holding_pct", 0),
            "rd_intensity": sd.get("rd_intensity", 0),
        }
        names = master_names if isinstance(master_names, list) else [master_names]
        results = registry.analyze_selected(stock_code, field_map, names)
        # Normalize results to handle varying return formats
        normalized = []
        for r in results:
            if not r:
                continue
            # Handle both formats: {"analyst", "score"...} and {"name", "score"...}
            if "analyst" not in r and "name" in r:
                r["analyst"] = r["name"]
            if "stock_code" not in r:
                r["stock_code"] = stock_code
            normalized.append(r)
        return {"results": normalized}

    return AgentTool(
        name="master_analyze",
        description=(
            "调用指定的投资大师分析器对股票进行量化评估."
            " 参数: stock_code=股票代码, master_names=大师名称列表, "
            "stock_data=股票基本面数据字典"
        ),
        parameters={
            "stock_code": "股票代码(如600519)",
            "master_names": "大师名称列表",
            "stock_data": "股票数据字典",
        },
        required_params=["stock_code", "master_names"],
        fn=_analyze,
    )


def get_skill_knowledge_tool() -> AgentTool:
    """工具: 获取技能知识"""
    engine = get_skill_engine()

    def _knowledge(skill_name: str, context: str = "") -> dict:
        known_skills = engine.get_all_skill_names()
        if skill_name not in known_skills:
            available = [s for s in known_skills if skill_name.lower() in s.lower()]
            if not available:
                return {"error": f"Unknown skill: {skill_name}", "available": known_skills}
            skill_name = available[0]
        knowledge = engine.inject_knowledge(skill_name, context)
        return {"skill": skill_name, "knowledge": knowledge[:3000]}

    return AgentTool(
        name="skill_knowledge",
        description=(
            "获取指定投资技能的分析框架和知识。可用技能包括: "
            "buffett(巴菲特), munger-perspective(芒格), taleb-perspective(塔勒布), "
            "financial-health(财务健康), industry-competition-moat(护城河), "
            "risk-warning-catalysts(风险预警), valuation-investment-strategy(估值), "
            "limit-up-strategy(涨停策略), turtle-trading-rules(海龟交易)"
        ),
        parameters={"skill_name": "技能名称", "context": "上下文(股票代码或分析焦点)"},
        required_params=["skill_name"],
        fn=_knowledge,
    )


# ── 数据工具: 包装 DataBus/MarketDataProvider ──


def get_financials_tool() -> AgentTool:
    """工具: 获取个股基本面数据"""

    def _fetch(stock_code: str) -> dict:
        try:
            bus = DatabaseBackedDataBus()
            # 尝试从DataBus获取基本面
            result = bus.get_stock_basic(stock_code)
            if result and not isinstance(result, dict):
                result = result.to_dict() if hasattr(result, "to_dict") else {"data": str(result)}
            if result:
                return {"stock_code": stock_code, "financials": result}
            # 降级到StockInfo表
            session = get_session()
            info = session.query(StockInfo).filter_by(stock_code=stock_code).first()
            session.close()
            if info:
                return {
                    "stock_code": stock_code,
                    "financials": {
                        "pe": getattr(info, "pe_ratio", 0),
                        "pb": getattr(info, "pb_ratio", 0),
                        "roe": getattr(info, "roe", 0),
                        "market_cap": getattr(info, "total_market_cap", 0),
                        "revenue_growth": getattr(info, "revenue_growth_3y", 0),
                        "earnings_growth": getattr(info, "earnings_growth_3y", 0),
                        "gross_margin": getattr(info, "gross_margin", 0),
                        "debt_to_equity": getattr(info, "debt_to_equity", 0),
                        "free_cash_flow": getattr(info, "free_cash_flow", 0),
                    },
                }
            return {"stock_code": stock_code, "error": "No data found"}
        except Exception as e:
            return {"stock_code": stock_code, "error": str(e)[:200]}

    return AgentTool(
        name="get_financials",
        description="获取指定股票的最新基本面数据(PE/PB/ROE/营收增长/毛利率等)",
        parameters={"stock_code": "股票代码(如600519)"},
        required_params=["stock_code"],
        fn=_fetch,
    )


def get_technical_tool() -> AgentTool:
    """工具: 获取个股技术指标数据"""

    def _fetch(stock_code: str, days: int = 90) -> dict:
        try:
            bus = DatabaseBackedDataBus()
            kline = bus.get_kline(stock_code, days=days)
            if kline:
                # 计算常用技术指标
                prices = []
                volumes = []
                if isinstance(kline, list):
                    for bar in kline:
                        if isinstance(bar, dict):
                            prices.append(bar.get("close", 0))
                            volumes.append(bar.get("volume", 0))
                if prices:
                    n5 = min(5, len(prices[-5:]))
                    ma5 = sum(prices[-5:]) / n5 if n5 else 0
                    n10 = min(10, len(prices[-10:]))
                    ma10 = sum(prices[-10:]) / n10 if n10 else 0
                    n20 = min(20, len(prices[-20:]))
                    ma20 = sum(prices[-20:]) / n20 if n20 else 0
                    n60 = min(60, len(prices[-60:]))
                    ma60 = sum(prices[-60:]) / n60 if n60 else 0
                    high = max(prices[-20:]) if len(prices) >= 20 else 0
                    low = min(prices[-20:]) if len(prices) >= 20 else 0
                    current = prices[-1] if prices else 0
                    volatility = ((high - low) / low * 100) if low > 0 else 0
                    vol_n = min(20, len(volumes[-20:]))
                    vol_avg = sum(volumes[-20:]) / vol_n if vol_n else 0
                    return {
                        "stock_code": stock_code,
                        "price": current,
                        "ma5": ma5,
                        "ma10": ma10,
                        "ma20": ma20,
                        "ma60": ma60,
                        "high_20d": high,
                        "low_20d": low,
                        "volatility_20d": round(volatility, 2),
                        "volume_avg_20d": vol_avg,
                        "bars": len(prices),
                    }
            return {"stock_code": stock_code, "error": "No kline data"}
        except Exception as e:
            return {"stock_code": stock_code, "error": str(e)[:200]}

    return AgentTool(
        name="get_technical",
        description="获取指定股票的技术指标数据(均线MA5/MA10/MA20/MA60,波动率,最高最低价)",
        parameters={"stock_code": "股票代码(如600519)", "days": "回溯天数(默认90)"},
        required_params=["stock_code"],
        fn=_fetch,
    )


def get_sentiment_tool() -> AgentTool:
    """工具: 获取个股市场情绪数据"""

    def _fetch(stock_code: str) -> dict:
        result = {"stock_code": stock_code, "hot_score": 0, "lhb": None, "zt_info": None}
        try:
            # 人气榜
            adapter = get_adapter("hot_rank")
            if adapter and adapter.cb.peek_available():
                data = adapter.fetch_hot_rank() or []
                for item in data:
                    if isinstance(item, dict) and item.get("code", "") == stock_code:
                        result["hot_score"] = item.get("hot_score", 0) or item.get("热度", 0)
                        result["hot_rank"] = item.get("rank", 0)
                        break
            # 龙虎榜
            adapter = get_adapter("lhb")
            if adapter and adapter.cb.peek_available():
                for offset in (0, 1):
                    d = (datetime.now() - timedelta(days=offset)).strftime("%Y-%m-%d")
                    df = adapter.fetch_lhb_detail(d)
                    if df is not None and not df.empty:
                        mask = df["代码"].astype(str).str.strip() == stock_code
                        match = df[mask]
                        if not match.empty:
                            row = match.iloc[0]
                            result["lhb"] = {
                                "net_buy": float(row.get("龙虎榜净买额", 0) or 0),
                                "buy_amount": float(row.get("龙虎榜买入额", 0) or 0),
                            }
                            break
        except Exception as e:
            result["error"] = str(e)[:200]
        return result

    return AgentTool(
        name="get_sentiment",
        description="获取指定股票的市场情绪数据(人气热度,龙虎榜资金流向,涨停信息)",
        parameters={"stock_code": "股票代码(如600519)"},
        required_params=["stock_code"],
        fn=_fetch,
    )


def create_default_tools() -> list[AgentTool]:
    """创建默认的工具集 (MasterAgent + SkillEngine + Data)"""
    return [
        get_master_list_tool(),
        get_master_analyze_tool(),
        get_skill_knowledge_tool(),
        get_financials_tool(),
        get_technical_tool(),
        get_sentiment_tool(),
    ]
