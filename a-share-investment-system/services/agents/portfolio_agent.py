"""PortfolioAgent - 组合级分析"""

import json

from services.agents.base_agent import AgentExecutor, extract_json

PORTFOLIO_AGENT_SYSTEM_PROMPT = """\
你是一位专业的投资组合分析师. 你的任务是根据已完成的个股分析结果和当前持仓, 给出组合层面的建议.

## 输入数据
- stock_opinions: 每只候选股的 StockAgent 分析结果
- portfolio_holdings: 当前持仓(如有)

## 输出要求
输出 JSON:
{
  "portfolio_risk_score": 1-10,
  "sector_exposure": {"行业名": "占比%"},
  "total_candidates": 数量,
  "recommended_count": 建议关注的股票数量,
  "position_plan": [
    {"code": "代码", "weight": 0.15, "action": "新开仓/加仓/持有/减仓/清仓", "reason": "原因"}
  ],
  "warnings": ["风险警告列表"]
}

## 注意
如果 portfolio_holdings 为空或 {}, 表示当前无持仓, 仅做新开仓分析.
"""


class PortfolioAgent:
    """组合分析 Agent"""

    def __init__(self, llm_config: dict):
        self.llm_config = llm_config

    def analyze(self, stock_opinions: list, portfolio_holdings: dict) -> dict:
        user_msg = json.dumps(
            {
                "stock_opinions": stock_opinions,
                "portfolio_holdings": portfolio_holdings,
            },
            ensure_ascii=False,
        )
        executor = AgentExecutor(self.llm_config, [])
        result = executor.run(PORTFOLIO_AGENT_SYSTEM_PROMPT, user_msg)
        try:
            return json.loads(extract_json(result.get("content", "{}")))
        except (json.JSONDecodeError, TypeError):
            return {"portfolio_risk_score": 5, "warnings": ["Analysis failed"]}
