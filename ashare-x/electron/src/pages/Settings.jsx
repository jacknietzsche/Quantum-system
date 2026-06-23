import React, { useEffect, useState } from 'react'
import api from '../api'

export default function Settings() {
  const [settings, setSettings] = useState({})
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    api.get('/settings').then((data) => setSettings(data || {}))
  }, [])

  const handleChange = (key, value) => {
    setSettings((prev) => ({ ...prev, [key]: value }))
  }

  const handleSave = async () => {
    try {
      await api.put('/settings', settings)
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    } catch {
      alert('保存失败')
    }
  }

  return (
    <div>
      <h2 className="text-xl font-bold mb-5">系统设置</h2>
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 space-y-4 max-w-2xl mb-5">
        <h3 className="font-bold text-slate-200">模型接入</h3>
        <div>
          <label className="block text-sm text-slate-400 mb-1">LLM 提供商</label>
          <select
            className="w-full bg-slate-850 border border-slate-700 rounded-lg px-3 py-2 text-sm"
            value={settings.llm_provider || 'deepseek'}
            onChange={(e) => handleChange('llm_provider', e.target.value)}
          >
            <option value="deepseek">DeepSeek</option>
            <option value="qwen">Qwen</option>
            <option value="zhipu">Zhipu</option>
          </select>
        </div>
        <div>
          <label className="block text-sm text-slate-400 mb-1">API Key</label>
          <input
            type="password"
            className="w-full bg-slate-850 border border-slate-700 rounded-lg px-3 py-2 text-sm"
            value={settings.api_key || ''}
            onChange={(e) => handleChange('api_key', e.target.value)}
            placeholder="留空表示保持原有设置"
          />
        </div>
        <div>
          <label className="block text-sm text-slate-400 mb-1">月度预算 (RMB)</label>
          <input
            type="number"
            className="w-full bg-slate-850 border border-slate-700 rounded-lg px-3 py-2 text-sm"
            value={settings.monthly_budget_rmb || 100}
            onChange={(e) => handleChange('monthly_budget_rmb', Number(e.target.value))}
          />
        </div>
      </div>

      <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 space-y-4 max-w-2xl">
        <h3 className="font-bold text-slate-200">交易计划邮件推送</h3>
        <div>
          <label className="block text-sm text-slate-400 mb-1">发件邮箱 (QQ)</label>
          <input
            type="email"
            className="w-full bg-slate-850 border border-slate-700 rounded-lg px-3 py-2 text-sm"
            value={settings.email_sender || ''}
            onChange={(e) => handleChange('email_sender', e.target.value)}
            placeholder="如 123456@qq.com"
          />
        </div>
        <div>
          <label className="block text-sm text-slate-400 mb-1">授权码</label>
          <input
            type="password"
            className="w-full bg-slate-850 border border-slate-700 rounded-lg px-3 py-2 text-sm"
            value={settings.email_password || ''}
            onChange={(e) => handleChange('email_password', e.target.value)}
            placeholder="QQ 邮箱 SMTP 授权码"
          />
        </div>
        <div>
          <label className="block text-sm text-slate-400 mb-1">默认收件人</label>
          <input
            type="email"
            className="w-full bg-slate-850 border border-slate-700 rounded-lg px-3 py-2 text-sm"
            value={settings.email_recipient || ''}
            onChange={(e) => handleChange('email_recipient', e.target.value)}
            placeholder="如 654321@qq.com"
          />
        </div>
        <div className="pt-2 flex items-center gap-3">
          <button
            onClick={handleSave}
            className="px-4 py-2 bg-sky-600 hover:bg-sky-500 rounded-lg text-sm font-medium"
          >
            保存设置
          </button>
          {saved && <span className="text-sm text-emerald-400">已保存</span>}
        </div>
      </div>
    </div>
  )
}
