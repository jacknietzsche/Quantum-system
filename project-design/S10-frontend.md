# S10 — 前端交互设计

> **设计依据**: 参考 TradingAgents-AShare(KylinMountain) 的完整前端实现、
> PySpur(5.7k stars) 的可视化工作流、Dify/Flowise 的Agent UI模式。

## 10.1 技术栈选择（借鉴TradingAgents-AShare）

TradingAgents-AShare的前端是目前最成熟的Agent交易前端，技术栈：

| 组件 | 选择 | 版本 | 用途 |
|------|------|------|------|
| 框架 | React | 18.x | 基础UI |
| 构建 | Vite | 6.x | 开发构建 |
| 类型 | TypeScript | 6.x | 类型安全 |
| 样式 | Tailwind CSS | 4.x | 原子化CSS |
| 状态管理 | Zustand | 5.x | 轻量状态管理 |
| 图表 | Recharts | 2.x | 数据图表 |
| K线图 | lightweight-charts | 5.x | TradingView K线 |
| 流程图 | @xyflow/react (ReactFlow) | 12.x | Agent协作可视化 |
| Markdown | react-markdown + remark-gfm | 10.x | 报告渲染 |
| 图标 | lucide-react | 0.344 | 图标库 |
| 虚拟滚动 | @tanstack/react-virtual | 3.x | 大列表优化 |
| 路由 | react-router-dom | 6.x | 页面路由 |
| 工具 | clsx + tailwind-merge | — | className合并 |
| 日期 | date-fns | 4.x | 日期处理 |

**对比我们之前的设计**: 删除ECharts（用Recharts+lightweight-charts替代），删除shadcn/ui（用Tailwind原生组件），增加ReactFlow（Agent可视化核心）。

## 10.2 状态管理（借鉴TradingAgents-AShare）

TradingAgents-AShare使用Zustand + persist中间件：

```typescript
// analysisStore.ts 的核心模式
import { create } from 'zustand'
import { persist, createJSONStorage } from 'zustand/middleware'

interface AnalysisState {
    // 当前任务
    currentJobId: string | null
    currentSymbol: string
    jobStatus: JobStatus | null

    // Agent状态
    agents: Agent[]

    // 报告
    report: AnalysisReport | null

    // 流式报告状态（打字机效果）
    streamingSections: Record<string, StreamingSectionState>

    // 辩论消息（临时，用于battle视图）
    debateMessages: Record<string, DebateMessage[]>
    debateScrollTick: number

    // 聊天消息（跨路由持久化）
    chatMessages: ChatMessage[]

    // 加载状态
    isAnalyzing: boolean
    isConnected: boolean
    analysisRunState: 'idle' | 'running' | 'completed' | 'failed'

    // 操作方法
    updateAgentStatus: (event: AgentStatusEvent) => void
    addAgentMessage: (event: AgentMessageEvent) => void
    addReportChunk: (event: ReportChunkEvent) => void
    // ...
}

export const useAnalysisStore = create<AnalysisState>()(
    persist(
        (set, get) => ({
            // ... 实现
        }),
        {
            name: 'analysis-storage',
            storage: createJSONStorage(() => localStorage),
            partialize: (state) => ({
                // 只持久化必要字段
                chatMessages: state.chatMessages,
                currentSymbol: state.currentSymbol,
            }),
        }
    )
)
```

**关键设计**:
- `debateMessages` 不持久化（临时数据，刷新即丢）
- `chatMessages` 持久化（跨路由保留对话）
- `streamingSections` 实时更新（打字机效果）

## 10.3 页面结构

| 路由 | 页面 | 核心组件 | 数据来源 |
|------|------|----------|----------|
| `/` | Dashboard | KeyMetrics + 最近决策 | GET /api/dashboard |
| `/analysis` | 个股分析 | 输入框 + Agent协作图 | POST /api/analysis |
| `/analysis/:ticker` | 分析详情 | Agent协作图 + 辩论抽屉 + 决策卡片 | SSE /ws/analysis/{id} |
| `/screening` | 智能选股 | 筛选条件 + 结果列表 | GET /api/screening |
| `/portfolio` | 组合管理 | 持仓表 + NAV曲线 | GET /api/portfolio |
| `/reports` | 报告中心 | 报告列表 + 查看器 | GET /api/reports |
| `/settings` | 设置 | LLM配置 + Skill开关 | GET/PUT /api/settings |

