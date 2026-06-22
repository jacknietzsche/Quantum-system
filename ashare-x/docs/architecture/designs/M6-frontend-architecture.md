# Module 6: 前端架构与交互设计

**前置**: M5 (API 设计), M3.5/M4 (State & 工作流图)  
**用途**: 定义 Vue 3 SPA 的整体结构、组件职责、状态管理与 SSE 交互机制  
**状态**: Draft | **日期**: 2026-06-07

> ⚠️ **TARGET ARCHITECTURE** — 本文档描述目标架构，非当前实现。当前实际架构参见 `docs/ACTUAL_ARCHITECTURE.md`。

---

## 1. 页面布局与路由

**布局**: 经典左导航 + 右内容区 + 顶部状态栏

- **侧边栏**: Chat(对话主界面), Dashboard(今日摘要), Reports(历史报告), Portfolio(持仓), Settings(设置)
- **顶部状态栏**: 系统状态指示、当前日期、快捷操作按钮

**路由表**:

| 路径 | 组件 | 说明 |
|------|------|------|
| `/` | 重定向至 `/chat` | — |
| `/chat` | ChatView | 主交互区，对话界面 |
| `/dashboard` | DashboardView | 今日摘要，可查看当前推荐 |
| `/reports` | ReportListView | 历史报告列表 |
| `/reports/:date` | ReportDetailView | 单日报告详情 |
| `/portfolio` | PortfolioView | 持仓列表与指标 |
| `/settings` | SettingsView | 邮箱配置 |

---

## 2. 核心组件树

```
App.vue
└── BasicLayout
    ├── SideBar.vue
    ├── TopBar.vue (状态灯 + 快捷按钮)
    └── RouterView
        ├── ChatView
        │   ├── MessageList
        │   │   ├── UserMessageBubble
        │   │   └── AgentMessageBubble
        │   │       ├── TextContent
        │   │       ├── MarketStatusCard
        │   │       ├── RecommendationCard
        │   │       ├── ProgressBanner
        │   │       └── ConfirmationCard
        │   └── ChatInputBar
        ├── DashboardView
        │   ├── MarketOverview
        │   └── StockList
        └── ...
```

---

## 3. 状态管理 (Pinia)

### 3.1 任务/对话状态 (`stores/chat.ts`)

| 字段 | 类型 | 说明 |
|------|------|------|
| `sessionId` | `string \| null` | 当前会话 ID（前端 cookie 标识，服务端不持久化，见 M5 §3.1.1） |
| `sessionPersistence` | `'memory' \| 'localStorage'` | **MVP 默认 `'memory'`**；路由跳转后消息列表**保留在内存**（SPA 不刷新即可），浏览器刷新后清空；`localStorage` 模式推 Phase 4 |
| `messages` | `Message[]` | 对话历史，含 role, content, timestamp, meta?。**`role` 包含 `system`**（2026-06-07 补强 P0-4 / F-5：Interrupt 暂停/恢复/error 终态时追加 system 消息） |
| `currentRunId` | `string \| null` | 当前任务 run_id（**2026-06-07 补强 C-10**：由 API 层 `/api/chat` 在创建任务时生成，前端从 `run_start` 事件 `data.run_id` 字段接收） |
| `taskStatus` | `'idle' \| 'running' \| 'waiting_confirmation' \| 'completed' \| 'failed' \| 'cancelling' \| 'cancelled'` | 任务状态（**含 cancelling 中间态**，见 M3.5 §1.2）。**2026-06-07 补强 F-8**：终态 `completed / failed / cancelled`，前端不再需要识别 `timeout` 状态（已统一归 `cancelled`） |
| `progressSteps` | `StepProgress[]` | 步骤执行进度 |
| `confirmationData` | `ConfirmationData \| null` | 暂停时收到的确认信息（**2026-06-07 补强 P0-1**：`type` 字段值包括 `confirm_plan / confirm_email / wait_for_user`，不再只是 `confirm`） |
| `streamingContent` | `string` | 当前流式接收的 AI 回复片段（**confirm 切流时清空**，见 §4.3.1） |
| `eventSource` | `EventSource \| null` | 当前活跃 SSE 连接 |
| `canResume` | `boolean` | **2026-06-07 补强 P0-2**：根据 `GET /api/tasks/{run_id}/status` 返回的 `last_event_time` 与当前时间差，1h 内为 true 可用"恢复"按钮，超过 1h 为 false 显示 tooltip "超过 1 小时不可恢复，可查看历史" |

