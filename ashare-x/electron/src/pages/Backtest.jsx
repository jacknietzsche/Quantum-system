import React, { useEffect, useState } from 'react'
import api from '../api'

export default function Backtest() {
  const [codes, setCodes] = useState('600519')
  const [strategy, setStrategy] = useState('ma_cross')
  const [days, setDays] = useState(250)
  const [capital, setCapital] = useState(1000000)
  const [strategies, setStrategies] = useState([])
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    api.get('/backtest/strategies')
      .then((data) => setStrategies(data?.strategies || []))
      .catch(() => setStrategies([]))
  }, [])

  const runBacktest = async () => {
    setLoading(true)
    try {
      const data = await api.post('/backtest', {
        stock_codes: codes.split(/[,，\s]+/).filter(Boolean),
        strategy,
        days,
        initial_capital: capital,
      })
      setResult(data)
    } catch (err) {
      setResult({ error: err })
    } finally {
      setLoading(false)
    }
  }

  return (
    <div>
      <h2 className="text-xl font-bold mb-5">策略回测</h2>

      <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 mb-5">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          <div>
            <label className="block text-sm text-slate-400 mb-1">股票代码</label>
            <input
              className="w-full bg-slate-850 border border-slate-700 rounded-lg px-3 py-2 text-sm"
              value={codes}
              onChange={(e) => setCodes(e.target.value)}
              placeholder="多个代码用逗号分隔"
            />
          </div>
          <div>
            <label className="block text-sm text-slate-400 mb-1">策略</label>
            <select
              className="w-full bg-slate-850 border border-slate-700 rounded-lg px-3 py-2 text-sm"
              value={strategy}
              onChange={(e) => setStrategy(e.target.value)}
            >
              {strategies.map((s) => (
                <option key={s.name} value={s.name}>
                  {s.name}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-sm text-slate-400 mb-1">回测天数</label>
            <input
              type="number"
              className="w-full bg-slate-850 border border-slate-700 rounded-lg px-3 py-2 text-sm"
              value={days}
              onChange={(e) => setDays(Number(e.target.value))}
            />
          </div>
          <div>
            <label className="block text-sm text-slate-400 mb-1">初始资金</label>
            <input
              type="number"
              className="w-full bg-slate-850 border border-slate-700 rounded-lg px-3 py-2 text-sm"
              value={capital}
              onChange={(e) => setCapital(Number(e.target.value))}
            />
          </div>
        </div>
        <div className="mt-4">
          <button
            onClick={runBacktest}
            disabled={loading}
            className="px-4 py-2 bg-sky-600 hover:bg-sky-500 disabled:bg-slate-700 rounded-lg text-sm font-medium"
          >
            {loading ? '回测中...' : '📈 运行回测'}
          </button>
        </div>
      </div>

      {result?.error && (
        <div className="bg-rose-900/20 border border-rose-800 rounded-xl p-4 mb-5 text-sm text-rose-200">
          {result.error}
        </div>
      )}

      {result && !result.error && (
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-6">
          <h3 className="font-bold mb-4">回测结果</h3>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="p-3 bg-slate-850 rounded-lg">
              <div className="text-xs text-slate-400">总收益率</div>
              <div className="text-lg font-bold text-emerald-400">
                {result.total_return ? `${(result.total_return * 100).toFixed(2)}%` : '-'}
              </div>
            </div>
            <div className="p-3 bg-slate-850 rounded-lg">
              <div className="text-xs text-slate-400">年化收益</div>
              <div className="text-lg font-bold">
                {result.annualized_return ? `${(result.annualized_return * 100).toFixed(2)}%` : '-'}
              </div>
            </div>
            <div className="p-3 bg-slate-850 rounded-lg">
              <div className="text-xs text-slate-400">最大回撤</div>
              <div className="text-lg font-bold text-rose-400">
                {result.max_drawdown ? `${(result.max_drawdown * 100).toFixed(2)}%` : '-'}
              </div>
            </div>
            <div className="p-3 bg-slate-850 rounded-lg">
              <div className="text-xs text-slate-400">夏普比率</div>
              <div className="text-lg font-bold">{result.sharpe || '-'}</div>
            </div>
          </div>
          {result.trades && (
            <div className="mt-5">
              <h4 className="text-sm font-bold mb-2">交易记录</h4>
              <div className="text-sm text-slate-400">共 {result.trades.length} 笔交易</div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