## 10.4 核心组件设计

### 10.4.1 Agent协作可视化（借鉴TradingAgents-AShare）

TradingAgents-AShare使用ReactFlow实现Agent流程图：

```tsx
// AgentCollaboration.tsx 的核心模式
import { ReactFlow, Handle, Position, type Node, type Edge } from '@xyflow/react'

// Agent元数据定义
interface AgentMeta {
    name: string        # 内部名
    label: string       # 显示名
    goal: string        # 目标描述
    section?: string    # 对应报告字段
    debate?: 'research' | 'risk'  # 辩论类型
    Icon: React.FC      # 图标
    badgeBg: string     # 背景色
    badgeText: string   # 文字色
}

const META: AgentMeta[] = [
    { name: 'Market Analyst', label: '技术面', section: 'market_report', ... },
    { name: 'Bull Researcher', label: '多头', debate: 'research', ... },
    { name: 'Bear Researcher', label: '空头', debate: 'research', ... },
    // ... 12个Agent
]

// 流程图节点布局
const NODE_POSITIONS: Record<string, { x: number; y: number }> = {
    'Market Analyst':       { x: 0, y: 0 },
    'Bull Researcher':      { x: 470, y: 80 },
    'Bear Researcher':      { x: 470, y: 250 },
    // ...
}
```

**ReactFlow的核心价值**:
- 每个Agent是一个节点，状态实时更新（待命→分析中→完成→异常）
- 节点间连线显示数据流向
- 点击节点展开详细报告
- 支持拖拽、缩放、自动布局

### 10.4.2 辩论抽屉（借鉴TradingAgents-AShare）

TradingAgents-AShare的DebateDrawer是实时辩论可视化的核心：

```tsx
// DebateDrawer.tsx 的核心模式
const DEBATE_PARTICIPANTS = {
    research: [
        { emoji: '🐂', label: '多头', cls: 'bg-emerald-500/15 text-emerald-400' },
        { emoji: '🐻', label: '空头', cls: 'bg-rose-500/15 text-rose-400' },
        { emoji: '🏛️', label: '研究总监', cls: 'bg-blue-500/15 text-blue-400' },
    ],
    risk: [
        { emoji: '🔥', label: '激进', cls: 'bg-red-500/15 text-red-400' },
        { emoji: '⚖️', label: '中性', cls: 'bg-slate-500/15 text-slate-400' },
        { emoji: '🛡️', label: '稳健', cls: 'bg-amber-500/15 text-amber-400' },
        { emoji: '🏛️', label: '风控', cls: 'bg-blue-500/15 text-blue-400' },
    ],
}

// 辩论时间线
function DebateTimeline({ messages, debate }) {
    // 按轮次分组
    const rounds = new Map<number, DebateMessage[]>()
    for (const msg of speeches) {
        const list = rounds.get(msg.round) || []
        list.push(msg)
        rounds.set(msg.round, list)
    }

    return (
        <div>
            {sortedRounds.map(([round, msgs]) => (
                <div key={round}>
                    {/* 轮次分隔线 */}
                    <div className="flex items-center gap-3 my-4">
                        <div className="flex-1 h-px bg-amber-500/20" />
                        <span className="text-xs font-bold text-amber-500">
                            Round {round}
                        </span>
                        <div className="flex-1 h-px bg-amber-500/20" />
                    </div>
                    {/* 发言卡片 */}
                    {msgs.map((msg) => (
                        <div className="ml-2 rounded-lg border p-4">
                            <span className="text-base">{meta.emoji}</span>
                            <span className="text-sm font-bold">{meta.label}</span>
                            <ReactMarkdown>{msg.content}</ReactMarkdown>
                        </div>
                    ))}
                </div>
            ))}
        </div>
    )
}
```

**关键设计**:
- 抽屉式设计（从右侧滑入，占屏幕50%宽度）
- 按轮次分组显示，每轮有分隔线
- 每个Agent有独立的颜色和emoji标识
- 自动滚动到底部（用户向上滚动时暂停）
- Escape键关闭

