import axios from 'axios'
import { ElMessage } from 'element-plus'

const api = axios.create({
  baseURL: '',
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
})

api.interceptors.request.use((config) => config)

api.interceptors.response.use(
  (response) => response.data,
  (error) => {
    const message = error.response?.data?.error || error.response?.data?.message || error.message || '请求失败'
    ElMessage.error(message)
    return Promise.reject(error)
  }
)

export default api

type ApiResponse<T = any> = T

export async function get<T = any>(url: string, params?: any): Promise<ApiResponse<T>> {
  try {
    return await api.get(url, { params }) as any
  } catch (error) {
    console.error(`GET ${url} failed:`, error)
    throw error
  }
}

export async function post<T = any>(url: string, data?: any): Promise<ApiResponse<T>> {
  try {
    return await api.post(url, data) as any
  } catch (error) {
    console.error(`POST ${url} failed:`, error)
    throw error
  }
}

export async function put<T = any>(url: string, data?: any): Promise<ApiResponse<T>> {
  try {
    return await api.put(url, data) as any
  } catch (error) {
    console.error(`PUT ${url} failed:`, error)
    throw error
  }
}

export async function del<T = any>(url: string): Promise<ApiResponse<T>> {
  try {
    return await api.delete(url) as any
  } catch (error) {
    console.error(`DELETE ${url} failed:`, error)
    throw error
  }
}
