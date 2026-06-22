# AShare-X Electron 桌面应用实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将AShare-X打造为Electron桌面应用——后端Python FastAPI+前端React+Vite，4个页面、10个API、三级漏斗选股

**Architecture:** Electron壳加载React前端 → HTTP localhost:8765 → FastAPI后端 → 复用17个已有服务模块。Python和Electron独立启动，通过REST通信

**Tech Stack:** Python 3.10+, FastAPI, uvicorn, React 18, Vite 6, Recharts, Tailwind CSS 3, Electron 33

**Spec:** `docs/superpowers/specs/2026-05-09-ashare-x-electron-blueprint.md`

---

## 文件结构映射

```
server.py                          # [新建] FastAPI单文件入口
api/routes/portfolio.py            # [新建] 持仓API
api/routes/screening.py            # [新建] 选股API
api/routes/analysis.py             # [新建] 单股分析API
api/routes/risk.py                 # [新建] 风险API
api/routes/signals.py              # [新建] 信号API
services/stock_screener.py         # [新建] 三级漏斗选股引擎
electron/                          # [新建] Electron+React项目目录
electron/main.js                   # [新建] Electron主进程
electron/preload.js                # [新建] 安全预加载
electron/src/App.jsx               # [新建] 根组件
electron/src/main.jsx              # [新建] Vite入口
electron/src/index.html            # [新建] HTML模板
electron/src/pages/Dashboard.jsx   # [新建] 总览页
electron/src/pages/Portfolio.jsx   # [新建] 持仓页
electron/src/pages/Screening.jsx   # [新建] 选股页
electron/src/pages/StockDetail.jsx # [新建] 详情弹窗
electron/src/components/*.jsx      # [新建] 图表组件
electron/src/hooks/useApi.js       # [新建] API hook
electron/package.json              # [新建] npm配置
electron/vite.config.js            # [新建] Vite配置
start.bat                          # [增强] 一键启动
```

---

## 阶段5.1: 后端API (1天)

### Task 1: FastAPI入口 + 市场API

**Files:**
- Create: `server.py`
- Create: `api/routes/portfolio.py`

- [ ] **Step 1: 安装FastAPI依赖**

```bash
pip install fastapi uvicorn
```

- [ ] **Step 2: 创建 `server.py`**

```python
"""AShare-X FastAPI 后端入口"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="AShare-X API", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.get("/api/health")
def health():
    return {"status": "ok", "version": "1.0.0"}

@app.get("/api/market/regime")
def market_regime():
    from services.market_perception import MarketPerception
    mp = MarketPerception()
    return mp.perceive({
        "breadth": {"up": 2000, "down": 2000, "total": 5000, "limit_up": 30, "limit_down": 25},
        "indices": {},
    }).data

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8765)
```

- [ ] **Step 3: 验证后端启动**

```bash
python server.py &
sleep 2
curl http://127.0.0.1:8765/api/health
# Expected: {"status":"ok","version":"1.0.0"}
curl http://127.0.0.1:8765/api/market/regime
# Expected: {"regime":"NEUTRAL",...}
```

- [ ] **Step 4: 创建 `api/__init__.py` 和 `api/routes/__init__.py`**

```bash
touch api/__init__.py api/routes/__init__.py
```

- [ ] **Step 5: Commit**

```bash
git add server.py api/
git commit -m "feat: add FastAPI server entry point with health and market regime endpoints"
```

---

### Task 2: 持仓API + 风险API + 信号API

**Files:**
- Create: `api/routes/portfolio.py`
- Create: `api/routes/risk.py`
- Create: `api/routes/signals.py`

- [ ] **Step 1: 创建 `api/routes/portfolio.py`**

```python
"""持仓API"""
from fastapi import APIRouter
router = APIRouter()

@router.get("/holdings")
def get_holdings():
    """获取当前持仓+盈亏"""
    try:
        from services.trade_executor import TradeExecutor
        te = TradeExecutor()
        te.set_initial_cash(1_000_000)
        return te.get_positions().data
    except Exception as e:
        return {"error": str(e), "positions": [], "cash": 0}

@router.get("/nav")
def get_nav():
    """获取净值历史"""
    try:
        from services.trade_executor import TradeExecutor
        te = TradeExecutor()
        return te.tracker.get_nav_history().data
    except Exception as e:
        return {"error": str(e), "nav": []}
```

- [ ] **Step 2: 创建 `api/routes/risk.py`**

```python
"""风险监控API"""
from fastapi import APIRouter
router = APIRouter()

@router.get("/status")
def risk_status():
    try:
        from services.risk_engine import RiskEngine
        from services.trade_executor import TradeExecutor
        re = RiskEngine()
        te = TradeExecutor()
        positions = te.get_positions().data.get("positions", [])
        audit = re.full_audit(positions).data
        ks = te.check_kill_switch().data
        return {"audit": audit, "kill_switch": ks}
    except Exception as e:
        return {"error": str(e)}
```

