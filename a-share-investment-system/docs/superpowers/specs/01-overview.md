# AShare-X 前端重构 — 概览与设计规范

> **实现状态**: ⚠️ 部分实现 — 设计规范已采用，部分页面已实现。当前实际架构参见 `docs/ACTUAL_ARCHITECTURE.md`。

## 目标
将传统量化前端升级为AI-Native认知交互界面，使前端能完整呈现AI选股引擎的感知→推理→决策→学习全链路。

## 技术栈
Vue 3.3 + TypeScript 5 + Vite 5 + Element Plus 2.3 + ECharts 5 + Pinia 2

## 设计规范

### 色彩系统
```scss
--bg-root: #0b1120;        // 深海军蓝背景
--bg-card: #131a2b;        // 卡片表面
--bg-surface: #1a2340;      // 次级表面
--border: #1e2d4a;         // 蓝色调边框
--text-primary: #e2e8f0;   // 主文字
--text-secondary: #8892b0; // 次要文字
--text-muted: #5a6a8a;     // 禁用文字
--accent-green: #10b981;   // 涨/正向
--accent-red: #ef4444;     // 跌/负向
--accent-blue: #3b82f6;    // 交互/链接
--accent-amber: #f59e0b;   // 警告
```

### 字体
- 数据/代码: JetBrains Mono (`.mono` class)
- UI标签: Noto Sans SC

### 布局
- 左侧固定侧边栏(220px) + 右侧内容区
- 内容区最大宽度1280px，居中
- 4px 网格间距系统

## 页面分级

| 级别 | 页面 | 类型 |
|------|------|------|
| P0 | Dashboard, Screening, AI Memory | AI-Native重写 |
| P1 | Database, Portfolio | 功能重写 |
| P2 | Analysis, Reports, Settings 等 | 精简重写 |

## API层结构
```
src/api/
├── ai.ts          # 新增: AI认知/Memory/Agent健康度
├── core.ts        # 基础CRUD (dbApi)
├── analysis.ts    # 分析
├── portfolio.ts   # 持仓
├── reports.ts     # 报告
├── screening.ts   # 选股
├── request.ts     # HTTP客户端(已有,复用)
└── index.ts       # 导出
```
