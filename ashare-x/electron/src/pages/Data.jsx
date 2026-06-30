import React, { useEffect, useRef, useState } from 'react'
import api from '../api'
import ErrorAlert from '../components/ErrorAlert'
import KLineChart from '../components/KLineChart'
import { validateStockCode, validatePositiveNumber } from '../utils/validation'

export default function Data() {
  const [stats, setStats] = useState({})
  const [health, setHealth] = useState(null)
  const [code, setCode] = useState('600519')
  const [codeError, setCodeError] = useState('')
  const [days, setDays] = useState('30')
  const [daysError, setDaysError] = useState('')
  const [kline, setKline] = useState([])
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const intervalRef = useRef(null)

  // Cleanup interval on unmount
  useEffect(() => {
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current)
    }
  }, [])

  const fetchStats = async () => {
    try {
      const data = await api.get('/data/stats')
      setStats(data || {})
    } catch (err) {
      setError(typeof err === 'string' ? err : '获取数据统计失败')
    }
  }

  const fetchHealth = async () => {
    try {
      const data = await api.get('/data/health')
      setHealth(data || null)
    } catch (err) {
      setError(typeof err === 'string' ? err : '获取数据源健康失败')
    }
  }

  useEffect(() => {
    fetchStats()
    fetchHealth()
  }, [])

  const queryKline = async () => {
    const codeErr = validateStockCode(code)
    const daysErr = validatePositiveNumber(days, '天数')
    setCodeError(codeErr)
    setDaysError(daysErr)
    if (codeErr || daysErr) return

    setError('')
    try {
      const data = await api.get(`/data/kline?code=${code.trim()}&days=${days}`)
      setKline(data?.kline || [])
      if (!data?.kline?.length) {
        setMessage('未查询到 K 线数据')
      } else {
        setMessage('')
      }
    } catch (err) {
      setKline([])
      setError(typeof err === 'string' ? err : '查询 K 线失败')
    }
  }

  const refreshData = async () => {
    setRefreshing(true)
    setError('')
    setMessage('')
    try {
      const job = await api.post('/data/refresh')
      if (job?.job_id) {
        setMessage('数据刷新已触发，后台执行中...')
        const interval = setInterval(async () => {
          try {
            const status = await api.get(`/data/refresh/${job.job_id}`)
            if (status?.status !== 'running') {
              clearInterval(interval)
              intervalRef.current = null
              setRefreshing(false)
              if (status?.status === 'failed') {
                setError(status?.error || '刷新失败')
              } else {
                setMessage('数据刷新完成')
                await fetchStats()
                await fetchHealth()
              }
            }
          } catch {
            clearInterval(interval)
            intervalRef.current = null
            setRefreshing(false)
            setError('查询刷新状态失败')
          }
        }, 2000)
        intervalRef.current = interval
      } else {
        setRefreshing(false)
        setError('触发刷新失败')
      }
    } catch (err) {
      setRefreshing(false)
      setError(typeof err === 'string' ? err : '刷新失败')
    }
  }

  return (
    <div>
      <h2 className="text-xl font-bold mb-5">数据管理</h2>

      <ErrorAlert message={error} onClose={() => setError('')} />

      {message && (
        <div className="bg-sky-900/20 border border-sky-800 rounded-xl p-4 mb-5 text-sm text-sky-200">
          {message}
        </div>
      )}

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
      </div>

      <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 mb-5">
        <h3 className="font-bold mb-4">K线查询</h3>
        <div className="flex flex-wrap items-end gap-4">
          <div>
            <label className="block text-sm text-slate-400 mb-1">股票代码</label>
            <input
              className={`bg-slate-850 border rounded-lg px-3 py-2 text-sm w-40 ${
                codeError ? 'border-rose-500' : 'border-slate-700'
              }`}
              value={code}
              onChange={(e) => {
                setCode(e.target.value)
                setCodeError('')
              }}
            />
            {codeError && <div className="text-xs text-rose-400 mt-1">{codeError}</div>}
          </div>
          <div>
            <label className="block text-sm text-slate-400 mb-1">天数</label>
            <input
              type="text"
              inputMode="numeric"
              pattern="[0-9]*"
              className={`bg-slate-850 border rounded-lg px-3 py-2 text-sm w-28 ${
                daysError ? 'border-rose-500' : 'border-slate-700'
              }`}
              value={days}
              autoComplete="off"
              onFocus={(e) => e.target.select()}
              onClick={(e) => e.target.select()}
              onKeyDown={(e) => e.target.select()}
              onChange={(e) => {
                const raw = e.target.value.replace(/[^0-9]/g, '').slice(0, 4)
                setDays(raw)
                setDaysError('')
              }}
              onBlur={(e) => {
                const num = Number(e.target.value)
                if (!num || num <= 0) setDays('30')
              }}
            />
            {daysError && <div className="text-xs text-rose-400 mt-1">{daysError}</div>}
          </div>
          <button
            onClick={queryKline}
            className="px-4 py-2 bg-slate-700 hover:bg-slate-600 rounded-lg text-sm font-medium"
          >
            查询
          </button>
        </div>

        {kline.length > 0 && (
          <div className="mt-4 bg-slate-850 rounded-lg p-2">
            <KLineChart data={kline} height={360} />
          </div>
        )}

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
