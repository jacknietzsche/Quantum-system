import axios from 'axios'

const API_BASE = import.meta.env.PROD ? '' : 'http://127.0.0.1:8765'

const api = axios.create({
  baseURL: `${API_BASE}/api`,
  headers: { 'Content-Type': 'application/json' },
  timeout: 30000,
})

api.interceptors.response.use(
  (res) => res.data,
  (err) => {
    const msg = err.response?.data?.message || err.message || '请求失败'
    console.error(msg)
    return Promise.reject(msg)
  },
)

export default api
