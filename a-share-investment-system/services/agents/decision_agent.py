"""DecisionAgent - 生成最终交易计划"""

import json

from services.agents.base_agent import AgentExecutor, extract_json
from services.trading_plan import ConditionalOrder, OrderItem, RiskManagement, TradingPlan

DECISION_AGENT_SYSTEM_PROMPT = """\
你是一位专业的投资组合经理. 你的任务是根据个股分析和组合评估, 制定一份完整的交易计划.

## 输入
- stock_opinions: 所有候选股的深度分析结果
- portfolio_assessment: 组合层面评估
- portfolio_holdings: 当前持仓(如有)

## 输出要求
输出 JSON:
{
  "market_assessment": {"regime": "震荡偏多/震荡偏空/单边上涨/单边下跌",
                         "risk_level": "低/中/高", "max_position": 0.7},
  "execution_plan": {
    "immediate_summary": "今日操作概要",
    "orders": [
      {"code": "代码", "name": "名称", "action": "买入/卖出/加仓/减仓/持有",
       "quantity": 股数, "weight": "仓位比例", "limit_price": "限价",
       "stop_loss": "止损位", "take_profit": "目标位",
       "confidence": "高/中/低", "reasoning": "理由"}
    ],
    "conditional_orders": [
      {"condition": "触发条件", "action": "操作", "timing": "时间"}
    ]
  },
  "risk_management": {
    "circuit_breaker": "熔断条件",
    "portfolio_stop": "组合止损线",
    "key_risks": ["风险1", "风险2"]
  }
}
"""


class DecisionAgent:
    """交易计划制定 Agent"""

    def __init__(self, llm_config: dict):
        self.llm_config = llm_config

    def decide(
        self, stock_opinions: list, portfolio_assessment: dict, portfolio_holdings: dict
    ) -> TradingPlan:
        user_msg = json.dumps(
            {
                "stock_opinions": stock_opinions,
                "portfolio_assessment": portfolio_assessment,
                "portfolio_holdings": portfolio_holdings,
            },
            ensure_ascii=False,
        )
        executor = AgentExecutor(self.llm_config, [])
        result = executor.run(DECISION_AGENT_SYSTEM_PROMPT, user_msg)
        plan = TradingPlan()
        try:
            data = json.loads(extract_json(result.get("content", "{}")))
            ma = data.get("market_assessment", {})
            plan.market_regime = ma.get("regime", "")
            plan.risk_level = ma.get("risk_level", "中等")
            plan.max_position = ma.get("max_position", 0.7)
            ep = data.get("execution_plan", {})
            plan.execution.immediate_summary = ep.get("immediate_summary", "")
            for o in ep.get("orders", []):
                plan.execution.immediate_orders.append(OrderItem(**o))
            for c in ep.get("conditional_orders", []):
                plan.execution.conditional_orders.append(
                    ConditionalOrder(
                        condition=c.get("condition", ""),
                        action=c.get("action", ""),
                        timing=c.get("timing", ""),
                    )
                )
            rm = data.get("risk_management", {})
            plan.risk = RiskManagement(
                circuit_breaker=rm.get("circuit_breaker", ""),
                portfolio_stop=rm.get("portfolio_stop", ""),
                key_risks=rm.get("key_risks", []),
            )
        except Exception as e:
            plan.risk.key_risks = [f"DecisionAgent parse error: {e}"]
        return plan
