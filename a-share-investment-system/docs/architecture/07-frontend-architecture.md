# 7. 前端架构

## 7.1 页面结构

```
┌──────────────────────────────────────────────┐
│  Top Bar: 日期 | 市场状态灯 | 快捷操作按钮    │
├────────┬─────────────────────────────────────┤
│        │                                     │
│  Nav   │    Content Area                     │
│        │                                     │
│  - Chat│  ┌─────────────────────────────┐    │
│  -     │  │ Chat Messages              │    │
│  Dash- │  │ - User: "开始分析"          │    │
│  board │  │ - AI: 卡片(市场状态)        │    │
│  -     │  │ - AI: 进度条(选股中...)     │    │
│  Repo- │  │ - AI: 推荐列表卡片          │    │
│  rts   │  │ - User: "发送邮件"          │    │
│  -     │  │ - AI: 邮件已发送 ✓         │    │
│  Port- │  └─────────────────────────────┘    │
│  folio │                                     │
│  -     │  ┌─────────────────────────────┐    │
│  Sett- │  │ Input Box                   │    │
│  ings  │  │ [输入消息...]    [快捷指令▼] │    │
│        │  └─────────────────────────────┘    │
└────────┴─────────────────────────────────────┘
```

## 7.2 核心组件

| 组件 | 功能 | 技术 |
|------|------|------|
| `ChatPanel` | 消息列表 + 输入框 | 自定义虚拟滚动 |
| `MarketStatusCard` | 市场状态指示灯 | Element Plus Card |
| `RecommendationCard` | 股票推荐卡片 | 包含分数/信号/理由 |
| `DebatePanel` | 辩论详情展开 | 牛熊论点对比 |
| `ScreeningFunnel` | 选股漏斗图 | ECharts funnel |
| `KlineChart` | K 线图 | ECharts candlestick |
| `ProgressOverlay` | 分析进度条 | SSE 事件驱动 |
| `ReportPreview` | HTML 报告预览 | iframe 嵌入 |
| `EmailSettings` | 邮箱配置 | Element Plus Form |

## 7.3 状态管理 (Pinia)

```typescript
// stores/chat.ts
interface ChatState {
  messages: Message[]
  isStreaming: boolean
  currentRunId: string | null
  progress: TaskProgress | null
}

// stores/market.ts
interface MarketState {
  regime: string
  indices: IndexData[]
  lastUpdated: string
}

// stores/recommendations.ts
interface RecommendationState {
  date: string
  recommendations: StockRecommendation[]
  loading: boolean
}
```

---

**上一节**: [06-api-design.md](06-api-design.md)
**下一节**: [08-deployment.md](08-deployment.md)
