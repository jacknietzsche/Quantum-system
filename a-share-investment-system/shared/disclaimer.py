"""
免责声明和数据来源标注 — 合规要求

在所有报告输出中自动附加.
"""

from __future__ import annotations

from datetime import datetime

# ═══ 免责声明 ═══

DISCLAIMER_CN = """---
⚠️ **免责声明**
1. 本系统仅供个人学习和研究使用,不构成任何投资建议
2. 任何投资决策应基于个人独立判断,本系统不对投资损益负责
3. 使用本系统应遵守相关法律法规,不得用于商业目的
4. 投资有风险,入市需谨慎
"""


# ═══ 数据来源标注 ═══

DATA_ATTRIBUTION_TEMPLATE = """---
📊 **数据来源声明**
- 行情数据: {sources}
- 生成时间: {timestamp}
- 数据仅供参考,不构成投资建议
- 请以证券交易所官方数据为准
"""


# ═══ 报告模板 ═══

REPORT_FOOTER_TEMPLATE = """
---
*由 A股智能投研系统 生成*
*生成时间: {timestamp}*
*数据来源: {sources}*
*本报告仅供学习研究使用,不构成投资建议*
"""


def get_disclaimer() -> str:
    """获取免责声明"""
    return DISCLAIMER_CN


def get_attribution(sources: list[str]) -> str:
    """获取数据来源标注"""
    source_str = "、".join(sources) if sources else "Tushare、yfinance、zzshare"
    return DATA_ATTRIBUTION_TEMPLATE.format(
        sources=source_str,
        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )


def get_report_footer(sources: list[str] | None = None) -> str:
    """获取报告底部信息"""
    if sources is None:
        sources = ["Tushare", "yfinance", "zzshare"]
    return REPORT_FOOTER_TEMPLATE.format(
        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        sources="、".join(sources),
    )


def append_to_report(content: str, sources: list[str] | None = None) -> str:
    """为报告内容附加免责声明和数据来源"""
    return content + "\n" + get_report_footer(sources) + "\n" + get_disclaimer()
