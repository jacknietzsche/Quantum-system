import React, { useState } from 'react'
import Sidebar from './components/Sidebar'
import Analysis from './pages/Analysis'
import Backtest from './pages/Backtest'
import Dashboard from './pages/Dashboard'
import Data from './pages/Data'
import Reports from './pages/Reports'
import Screening from './pages/Screening'
import Settings from './pages/Settings'
import TradingPlan from './pages/TradingPlan'

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
          {page === 'analysis' && <Analysis />}
          {page === 'screening' && <Screening />}
          {page === 'backtest' && <Backtest />}
          {page === 'tradingplan' && <TradingPlan />}
          {page === 'data' && <Data />}
          {page === 'reports' && <Reports />}
          {page === 'settings' && <Settings />}
        </div>
      </main>
    </div>
  )
}
