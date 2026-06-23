import React, { useEffect, useState } from 'react'
import api from '../api'

export default function TradingPlan() {
  const [plan, setPlan] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api.get('/trading-plan/today')
      .then((data) => {
        if (data?.ok) setPlan(data.plan)
      })
      .catch(() => setPlan(null))
      .finally(() => setLoading(false))
  }, [])

  return (
    <div>
      <div className="flex items-center justify-between mb-5">
        <h2 className="text-xl font-bold">交易计划</h2>
        <div className="flex gap-2">
          <button className="px-4 py-2 bg-sky-600 hover:bg-sky-500 rounded-lg text-sm font-medium">
            ⚡ 运行每日分析
          </button>
          <button className="px-4 py-2 bg-slate-700 hover:bg-slate-600 rounded-lg text-sm font-medium">
            ⚖️ 再平衡
          </button>
          <button className="px-4 py-2 bg-slate-700 hover:bg-slate-600 rounded-lg text-sm font-medium">
            📧 发送到 QQ 邮箱
          </button>
        </div>
      </div>

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
    </div>
  )
}