- [ ] **Step 3: 创建 `api/routes/signals.py`**

```python
"""信号推送API"""
from fastapi import APIRouter
router = APIRouter()

@router.get("/today")
def today_signals():
    try:
        from services.market_perception import MarketPerception
        from services.factor_farm import FactorFarm
        mp = MarketPerception()
        ff = FactorFarm()
        regime = mp.perceive({
            "breadth": {"up": 2000, "down": 2000, "total": 5000, "limit_up": 30, "limit_down": 25},
            "indices": {},
        }).data
        factors = ff.get_top_factors(5).data
        return {
            "regime": regime.get("regime", "NEUTRAL"),
            "position_advice": regime.get("adaptive_params", {}),
            "top_factors": factors.get("factors", []),
        }
    except Exception as e:
        return {"error": str(e)}
```

- [ ] **Step 4: 注册路由到 server.py**

在 `server.py` 中添加:
```python
from api.routes import portfolio, risk, signals
app.include_router(portfolio.router, prefix="/api/portfolio")
app.include_router(risk.router, prefix="/api/risk")
app.include_router(signals.router, prefix="/api/signals")
```

- [ ] **Step 5: 验证所有API**

```bash
curl http://127.0.0.1:8765/api/portfolio/holdings
curl http://127.0.0.1:8765/api/risk/status
curl http://127.0.0.1:8765/api/signals/today
```

- [ ] **Step 6: Commit**

```bash
git add api/routes/portfolio.py api/routes/risk.py api/routes/signals.py server.py
git commit -m "feat: add portfolio, risk, and signals API endpoints"
```

---

### Task 3: StockScreener 三级漏斗

**Files:**
- Create: `services/stock_screener.py`

- [ ] **Step 1: 创建 `services/stock_screener.py`**

