import React, { useEffect, useState } from 'react'
import api from '../api'

export default function Reports() {
  const [reports, setReports] = useState([])
  const [filter, setFilter] = useState('')
  const [selected, setSelected] = useState(null)

  const fetchReports = async () => {
    try {
      const data = await api.get('/reports?limit=50')
      setReports(data?.reports || [])
    } catch {
      setReports([])
    }
  }

  useEffect(() => {
    fetchReports()
  }, [])

  const filtered = filter
    ? reports.filter((r) => r.ticker?.includes(filter))
    : reports

  return (
    <div>
      <h2 className="text-xl font-bold mb-5">历史报告</h2>

      <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 mb-5">
        <div className="flex items-center gap-4">
          <input
            className="bg-slate-850 border border-slate-700 rounded-lg px-3 py-2 text-sm w-48"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder="按股票代码过滤"
          />
          <button
            onClick={fetchReports}
            className="px-4 py-2 bg-slate-700 hover:bg-slate-600 rounded-lg text-sm font-medium"
          >
            刷新
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        <div className="lg:col-span-1 bg-slate-900 border border-slate-800 rounded-xl overflow-hidden max-h-[600px] overflow-y-auto">
          <table className="w-full text-sm text-left">
            <thead className="bg-slate-850 text-slate-400 sticky top-0">
              <tr>
                <th className="px-4 py-3">代码</th>
                <th className="px-4 py-3">决策</th>
                <th className="px-4 py-3">时间</th>
              </tr>
            </thead>
            <tbody>
              {filtered.length === 0 && (
                <tr>
                  <td colSpan={3} className="px-4 py-6 text-center text-slate-500">
                    暂无报告
                  </td>
                </tr>
              )}
              {filtered.map((r) => (
                <tr
                  key={r.id}
                  onClick={() => setSelected(r)}
                  className={`border-t border-slate-800 cursor-pointer hover:bg-slate-850 ${
                    selected?.id === r.id ? 'bg-slate-850' : ''
                  }`}
                >
                  <td className="px-4 py-3 font-mono">{r.ticker}</td>
                  <td className="px-4 py-3">
                    <span
                      className={`px-2 py-1 rounded text-xs ${
                        r.action?.toUpperCase().includes('BUY')
                          ? 'bg-emerald-900/30 text-emerald-400'
                          : r.action?.toUpperCase().includes('SELL')
                            ? 'bg-rose-900/30 text-rose-400'
                            : 'bg-slate-800 text-slate-300'
                      }`}
                    >
                      {r.action}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-slate-400">{r.created_at || '-'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="lg:col-span-2 bg-slate-900 border border-slate-800 rounded-xl p-6">
          {selected ? (
            <div>
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-lg font-bold">{selected.ticker} 分析报告</h3>
                <span className="text-sm text-slate-400">{selected.created_at}</span>
              </div>
              <div className="grid grid-cols-3 gap-4 mb-4">
                <div className="p-3 bg-slate-850 rounded-lg">
                  <div className="text-xs text-slate-400">决策</div>
                  <div className="text-lg font-bold text-sky-400">{selected.action}</div>
                </div>
                <div className="p-3 bg-slate-850 rounded-lg">
                  <div className="text-xs text-slate-400">置信度</div>
                  <div className="text-lg font-bold">{selected.confidence}%</div>
                </div>
                <div className="p-3 bg-slate-850 rounded-lg">
                  <div className="text-xs text-slate-400">仓位</div>
                  <div className="text-lg font-bold">{selected.position_pct}%</div>
                </div>
              </div>
              {selected.thesis && (
                <div className="text-sm text-slate-300 leading-relaxed whitespace-pre-line">
                  {selected.thesis}
                </div>
              )}
            </div>
          ) : (
            <div className="h-full flex items-center justify-center text-slate-500">
              选择左侧报告查看详情
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
