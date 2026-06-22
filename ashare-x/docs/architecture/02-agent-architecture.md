# 2. Agent 架构详设

## 2.1 Agent 角色定义

### Master Agent (Planner)

```
职责:
  - 接收用户意图, 生成执行计划
  - 调度 Specialist Agents 和 Skills
  - 汇总结果, 生成最终回复

输入:
  - user_message: str
  - context: ConversationContext
  - available_skills: list[SkillSchema]

输出:
  - plan: ExecutionPlan
  - response: str (最终回复)

内部流程:
  1. 解析意图 (daily_analysis / stock_deep_dive / reflection / general_chat)
  2. 生成 Plan: [{step, skill_name, params, depends_on}]
  3. 顺序执行 Plan, 等待 Skill 返回
  4. 对于需要 Specialist Agent 的步骤, 调用 sub-agent
  5. 汇总所有结果, LLM 生成自然语言回复
```

### Market Agent (Specialist)

```
职责:
  - 分析当前市场状态
  - 输出: 市场阶段, 风格偏好, 风险等级

调用 Skills:
  - market.fetch_indices        # 获取指数数据
  - market.calculate_breadth    # 计算市场宽度
  - market.detect_regime        # 判断市场阶段
  - market.analyze_sectors      # 行业轮动分析

输出 Schema:
  regime: "bull" | "bear" | "sideways"
  style_bias: "value" | "momentum" | "hybrid" | "defensive"
  risk_level: "low" | "medium" | "high" | "extreme"
  summary: str
  confidence: float
```

### Analyst Agent (Specialist)

```
职责:
  - 对单只股票进行多维度深度分析
  - 支持批量并发调用

调用 Skills:
  - data.fetch_kline
  - data.fetch_fundamentals
  - quant.factor_score
  - quant.master_score      # 大师风格评分
  - quant.debate_analysis   # LLM 多空辩论

输出 Schema:
  stock_code: str
  stock_name: str
  total_score: float
  factors: dict[str, float]
  master_scores: dict[str, float]
  debate_summary: {bull_thesis, bear_thesis, verdict, confidence}
  recommendation: "strong_buy" | "buy" | "hold" | "sell" | "strong_sell"
  reasoning: str
```

### Portfolio Agent (Specialist)

```
职责:
  - 分析用户持仓组合
  - 风险评估, 集中度分析

调用 Skills:
  - portfolio.get_holdings
  - risk.calculate_var
  - risk.concentration_check
  - quant.correlation_matrix

输出 Schema:
  total_asset: float
  positions: list[Position]
  risk_metrics: {var, max_drawdown, sharpe_ratio}
  warnings: list[str]
```

### Reflection Agent (Specialist)

```
职责:
  - 对比历史预测与实际结果
  - 生成改进建议

调用 Skills:
  - memory.retrieve_predictions
  - data.fetch_actual_performance
  - quant.compare_prediction_vs_actual

输出 Schema:
  period: str
  accuracy: float
  avg_return: float
  failed_cases: list[{stock_code, predicted, actual, reason}]
  improvement_suggestions: list[str]
```

## 2.2 Agent 间通信

```
Master Agent (唯一的用户入口)
    │
    ├── [需要市场分析] ──→ Market Agent ──→ 返回市场状态
    │
    ├── [需要选股] ──→ 调 skills/screening.run
    │                     ↓
    │              候选池 (30-50 只)
    │                     ↓
    │              并发调用 Analyst Agent × N ──→ 返回各股分析
    │                     ↓
    │              Master 汇总排序 ──→ Top 10
    │
    ├── [需要持仓分析] ──→ Portfolio Agent ──→ 返回风险评估
    │
    └── [需要复盘] ──→ Reflection Agent ──→ 返回改进建议
```

### 关键约束

- Master Agent 是唯一能直接和用户对话的 Agent
- Specialist Agent 不互相调用, 不直接访问 UI
- 所有 Agent 通过 Skill 获取数据, 不直接操作 DB

---

**上一节**: [01-overview.md](01-overview.md)
**下一节**: [03-skill-system.md](03-skill-system.md)