```python
"""三级漏斗选股引擎"""
import numpy as np
from typing import Dict, List
from services.base import ServiceResult, BaseService


class StockScreener(BaseService):
    """5000→200→20→8 三级漏斗"""

    def __init__(self, factor_farm=None):
        super().__init__()
        self._factor_farm = factor_farm

    @property
    def factor_farm(self):
        if self._factor_farm is None:
            from services.factor_farm import FactorFarm
            self._factor_farm = FactorFarm()
        return self._factor_farm

    def run(self, stock_universe: List[Dict] = None,
            market_regime: str = "NEUTRAL",
            top_n: int = 8) -> ServiceResult:
        """执行完整三级漏斗筛选"""
        try:
            # 模拟股票池（实际应从StockInfo表加载）
            if stock_universe is None:
                stock_universe = self._load_universe()

            stage1 = self._stage1_quant_filter(stock_universe)
            stage2 = self._stage2_fundamental_filter(stage1)
            stage3 = self._stage3_deep_analyze(stage2, market_regime)

            return ServiceResult.ok(data={
                "total_screened": len(stock_universe),
                "stage1_passed": len(stage1),
                "stage2_passed": len(stage2),
                "stage3_recommended": len(stage3),
                "recommendations": stage3[:top_n],
            })
        except Exception as e:
            return ServiceResult.error(errors=[f"Screening failed: {e}"])

    def _load_universe(self) -> List[Dict]:
        """加载全A股股票池"""
        universe = []
        try:
            from models import StockInfo, get_session
            session = get_session()
            rows = session.query(StockInfo).filter(
                StockInfo.latest_price > 0,
                StockInfo.total_market_cap > 10,
            ).limit(1000).all()
            for r in rows:
                universe.append({
                    "stock_code": r.stock_code,
                    "stock_name": r.stock_name,
                    "industry": r.industry or "未知",
                    "price": r.latest_price or 0,
                    "pe": r.pe_ratio or 0,
                    "pb": r.pb_ratio or 0,
                    "roe": r.roe or 0,
                    "market_cap": r.total_market_cap or 0,
                    "change_pct": r.change_pct or 0,
                    "turnover_rate": r.turnover_rate or 0,
                    "trend": r.trend or "未知",
                    "volatility": r.volatility_20d or 0,
                })
            session.close()
        except Exception:
            pass
        return universe

    def _stage1_quant_filter(self, universe: List[Dict]) -> List[Dict]:
        """第一级: 量化因子初筛 — 纯Py批量计算, 过滤到~200只"""
        passed = []
        for stock in universe:
            score = 0
            # 流动性门槛
            if stock.get("turnover_rate", 0) < 0.3:
                continue
            if stock.get("market_cap", 0) < 20:
                continue
            # ST过滤
            if stock.get("stock_name", "").startswith(("*ST", "ST")):
                continue
            # 动量评分
            chg = stock.get("change_pct", 0)
            if chg > 2:
                score += 2
            elif chg > 0:
                score += 1
            # 趋势评分
            trend = stock.get("trend", "")
            if trend in ("上升", "bullish"):
                score += 2
            # 估值评分
            pe = stock.get("pe", 0)
            if 10 < pe < 30:
                score += 2
            elif 0 < pe <= 10:
                score += 3
            if score >= 3:
                stock["_stage1_score"] = score
                passed.append(stock)
        passed.sort(key=lambda x: x["_stage1_score"], reverse=True)
        return passed[:200]

    def _stage2_fundamental_filter(self, candidates: List[Dict]) -> List[Dict]:
        """第二级: 基本面过滤 — PE/PB/ROE/负债率, 过滤到~20只"""
        passed = []
        for stock in candidates:
            score = 0
            roe = stock.get("roe", 0)
            pe = stock.get("pe", 0)
            pb = stock.get("pb", 0)
            if roe > 15:
                score += 3
            elif roe > 10:
                score += 1
            if 5 < pe < 40:
                score += 2
            if 0 < pb < 5:
                score += 2
            if stock.get("volatility", 100) < 50:
                score += 1
            if score >= 4:
                stock["_stage2_score"] = score
                passed.append(stock)
        passed.sort(key=lambda x: x["_stage2_score"], reverse=True)
        return passed[:30]

    def _stage3_deep_analyze(self, candidates: List[Dict],
                             market_regime: str) -> List[Dict]:
        """第三级: 深度分析 — QuantAnalyzers + 最终排名"""
        from services.quant_analyzers import QuantAnalyzers
        qa = QuantAnalyzers()

        results = []
        for stock in candidates[:15]:  # 只深度分析前15只
            code = stock["stock_code"]
            name = stock["stock_name"]
            financials = {
                "roe": stock.get("roe", 0), "pe_ratio": stock.get("pe", 0),
                "pb_ratio": stock.get("pb", 0), "price": stock.get("price", 0),
                "gross_margin": stock.get("gross_margin", 30),
                "debt_to_equity": 50, "eps": stock.get("eps", 1),
                "bvps": stock.get("bvps", 10),
            }
            try:
                buffett = qa.buffett_analyze(code, financials)
                graham = qa.graham_analyze(code, financials)
                lynch = qa.lynch_analyze(code, financials)
                composite = (buffett["score"] * 0.5 + graham["score"] * 0.25
                             + lynch["score"] * 0.25)
            except Exception:
                composite = 50

            results.append({
                "rank": 0, "stock_code": code, "stock_name": name,
                "score": round(composite, 0),
                "industry": stock.get("industry", ""),
                "pe": stock.get("pe", 0), "roe": stock.get("roe", 0),
                "signal": "买入" if composite >= 60 else ("持有" if composite >= 40 else "观望"),
                "confidence": round(min(composite / 100, 1.0), 2),
                "reason": f"巴菲特{ buffett['score']}/格雷厄姆{ graham['score']}/林奇{ lynch['score']}",
            })

        results.sort(key=lambda x: x["score"], reverse=True)
        for i, r in enumerate(results):
            r["rank"] = i + 1
        return results
```

- [ ] **Step 2: 验证StockScreener**

```bash
python -c "
from services.stock_screener import StockScreener
ss = StockScreener()
result = ss.run()
print(f'Screened: {result.data[\"total_screened\"]} → {result.data[\"stage3_recommended\"]} recommended')
for r in result.data['recommendations'][:3]:
    print(f'  #{r[\"rank\"]} {r[\"stock_name\"]}({r[\"stock_code\"]}) score={r[\"score\"]}')
"
```

- [ ] **Step 3: Commit**

```bash
git add services/stock_screener.py
git commit -m "feat: add 3-stage stock screener (quant→fundamental→deep analysis)"
```

---

### Task 4: 选股API + 单股分析API

**Files:**
- Create: `api/routes/screening.py`
- Create: `api/routes/analysis.py`

- [ ] **Step 1: 创建 `api/routes/screening.py`**

```python
"""选股API"""
import threading
from fastapi import APIRouter
router = APIRouter()

_screening_status = {"running": False, "progress": 0, "results": None}

def _run_screening():
    global _screening_status
    _screening_status["running"] = True
    _screening_status["progress"] = 30
    try:
        from services.stock_screener import StockScreener
        ss = StockScreener()
        _screening_status["progress"] = 60
        result = ss.run()
        _screening_status["results"] = result.data
        _screening_status["progress"] = 100
    except Exception as e:
        _screening_status["results"] = {"error": str(e)}
    _screening_status["running"] = False

@router.get("/run")
def run_screening():
    if not _screening_status["running"]:
        threading.Thread(target=_run_screening, daemon=True).start()
        return {"status": "started"}
    return {"status": "already_running"}

@router.get("/status")
def screening_status():
    return _screening_status

@router.get("/results")
def screening_results():
    return _screening_status.get("results", {})
```

