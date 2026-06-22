# AShare-X Electron 桌面应用蓝图

> 日期: 2026-05-09 | 轻量看板 + 三级漏斗选股 | React + Vite + FastAPI

---

## 一、项目结构

```
a-share-investment-system/
├── server.py                    # [新建] FastAPI 后端入口 (1个文件启动)
├── api/
│   └── routes/
│       ├── portfolio.py         # [保留增强] 持仓API
│       ├── screening.py         # [新建] 选股API
│       ├── analysis.py          # [新建] 单股深度分析API
│       ├── risk.py              # [新建] 风险监控API
│       └── signals.py           # [新建] 信号推送API
├── services/                    # [已有] 17个服务模块，不动
├── electron/                    # [新建] Electron前端目录
│   ├── package.json
│   ├── main.js                  # Electron主进程
│   ├── preload.js               # 安全桥接
│   ├── src/
│   │   ├── App.jsx              # 根组件(布局+路由)
│   │   ├── main.jsx             # Vite入口
│   │   ├── index.html
│   │   ├── pages/
│   │   │   ├── Dashboard.jsx    # 首页: 总览+风险状态
│   │   │   ├── Portfolio.jsx    # 持仓面板
│   │   │   ├── Screening.jsx    # 选股漏斗
│   │   │   └── StockDetail.jsx  # 单股详情(弹窗)
│   │   ├── components/
│   │   │   ├── KLineChart.jsx   # K线图(recharts)
│   │   │   ├── SignalBadge.jsx  # 信号标签(买/卖/持)
│   │   │   ├── RiskGauge.jsx    # 风险仪表盘
│   │   │   ├── FactorRadar.jsx  # 因子雷达图
│   │   │   └── FunnelChart.jsx  # 选股漏斗图
│   │   ├── hooks/
│   │   │   ├── useApi.js        # API调用hook
│   │   │   └── useRefresh.js    # 自动刷新hook(30s/5min)
│   │   └── styles/
│   │       └── index.css        # Tailwind CSS
│   ├── vite.config.js
│   └── electron-builder.yml     # 打包配置
├── scripts/
│   └── build.py                 # [新建] Python打包脚本
└── start.bat                    # [增强] 一键启动
```

---

## 二、FastAPI 后端 (server.py)

### 端口: `localhost:8765`

```python
# server.py — 单文件启动全部后端
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.routes import portfolio, screening, analysis, risk, signals

app = FastAPI(title="AShare-X API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"])

app.include_router(portfolio.router, prefix="/api/portfolio")
app.include_router(screening.router, prefix="/api/screening")
app.include_router(analysis.router, prefix="/api/analysis")
app.include_router(risk.router, prefix="/api/risk")
app.include_router(signals.router, prefix="/api/signals")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8765)
```

### API 接口列表

| 方法 | 路径 | 功能 | 响应(ms) |
|------|------|------|---------|
| GET | `/api/portfolio/holdings` | 持仓列表+盈亏 | <100 |
| GET | `/api/portfolio/nav` | 净值曲线 | <200 |
| GET | `/api/screening/run` | 触发选股(异步) | 立即返回 |
| GET | `/api/screening/status` | 选股进度 | <50 |
| GET | `/api/screening/results` | 选股结果Top10 | <50 |
| GET | `/api/analysis/{code}` | 单股深度分析 | 2000-5000 |
| GET | `/api/risk/status` | 风险+熔断状态 | <100 |
| GET | `/api/signals/today` | 今日所有信号 | <200 |
| GET | `/api/market/regime` | 市场环境感知 | <100 |
| POST | `/api/portfolio/order` | 提交订单确认 | <100 |

### 后端启动

```bash
pip install fastapi uvicorn
python server.py
# INFO: Uvicorn running on http://127.0.0.1:8765
```

---

## 三、React 前端组件树

```
App.jsx
├── Sidebar                    # 左侧导航
│   ├── 📊 总览
│   ├── 💼 持仓
│   ├── 🔍 选股
│   └── ⚙️ 设置
│
├── Dashboard.jsx              # 首页总览
│   ├── MarketBanner           # 市场环境横幅 (BULL/BEAR)
│   ├── AssetSummary           # 总资产+今日盈亏
│   ├── RiskStatus             # 风险熔断状态
│   └── TopSignals             # 今日重要信号 (前3条)
│
├── Portfolio.jsx              # 持仓面板
│   ├── PortfolioTable         # 持仓表格 (排序/筛选)
│   │   └── StockRow           # 每行: 代码/名称/成本/现价/盈亏/信号
│   └── PortfolioChart         # 净值曲线+基准对比
│
├── Screening.jsx              # 选股漏斗
│   ├── FunnelControl          # 筛选参数面板
│   ├── FunnelProgress         # 漏斗进度动画
│   ├── StockRanking           # 排名列表
│   │   └── StockCard          # 每张卡片: 排名/得分/核心逻辑
│   └── [点击] → StockDetail   # 弹出详情
│
└── StockDetail.jsx (Modal)    # 单股深度分析弹窗
    ├── Tab: 估值              # 4方法估值对比
    │   ├── ValuationBar       # 估值柱状图
    │   └── SafetyMargin       # 安全边际仪表
    ├── Tab: 技术              # 5策略技术集成
    │   ├── KLineChart         # K线+均线+布林带
    │   └── StrategySignals    # 各策略信号列表
    ├── Tab: 因子              # 29因子雷达图
    │   └── FactorRadar        # 雷达图(spider chart)
    └── Tab: 辩论              # 多空辩论摘要
        └── DebateClaims       # 声明列表+裁决
```