### 10.4.3 决策卡片（借鉴TradingAgents-AShare）

```tsx
// DecisionCard.tsx 的核心模式
const decisionConfig = {
    buy:    { label: '买入', color: 'bg-red-100 text-red-700', icon: TrendingUp },
    sell:   { label: '卖出', color: 'bg-green-100 text-green-700', icon: TrendingDown },
    hold:   { label: '持有', color: 'bg-blue-100 text-blue-700', icon: Shield },
    add:    { label: '增持', color: 'bg-red-100 text-red-700', icon: TrendingUp },
    reduce: { label: '减持', color: 'bg-orange-100 text-orange-700', icon: TrendingDown },
    watch:  { label: '观望', color: 'bg-slate-100 text-slate-700', icon: Info },
}

function DecisionCard({ decision, confidence, targetPrice, stopLoss, reasoning }) {
    return (
        <div className="card">
            {/* 决策标签 */}
            <div className={config.color}>
                <DecisionIcon className="w-5 h-5" />
                <span>{config.label}</span>
            </div>
            {/* 目标价/止损价 */}
            <div className="grid grid-cols-2 gap-4">
                <div>
                    <span className="text-xs text-slate-500">目标价</span>
                    <span className="text-lg font-bold">{targetPrice}</span>
                </div>
                <div>
                    <span className="text-xs text-slate-500">止损价</span>
                    <span className="text-lg font-bold">{stopLoss}</span>
                </div>
            </div>
            {/* 置信度 */}
            <div className="w-full bg-slate-200 rounded-full h-2">
                <div className="bg-blue-500 h-2 rounded-full" style={{width: `${confidence}%`}} />
            </div>
            {/* 理由（可展开） */}
            <ReactMarkdown>{reasoning}</ReactMarkdown>
        </div>
    )
}
```

### 10.4.4 风险雷达（借鉴TradingAgents-AShare）

```tsx
// RiskRadar.tsx 的核心模式
const LEVEL_CONFIG = {
    high:   { color: 'text-rose-400', bg: 'bg-rose-500/20', label: '高风险', icon: AlertTriangle },
    medium: { color: 'text-amber-400', bg: 'bg-amber-500/20', label: '中风险', icon: AlertCircle },
    low:    { color: 'text-emerald-400', bg: 'bg-emerald-500/20', label: '低风险', icon: Shield },
}

function RiskRadar({ items }) {
    return (
        <div className="card">
            <h3>风险雷达</h3>
            {risks.map((risk) => (
                <div className="flex items-center justify-between p-2.5 rounded-lg">
                    <span>{risk.name}</span>
                    <span className={LEVEL_CONFIG[risk.level].color}>
                        {LEVEL_CONFIG[risk.level].label}
                    </span>
                </div>
            ))}
        </div>
    )
}
```

## 10.5 实时数据流（SSE）

TradingAgents-AShare使用SSE（Server-Sent Events）实现Agent状态实时推送：

```typescript
// SSE事件类型定义
type AgentStatusEvent = {
    type: 'agent.status'
    agent: string
    status: 'pending' | 'in_progress' | 'completed' | 'error'
}

type AgentMessageEvent = {
    type: 'agent.message'
    agent: string
    content: string
    round?: number  # 辩论轮次
}

type ReportChunkEvent = {
    type: 'report.chunk'
    section: string
    content: string
}

type AgentTokenEvent = {
    type: 'agent.token'
    agent: string
    tokens: number
}

// SSE连接管理
function useAnalysisSSE(jobId: string) {
    const store = useAnalysisStore()

    useEffect(() => {
        const eventSource = new EventSource(`/api/stream/${jobId}`)

        eventSource.addEventListener('agent.status', (e) => {
            store.updateAgentStatus(JSON.parse(e.data))
        })

        eventSource.addEventListener('agent.message', (e) => {
            store.addAgentMessage(JSON.parse(e.data))
        })

        eventSource.addEventListener('report.chunk', (e) => {
            store.addReportChunk(JSON.parse(e.data))
        })

        eventSource.addEventListener('agent.token', (e) => {
            store.addAgentToken(JSON.parse(e.data))
        })

        eventSource.addEventListener('job.completed', (e) => {
            store.setReport(JSON.parse(e.data).result)
            eventSource.close()
        })

        return () => eventSource.close()
    }, [jobId])
}
```

