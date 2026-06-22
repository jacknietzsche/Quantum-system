# 6. API 设计

## 6.1 端点清单（精简至 16 个）

| 方法 | 路径 | 功能 |
|------|------|------|
| POST | `/api/chat/send` | 发送消息 (SSE 流式响应) |
| POST | `/api/daily/start` | 触发每日分析 |
| GET | `/api/daily/stream` | SSE 流式进度推送 |
| GET | `/api/task/{run_id}` | 查询任务状态 |
| GET | `/api/report/{date}` | 获取报告 |
| GET | `/api/report/{date}/email` | 发送报告到邮箱 |
| GET | `/api/report/list` | 报告列表 |
| GET | `/api/stock/{code}` | 股票详情分析 |
| GET | `/api/stock/{code}/kline` | K 线数据 |
| GET | `/api/market/status` | 市场状态 |
| GET | `/api/portfolio/holdings` | 持仓列表 |
| POST | `/api/portfolio/holding` | 添加持仓 |
| PUT | `/api/portfolio/holding/{code}/sell` | 卖出 |
| GET | `/api/settings/email` | 邮箱设置 |
| POST | `/api/settings/email` | 保存邮箱设置 |
| GET | `/api/health` | 健康检查 |

## 6.2 核心端点详设

### POST /api/chat/send

```
描述: 通用对话入口, 支持 SSE 流式响应

请求体:
  message: str           # 用户消息
  session_id: str        # 会话 ID (多轮对话)
  stream: bool = true    # 是否流式

响应 (SSE):
  event: "thinking"      # Agent 正在思考
  data: {"step": "parsing_intent"}

  event: "skill_call"    # 调用 Skill
  data: {"skill": "market.fetch_indices", "status": "started"}

  event: "skill_result"  # Skill 返回
  data: {"skill": "market.fetch_indices", "summary": "..."}

  event: "agent_message" # Agent 回复片段
  data: {"content": "今日市场..."}

  event: "done"          # 完成
  data: {"run_id": "xxx", "summary": "..."}
```

### POST /api/daily/start

```
描述: 触发每日完整分析流程

请求体:
  date: str | None           # 分析日期, 默认今天
  style: str = "hybrid"      # 选股风格
  portfolio_type: str = "value"
  skip_email: bool = false   # 是否跳过邮件发送

响应:
  {
    "run_id": "uuid",
    "status": "started",
    "estimated_duration": "5-10 min"
  }

说明:
  - 后台异步执行, 通过 GET /api/daily/stream 订阅进度
  - 17:00 前返回 400: "数据尚未更新"
```

### GET /api/report/{date}

```
描述: 获取指定日期的分析报告

响应:
  {
    "date": "2026-06-07",
    "market_summary": "...",
    "recommendations": [...],
    "report_html": "...",
    "email_sent": false
  }
```

### GET /api/report/{date}/email

```
描述: 发送报告到配置的 QQ 邮箱

响应:
  {
    "success": true,
    "sent_to": "user@qq.com",
    "message": "邮件已发送"
  }
```

### GET /api/stock/{code}

```
描述: 单股深度分析

响应:
  {
    "stock_code": "600519",
    "stock_name": "贵州茅台",
    "total_score": 85,
    "factors": {"pe": 23, "roe": 18, ...},
    "master_scores": {"buffett": 80, "lynch": 75, ...},
    "debate_summary": {...},
    "recommendation": "buy",
    "reasoning": "..."
  }
```

---

**上一节**: [05-database-design.md](05-database-design.md)
**下一节**: [07-frontend-architecture.md](07-frontend-architecture.md)