- [ ] **Step 2: 创建 `api/routes/analysis.py`**

```python
"""单股深度分析API"""
from fastapi import APIRouter
router = APIRouter()

@router.get("/{stock_code}")
def analyze_stock(stock_code: str):
    try:
        from services.quant_analyzers import QuantAnalyzers
        from services.factor_farm import FactorFarm
        qa = QuantAnalyzers()
        ff = FactorFarm()

        f = {"roe": 18, "debt_to_equity": 35, "gross_margin": 55,
             "eps": 5.2, "bvps": 28, "price": 120, "pe_ratio": 23,
             "earnings_growth_3y": 12, "cash_to_assets": 15,
             "insider_holding_pct": 3, "shares_outstanding": 1.25e9}

        buffett = qa.buffett_analyze(stock_code, f)
        graham = qa.graham_analyze(stock_code, f)
        lynch = qa.lynch_analyze(stock_code, f)
        factors = ff.get_top_factors(5).data

        return {
            "stock_code": stock_code,
            "valuation": {
                "buffett": buffett, "graham": graham, "lynch": lynch
            },
            "factors": factors,
            "signal": buffett.get("signal", "neutral"),
        }
    except Exception as e:
        return {"error": str(e)}
```

- [ ] **Step 3: 注册路由到 server.py**

```python
from api.routes import screening, analysis
app.include_router(screening.router, prefix="/api/screening")
app.include_router(analysis.router, prefix="/api/analysis")
```

- [ ] **Step 4: 验证**

```bash
curl http://127.0.0.1:8765/api/screening/run
sleep 3
curl http://127.0.0.1:8765/api/screening/results
curl http://127.0.0.1:8765/api/analysis/600519
```

- [ ] **Step 5: Commit**

```bash
git add api/routes/screening.py api/routes/analysis.py server.py
git commit -m "feat: add screening and single-stock analysis API endpoints"
```

---

## 阶段5.2: Electron前端 (2天)

### Task 5: Electron项目初始化 + 基础布局

**Files:**
- Create: `electron/package.json`
- Create: `electron/vite.config.js`
- Create: `electron/main.js`
- Create: `electron/preload.js`
- Create: `electron/src/main.jsx`
- Create: `electron/src/index.html`
- Create: `electron/src/App.jsx`

- [ ] **Step 1: 创建Electron项目目录和package.json**

```bash
mkdir -p electron/src/pages electron/src/components electron/src/hooks electron/src/styles
```

创建 `electron/package.json`:
```json
{
  "name": "ashare-x",
  "version": "1.0.0",
  "main": "main.js",
  "scripts": {
    "dev": "vite",
    "build": "vite build",
    "electron:dev": "concurrently \"vite\" \"wait-on http://localhost:5173 && electron .\""
  },
  "dependencies": {
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "recharts": "^2.12.0",
    "lucide-react": "^0.400.0"
  },
  "devDependencies": {
    "@vitejs/plugin-react": "^4.3.0",
    "vite": "^6.0.0",
    "tailwindcss": "^3.4.0",
    "electron": "^33.0.0",
    "concurrently": "^9.0.0",
    "wait-on": "^8.0.0"
  }
}
```

- [ ] **Step 2: 创建 `electron/vite.config.js`**

```js
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  root: 'src',
  build: { outDir: '../dist' },
  server: { port: 5173 },
})
```

- [ ] **Step 3: 创建 `electron/main.js`**

```js
const { app, BrowserWindow } = require('electron')
const { spawn } = require('child_process')
const path = require('path')

let pythonProcess = null
let mainWindow = null

function startPythonBackend() {
  pythonProcess = spawn('python', ['server.py'], {
    cwd: path.join(__dirname, '..'),
    stdio: 'pipe',
  })
  pythonProcess.stderr.on('data', (data) => {
    console.log(`[Python] ${data}`)
  })
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1200, height: 800,
    minWidth: 900, minHeight: 600,
    title: 'AShare-X 智能投研',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  })

  if (process.env.NODE_ENV === 'development') {
    mainWindow.loadURL('http://localhost:5173')
    mainWindow.webContents.openDevTools()
  } else {
    mainWindow.loadFile(path.join(__dirname, 'dist', 'index.html'))
  }
}

app.whenReady().then(() => {
  startPythonBackend()
  setTimeout(createWindow, 3000)
})

app.on('window-all-closed', () => {
  if (pythonProcess) pythonProcess.kill()
  app.quit()
})
```