### 3.2 其他 Store

`stores/market.ts`: regime, styleBias, riskLevel, summary, lastUpdated  
`stores/recommendations.ts`: date, recommendations[], loading  
`stores/portfolio.ts`: positions[], totalAsset, cash, totalReturnPct

---

## 4. SSE 交互流程

**SSE 客户端选择**: 使用 `fetch` + `ReadableStream` 而非 `EventSource`，因为需要 `POST` 方法。

### 4.1 建立连接

用户发送消息 → `fetch('/api/chat', {method:'POST', body, headers:{Accept:'text/event-stream'}})` → 读取 `response.body.getReader()`

### 4.2 事件处理循环

```
run_start:
  → chatStore.runId = data.run_id
  → chatStore.taskStatus = 'running'
  → 清空 progressSteps

step_start:
  → progressSteps 追加条目
  → UI 进度条更新

step_result:
  → 更新对应步骤状态
  → 若是 market_agent → 同时更新 marketStore
  → 若是 screening → 可更新候选池
  → 若失败 → 标记该步骤
  → **若 data.failed_codes 非空 → 渲染告警条**（"3 只股票因数据缺失跳过"）

agent_message:
  → 追加到 streamingContent
  → 打字机效果
  → 下个非 agent_message 或 task_complete 到达时
    → 推入 messages
    → 清空 streamingContent
  → **confirm 切流时强制清空 streamingContent**（见 §4.3.1）

waiting_confirmation:
  → chatStore.taskStatus = 'waiting_confirmation'
  → 保存 confirmationData
  → 消息列表末尾插入 ConfirmationCard

error:
  → 显示错误提示

task_complete:
  → chatStore.taskStatus = 'completed'
  → 清理 currentRunId
```

### 4.3 确认中断流程

```
1. 原 SSE 推送 waiting_confirmation 后关闭
2. 前端显示确认卡片
3. 用户确认 → POST /api/tasks/{run_id}/confirm (Accept: text/event-stream)
4. 创建新 fetch 流接收后续事件
5. 新流推送 step_result → 后续步骤 → agent_message → task_complete
6. 确认卡片消失
```

#### §4.3.1 confirm 切流时 streamingContent 处理（产品决定）

**核心决策**：confirm 前的 `streamingContent` **丢弃**，confirm 后的新流**重新生成完整回复**。

**具体行为**：
1. 用户点"确认"按钮 → 前端 `streamingContent` 立即**清空**（不保留正在打字机渲染的片段）
2. 关闭老 EventSource
3. 调用 `POST /api/tasks/{run_id}/confirm`，开启新 fetch 流
4. 新流的 `agent_message` 事件**从零开始**拼接到 `streamingContent`，重新打字机渲染

**为什么不保留**：
- confirm 后的 plan 可能完全变了（"modify" 场景），老片段语义失效
- 拼接"老片段 + 新片段"在 UI 上会出现内容跳跃、用户困惑
- "丢弃重渲"对用户语义最清晰：老的内容是"中断前的草稿"，新内容是"确认后的正式回复"

**UI 提示**（避免用户以为内容丢失）：
- confirm 卡片在用户点确认后立即**淡出**（300ms 动画）
- 新流的首个 `step_start` 事件触发**全屏 loading**（< 1s），告诉用户"正在生成新回复"
- `agent_message` 首个片段到达后，loading 消失，开始打字机

→ 由 software-product-manager 于 2026-06-07 补强，依据 review 第 2 轮 P0。

### 4.4 重连策略（2026-06-07 补强 F-13）

- **页面刷新后恢复**（**MVP 支持**）：前端路由初始化时若 `chatStore.currentRunId` 非空（来自 URL 参数或 localStorage 暂存），调用 `GET /api/tasks/{run_id}/status`（F-13 新增端点）获取最新状态：
  - `status="waiting_user"` + `last_event_time` 在 1h 内 → 显示 ConfirmationCard，启用"恢复"按钮
  - `status="waiting_user"` + `last_event_time` 超过 1h → 显示"超过 1 小时不可恢复，可查看历史"tooltip，恢复按钮 disabled
  - `status="completed / failed / cancelled"` → 渲染最终结果/错误信息
  - `status="executing"` + SSE 流已断开 → 提示"任务正在执行中（SSE 连接断开）"，可选尝试重连（`POST /api/tasks/{run_id}/resume` Phase 4 端点）
