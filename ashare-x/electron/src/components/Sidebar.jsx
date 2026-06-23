import React from 'react'

const navItems = [
  { id: 'dashboard', icon: '📊', label: '控制台' },
  { id: 'analysis', icon: '🔍', label: '个股分析' },
  { id: 'screening', icon: '📈', label: '智能选股' },
  { id: 'backtest', icon: '🔬', label: '策略回测' },
  { id: 'tradingplan', icon: '📋', label: '交易计划' },
  { id: 'data', icon: '🗄️', label: '数据管理' },
  { id: 'reports', icon: '📋', label: '历史报告' },
  { id: 'settings', icon: '⚙️', label: '系统设置' },
]

export default function Sidebar({ active, onChange }) {
  return (
    <aside className="w-64 h-screen bg-slate-900 border-r border-slate-800 flex flex-col">
      <div className="p-5 flex items-center gap-3 border-b border-slate-800">
        <div className="text-2xl">📈</div>
        <div>
          <h1 className="font-bold text-lg">AShare-X</h1>
          <p className="text-xs text-slate-400">AI智能投研系统</p>
        </div>
      </div>
      <nav className="flex-1 overflow-y-auto py-4 scrollbar-thin">
        {navItems.map((item) => (
          <button
            key={item.id}
            onClick={() => onChange(item.id)}
            className={`w-full text-left px-5 py-3 flex items-center gap-3 transition-colors ${
              active === item.id
                ? 'bg-slate-800 text-sky-400 border-l-4 border-sky-400'
                : 'text-slate-300 hover:bg-slate-800 hover:text-slate-100'
            }`}
          >
            <span>{item.icon}</span>
            <span>{item.label}</span>
          </button>
        ))}
      </nav>
      <div className="p-4 text-xs text-slate-500 border-t border-slate-800">
        AShare-X v0.1.0
      </div>
    </aside>
  )
}
