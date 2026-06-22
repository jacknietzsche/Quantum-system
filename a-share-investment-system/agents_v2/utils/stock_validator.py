"""股票数据预验证系统 — 参考 TradingAgents-CN/stock_validator.py

在分析流程开始前验证股票是否存在,预获取必要数据.
关键功能:
1. 格式验证
2. 数据可用性检查
3. 友好的错误信息和建议
4. 异步支持 (FastAPI)
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

from agents_v2.utils.logging_init import get_logger
from agents_v2.utils.stock_utils import StockMarket, StockUtils

logger = get_logger("validator")


@dataclass
class ValidationResult:
    """验证结果"""

    is_valid: bool
    stock_code: str
    market_type: str = ""
    stock_name: str = ""
    error_message: str = ""
    suggestion: str = ""
    has_historical_data: bool = False
    has_basic_info: bool = False
    data_period_days: int = 0
    cache_status: str = ""

    def to_dict(self) -> dict:
        return {
            "is_valid": self.is_valid,
            "stock_code": self.stock_code,
            "market_type": self.market_type,
            "stock_name": self.stock_name,
            "error_message": self.error_message,
            "suggestion": self.suggestion,
            "has_historical_data": self.has_historical_data,
            "has_basic_info": self.has_basic_info,
            "data_period_days": self.data_period_days,
            "cache_status": self.cache_status,
        }


class StockValidator:
    """股票数据预验证器"""

    def __init__(self, default_period_days: int = 30):
        self.default_period_days = default_period_days
        self.timeout_seconds = 15

    def validate(
        self,
        stock_code: str,
        market_type: str = "auto",
        period_days: int | None = None,
        analysis_date: str | None = None,
    ) -> ValidationResult:
        """验证股票代码并预获取数据

        Args:
            stock_code: 股票代码
            market_type: 市场类型 ("A股"/"港股"/"美股"/"auto")
            period_days: 历史数据时长 (天)
            analysis_date: 分析日期
        """
        if period_days is None:
            period_days = self.default_period_days
        if analysis_date is None:
            analysis_date = datetime.now().strftime("%Y-%m-%d")

        logger.info(f"[验证] 开始: {stock_code} (市场={market_type}, 周期={period_days}天)")

        # 1. 格式验证
        format_result = self._validate_format(stock_code, market_type)
        if not format_result.is_valid:
            return format_result

        # 2. 自动检测市场
        if market_type == "auto":
            market_info = StockUtils.get_market_info(stock_code)
            market_type = market_info["market_name"]
            logger.debug(f"[验证] 自动检测市场: {market_type}")

        # 3. 数据验证
        return self._validate_data(stock_code, market_type, period_days, analysis_date)

    def _validate_format(self, stock_code: str, market_type: str) -> ValidationResult:  # noqa: PLR0911
        """验证股票代码格式"""
        stock_code = stock_code.strip()

        if not stock_code:
            return ValidationResult(
                is_valid=False,
                stock_code=stock_code,
                error_message="股票代码不能为空",
                suggestion="请输入有效的股票代码",
            )

        if len(stock_code) > 10:
            return ValidationResult(
                is_valid=False,
                stock_code=stock_code,
                error_message="股票代码长度不能超过10个字符",
                suggestion="请检查股票代码格式",
            )

        # A股格式验证
        if market_type == "A股":
            if not re.match(r"^\d{6}$", stock_code):
                return ValidationResult(
                    is_valid=False,
                    stock_code=stock_code,
                    market_type="A股",
                    error_message="A股代码格式错误,应为6位数字",
                    suggestion="请输入6位数字的A股代码,如: 000001, 600519",
                )

        # 港股格式验证
        elif market_type == "港股":
            ticker = stock_code.upper()
            hk_pattern = re.match(r"^\d{4,5}(\.HK)?$", ticker)
            if not hk_pattern:
                return ValidationResult(
                    is_valid=False,
                    stock_code=stock_code,
                    market_type="港股",
                    error_message="港股代码格式错误",
                    suggestion="港股代码应为4-5位数字,如: 0700.HK 或 0700",
                )

        # 美股格式验证
        elif market_type == "美股":
            if not re.match(r"^[A-Za-z]{1,5}$", stock_code):
                return ValidationResult(
                    is_valid=False,
                    stock_code=stock_code,
                    market_type="美股",
                    error_message="美股代码格式错误,应为1-5位字母",
                    suggestion="美股代码如: AAPL, TSLA, MSFT",
                )

        # 未知市场 - 基本检查
        elif market_type in ("auto", "未知") and not re.match(r"^[A-Za-z0-9.]+$", stock_code):
            return ValidationResult(
                is_valid=False,
                stock_code=stock_code,
                error_message="股票代码格式不正确",
                suggestion="请输入有效的股票代码",
            )

        return ValidationResult(is_valid=True, stock_code=stock_code, market_type=market_type)

    def _validate_data(
        self, stock_code: str, market_type: str, period_days: int, analysis_date: str
    ) -> ValidationResult:
        """验证数据可用性

        尝试获取基础数据来确认股票存在.
        超时或失败不阻止分析,只记录警告.
        """
        try:
            # A 股验证
            if market_type == "中国A股":
                return self._validate_china_a(stock_code, period_days)

            # 港股验证
            if market_type == "港股":
                return self._validate_hk(stock_code, period_days)

            # 美股验证
            if market_type == "美股":
                return self._validate_us(stock_code, period_days)

            # 未知市场: 尝试自动检测  # noqa: ERA001
            market_info = StockUtils.get_market_info(stock_code)
            if market_info["market"] != StockMarket.UNKNOWN.value:
                return self._validate_data(
                    stock_code,
                    market_info["market_name"],
                    period_days,
                    analysis_date,
                )
            return ValidationResult(
                is_valid=False,
                stock_code=stock_code,
                error_message="无法识别股票市场",
                suggestion="请使用6位数字的A股代码,或带.HK后缀的港股代码",
            )

        except Exception as e:
            logger.warning(f"[验证] 数据获取异常: {e}")
            # 异常不阻止分析,返回降级结果
            return ValidationResult(
                is_valid=True,
                stock_code=stock_code,
                market_type=market_type,
                error_message=f"数据预获取失败但不影响分析: {str(e)[:100]}",
                suggestion="建议检查网络连接",
            )

    def _validate_china_a(self, stock_code: str, period_days: int) -> ValidationResult:
        """验证 A 股数据"""
        try:
            import efinance as ef

            df = ef.stock.get_quote_history(stock_code, count=min(period_days, 30))
            if df is not None and not df.empty:
                stock_name = ""
                try:
                    stocks = ef.stock.get_realtime_quotes()
                    if stocks is not None:
                        row = stocks[stocks["code"] == stock_code]
                        if not row.empty:
                            stock_name = row.iloc[0].get("name", "")
                except Exception:
                    pass

                return ValidationResult(
                    is_valid=True,
                    stock_code=stock_code,
                    market_type="中国A股",
                    stock_name=stock_name or f"A股{stock_code}",
                    has_historical_data=True,
                    has_basic_info=True,
                    data_period_days=len(df),
                    cache_status=f"历史数据 {len(df)} 条",
                )
            return ValidationResult(
                is_valid=False,
                stock_code=stock_code,
                market_type="中国A股",
                error_message=f"A股代码 {stock_code} 不存在或无法获取数据",
                suggestion="请检查股票代码是否正确,如: 000001(平安银行), 600519(贵州茅台)",
            )
        except ImportError:
            logger.warning("[验证] efinance 未安装,跳过 A 股数据验证")
            return ValidationResult(
                is_valid=True,
                stock_code=stock_code,
                market_type="中国A股",
                has_historical_data=False,
                cache_status="未验证(缺少 efinance)",
            )
        except Exception as e:
            logger.warning(f"[验证] A 股数据获取失败: {e}")
            return ValidationResult(
                is_valid=True,
                stock_code=stock_code,
                market_type="中国A股",
                error_message=f"数据获取失败: {str(e)[:100]}",
            )

    def _validate_hk(self, stock_code: str, period_days: int) -> ValidationResult:
        """验证港股数据"""
        import yfinance as yf

        formatted_code = StockUtils.normalize_hk_ticker(stock_code)
        try:
            ticker_obj = yf.Ticker(formatted_code)
            hist = ticker_obj.history(period=f"{period_days}d")
            if hist is not None and not hist.empty:
                info = ticker_obj.info
                stock_name = info.get("longName", info.get("shortName", f"港股{stock_code}"))
                return ValidationResult(
                    is_valid=True,
                    stock_code=formatted_code,
                    market_type="港股",
                    stock_name=stock_name,
                    has_historical_data=True,
                    has_basic_info=True,
                    data_period_days=len(hist),
                    cache_status=f"历史数据 {len(hist)} 条",
                )
            return ValidationResult(
                is_valid=False,
                stock_code=formatted_code,
                market_type="港股",
                error_message=f"港股代码 {formatted_code} 不存在或无法获取数据",
                suggestion="请检查港股代码是否正确,如: 0700.HK(腾讯), 9988.HK(阿里巴巴)",
            )
        except Exception as e:
            return ValidationResult(
                is_valid=False,
                stock_code=formatted_code,
                market_type="港股",
                error_message=f"港股数据获取失败: {str(e)[:100]}",
                suggestion="请检查网络连接或股票代码",
            )

    def _validate_us(self, stock_code: str, period_days: int) -> ValidationResult:
        """验证美股数据"""
        import yfinance as yf

        formatted_code = stock_code.upper()
        try:
            ticker_obj = yf.Ticker(formatted_code)
            hist = ticker_obj.history(period=f"{period_days}d")
            if hist is not None and not hist.empty:
                info = ticker_obj.info
                stock_name = info.get("longName", info.get("shortName", f"美股{stock_code}"))
                return ValidationResult(
                    is_valid=True,
                    stock_code=formatted_code,
                    market_type="美股",
                    stock_name=stock_name,
                    has_historical_data=True,
                    has_basic_info=True,
                    data_period_days=len(hist),
                    cache_status=f"历史数据 {len(hist)} 条",
                )
            return ValidationResult(
                is_valid=False,
                stock_code=formatted_code,
                market_type="美股",
                error_message=f"美股代码 {formatted_code} 不存在或无法获取数据",
                suggestion="请检查美股代码是否正确,如: AAPL(苹果), TSLA(特斯拉)",
            )
        except Exception as e:
            return ValidationResult(
                is_valid=False,
                stock_code=formatted_code,
                market_type="美股",
                error_message=f"美股数据获取失败: {str(e)[:100]}",
                suggestion="请检查网络连接或股票代码",
            )


# ─── 全局单例 ───
_validator: StockValidator | None = None


def get_validator(default_period_days: int = 30) -> StockValidator:
    global _validator  # noqa: PLW0603
    if _validator is None:
        _validator = StockValidator(default_period_days)
    return _validator


def validate_stock(
    stock_code: str,
    market_type: str = "auto",
    period_days: int | None = None,
    analysis_date: str | None = None,
) -> ValidationResult:
    """便捷函数: 验证股票"""
    return get_validator().validate(stock_code, market_type, period_days, analysis_date)