**事件流设计**:

| 事件 | 触发时机 | 前端行为 |
|------|----------|----------|
| `agent.status` | Agent状态变化 | 更新ReactFlow节点颜色 |
| `agent.message` | Agent输出消息 | 追加到辩论抽屉 |
| `report.chunk` | 报告文本片段 | 打字机效果追加到报告 |
| `agent.tool_call` | Agent调用工具 | 显示工具调用状态 |
| `agent.token` | Token使用量 | 更新token计数器 |
| `agent.milestone` | 关键里程碑 | 追加到聊天消息 |
| `job.completed` | 任务完成 | 显示最终报告和决策卡片 |
| `job.failed` | 任务失败 | 显示错误信息 |

## 10.6 布局设计

借鉴TradingAgents-AShare的Layout组件：

```
┌──────────────────────────────────────────────────────────┐
│  Header: Logo + 股票搜索 + 主题切换 + 用户菜单           │
├──────────┬───────────────────────────────────────────────┤
│          │                                               │
│ Sidebar  │              Main Content                     │
│          │                                               │
│ 导航菜单 │  ┌─────────────────────────────────────────┐  │
│          │  │ Agent协作图（ReactFlow）                 │  │
│ Dashboard│  │ 每个Agent节点显示实时状态                │  │
│ 分析     │  └─────────────────────────────────────────┘  │
│ 选股     │                                               │
│ 组合     │  ┌──────────────┐ ┌──────────────────────┐   │
│ 报告     │  │ 决策卡片      │ │ 风险雷达             │   │
│ 设置     │  │ Buy/Sell/Hold │ │ 高/中/低风险         │   │
│          │  └──────────────┘ └──────────────────────┘   │
│          │                                               │
│          │  ┌─────────────────────────────────────────┐  │
│          │  │ 聊天面板（可选）                         │  │
│          │  │ 用户输入 → Agent响应                     │  │
│          │  └─────────────────────────────────────────┘  │
└──────────┴───────────────────────────────────────────────┘
```

## 10.7 暗色模式（借鉴TradingAgents-AShare）

TradingAgents-AShare全面支持暗色模式：

```css
/* Tailwind暗色模式配置 */
/* 所有组件同时定义 light 和 dark 样式 */
<div className="bg-white dark:bg-slate-900 text-slate-900 dark:text-slate-100">
<div className="bg-slate-100 dark:bg-slate-800 border-slate-200 dark:border-slate-700">
```

**颜色系统**:
- 买入: `red` (A股红色=涨)
- 卖出: `green` (A股绿色=跌)
- 中性: `blue`
- 风险等级: 高风险 `rose` / 中风险 `amber` / 低风险 `emerald`

## 10.8 Electron桌面应用（类QQ窗口）

前端打包为 Electron 桌面应用，打开就是一个独立窗口，和QQ一样。

### 为什么选Electron（决策订正）

> ⚠️ **订正说明**：原设计曾选 Tauri（看中其 5MB/30MB 的轻量优势）。经评估后改为 Electron，理由：(1) 与前端同栈 Node.js，无需引入 Rust；(2) 自带 Chromium 渲染一致性最佳，免除 WebView2/WKWebView/WebKitGTK 多平台差异测试；(3) 生态成熟、调试体验好（Chrome DevTools 全套）；(4) 仓库已有 `electron/` 现成代码可复用。轻量化非本项目硬指标（桌面机 200MB 内存可接受），开发效率优先。

| 维度 | Electron（选定） | Tauri（未选） |
|------|------------------|---------------|
| 后端语言 | Node.js（与前端同栈） | Rust（需额外学习） |
| 包体积 | ~150MB | ~5MB |
| 内存占用 | ~200MB | ~30MB |
| 启动速度 | 3-5秒 | 1-2秒 |
| 渲染一致性 | 极佳（自带 Chromium） | 一般（依赖系统 WebView，多平台有差异） |
| 安全性 | 中 | 高（Rust 内存安全） |
| 原生 API | 优秀 | 优秀 |
| 打包 | electron-builder | tauri build |
| 参考项目 | VS Code/Slack/Discord | Flock（多Agent桌面应用） |

