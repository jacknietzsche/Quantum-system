"""StockAgent - AI 个股分析师, 通过 Tool calling 自主调用大师和技能"""

import json

from services.agents.base_agent import AgentExecutor, extract_json
from services.agents.tool_registry import create_default_tools
from shared.logging import emit_log

STOCK_AGENT_SYSTEM_PROMPT = """你是一位专业的 A 股股票分析师.
你的任务是分析一只候选股票, 给出是否值得买入的判断.

## 可用工具
- **get_financials(stock_code)**: 获取基本面数据(PE/PB/ROE/营收增长/毛利率等)
- **get_technical(stock_code, days=90)**: 获取技术指标(均线MA5/10/20/60,波动率,最高最低价)
- **get_sentiment(stock_code)**: 获取市场情绪(人气热度,龙虎榜资金流向)
- **get_master_list()**: 获取可用投资大师分析器列表
- **master_analyze(stock_code, master_names, stock_data)**: 调用指定大师进行量化分析
- **skill_knowledge(skill_name, context)**: 获取投资技能知识和分析框架

## 工作流程
1. **收集数据**: 先调用 get_financials / get_technical / get_sentiment
   获取基本面+技术+情绪数据
2. **了解可用工具**: 调用 get_master_list() 查看可用的投资大师分析器
3. **调用大师分析**: 根据股票特征选择 2-4 个最合适的大师, 调用 master_analyze()
4. **注入技能知识**: 需要特定分析框架时, 调用 skill_knowledge() 获取方法论
5. **综合判断**: 结合真实数据和大师评分, 输出分析结论

## 输出要求
分析完所有数据后, 输出 JSON 格式结论:
{
  "overall_score": 0-100,
  "signal": "买入/持有/观望/卖出",
  "confidence": "高/中/低",
  "masters_used": ["大师名(分数)"],
  "skills_injected": ["技能名"],
  "data_sources": ["financials", "technical", "sentiment"],
  "entry": {"price_range": "入场区间", "timing": "时机"},
  "stop_loss": "止损价位或比例",
  "take_profit": "目标价位或比例",
  "position_size": "仓位建议(重仓/中仓/轻仓/观望)",
  "reasoning": "综合分析推理过程(100-300字)"
}
"""


class StockAgent:
    """个股分析 Agent - 支持锚定模式(含 quant_report 约束注入)"""

    def __init__(
        self,
        llm_config: dict,
        quant_anchor: dict | None = None,
        max_adjustment: int = 15,
        force_dissent: bool = False,
    ):
        self.llm_config = llm_config
        self.tools = create_default_tools()
        self.quant_anchor = quant_anchor
        self.max_adjustment = max_adjustment
        self.force_dissent = force_dissent

    def _build_anchor_prompt(self) -> str:
        if not self.quant_anchor:
            return ""
        qr = self.quant_anchor
        master_score = qr.get("master_score", 50)
        admission_tags = qr.get("admission_tags", [])
        qr.get("quant_report", {})
        lo = max(0, master_score - self.max_adjustment)
        hi = min(100, master_score + self.max_adjustment)
        dissent_warn = ""
        if self.force_dissent:
            dissent_warn = "\n如需超出约束范围必须启动异议审查, 经独立审查员复验通过后方可生效。"
        lines = [
            "\n\n【量化锚定约束】",
            f"- 大师综合评分: {master_score}/100",
            f"- 准入规则: {', '.join(admission_tags) if admission_tags else 'N/A'}",
            f"- 最大允许调整: ±{self.max_adjustment}",
            f"- 最终 overall_score 必须在 [{lo}, {hi}] 范围内{dissent_warn}\n",
        ]
        return "\n".join(lines)

    def _parse_llm_output(self, text: str) -> dict:
        try:
            return json.loads(extract_json(text))
        except (json.JSONDecodeError, TypeError):
            return {"error": "parse_failed", "raw": text[:200]}

    def analyze(self, stock: dict) -> dict:
        """分析一只股票"""
        user_msg = json.dumps(
            {
                "stock_code": stock.get("stock_code"),
                "stock_name": stock.get("stock_name"),
                "price": stock.get("price"),
                "pe": stock.get("pe"),
                "pb": stock.get("pb"),
                "roe": stock.get("roe"),
                "market_cap": stock.get("market_cap"),
                "turnover_rate": stock.get("turnover_rate"),
                "volume_ratio": stock.get("volume_ratio"),
                "change_pct": stock.get("change_pct"),
                "change_pct_5d": stock.get("change_pct_5d"),
                "change_pct_20d": stock.get("change_pct_20d"),
                "change_pct_60d": stock.get("change_pct_60d"),
                "industry": stock.get("industry"),
                "trend": stock.get("trend"),
                "ma_alignment": stock.get("ma_alignment"),
                "earnings_growth_3y": stock.get("earnings_growth_3y"),
                "revenue_growth_3y": stock.get("revenue_growth_3y"),
                "free_cash_flow": stock.get("free_cash_flow"),
                "debt_to_equity": stock.get("debt_to_equity"),
                "gross_margin": stock.get("gross_margin"),
                "hot_score": stock.get("hot_score", 0),
                "consecutive_limit_ups": stock.get("consecutive_limit_ups", 0),
            },
            ensure_ascii=False,
        )

        prompt = STOCK_AGENT_SYSTEM_PROMPT + self._build_anchor_prompt()
        executor = AgentExecutor(self.llm_config, self.tools)
        result = executor.run(prompt, user_msg)
        content = result.get("content", "")
        try:
            parsed = self._parse_llm_output(content)
            if "stock_code" not in parsed:
                parsed["stock_code"] = stock.get("stock_code")
            return parsed
        except Exception as e:
            emit_log("WARNING", "stock_agent", f"Parse failed: {str(e)[:100]}")
            return {
                "stock_code": stock.get("stock_code"),
                "overall_score": 50,
                "signal": "观望",
                "confidence": "低",
                "error": "parse_failed",
            }
