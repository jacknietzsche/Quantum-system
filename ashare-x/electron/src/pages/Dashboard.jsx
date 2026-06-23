import React, { useEffect, useState } from 'react'
import api from '../api'

function StatCard({ label, value, colorClass }) {
  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-5">
      <div className={`text-2xl font-bold ${colorClass}`}>{value}</div>
      <div className="text-sm text-slate-400 mt-1">{label}</div>
    </div>
  )
}

export default function Dashboard() {
  const [stats, setStats] = useState({})
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api.get('/health')
      .then((data) => {
        setStats(data || {})
      })
      .catch(() => setStats({}))
      .finally(() => setLoading(false))
  }, [])

  return (
    <div>
      <h2 className="text-xl font-bold mb-5">控制台</h2>
      {loading ? (
        <div className="text-slate-400">加载中...</div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          <StatCard label="服务状态" value={stats.status || '未知'} colorClass="text-sky-400" />
          <StatCard label="版本" value={stats.version || '-'} colorClass="text-slate-100" />
          <StatCard label="数据总量" value={stats.data_count || '-'} colorClass="text-emerald-400" />
          <StatCard label="累计报告" value={stats.reports || '-'} colorClass="text-amber-400" />
        </div>
      )}
      <div className="mt-6 bg-slate-900 border border-slate-800 rounded-xl p-6">
        <h3 className="font-bold mb-3">欢迎来到 AShare-X</h3>
        <p className="text-slate-400 text-sm leading-relaxed">
          React 版本前端已搭建完成。后续将逐步迁移个股分析、智能选股、交易计划等功能到本工程。
        </p>
      </div>
    </div>
  )
}
