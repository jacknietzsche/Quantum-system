import React, { useEffect, useState } from 'react'
import api from '../api'

export default function Data() {
  const [stats, setStats] = useState({})
  const [health, setHealth] = useState(null)
  const [code, setCode] = useState('600519')
  const [days, setDays] = useState(30)
  const [kline, setKline] = useState([])
  const [refreshing, setRefreshing] = useState(false)
  const [message, setMessage] = useState('')

  const fetchStats = async () => {
    try {
      const data = await api.get('/data/stats')
      setStats(data || {})
    } catch {
      setStats({})
    }
  }

  const fetchHealth = async () => {
    try {
      const data = await api.get('/data/health')
      setHealth(data || null)
    } catch {
      setHealth(null)
    }
  }

  useEffect(() => {
    fetchStats()
    fetchHealth()
  }, [])

  const queryKline = async () => {
    try {
      const data = await api.get(`/data/kline?code=${code}&days=${days}`)
      setKline(data?.kline || [])
    } catch {
      setKline([])
    }
  }

  const refreshData = async () => {
    setRefreshing(true)
    setMessage('')
    try {
      await api.post('/data/refresh')
      setMessage('数据刷新已触发')
      await fetchStats()
      await fetchHealth()
    } catch {
      setMessage('刷新失败')
    } finally {
      setRefreshing(false)
    }
  }

  return (
    <div>
      <h2 className="text-xl font-bold mb-5">数据管理</h2>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-5">
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-5">
          <div className="text-2xl font-bold text-sky-400">{stats.kline_count || 0}</div>
          <div className="text-sm text-slate-400 mt-1">K线记录数</div>
        </div>
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-5">
          <div className="text-2xl font-bold text-emerald-400">{stats.stock_count || 0}</div>
          <div className="text-sm text-slate-400 mt-1">股票数量</div>
        </div>
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-5">
          <div className="text-2xl font-bold text-amber-400">{stats.db_size || '0 MB'}</div>
          <div className="text-sm text-slate-400 mt-1">数据库大小</div>
        </div>
      </div>

      <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 mb-5">
        <h3 className="font-bold mb-4">数据源健康</h3>
        <div className="space-y-2">
          {health?.sources ? (
            health.sources.map((s) => (
              <div
                key={s.name}
                className="flex items-center justify-between text-sm p-3 bg-slate-850 rounded-lg"
              >
                <span>{s.name}</span>
                <span
                  className={`px-2 py-1 rounded text-xs ${
                    s.status === 'healthy'
                      ? 'bg-emerald-900/30 text-emerald-400'
                      : s.status === 'warning'
                        ? 'bg-amber-900/30 text-amber-400'
                        : 'bg-rose-900/30 text-rose-400'
                  }`}
                >
                  {s.status}
                </span>
              </div>
            ))
          ) : (
            <div className="text-slate-500 text-sm">暂无健康数据</div>
          )}
        </div>
        <button
          onClick={refreshData}
          disabled={refreshing}
          className="mt-4 px-4 py-2 bg-sky-600 hover:bg-sky-500 disabled:bg-slate-700 rounded-lg text-sm font-medium"
        >
          {refreshing ? '刷新中...' : '🔄 刷新数据'}
        </button>
        {message && <div className="mt-2 text-sm text-slate-400">{message}</div>}
      </div>

      <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 mb-5">
        <h3 className="font-bold mb-4">K线查询</h3>
        <div className="flex flex-wrap items-end gap-4">
          <div>
            <label className="block text-sm text-slate-400 mb-1">股票代码</label>
            <input
              className="bg-slate-850 border border-slate-700 rounded-lg px-3 py-2 text-sm w-40"
              value={code}
              onChange={(e) => setCode(e.target.value)}
            />
          </div>
          <div>
            <label className="block text-sm text-slate-400 mb-1">天数</label>
            <input
              type="number"
              className="bg-slate-850 border border-slate-700 rounded-lg px-3 py-2 text-sm w-28"
              value={days}
              onChange={(e) => setDays(Number(e.target.value))}
            />
          </div>
          <button
            onClick={queryKline}
            className="px-4 py-2 bg-slate-700 hover:bg-slate-600 rounded-lg text-sm font-medium"
          >
            查询
          </button>
        </div>

        {kline.length > 0 && (
          <div className="mt-4 overflow-x-auto">
            <table className="w-full text-sm text-left">
              <thead className="text-slate-400 border-b border-slate-800">
                <tr>
                  <th className="py-2">日期</th>
                  <th className="py-2">开盘</th>
                  <th className="py-2">收盘</th>
                  <th className="py-2">最高</th>
                  <th className="py-2">最低</th>
                  <th className="py-2">成交量</th>
                </tr>
              </thead>
              <tbody>
                {kline.slice(0, 10).map((row, i) => (
                  <tr key={i} className="border-t border-slate-800">
                    <td className="py-2">{row.date}</td>
                    <td className="py-2">{row.open}</td>
                    <td className="py-2">{row.close}</td>
                    <td className="py-2">{row.high}</td>
                    <td className="py-2">{row.low}</td>
                    <td className="py-2">{row.volume}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {kline.length > 10 && (
              <div className="text-xs text-slate-500 mt-2">仅显示前 10 条，共 {kline.length} 条</div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
