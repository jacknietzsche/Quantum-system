# 8. 部署与运维

## 8.1 目录结构（重构后）

```
ashare-x/
├── backend/
│   ├── api/                    # FastAPI 路由 (15 个端点)
│   ├── agents/                 # Agent 定义 (Master + 4 Specialist)
│   │   ├── master_agent.py     # intent_parser + plan_generator + summarize
│   │   ├── market_agent.py     # Market Agent
│   │   ├── analyst_agent.py    # Analyst Agent
│   │   ├── portfolio_agent.py  # Portfolio Agent
│   │   ├── reflection_agent.py # Reflection Agent
│   │   └── nodes/              # LangGraph 图节点实现 (9 个节点)
│   │       ├── init.py
│   │       ├── execution_loop.py
│   │       ├── skill_executor.py
│   │       ├── agent_executor.py
│   │       ├── interrupt_node.py
│   │       └── error_handler.py
│   ├── skills/                 # Skill 实现 (按 category 分目录)
│   │   ├── data/
│   │   ├── quant/
│   │   ├── report/
│   │   ├── communication/
│   │   └── memory/
│   ├── providers/              # 数据源适配层 (利旧)
│   ├── shared/                 # 基础设施 (DB, Config, Logging)
│   ├── workflow/               # LangGraph 图定义
│   ├── main.py                 # FastAPI 入口
│   └── config.yaml             # 配置
├── frontend/                   # Vue 3 SPA (重写)
│   └── src/
│       ├── components/
│       ├── views/
│       ├── stores/
│       └── api/
├── tests/
├── docs/
└── pyproject.toml
```

## 8.2 配置管理

```yaml
# config.yaml
llm:
  provider: deepseek
  model: deepseek-chat
  temperature: 0.1

data:
  primary_sources: [tencent, eastmoney]
  fallback_chain: [baostock, akshare, tushare]
  cache_ttl_seconds: 3600

email:
  smtp_host: smtp.qq.com
  smtp_port: 465
  sender_email: "${QQ_EMAIL}"  # 从 .env 读取
  sender_password: "${QQ_SMTP_PASSWORD}"

schedule:
  analysis_start_time: "17:00"
  auto_refresh_data: true

limits:
  max_candidates: 50
  debate_per_stock: 20
  daily_report_max_stocks: 10
```

---

**上一节**: [07-frontend-architecture.md](07-frontend-architecture.md)
**下一节**: [09-roadmap.md](09-roadmap.md)
