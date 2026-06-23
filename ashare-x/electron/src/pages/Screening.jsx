import React, { useState } from 'react'
import api from '../api'

const STYLES = [
  { key: 'balanced', label: '均衡' },
  { key: 'value', label: '价值' },
  { key: 'growth', label: '成长' },
  { key: 'momentum', label: '动量' },
  { key: 'quality', label: '质量' },
]

export default function Screening() {
  const [style, setStyle] = useState('balanced')
  const [stocks, setStocks] = useState([])
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState('')

  const runScreening = async () => {
    setLoading(true)
    setMessage('')
    try {
      const data = await api.get(`/screening?style=${style}&limit=20`)
      setStocks(data?.stocks || [])
      if (data?.message) setMessage(data.message)
    } catch {
      setMessage('选股请求失败')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div>
      <h2 className="text-xl font-bold mb-5">智能选股</h2>

      <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 mb-5">
        <div className="flex flex-wrap items-end gap-4">
          <div>
            <label className="block text-sm text-slate-400 mb-1">选股风格</label>
            <select
              className="bg-slate-850 border border-slate-700 rounded-lg px-3 py-2 text-sm w-40"
              value={style}
              onChange={(e) => setStyle(e.target.value)}
            >
              {STYLES.map((s) => (
                <option key={s.key} value={s.key}>
                  {s.label}
                </option>
              ))}
            </select>
          </div>
          <button
            onClick={runScreening}
            disabled={loading}
            className="px-4 py-2 bg-sky-600 hover:bg-sky-500 disabled:bg-slate-700 rounded-lg text-sm font-medium"
          >
            {loading ? '计算中...' : '🔍 运行选股'}
          </button>
        </div>
      </div>

      {message && (
        <div className="bg-amber-900/20 border border-amber-800 rounded-xl p-4 mb-5 text-sm text-amber-200">
          {message}
        </div>
      )}

      {stocks.length > 0 && (
        <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden">
          <table className="w-full text-sm text-left">
            <thead className="bg-slate-850 text-slate-400">
              <tr>
                <th className="px-4 py-3">排名</th>
                <th className="px-4 py-3">代码</th>
                <th className="px-4 py-3">名称</th>
                <th className="px-4 py-3">综合得分</th>
                <th className="px-4 py-3">价值</th>
                <th className="px-4 py-3">成长</th>
                <th className="px-4 py-3">动量</th>
                <th className="px-4 py-3">质量</th>
              </tr>
            </thead>
            <tbody>
              {stocks.map((s) => (
                <tr key={s.stock_code} className="border-t border-slate-800 hover:bg-slate-850/50">
                  <td className="px-4 py-3">{s.rank}</td>
                  <td className="px-4 py-3 font-mono">{s.stock_code}</td>
                  <td className="px-4 py-3">{s.stock_name}</td>
                  <td className="px-4 py-3 font-bold text-sky-400">{s.score}</td>
                  <td className="px-4 py-3">{s.factors?.value}</td>
                  <td className="px-4 py-3">{s.factors?.growth}</td>
                  <td className="px-4 py-3">{s.factors?.momentum}</td>
                  <td className="px-4 py-3">{s.factors?.quality}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