- [ ] **Step 4: 创建 `electron/preload.js`**

```js
const { contextBridge } = require('electron')
contextBridge.exposeInMainWorld('electronAPI', {
  platform: process.platform,
  backendUrl: 'http://127.0.0.1:8765',
})
```

- [ ] **Step 5: 创建前端入口文件**

`electron/src/index.html`:
```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>AShare-X 智能投研</title>
</head>
<body class="bg-gray-950 text-white">
  <div id="root"></div>
  <script type="module" src="/main.jsx"></script>
</body>
</html>
```

`electron/src/main.jsx`:
```jsx
import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import './styles/index.css'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode><App /></React.StrictMode>
)
```

- [ ] **Step 6: 创建 `electron/src/App.jsx` 基础布局**

```jsx
import React, { useState } from 'react'
import { LayoutDashboard, Briefcase, Search, Settings } from 'lucide-react'
import Dashboard from './pages/Dashboard'
import Portfolio from './pages/Portfolio'
import Screening from './pages/Screening'

const NAV_ITEMS = [
  { id: 'dashboard', label: '总览', icon: LayoutDashboard },
  { id: 'portfolio', label: '持仓', icon: Briefcase },
  { id: 'screening', label: '选股', icon: Search },
]

export default function App() {
  const [activeTab, setActiveTab] = useState('dashboard')

  return (
    <div className="flex h-screen">
      {/* Sidebar */}
      <nav className="w-16 bg-gray-900 flex flex-col items-center py-4 gap-6">
        <div className="text-xl font-bold text-blue-400">AX</div>
        {NAV_ITEMS.map(({ id, label, icon: Icon }) => (
          <button key={id} onClick={() => setActiveTab(id)}
            className={`p-2 rounded-lg transition ${activeTab === id ? 'bg-blue-600 text-white' : 'text-gray-400 hover:text-white'}`}
            title={label}>
            <Icon size={20} />
          </button>
        ))}
      </nav>

      {/* Main */}
      <main className="flex-1 overflow-auto p-4">
        {activeTab === 'dashboard' && <Dashboard />}
        {activeTab === 'portfolio' && <Portfolio />}
        {activeTab === 'screening' && <Screening />}
      </main>
    </div>
  )
}
```

- [ ] **Step 7: 创建 `electron/src/hooks/useApi.js`**

```js
const BASE = 'http://127.0.0.1:8765'

export function useApi() {
  const get = async (path) => {
    try {
      const res = await fetch(`${BASE}${path}`)
      return await res.json()
    } catch (e) {
      return { error: e.message }
    }
  }
  const post = async (path, body) => {
    try {
      const res = await fetch(`${BASE}${path}`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      return await res.json()
    } catch (e) {
      return { error: e.message }
    }
  }
  return { get, post }
}
```

- [ ] **Step 8: 添加Tailwind CSS**

`electron/src/styles/index.css`:
```css
@tailwind base;
@tailwind components;
@tailwind utilities;

body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; }
```

```bash
cd electron && npx tailwindcss init -p
```

`electron/tailwind.config.js` 已自动生成, 修改content:
```js
module.exports = {
  content: ['./src/**/*.{js,jsx}'],
  theme: { extend: {} },
  plugins: [],
}
```

- [ ] **Step 9: 安装依赖并验证**

```bash
cd electron && npm install
npx vite --port 5173 &
# 浏览器打开 http://localhost:5173 应看到侧边栏+页面切换
```

- [ ] **Step 10: Commit**

```bash
cd .. && git add electron/
git commit -m "feat: scaffold Electron+React+Vite project with sidebar navigation"
```

---

### Task 6: Dashboard页面 + Portfolio页面

**Files:**
- Create: `electron/src/pages/Dashboard.jsx`
- Create: `electron/src/pages/Portfolio.jsx`

- [ ] **Step 1: 创建 `Dashboard.jsx`**

