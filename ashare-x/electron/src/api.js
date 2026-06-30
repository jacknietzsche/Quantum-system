import axios from 'axios'

export const API_BASE = import.meta.env.PROD ? '' : 'http://127.0.0.1:8766'

const api = axios.create({
  baseURL: `${API_BASE}/api`,
  headers: { 'Content-Type': 'application/json' },
  timeout: 180000,
})

api.interceptors.response.use(
  (res) => res.data,
  (err) => {
    const data = err.response?.data
    const message =
      data?.message || data?.error || err.message || '请求失败'
    console.error('[API Error]', message)
    return Promise.reject(message)
  },
)

export default api
