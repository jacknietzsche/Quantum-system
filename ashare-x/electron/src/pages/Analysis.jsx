import React, { useEffect, useRef, useState } from 'react'
import api from '../api'

const AGENT_STATUS_COLORS = {
  in_progress: 'text-amber-400',
  completed: 'text-emerald-400',
  failed: 'text-rose-400',
}

export default function Analysis() {
  const [ticker, setTicker] = useState('600519')
  const [fastMode, setFastMode] = useState(false)
  const [enableMasters, setEnableMasters] = useState(false)
  const [job, setJob] = useState(null)
  const [progress, setProgress] = useState(0)
  const [agents, setAgents] = useState([])
  const [logs, setLogs] = useState([])
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const esRef = useRef(null)

  const startAnalysis = async () => {
    setLoading(true)
    setProgress(0)
    setAgents([])
    setLogs([])
    setResult(null)
    try {
      const data = await api.post('/analysis', {
        ticker,
        fast_mode: fastMode,
        enable_masters: enableMasters,
      })
      setJob(data)
    } catch {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (!job?.job_id) return

    const es = new EventSource(`http://127.0.0.1:8765/api/stream/${job.job_id}`)
    esRef.current = es

    es.onmessage = (e) => {
      try {
        const payload = JSON.parse(e.data)
        if (e.lastEventId === 'progress' || payload.progress !== undefined) {
          setProgress(payload.progress || 0)
        }
        if (e.lastEventId === 'agent_status' || payload.agent) {
          setAgents((prev) => {
            const idx = prev.findIndex((a) => a.agent === payload.agent)
            if (idx >= 0) {
              const next = [...prev]
              next[idx] = payload
              return next
            }
            return [...prev, payload]
          })
        }
        if (e.lastEventId === 'log' || payload.message) {
          setLogs((prev) => [...prev.slice(-99), payload])
        }
        if (e.lastEventId === 'done' || payload.status) {
          if (payload.status === 'completed') {
            fetchResult(job.job_id)
          }
          setLoading(false)
          es.close()
        }
      } catch {
        // ignore
      }
    }

    es.onerror = () => {
      es.close()
      setLoading(false)
    }

    return () => es.close()
  }, [job])

  const fetchResult = async (jobId) => {
    try {
      const data = await api.get(`/analysis/${jobId}`)
      setResult(data?.result || null)
    } catch {
      // ignore
    }
  }

  return (
    <div>
      <h2 className="text-xl font-bold mb-5">个股分析</h2>

      <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 mb-5">
        <div className="flex flex-wrap items-end gap-4">
          <div>
            <label className="block text-sm text-slate-400 mb-1">股票代码</label>
            <input
              className="bg-slate-850 border border-slate-700 rounded-lg px-3 py-2 text-sm w-40"
              value={ticker}
              onChange={(e) => setTicker(e.target.value)}
              placeholder="如 600519"
            />
          </div>
          <label className="flex items-center gap-2 text-sm text-slate-300">
            <input
              type="checkbox"
              className="rounded bg-slate-800 border-slate-700"
              checked={fastMode}
              onChange={(e) => setFastMode(e.target.checked)}
            />
            快速模式
          </label>
          <label className="flex items-center gap-2 text-sm text-slate-300">
            <input
              type="checkbox"
              className="rounded bg-slate-800 border-slate-700"
              checked={enableMasters}
              onChange={(e) => setEnableMasters(e.target.checked)}
            />
            大师Agent
          </label>
          <button
            onClick={startAnalysis}
            disabled={loading}
            className="px-4 py-2 bg-sky-600 hover:bg-sky-500 disabled:bg-slate-700 rounded-lg text-sm font-medium"
          >
            {loading ? '分析中...' : '⚡ 启动分析'}
          </button>
        </div>
      </div>

      {job && (
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 mb-5">
          <div className="flex items-center justify-between mb-3">
            <span className="text-sm text-slate-400">任务 {job.job_id}</span>
            <span className="text-sm font-medium">{progress}%</span>
          </div>
          <div className="h-2 bg-slate-800 rounded-full overflow-hidden">
            <div
              className="h-full bg-sky-500 transition-all duration-300"
              style={{ width: `${progress}%` }}
            />
          </div>
        </div>
      )}

      {agents.length > 0 && (
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 mb-5">
          <h3 className="font-bold mb-3">Agent 状态</h3>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
            {agents.map((a) => (
              <div key={a.agent} className="flex items-center gap-2 text-sm">
                <span className={AGENT_STATUS_COLORS[a.status] || 'text-slate-400'}>●</span>
                <span>{a.label || a.agent}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {result && (
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 mb-5">
          <h3 className="font-bold mb-4">分析结果</h3>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
            <div className="p-3 bg-slate-850 rounded-lg">
              <div className="text-xs text-slate-400">决策</div>
              <div className="text-lg font-bold text-sky-400">{result.action}</div>
            </div>
            <div className="p-3 bg-slate-850 rounded-lg">
              <div className="text-xs text-slate-400">置信度</div>
              <div className="text-lg font-bold">{result.confidence}%</div>
            </div>
            <div className="p-3 bg-slate-850 rounded-lg">
              <div className="text-xs text-slate-400">仓位建议</div>
              <div className="text-lg font-bold">{result.position_pct}%</div>
            </div>
            <div className="p-3 bg-slate-850 rounded-lg">
              <div className="text-xs text-slate-400">目标价</div>
              <div className="text-lg font-bold">{result.take_profit || '-'}</div>
            </div>
          </div>
          {result.thesis && (
            <p className="text-sm text-slate-300 leading-relaxed">{result.thesis}</p>
          )}
        </div>
      )}

      {logs.length > 0 && (
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-6">
          <h3 className="font-bold mb-3">运行日志</h3>
          <div className="h-48 overflow-y-auto text-xs font-mono space-y-1">
            {logs.map((log, i) => (
              <div key={i} className="text-slate-400">
                <span className="text-slate-600">[{log.time || '--:--:--'}]</span>{' '}
                {log.message}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