---

## 四、Electron 主进程 (main.js)

```javascript
// electron/main.js — 极简主进程
const { app, BrowserWindow } = require('electron')
const { spawn } = require('child_process')
const path = require('path')

let pythonProcess = null

function startPythonBackend() {
  // 启动 Python FastAPI 后端
  pythonProcess = spawn('python', ['server.py'], {
    cwd: path.join(__dirname, '..'),
  })
}

function createWindow() {
  const win = new BrowserWindow({
    width: 1200, height: 800,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
    },
  })
  
  // 开发模式: Vite dev server; 生产模式: 加载打包文件
  if (process.env.NODE_ENV === 'development') {
    win.loadURL('http://localhost:5173')  // Vite dev
  } else {
    win.loadFile('dist/index.html')
  }
}

app.whenReady().then(() => {
  startPythonBackend()
  setTimeout(createWindow, 2000)  // 等后端就绪
})

app.on('window-all-closed', () => {
  if (pythonProcess) pythonProcess.kill()
  app.quit()
})
```

---

## 五、关键依赖

### Python (server.py 运行需要的额外依赖)

```
fastapi>=0.100.0
uvicorn[standard]>=0.23.0
```

已有依赖不变 (pandas, numpy, jieba, rank-bm25, pyyaml, akshare等)

### Electron/React (electron/package.json)

```json
{
  "dependencies": {
    "react": "^18.3",
    "react-dom": "^18.3",
    "recharts": "^2.12",
    "lucide-react": "^0.400"
  },
  "devDependencies": {
    "electron": "^33.0",
    "vite": "^6.0",
    "@vitejs/plugin-react": "^4.0",
    "tailwindcss": "^3.4",
    "electron-builder": "^25.0"
  }
}
```

---

## 六、打包分发

### 开发模式启动

```bash
# 终端1: Python后端
python server.py

# 终端2: Electron前端
cd electron && npm install && npm run dev
```

### 一件启动 (start.bat)

```bat
@echo off
start "AShare-X Backend" python server.py
timeout /t 3 >nul
cd electron
npm run dev
```

### 生产打包

```bash
# 1. Python → 单文件exe
pip install pyinstaller
pyinstaller --onefile --name ashare-x-server server.py

# 2. Electron → 安装包
cd electron && npm run build
# 输出: dist/AShare-X-Setup-1.0.0.exe
```

---

## 七、实施路线图

### 阶段5.1: 后端API (1天)

| # | 任务 |
|---|------|
| 5.1.1 | 新建 `server.py` FastAPI入口 |
| 5.1.2 | 新建 `services/stock_screener.py` 三级漏斗 |
| 5.1.3 | 新建 `api/routes/portfolio.py` 持仓API |
| 5.1.4 | 新建 `api/routes/screening.py` 选股API |
| 5.1.5 | 新建 `api/routes/analysis.py` 分析API |
| 5.1.6 | 新建 `api/routes/risk.py` 风险API |
| 5.1.7 | 新建 `api/routes/signals.py` 信号API |
| 5.1.8 | 验证: `curl localhost:8765/api/market/regime` |

### 阶段5.2: Electron前端 (2天)

| # | 任务 |
|---|------|
| 5.2.1 | `npm create vite@latest electron -- --template react` |
| 5.2.2 | 安装依赖 (tailwind, recharts, lucide-react) |
| 5.2.3 | 编写 `main.js` + `preload.js` |
| 5.2.4 | 编写 `Dashboard.jsx` (总览页) |
| 5.2.5 | 编写 `Portfolio.jsx` (持仓页) |
| 5.2.6 | 编写 `Screening.jsx` (选股页) |
| 5.2.7 | 编写 `StockDetail.jsx` (详情弹窗) |
| 5.2.8 | 编写图表组件 (KLineChart/FactorRadar/RiskGauge) |
| 5.2.9 | `useApi.js` + `useRefresh.js` hooks |
| 5.2.10 | 端到端验证: 启动→加载持仓→选股→查看详情 |

### 阶段5.3: 打包+一键启动 (0.5天)

| # | 任务 |
|---|------|
| 5.3.1 | 增强 `start.bat` 一键启动 |
| 5.3.2 | `electron-builder.yml` 打包配置 |
| 5.3.3 | `build.py` Python打包脚本 |
| 5.3.4 | 打包测试: 生成安装包 |

**总工期**: 约3.5天

---

## 八、成功标准

1. `python server.py` 一键启动后端, 所有API <200ms (除深度分析)
2. `cd electron && npm run dev` 启动前端, 4个页面正常渲染
3. 选股漏斗: 5000只 → 推荐8只, 全过程 <30秒
4. 单股分析弹窗: 4个Tab (估值/技术/因子/辩论) 完整展示
5. `start.bat` 双击启动, 自动打开桌面窗口