- **运行中 SSE 非正常中断**：MVP 暂不自动重连，提示用户重新发起
- **未来扩展**：`POST /api/tasks/{run_id}/resume`（Phase 4）支持显式重连

---

## 5. 关键交互细节

| 场景 | 实现方式 |
|------|----------|
| 快捷指令 | 输入框上方按钮（"今日分析""我的持仓""最近市场"），点击自动填充并发送 |
| 卡片嵌入 | AgentMessageBubble 根据 `meta` 类型渲染嵌入式卡片 |
| 进度展示 | 任务过程中用单条系统消息动态更新卡片内容，而非频繁增加消息 |
| 报告渲染 | GET /api/reports/{date} 获取 Markdown，`marked` 库渲染 |
| 持仓管理 | 表单提交 PUT /api/portfolio/holding，简单添加/卖出 |

---

#### §5.1 大量 step_result 的渲染策略

Analyst Agent 批量分析时可能产生 160+ 条 `step_result` 事件。渲染策略：
- 使用 `requestAnimationFrame` 限流，每 16ms（60fps）最多 commit 一次 Pinia store
- 步骤进度条按 batch 刷新（每 5 条合并一次 UI 更新），非流式逐条追加
- 入场动画使用 CSS `content-visibility: auto`，只渲染可视区域内的卡片

#### §5.2 拒绝大量 SSE 事件的策略

- MVP **不做 SSE 重连**（与 M5 一致）。EventSource 断线后直接提示"连接已断开"
- 不做心跳（ping/pong），SSE 连接绑定任务生命周期
- 无事件即无连接，不存在空闲连接存活场景

## 6. 技术选型

| 库 | 用途 |
|----|------|
| Vue 3 + Composition API | 框架 |
| Pinia | 状态管理 |
| Vue Router 4 | 路由 |
| Element Plus | 基础 UI 组件 |
| ECharts 5 + vue-echarts | K 线图、市场宽度图表 |
| `marked` | Markdown 渲染 |
| `dayjs` | 日期处理 |
| Fetch API + ReadableStream | SSE 客户端 |

---

## 7. 构建与部署

- 开发: Vite 代理 `/api` → `http://localhost:8000`
- 生产: 构建产物放入 `backend/static/`，FastAPI 服务静态文件

#### §7.1 端口代理配置

**禁止硬编码端口**！Vite dev 代理必须从 `.env` 读 `VITE_API_PORT`。

```bash
# frontend/.env.development
VITE_API_PORT=8765
```

```typescript
// frontend/vite.config.ts
import { defineConfig, loadEnv } from 'vite'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const apiPort = env.VITE_API_PORT || '8765'
  return {
    server: {
      port: 5173,  // Vite dev 自身端口（与后端 8765 区分）
      proxy: {
        '/api': {
          target: `http://localhost:${apiPort}`,
          changeOrigin: true,
          // SSE 必须禁用 buffer（防响应被截断）
          configure: (proxy) => {
            proxy.on('proxyRes', (proxyRes) => {
              proxyRes.headers['x-accel-buffering'] = 'no'
              proxyRes.headers['cache-control'] = 'no-cache'
            })
          },
        },
      },
    },
  }
})
```

**与 M5 §3.11.1 端口契约对齐**：
- 前端 `.env` 端口 = 后端 `ASAREX_PORT`
- 默认均为 8765
- 修改时**两边同步**（可在 launch.py 启动时自动写 `.env`）

**生产构建**（`npm run build` → 产物到 `backend/static/`）：
- 生产无 Vite 代理，FastAPI 直接服务静态文件 + API
- 端口仅由 `ASAREX_PORT` 控制（与 M5 §3.11.1 一致）

→ 由 software-product-manager 于 2026-06-07 补强，依据 review 第 2 轮 P1。

---

## 8. MVP 范围确认

| 功能 | MVP | 后续 |
|------|-----|------|
| ChatView（对话+流式+确认） | ✅ | — |
| Dashboard（静态展示） | ✅ | 实时更新 |
| 报告列表 + 详情 | ✅ | PDF 下载 |
| 持仓查看 + 修改 | ✅ | 净值曲线 |
| 邮箱设置 | ✅ | 更多通知渠道 |
| 多用户 | — | ❌ |
| 移动端适配 | — | ❌ |
| 国际化 | — | ❌ |

---

**上一节**: [M5 API 设计](M5-api-design.md)  
**文档索引**: [README](../README.md)
