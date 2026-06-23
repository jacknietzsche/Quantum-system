import React, { useState } from 'react'
import Sidebar from './components/Sidebar'
import Dashboard from './pages/Dashboard'
import TradingPlan from './pages/TradingPlan'
import Settings from './pages/Settings'

const pageTitles = {
  dashboard: '控制台',
  analysis: '个股分析',
  screening: '智能选股',
  backtest: '策略回测',
  tradingplan: '交易计划',
  data: '数据管理',
  reports: '历史报告',
  settings: '系统设置',
}

function Placeholder({ title }) {
  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-8 text-center text-slate-400">
      <h2 className="text-xl font-bold mb-3">{title}</h2>
      <p className="text-sm">React 版本该页面尚未实现，请继续使用现有 static/index.html。</p>
    </div>
  )
}

export default function App() {
  const [page, setPage] = useState('dashboard')

  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar active={page} onChange={setPage} />
      <main className="flex-1 flex flex-col min-w-0 bg-slate-950">
        <header className="h-16 bg-slate-900 border-b border-slate-800 flex items-center px-6">
          <h2 className="text-lg font-bold">{pageTitles[page] || page}</h2>
        </header>
        <div className="flex-1 overflow-y-auto p-6 scrollbar-thin">
          {page === 'dashboard' && <Dashboard />}
          {page === 'tradingplan' && <TradingPlan />}
          {page === 'settings' && <Settings />}
          {['analysis', 'screening', 'backtest', 'data', 'reports'].includes(page) && (
            <Placeholder title={pageTitles[page]} />
          )}
        </div>
      </main>
    </div>
  )
}
