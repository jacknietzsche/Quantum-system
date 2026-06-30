import React, { useEffect, useRef, useState } from 'react'
import api from '../api'
import ErrorAlert from '../components/ErrorAlert'

export default function TradingPlan() {
  const [plan, setPlan] = useState(null)
  const [history, setHistory] = useState([])
  const [loading, setLoading] = useState(true)
  const [running, setRunning] = useState(false)
  const [rebalancing, setRebalancing] = useState(false)
  const [sending, setSending] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const intervalRef = useRef(null)

  useEffect(() => {
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current)
    }
  }, [])

  const fetchToday = async () => {
    try {
      const data = await api.get('/trading-plan/today')
      if (data?.ok) setPlan(data.plan)
      else setPlan(null)
    } catch {
      setPlan(null)
    }
  }

  const fetchHistory = async () => {
    try {
      const data = await api.get('/trading-plan/history?limit=10')
      if (data?.ok) setHistory(data.history || [])
    } catch {
      setHistory([])
    }
  }

  useEffect(() => {
    setLoading(true)
    Promise.all([fetchToday(), fetchHistory()])
      .catch(() => setError('初始化数据失败'))
      .finally(() => setLoading(false))
  }, [])

  const runDaily = async () => {
    setRunning(true)
    setError('')
    setMessage('')
    try {
      const job = await api.post('/trading-plan/run', { fast_mode: true })
      if (job?.job_id) {
        const interval = setInterval(async () => {
          try {
            const status = await api.get(`/trading-plan/run/${job.job_id}`)
            if (status?.status !== 'running') {
              clearInterval(interval)
              intervalRef.current = null
              setRunning(false)
              if (status?.result?.error) {
                setError(status.result.error)
              } else {
                setMessage('每日分析已完成')
                await fetchToday()
                await fetchHistory()
              }
            }
          } catch {
            clearInterval(interval)
            setRunning(false)
            setError('查询任务状态失败')
          }
        }, 2000)
        intervalRef.current = interval
      } else {
        setRunning(false)
        setError('启动分析失败')
      }
    } catch {
      setRunning(false)
      setError('启动每日分析失败')
    }
  }

  const rebalance = async () => {
    setRebalancing(true)
    setError('')
    setMessage('')
    try {
      const data = await api.post('/portfolio/rebalance')
      if (data?.error) {
        setError(data.error)
      } else {
        setMessage(`再平衡：${data?.message || '完成'}`)
      }
    } catch {
      setError('再平衡请求失败')
    } finally {
      setRebalancing(false)
    }
  }

  const sendEmail = async () => {
    setSending(true)
    setError('')
    setMessage('')
    try {
      const data = await api.post('/trading-plan/send-email', {})
      if (data?.ok) {
        setMessage('交易计划邮件已发送')
      } else {
        setError(data?.error || '发送失败')
      }
    } catch {
      setError('发送邮件失败')
    } finally {
      setSending(false)
    }
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-5">
        <h2 className="text-xl font-bold">每日交易计划</h2>
        <div className="flex flex-wrap gap-2">
          <button
            onClick={runDaily}
            disabled={running}
            className="px-4 py-2 bg-sky-600 hover:bg-sky-500 disabled:bg-slate-700 rounded-lg text-sm font-medium"
          >
            {running ? '运行中...' : '⚡ 运行每日分析'}
          </button>
          <button
            onClick={rebalance}
            disabled={rebalancing}
            className="px-4 py-2 bg-slate-700 hover:bg-slate-600 disabled:bg-slate-800 rounded-lg text-sm font-medium"
          >
            {rebalancing ? '计算中...' : '⚖️ 再平衡'}
          </button>
          <button
            onClick={sendEmail}
            disabled={sending}
            className="px-4 py-2 bg-slate-700 hover:bg-slate-600 disabled:bg-slate-800 rounded-lg text-sm font-medium"
          >
            {sending ? '发送中...' : '📧 发送到 QQ 邮箱'}
          </button>
        </div>
      </div>

      <ErrorAlert message={error} onClose={() => setError('')} />

      {message && (
        <div className="bg-emerald-900/20 border border-emerald-800 rounded-xl p-4 mb-5 text-sm text-emerald-200">
          {message}
        </div>
      )}

      {running && (
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 mb-5 text-sm text-slate-300">
          每日分析正在后台运行，完成后会自动刷新...
        </div>
      )}

      {loading ? (
        <div className="text-slate-400">加载中...</div>
      ) : plan ? (
        <div className="space-y-4">
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-5">
            <div className="flex items-center justify-between">
              <span className="text-slate-400">日期</span>
              <span className="font-medium">{plan.date}</span>
            </div>
            <div className="flex items-center justify-between mt-3">
              <span className="text-slate-400">市场状态</span>
              <span className="px-2 py-1 rounded bg-slate-800 text-sky-400 text-sm">
                {plan.market_state}
              </span>
            </div>
            <p className="mt-4 text-slate-300 text-sm leading-relaxed">{plan.summary}</p>
          </div>

          <div className="bg-slate-900 border border-slate-800 rounded-xl p-5">
            <h3 className="font-bold mb-3">操作建议</h3>
            {(plan.actions || []).length > 0 ? (
              <div className="space-y-2">
                {plan.actions.map((a, i) => (
                  <div key={i} className="p-3 bg-slate-850 rounded-lg border-l-4 border-sky-500">
                    <div className="flex items-center gap-3">
                      <span className="font-bold text-sky-400">{a.action}</span>
                      <span>{a.stock_code} {a.stock_name}</span>
                      {a.confidence && (
                        <span className="ml-auto text-xs px-2 py-1 bg-slate-800 rounded">
                          {a.confidence}% 置信度
                        </span>
                      )}
                    </div>
                    {a.reasoning && (
                      <p className="mt-2 text-xs text-slate-400">{a.reasoning}</p>
                    )}
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-slate-500 text-sm">今日无操作建议</div>
            )}
          </div>
        </div>
      ) : (
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-8 text-center text-slate-400">
          今日尚未生成交易计划，请点击「运行每日分析」
        </div>
      )}

      <div className="mt-5 bg-slate-900 border border-slate-800 rounded-xl p-6">
        <h3 className="font-bold mb-3">历史计划</h3>
        {history.length === 0 ? (
          <div className="text-sm text-slate-500">暂无历史计划</div>
        ) : (
          <div className="space-y-2">
            {history.map((h) => (
              <div
                key={h.date || h.id}
                className="flex items-center justify-between text-sm p-3 bg-slate-850 rounded-lg"
              >
                <span>{h.date}</span>
                <span className="text-slate-400">{(h.actions || []).length} 条操作建议</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
