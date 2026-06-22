# Dashboard AI认知总览

> **实现状态**: ✅ 已实现 — Dashboard 页面已包含 AI 认知简报和 Agent 健康度。

## 页面布局

```
┌─ 顶部状态栏 ──────────────────────────────────┐
│  DASHBOARD  数据日期 2026-06-04  最后更新 10:30 │
└────────────────────────────────────────────────┘
┌─ AI认知简报 ──────────┬─ Agent健康度 ──────────┐
│  "存量博弈，偏防御"     │  Agent     7d   30d   │
│  置信度 ████████ 78%   │  Buffett  85%  72%   │
│  策略倾向:              │  Lynch    72%  68%   │
│  价值 ████████ 60%     │  Burry    60%  65%   │
│  成长 ████ 25%        │  Wood     55%  58%   │
│  防御 ███ 15%         │  Druck    68%  62%   │
└───────────────────────┴──────────────────────┘
┌─ 市场总览 ───────────────────────────────────┐
│  指数: 上证 +0.3%  深证 -0.1%  创业板 +0.8%  │
│  涨跌比: 1800/1200  涨停65  跌停12             │
└──────────────────────────────────────────────┘
┌─ 数据管道状态 ───────────────────────────────┐
│  数据源: 7/7可用  K线: 最新2026-06-04         │
│  StockInfo: 6716只 行业: 69%  PE: 52%        │
└──────────────────────────────────────────────┘
```

## API依赖
- `GET /api/screening/market-state` — 市场诊断 (Stage 0 输出, 含state/weights/details)
- `GET /api/ai/agent-health` — Agent健康度
- `GET /api/system/dashboard` — 市场数据
- `GET /api/db/stats` — 数据管道状态

## 数据契约
```typescript
interface MarketDiagnosis {
  state: 'BULL' | 'BEAR' | 'SHOCK' | 'VOLATILE'  // 市场状态
  confidence: number    // 置信度 0-1
  weights: {
    trend: number       // 趋势质量权重
    capital: number     // 资金行为权重
    fundamental: number // AI基本面权重
    defensive: number   // 防御性权重
  }
  summary: string       // 一句话市场总结
  timestamp: string     // 诊断时间
  details: {            // 详细指标
    breadth: { up, down, limit_up, limit_down, total }
    sectors: { top: {name, change}[], bottom: {name, change}[] }
    volatility: number
    limit_up_count: number
  }
}
```
