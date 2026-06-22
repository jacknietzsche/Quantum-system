# API契约定义

> **实现状态**: ❌ 已过时 — 实际 API 与文档描述不同，参见 `docs/ACTUAL_ARCHITECTURE.md`。

## AI认知端点 (新增)

### GET /api/ai/market-state
市场诊断摘要，Dashboard顶部展示。

```json
{
  "summary": "存量博弈，偏防御",
  "confidence": 0.78,
  "regime": "DIVERGENCE",
  "strategy_weights": {
    "value": 0.60,
    "growth": 0.25,
    "defensive": 0.15
  },
  "risk_level": "medium"
}
```

### GET /api/ai/agent-health
Agent推荐准确率统计。

```json
{
  "agents": [
    {
      "name": "buffett",
      "display_name": "巴菲特",
      "accuracy_7d": 0.85,
      "accuracy_30d": 0.72,
      "accuracy_all": 0.68,
      "total_picks": 120,
      "correct_picks": 82
    }
  ]
}
```

### GET /api/ai/memory/calendar?days=30
每日复盘日历。

```json
{
  "days": [
    {
      "trade_date": "2026-06-04",
      "regime": "DIVERGENCE",
      "picks_count": 8,
      "correct_count": 5,
      "avg_return": 0.021,
      "market_return": -0.003,
      "reflection": "防御策略正确，但漏掉了XX板块反弹"
    }
  ]
}
```

### GET /api/ai/memory/similar?date=2026-06-04
相似市场历史检索。

```json
{
  "similar_days": [
    {
      "trade_date": "2026-05-10",
      "similarity": 0.85,
      "regime": "DIVERGENCE",
      "strategy": "defensive",
      "result": 0.018
    }
  ]
}
```

## 选股流程扩展

### SSE事件流新增事件
```
event: market_diagnosis  → AI市场诊断完成
event: agent_proposal    → Agent提交动议 (可多次)
event: debate_round      → 辩论裁决 (可多轮)
event: final_recommendation → 最终推荐
```

### 选股结果扩展字段
每个推荐股票增加:
```json
{
  "stock_code": "600519",
  "stock_name": "贵州茅台",
  "score": 78,
  "logic_summary": "高ROE+强护城河,估值合理",
  "supporting_agents": ["buffett", "lynch"],
  "debate_report": {
    "key_issue": "估值是否偏高?",
    "pro_args": "PE 19倍低于历史中位数",
    "con_args": "营收增速放缓至6%",
    "verdict": "采纳多方, 维持推荐"
  }
}
```
