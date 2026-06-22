"""动态缓存 TTL — 根据 A 股交易时段自动调整缓存有效期

交易时段划分:
  盘前 (00:00-09:15): 使用盘后数据, TTL = 8h
  早盘 (09:15-11:30): 高频更新, TTL = 5min
  午休 (11:30-13:00): 中等频率, TTL = 30min
  午盘 (13:00-15:00): 高频更新, TTL = 5min
  盘后 (15:00-23:59): 数据稳定, TTL = 24h
  非交易日: 数据不变, TTL = 24h
"""

from datetime import datetime


def _now() -> datetime:
    """可测试的当前时间"""
    return datetime.now()


def is_trading_session() -> bool:
    """判断当前是否为交易时段(含午休)"""
    try:
        from services.trading_calendar import TradingCalendar

        cal = TradingCalendar()
        if not cal.is_trading_day():
            return False
    except Exception:
        if _now().weekday() >= 5:
            return False

    t = _now()
    morning = (9, 15) <= (t.hour, t.minute) < (11, 30)
    afternoon = (13, 0) <= (t.hour, t.minute) < (15, 0)
    return morning or afternoon


def get_session_phase() -> str:
    """返回当前市场时段: pre_market / morning / lunch / afternoon / post_market / closed"""
    t = _now()

    try:
        from services.trading_calendar import TradingCalendar

        cal = TradingCalendar()
        is_trading = cal.is_trading_day()
    except Exception:
        is_trading = t.weekday() < 5

    if not is_trading:
        return "closed"

    hour_min = (t.hour, t.minute)
    if hour_min < (9, 15):
        return "pre_market"
    if hour_min < (11, 30):
        return "morning"
    if hour_min < (13, 0):
        return "lunch"
    if hour_min < (15, 0):
        return "afternoon"
    return "post_market"


# ── 各数据类型的基准 TTL (秒) ──
_BASE_TTL = {
    "indices": 300,  # 指数: 5分钟
    "north_flow": 300,  # 北向资金: 5分钟
    "sectors": 600,  # 板块排名: 10分钟
    "kline_daily": 86400,  # 日K: 24小时
    "stock_basic": 86400,  # 基本面: 24小时
    "stock_quote": 300,  # 实时行情: 5分钟
}

# ── 时段 → TTL 倍率 ──
_PHASE_MULTIPLIER = {
    "morning": 1.0,  # 盘中: 使用基准 TTL
    "afternoon": 1.0,  # 盘中: 使用基准 TTL
    "lunch": 6.0,  # 午休: 放大 6 倍 (5min→30min)
    "pre_market": 16.0,  # 盘前: 放大 16 倍 (5min→80min)
    "post_market": 48.0,  # 盘后: 放大 48 倍 (5min→4h)
    "closed": 48.0,  # 非交易日: 同盘后
}


def get_dynamic_ttl(data_type: str) -> int:
    """根据当前市场时段返回动态 TTL (秒)

    Args:
        data_type: 数据类型键名, 如 "indices", "stock_quote" 等

    Returns:
        该数据类型在当前时段的推荐 TTL 秒数
    """
    base = _BASE_TTL.get(data_type, 300)
    phase = get_session_phase()
    multiplier = _PHASE_MULTIPLIER.get(phase, 1.0)

    # 盘后/非交易日: 日K和基本面数据保持 24h, 实时数据缩短到 4h
    if phase in ("post_market", "closed"):
        if data_type in ("kline_daily", "stock_basic"):
            return 86400
        return min(int(base * multiplier), 14400)  # cap at 4 hours

    # 盘前: 实时数据不更新, 日K保持 24h
    if phase == "pre_market":
        if data_type in ("kline_daily", "stock_basic"):
            return 86400
        return min(int(base * multiplier), 28800)  # cap at 8 hours

    return int(base * multiplier)
