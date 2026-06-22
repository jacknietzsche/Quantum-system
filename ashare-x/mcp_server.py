"""AShare-X MCP Server — 暴露tools为MCP工具供外部AI客户端调用。

Phase 8.1: 将 tools/ 中的数据获取函数包装为 MCP (Model Context Protocol) server，
使 Claude Desktop、Cursor 等AI客户端可直接查询A股数据。

使用方式:
  # 作为独立进程运行
  python mcp_server.py

  # 在 Claude Desktop 的 claude_desktop_config.json 中配置:
  {
    "mcpServers": {
      "ashare-x": {
        "command": "python",
        "args": ["path/to/ashare-x/mcp_server.py"]
      }
    }
  }

工具列表:
  - get_stock_data(code, days) — K线+技术指标
  - get_fundamentals(code) — 基本面数据
  - get_news(code, days) — 个股新闻
  - get_global_news() — 宏观新闻
  - get_social_sentiment(code) — 龙虎榜/北向/资金流向
  - detect_market_state(indices_data) — 市场状态检测
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

# 确保项目根目录在 sys.path 中
_PROJECT_ROOT = Path(__file__).resolve().parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

logger = logging.getLogger("ashare-x.mcp")

# MCP SDK 的 FastMAP 模式
try:
    from mcp.server.fastmcp import FastMCP
except ImportError:
    logger.error("MCP SDK未安装: pip install mcp")
    raise

mcp = FastMCP(
    "ashare-x",
    instructions=(
        "AShare-X MCP Server — A股投研数据工具。\n"
        "提供K线数据、基本面、新闻、情绪指标、市场状态检测等功能。\n"
        "所有股票代码格式: 6位数字，如 600519（贵州茅台）。"
    ),
)


@mcp.tool()
def get_stock_data(code: str, days: int = 120) -> dict:
    """获取A股K线数据和技术指标。

    Args:
        code: 6位股票代码，如 600519
        days: 获取最近N天的数据，默认120

    Returns:
        包含K线列表和技术指标(MA/MACD/RSI/BOLL)的字典
    """
    from tools.stock_data import get_stock_data as _get

    data = _get(code, days=days)
    kline = data.get("kline")
    indicators = data.get("indicators")

    # 序列化K线
    kline_list = []
    if kline is not None:
        if isinstance(kline, list):
            kline_list = kline
        elif hasattr(kline, "to_dict"):
            kline_list = kline.to_dict("records")

    return {
        "code": code,
        "kline": kline_list[-20:] if len(kline_list) > 20 else kline_list,
        "indicators": indicators,
        "total_bars": len(kline_list),
    }


@mcp.tool()
def get_fundamentals(code: str) -> dict:
    """获取A股基本面数据（PE/PB/ROE/营收/利润等）。

    Args:
        code: 6位股票代码，如 000858

    Returns:
        基本面指标字典，包含估值/盈利能力/成长性/财务健康
    """
    from tools.fundamentals import get_fundamentals as _get

    result = _get(code)
    return result if result else {"error": f"未找到 {code} 的基本面数据"}


@mcp.tool()
def get_news(code: str, days: int = 7) -> list[dict]:
    """获取个股相关新闻。

    Args:
        code: 6位股票代码
        days: 获取最近N天的新闻，默认7

    Returns:
        新闻列表，每条包含 title/source/date/content
    """
    from tools.news_search import get_news as _get

    return _get(code, days)


@mcp.tool()
def get_global_news() -> list[dict]:
    """获取宏观经济新闻（央视新闻联播财经摘要）。

    Returns:
        宏观新闻列表
    """
    from tools.news_search import get_global_news as _get

    return _get()


@mcp.tool()
def get_social_sentiment(code: str) -> dict:
    """获取社交情绪数据（龙虎榜/北向资金/换手率/资金流向）。

    Args:
        code: 6位股票代码

    Returns:
        情绪指标字典，包含换手率/龙虎榜/资金流向/北向资金
    """
    from tools.social_sentiment import get_social_sentiment as _get

    result = _get(code)
    return result if result else {"error": f"未找到 {code} 的情绪数据"}


@mcp.tool()
def get_market_breadth() -> dict:
    """获取市场广度数据（全市场涨跌家数/涨停跌停数）。

    Returns:
        市场广度字典
    """
    from tools.social_sentiment import get_market_breadth as _get

    return _get()


@mcp.tool()
def detect_market_state(
    sh_change_20d: float = 0,
    advance_count: int = 0,
    decline_count: int = 0,
    volume: float = 0,
    volume_ma20: float = 0,
    north_flow_5d: float = 0,
) -> str:
    """检测A股市场状态（BULL/NEUTRAL/BEAR/PANIC）。

    基于4指标综合评分:
    1. 上证20日涨跌幅
    2. 涨跌家数比
    3. 成交量/20日均量比
    4. 北向资金5日净流入

    Args:
        sh_change_20d: 上证综指20日涨跌幅(小数, 0.05=5%)
        advance_count: 上涨家数
        decline_count: 下跌家数
        volume: 今日成交量
        volume_ma20: 20日均量
        north_flow_5d: 北向资金5日净流入(亿元)

    Returns:
        市场状态: BULL / NEUTRAL / BEAR / PANIC
    """
    from tools.market_state import detect_market_state as _detect

    indices_data = {
        "sh_change_20d": sh_change_20d,
        "advance_count": advance_count,
        "decline_count": decline_count,
        "volume": volume,
        "volume_ma20": volume_ma20,
        "north_flow_5d": north_flow_5d,
    }
    return _detect(indices_data)


@mcp.tool()
def get_position_cap(state: str) -> float:
    """根据市场状态获取建议仓位上限。

    Args:
        state: 市场状态 (BULL/NEUTRAL/BEAR/PANIC/OVERHEAT)

    Returns:
        仓位上限比例 (0-1, 如0.6=60%)
    """
    from tools.market_state import get_position_cap

    return get_position_cap(state)


def main():
    """启动MCP server。"""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )
    logger.info("AShare-X MCP Server 启动中...")
    mcp.run()


if __name__ == "__main__":
    main()