### 架构

```
┌─────────────────────────────────────────┐
│           Electron Main Process (Node)  │
│  ┌─────────────────────────────────────┐ │
│  │  FastAPI Backend (Python)           │ │
│  │  - 通过 spawn 启动为子进程          │ │
│  │  - 监听 127.0.0.1:8765             │ │
│  └─────────────────────────────────────┘ │
│  ┌─────────────────────────────────────┐ │
│  │  BrowserWindow (React/Vite)         │ │
│  │  - 独立窗口，标题栏 + 菜单           │ │
│  │  - 加载 localhost:8765 或 dist/     │ │
│  │  - 系统托盘（Tray）+ 通知            │ │
│  └─────────────────────────────────────┘ │
└─────────────────────────────────────────┘
```

### Electron 配置（electron-builder）

```yaml
# electron/electron-builder.yml
appId: com.ashare-x.app
productName: AShare-X
directories:
  output: release
files:
  - main.ts        # 编译后的 main.js
  - preload.ts     # 编译后的 preload.js
  - package.json
win:
  target: nsis
  icon: build/icon.ico
mac:
  target: dmg
  icon: build/icon.icns
nsis:
  oneClick: false
  allowToChangeInstallationDirectory: true
```

### Electron 主进程（TypeScript）

```typescript
// electron/main.ts
import { app, BrowserWindow, Tray, Menu, Notification } from "electron";
import * as path from "path";
import { spawn, ChildProcess } from "child_process";

let mainWindow: BrowserWindow | null = null;
let tray: Tray | null = null;
let backendProcess: ChildProcess | null = null;
const BACKEND_PORT = 8765;

function startBackend() {
  // 启动 Python 后端为子进程
  backendProcess = spawn("python", ["main.py", "serve", "--port", String(BACKEND_PORT)], {
    cwd: path.resolve(__dirname, ".."),
    stdio: "pipe",
  });
  backendProcess.stdout?.on("data", (d) => console.log(`[backend] ${d}`));
  backendProcess.stderr?.on("data", (d) => console.error(`[backend] ${d}`));
}

function waitForBackend(url: string, retries = 30): Promise<void> {
  const http = require("http");
  return new Promise((resolve, reject) => {
    const tryConnect = (left: number) => {
      const req = http.get(url, () => resolve());
      req.on("error", () => (left > 0 ? setTimeout(() => tryConnect(left - 1), 500) : reject(new Error("backend timeout"))));
    };
    tryConnect(retries);
  });
}

async function createWindow() {
  startBackend();
  await waitForBackend(`http://127.0.0.1:${BACKEND_PORT}/health`);

  mainWindow = new BrowserWindow({
    width: 1400,
    height: 900,
    minWidth: 1000,
    minHeight: 700,
    title: "AShare-X",
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  // 生产环境加载打包后的前端，开发环境连 Vite dev server
  if (process.env.NODE_ENV === "development") {
    mainWindow.loadURL("http://localhost:5173");
  } else {
    mainWindow.loadURL(`http://127.0.0.1:${BACKEND_PORT}`);
  }

  mainWindow.on("close", (e) => {
    // 关闭时最小化到托盘而非退出
    e.preventDefault();
    mainWindow?.hide();
  });
}

function createTray() {
  tray = new Tray(path.join(__dirname, "build", "tray-icon.png"));
  const menu = Menu.buildFromTemplate([
    { label: "显示主窗口", click: () => mainWindow?.show() },
    { label: "每日分析", click: () => mainWindow?.webContents.send("action", "daily") },
    { type: "separator" },
    { label: "退出", click: () => { backendProcess?.kill(); app.quit(); } },
  ]);
  tray.setContextMenu(menu);
  tray.on("click", () => mainWindow?.show());
}

app.whenReady().then(() => {
  createWindow();
  createTray();
  new Notification({ title: "AShare-X", body: "后端已就绪" }).show();
});

app.on("before-quit", () => backendProcess?.kill());
```

### 预加载脚本（安全桥接）

```typescript
// electron/preload.ts
import { contextBridge, ipcRenderer } from "electron";

// 通过 contextBridge 暴露受限 API 给渲染进程，禁用 nodeIntegration
contextBridge.exposeInMainWorld("electronAPI", {
  onAction: (callback: (action: string) => void) =>
    ipcRenderer.on("action", (_e, action) => callback(action)),
  platform: process.platform,
});
```

### 用户体验

| 功能 | 实现 |
|------|------|
| 启动 | 双击桌面图标，显示启动画面，3秒后进入主窗口 |
| 系统托盘 | 最小化到托盘（`Tray`），右键菜单：显示/每日分析/退出 |
| 后台运行 | 关闭窗口后后端继续运行（子进程），托盘常驻 |
| 开机自启 | `app.setLoginItemSettings({ openAtLogin: true })` |
| 原生通知 | `new Notification({ title, body })` |
| 自动更新 | `electron-updater`（配合 GitHub Releases） |

### 与Tauri版的区别

> 决策已订正为 Electron（见本节开头订正说明）。关键差异：包体积 150MB vs 5MB、内存 200MB vs 30MB、Node.js vs Rust、渲染一致性 Electron 更优。本项目接受 Electron 的体积代价换取开发效率与渲染一致性。

## 10.9 性能优化

TradingAgents-AShare使用的性能优化：

| 技术 | 用途 | 实现 |
|------|------|------|
| `@tanstack/react-virtual` | 大列表虚拟滚动 | 报告历史、聊天记录 |
| `memo` + `useMemo` | React.memo避免重渲染 | Agent节点、辩论消息 |
| `react-markdown` | Markdown渲染 | 报告内容 |
| `lightweight-charts` | 高性能K线图 | 比ECharts轻量10x |
| `zustand/persist` | 选择性持久化 | 只持久化必要字段 |
| `debounce` | 搜索输入防抖 | 股票搜索框 |

## 10.10 与我们现有系统的对比

| 维度 | 现有系统 (Vue3) | TradingAgents-AShare | 我们的新设计 |
|------|-----------------|----------------------|-------------|
| 框架 | Vue 3 | React 18 | React 18 |
| 状态管理 | Pinia | Zustand | Zustand |
| 图表 | ECharts | Recharts + lightweight-charts | Recharts + lightweight-charts |
| Agent可视化 | 无 | ReactFlow | ReactFlow |
| 辩论可视化 | 无 | DebateDrawer + DebateTimeline | DebateDrawer + DebateTimeline |
| 实时推送 | WebSocket | SSE | SSE |
| 暗色模式 | 部分 | 全面 | 全面 |
| Markdown渲染 | 无 | react-markdown | react-markdown |

## 10.11 组件清单

| 组件 | 文件 | 功能 | 复杂度 |
|------|------|------|--------|
| Layout | `Layout.tsx` | 整体布局（Header+Sidebar+Main） | 低 |
| Header | `Header.tsx` | 顶部导航（搜索+主题+用户） | 低 |
| Sidebar | `Sidebar.tsx` | 侧边导航菜单 | 低 |
| AgentCollaboration | `AgentCollaboration.tsx` | Agent协作流程图（ReactFlow） | 高 |
| DebateDrawer | `DebateDrawer.tsx` | 辩论抽屉（右侧滑入） | 中 |
| DebateTimeline | `DebateTimeline.tsx` | 辩论时间线（按轮次分组） | 中 |
| DecisionCard | `DecisionCard.tsx` | 交易决策卡片 | 中 |
| RiskRadar | `RiskRadar.tsx` | 风险雷达 | 低 |
| KeyMetrics | `KeyMetrics.tsx` | 关键指标卡片 | 低 |
| KlinePanel | `KlinePanel.tsx` | K线图面板 | 中 |
| ReportViewer | `ReportViewer.tsx` | 报告查看器（Markdown） | 中 |
| TaskProgressBanner | `TaskProgressBanner.tsx` | 任务进度横幅 | 低 |
| ChatCopilotPanel | `ChatCopilotPanel.tsx` | 聊天助手面板 | 中 |
| TrackingBoardPanel | `TrackingBoardPanel.tsx` | 追踪面板 | 中 |

---

**依赖**: S3(架构), S6(工作流)
**被依赖**: 无
