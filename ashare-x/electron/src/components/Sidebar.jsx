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

export default function Sidebar({ active, onChange, open, onToggle }) {
  return (
    <>
      {/* 移动端遮罩 */}
      {open && (
        <div
          className="fixed inset-0 bg-black/50 z-40 lg:hidden"
          onClick={onToggle}
        />
      )}

      <aside
        className={`fixed lg:static inset-y-0 left-0 z-50 w-64 h-screen bg-slate-900 border-r border-slate-800 flex flex-col transition-transform duration-200 ease-in-out ${
          open ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'
        }`}
        style={{ transform: open ? 'translateX(0)' : undefined }}
      >
        <div className="p-5 flex items-center justify-between border-b border-slate-800">
          <div className="flex items-center gap-3">
            <div className="text-2xl">📈</div>
            <div>
              <h1 className="font-bold text-lg">AShare-X</h1>
              <p className="text-xs text-slate-400">AI智能投研系统</p>
            </div>
          </div>
          <button
            onClick={onToggle}
            className="lg:hidden text-slate-400 hover:text-slate-100 text-xl leading-none"
            aria-label="关闭菜单"
          >
            ✕
          </button>
        </div>
        <nav className="flex-1 overflow-y-auto py-4 scrollbar-thin">
          {navItems.map((item) => (
            <button
              key={item.id}
              onClick={() => {
                onChange(item.id)
                if (window.innerWidth < 1024) onToggle()
              }}
              className={`nav-item w-full text-left px-5 py-3 flex items-center gap-3 transition-colors ${
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
    </>
  )
}