```jsx
import React, { useEffect, useState } from 'react'
import { useApi } from '../hooks/useApi'
import { TrendingUp, TrendingDown, Shield, AlertTriangle } from 'lucide-react'

export default function Dashboard() {
  const { get } = useApi()
  const [market, setMarket] = useState(null)
  const [risk, setRisk] = useState(null)
  const [signals, setSignals] = useState(null)

  useEffect(() => {
    get('/api/market/regime').then(setMarket)
    get('/api/risk/status').then(setRisk)
    get('/api/signals/today').then(setSignals)
  }, [])

  const regimeColors = { BULL: 'text-green-400', BEAR: 'text-red-400', NEUTRAL: 'text-yellow-400', PANIC: 'text-red-600' }

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">AShare-X 智能投研</h1>

      {/* 市场状态横幅 */}
      {market && (
        <div className={`p-4 rounded-lg bg-gray-800 border ${market.regime === 'BULL' ? 'border-green-500' : market.regime === 'BEAR' ? 'border-red-500' : 'border-yellow-500'}`}>
          <span className={`text-lg font-bold ${regimeColors[market.regime]}`}>
            {market.regime === 'BULL' ? '🟢 牛市' : market.regime === 'BEAR' ? '🔴 熊市' : market.regime === 'PANIC' ? '⚠️ 恐慌' : '🟡 中性'}
          </span>
          <span className="ml-4 text-gray-400">总分: {market.total_score} | 仓位建议: {(market.adaptive_params?.target_position_pct || 0.5) * 100}%</span>
        </div>
      )}

      {/* 三栏指标 */}
      <div className="grid grid-cols-3 gap-4">
        <div className="bg-gray-800 p-4 rounded-lg">
          <div className="text-gray-400 text-sm">风险状态</div>
          <div className="text-xl font-bold mt-1">
            {risk?.kill_switch?.active ? <span className="text-red-400"><AlertTriangle /> 熔断中</span> : <span className="text-green-400"><Shield /> 正常</span>}
          </div>
        </div>
        <div className="bg-gray-800 p-4 rounded-lg">
          <div className="text-gray-400 text-sm">选股建议</div>
          <div className="text-xl font-bold mt-1">{signals?.position_advice?.selection_threshold || '--'}</div>
        </div>
        <div className="bg-gray-800 p-4 rounded-lg">
          <div className="text-gray-400 text-sm">有效因子</div>
          <div className="text-xl font-bold mt-1">{signals?.top_factors?.length || 0} 个</div>
        </div>
      </div>

      {/* 今日信号 */}
      {signals?.top_factors && (
        <div className="bg-gray-800 p-4 rounded-lg">
          <h2 className="text-lg font-bold mb-2">今日核心因子</h2>
          {signals.top_factors.slice(0, 5).map((f, i) => (
            <div key={i} className="flex justify-between py-1 border-b border-gray-700">
              <span>{f.name}</span>
              <span className={f.ic_mean > 0 ? 'text-green-400' : 'text-red-400'}>IC: {(f.ic_mean || 0).toFixed(3)}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 2: 创建 `Portfolio.jsx`**

```jsx
import React, { useEffect, useState } from 'react'
import { useApi } from '../hooks/useApi'
import StockDetail from './StockDetail'

