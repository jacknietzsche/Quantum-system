import { get, post } from './request'

export interface AnalysisParams {
  stock_code: string
  stock_name?: string
  trade_date?: string
  analyst?: string[]
  research_depth?: number
}

export interface TaskListParams {
  limit?: number
  offset?: number
  status?: string
}

export const analysisApi = {
  startAnalysis: (params: AnalysisParams) => post('/api/tasks', params),
  getTaskList: (params?: TaskListParams) => get('/api/tasks', params),
  getTaskDetail: (taskId: string) => get(`/api/tasks/${taskId}`),
  getTaskResult: (taskId: string) => get(`/api/tasks/${taskId}`),
  cancelTask: (taskId: string) => post(`/api/tasks/${taskId}/cancel`),
  getAnalystList: () => {
    const analysts = [
      { name: '巴菲特', style: '价值投资' },
      { name: '格雷厄姆', style: '深度价值' },
      { name: '彼得·林奇', style: '成长投资' },
    ]
    return Promise.resolve({ data: { analysts } })
  },
  getAnalysis: (stockCode: string) => get(`/api/analysis/${stockCode}`),
}
