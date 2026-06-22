"""A股交易日历 - chinese_calendar支持 + 日频策略适配"""

from datetime import datetime, timedelta

from services.base import BaseService


class TradingCalendar(BaseService):
    """A股交易日历(含节假日+调休),日频策略核心依赖"""

    def __init__(self):
        super().__init__()
        self._using_lib = None

    def _ensure_init(self):
        if self._using_lib is not None:
            return
        try:
            from chinese_calendar import is_workday  # noqa: F401

            self._using_lib = True
        except ImportError:
            self._using_lib = False

    def is_trading_day(self, date=None) -> bool:
        """判断是否A股交易日(排除周末+节假日+调休)"""
        self._ensure_init()
        target = date if date else datetime.now()
        if isinstance(target, str):
            target = datetime.strptime(target, "%Y-%m-%d")
        if hasattr(target, "date"):
            target = target.date() if not isinstance(target, datetime) else target

        if isinstance(target, datetime):
            target = target.date()

        if target.weekday() >= 5:
            return False
        if self._using_lib:
            from chinese_calendar import is_workday

            return bool(is_workday(target))
        return True

    def previous_trading_day(self, date=None) -> str:
        """获取上一个交易日(日频策略核心:取最近有效数据日)"""
        target = date if date else datetime.now()
        if isinstance(target, str):
            target = datetime.strptime(target, "%Y-%m-%d")
        target -= timedelta(days=1)
        while not self.is_trading_day(target):
            target -= timedelta(days=1)
        return target.strftime("%Y-%m-%d")

    def next_trading_day(self, date=None) -> str:
        """获取下一个交易日"""
        target = date if date else datetime.now()
        if isinstance(target, str):
            target = datetime.strptime(target, "%Y-%m-%d")
        target += timedelta(days=1)
        while not self.is_trading_day(target):
            target += timedelta(days=1)
        return target.strftime("%Y-%m-%d")

    def effective_data_date(self) -> str:
        """日频策略核心: 返回应该使用的数据日期。
        - 交易日且≥17:00(收盘后数据已完整) → 返回今天(用于晚间分析)
        - 交易日但<17:00(盘中数据不完整) → 返回前一日
        - 非交易日 → 返回前一个交易日
        """
        today = datetime.now()
        today_str = today.strftime("%Y-%m-%d")

        if self.is_trading_day(today_str):
            if today.hour >= 17:
                return today_str  # 盘后: 今天数据已完整
            return self.previous_trading_day(today)  # 盘中: 用昨日数据
        return self.previous_trading_day(today)  # 非交易日

    def is_market_closed_today(self) -> bool:
        """判断今天是否已收盘(≥17:00)且是交易日"""
        today = datetime.now()
        today_str = today.strftime("%Y-%m-%d")
        return self.is_trading_day(today_str) and today.hour >= 17

    def today_str(self) -> str:
        return datetime.now().strftime("%Y-%m-%d")