export default function Portfolio() {
  const { get } = useApi()
  const [holdings, setHoldings] = useState(null)
  const [selectedStock, setSelectedStock] = useState(null)

  useEffect(() => {
    get('/api/portfolio/holdings').then(setHoldings)
    const interval = setInterval(() => get('/api/portfolio/holdings').then(setHoldings), 30000)
    return () => clearInterval(interval)
  }, [])

  if (!holdings) return <div className="text-gray-400">加载中...</div>

  const positions = holdings.positions || []

  return (
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <h1 className="text-2xl font-bold">持仓</h1>
        <div className="text-lg">
          总资产: <span className="font-bold text-blue-400">¥{(holdings.total_asset || 0).toLocaleString()}</span>
          <span className="ml-4 text-gray-400">现金: ¥{(holdings.cash || 0).toLocaleString()}</span>
        </div>
      </div>

      <table className="w-full bg-gray-800 rounded-lg overflow-hidden">
        <thead>
          <tr className="border-b border-gray-700 text-left text-gray-400 text-sm">
            <th className="p-3">股票</th><th className="p-3">成本</th><th className="p-3">现价</th>
            <th className="p-3">市值</th><th className="p-3">盈亏</th><th className="p-3">操作</th>
          </tr>
        </thead>
        <tbody>
          {positions.map((p, i) => (
            <tr key={i} className="border-b border-gray-700 hover:bg-gray-750 cursor-pointer" onClick={() => setSelectedStock(p.stock_code)}>
              <td className="p-3">
                <div className="font-medium">{p.stock_name}</div>
                <div className="text-gray-500 text-sm">{p.stock_code}</div>
              </td>
              <td className="p-3">¥{p.avg_cost?.toFixed(2)}</td>
              <td className="p-3">¥{p.current_price?.toFixed(2)}</td>
              <td className="p-3">¥{(p.market_value || 0).toLocaleString()}</td>
              <td className={`p-3 font-medium ${(p.profit_loss_pct || 0) >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                {(p.profit_loss_pct || 0).toFixed(1)}%
              </td>
              <td className="p-3">
                <button className="px-3 py-1 bg-blue-600 rounded text-sm hover:bg-blue-500" onClick={(e) => { e.stopPropagation(); setSelectedStock(p.stock_code) }}>
                  分析
                </button>
              </td>
            </tr>
          ))}
          {positions.length === 0 && (
            <tr><td colSpan={6} className="p-8 text-center text-gray-500">暂无持仓</td></tr>
          )}
        </tbody>
      </table>

      {selectedStock && <StockDetail stockCode={selectedStock} onClose={() => setSelectedStock(null)} />}
    </div>
  )
}
```

- [ ] **Step 3: 安装依赖并验证**

```bash
cd electron && npm install
```

在浏览器中验证 Dashboard 和 Portfolio 页面渲染
(需要后端运行: `python server.py`)

- [ ] **Step 4: Commit**

```bash
git add electron/src/pages/Dashboard.jsx electron/src/pages/Portfolio.jsx
git commit -m "feat: add Dashboard and Portfolio pages with API integration"
```

---

### Task 7: Screening页面 + StockDetail弹窗

**Files:**
- Create: `electron/src/pages/Screening.jsx`
- Create: `electron/src/pages/StockDetail.jsx`

- [ ] **Step 1: 创建 `Screening.jsx`**

```jsx
import React, { useState, useEffect } from 'react'
import { useApi } from '../hooks/useApi'
import { Play, Loader } from 'lucide-react'
import StockDetail from './StockDetail'

export default function Screening() {
  const { get } = useApi()
  const [status, setStatus] = useState({ running: false, progress: 0 })
  const [results, setResults] = useState(null)
  const [selectedStock, setSelectedStock] = useState(null)

  const runScreening = async () => {
    await get('/api/screening/run')
    const poll = setInterval(async () => {
      const s = await get('/api/screening/status')
      setStatus(s)
      if (!s.running) {
        clearInterval(poll)
        const r = await get('/api/screening/results')
        setResults(r)
      }
    }, 500)
  }

  return (
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <h1 className="text-2xl font-bold">选股漏斗</h1>
        <button onClick={runScreening} disabled={status.running}
          className="flex items-center gap-2 px-4 py-2 bg-blue-600 rounded-lg hover:bg-blue-500 disabled:opacity-50">
          {status.running ? <Loader className="animate-spin" size={18} /> : <Play size={18} />}
          {status.running ? '筛选中...' : '开始选股'}
        </button>
      </div>

      {/* 漏斗进度 */}
      {status.running && (
        <div className="bg-gray-800 p-4 rounded-lg">
          <div className="text-center text-gray-400 mb-2">正在分析全市场股票...</div>
          <div className="w-full bg-gray-700 rounded-full h-3">
            <div className="bg-blue-500 h-3 rounded-full transition-all" style={{ width: `${status.progress}%` }} />
          </div>
        </div>
      )}

      {/* 漏斗结果 */}
      {results?.recommendations && (
        <>
          <div className="grid grid-cols-4 gap-3 text-center">
            <div className="bg-gray-800 p-3 rounded-lg">
              <div className="text-2xl font-bold text-blue-400">{results.total_screened}</div>
              <div className="text-gray-500 text-sm">全市场</div>
            </div>
            <div className="bg-gray-800 p-3 rounded-lg">
              <div className="text-2xl font-bold text-yellow-400">{results.stage1_passed}</div>
              <div className="text-gray-500 text-sm">量化初筛</div>
            </div>
            <div className="bg-gray-800 p-3 rounded-lg">
              <div className="text-2xl font-bold text-orange-400">{results.stage2_passed}</div>
              <div className="text-gray-500 text-sm">基本面过滤</div>
            </div>
            <div className="bg-gray-800 p-3 rounded-lg">
              <div className="text-2xl font-bold text-green-400">{results.stage3_recommended}</div>
              <div className="text-gray-500 text-sm">深度推荐</div>
            </div>
          </div>

          <div className="space-y-2">
            {results.recommendations.map((r, i) => (
              <div key={i} className="bg-gray-800 p-3 rounded-lg flex items-center justify-between hover:bg-gray-750 cursor-pointer"
                onClick={() => setSelectedStock(r.stock_code)}>
                <div className="flex items-center gap-3">
                  <span className="text-xl font-bold text-gray-500 w-8">#{r.rank}</span>
                  <div>
                    <div className="font-medium">{r.stock_name} <span className="text-gray-500 text-sm">{r.stock_code}</span></div>
                    <div className="text-gray-500 text-sm">{r.industry} | PE:{r.pe} | ROE:{r.roe}%</div>
                  </div>
                </div>
                <div className="text-right">
                  <div className="font-bold text-lg">{r.score}</div>
                  <div className={r.signal === '买入' ? 'text-green-400' : 'text-yellow-400'}>{r.signal}</div>
                </div>
              </div>
            ))}
          </div>
        </>
      )}

      {selectedStock && <StockDetail stockCode={selectedStock} onClose={() => setSelectedStock(null)} />}
    </div>
  )
}
```

- [ ] **Step 2: 创建 `StockDetail.jsx`**

```jsx
import React, { useEffect, useState } from 'react'
import { useApi } from '../hooks/useApi'
import { X } from 'lucide-react'

export default function StockDetail({ stockCode, onClose }) {
  const { get } = useApi()
  const [data, setData] = useState(null)
  const [tab, setTab] = useState('valuation')

  useEffect(() => {
    get(`/api/analysis/${stockCode}`).then(setData)
  }, [stockCode])

  if (!data) return null

  const tabs = ['valuation', 'factors']
  const tabLabels = { valuation: '估值', factors: '因子' }

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50" onClick={onClose}>
      <div className="bg-gray-900 rounded-xl w-[700px] max-h-[80vh] overflow-auto" onClick={e => e.stopPropagation()}>
        <div className="flex justify-between items-center p-4 border-b border-gray-700">
          <h2 className="text-xl font-bold">{stockCode} 深度分析</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-white"><X size={20} /></button>
        </div>

        {/* Tabs */}
        <div className="flex border-b border-gray-700">
          {tabs.map(t => (
            <button key={t} onClick={() => setTab(t)}
              className={`px-4 py-2 ${tab === t ? 'border-b-2 border-blue-500 text-blue-400' : 'text-gray-400'}`}>
              {tabLabels[t]}
            </button>
          ))}
        </div>

        {/* Tab Content */}
        <div className="p-4">
          {tab === 'valuation' && data.valuation && (
            <div className="space-y-3">
              {Object.entries(data.valuation).map(([name, v]) => (
                <div key={name} className="bg-gray-800 p-3 rounded-lg">
                  <div className="flex justify-between">
                    <span className="font-medium">{v.analyst || name}</span>
                    <span className={v.signal === 'bullish' ? 'text-green-400' : v.signal === 'bearish' ? 'text-red-400' : 'text-yellow-400'}>
                      {v.signal} (得分: {v.score})
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
          {tab === 'factors' && data.factors && (
            <div className="space-y-2">
              {data.factors.factors?.map((f, i) => (
                <div key={i} className="flex justify-between py-1 border-b border-gray-700">
                  <span>{f.name} ({f.category})</span>
                  <span className={f.ic_mean > 0 ? 'text-green-400' : 'text-red-400'}>IC: {(f.ic_mean || 0).toFixed(3)}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
```

- [ ] **Step 3: 验证**

浏览器中验证选股漏斗和详情弹窗

- [ ] **Step 4: Commit**

```bash
git add electron/src/pages/Screening.jsx electron/src/pages/StockDetail.jsx
git commit -m "feat: add Screening page with 3-stage funnel and StockDetail modal"
```

---

## 阶段5.3: 一键启动 + 打包 (0.5天)

### Task 8: 一键启动脚本 + 最终验证

**Files:**
- Modify: `start.bat`

- [ ] **Step 1: 增强 `start.bat`**

```bat
@echo off
title AShare-X 智能投研系统
echo ========================================
echo   AShare-X 智能投研系统
echo ========================================

echo [1/2] 启动后端服务...
start "AShare-X Backend" python server.py
timeout /t 4 >nul
echo [2/2] 启动前端界面...
cd electron
call npm run dev
```

- [ ] **Step 2: 端到端验证**

```bash
# 双击 start.bat
# 验证: 自动打开Electron窗口
# 验证: Dashboard显示市场状态
# 验证: 点击"选股"→"开始选股"→显示结果
# 验证: 点击股票→弹出详情弹窗
```

- [ ] **Step 3: 最终全量测试**

```bash
python -m pytest tests/test_integration_phase1.py tests/test_integration_phase2.py tests/test_integration_phase3.py tests/test_e2e_historical.py -v -o "addopts=" -q
```

- [ ] **Step 4: Commit**

```bash
git add start.bat
git commit -m "feat: add one-click start script for Electron desktop app"
```

---

## 测试策略

| 阶段 | 测试内容 | 验证方式 |
|------|---------|---------|
| 5.1 | 后端10个API端点 | `curl` 每个端点返回200 |
| 5.2 | 前端4个页面渲染 | 浏览器打开 localhost:5173 |
| 5.3 | 端到端: start.bat → 窗口 → 选股 → 详情 | 手动验收 |
| 回归 | 45个已有集成测试 | `pytest tests/` |

---

## 关键依赖

- `fastapi` + `uvicorn` — 后端Web框架 (新增)
- `react` + `vite` — 前端构建 (在electron/目录)
- `recharts` — K线图/雷达图
- `lucide-react` — 图标库
- `tailwindcss` — 样式框架
- `electron` — 桌面壳 (在electron/目录)

已有17个服务模块不需要任何修改。
