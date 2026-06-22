import { get, post } from './request'

export interface V2AnalysisResult {
  ok: boolean
  stock_code: string
  trade_date: string
  decision: string
  signal: {
    action: string
    confidence: number
    reasoning: string
  }
  reports: Record<string, string>
  debate: {
    bull_history: string
    bear_history: string
    judge_decision: string
  }
  risk_debate: {
    aggressive: string
    conservative: string
    neutral: string
  }
  final_decision: string
  error?: string
}

export interface WorkflowTrade {
  stock_code: string
  stock_name: string
  action: string
  price: number
  quantity: number
  reasoning: string
  timestamp: string
}

export interface WorkflowReflection {
  date: string
  stock_code: string
  rating: string
  reflection: string
  raw_return: number
  alpha_return: number
}

export const v2Api = {
  /** Run V2 multi-agent analysis for a single stock */
  analyzeStock: (stockCode: string, analysts?: string[]) => {
    const params = analysts ? { analysts: analysts.join(',') } : {}
    return get<V2AnalysisResult>(`/api/analysis/v2/${stockCode}`, params)
  },

  /** Get recent trades from workflow memory */
  getTrades: (limit = 20) => get('/api/workflow/memory/trades', { limit }),

  /** Record a trade */
  recordTrade: (trade: Omit<WorkflowTrade, 'timestamp'>) => post('/api/workflow/memory/trades', trade),

  /** Get reflections */
  getReflections: (limit = 10) => get('/api/workflow/memory/reflections', { limit }),

  /** Get performance summary */
  getPerformance: () => get('/api/workflow/memory/performance'),

  /** Get lessons */
  getLessons: () => get('/api/workflow/memory/lessons'),

  /** Get patterns */
  getPatterns: () => get('/api/workflow/memory/patterns'),

  /** Get email settings */
  getEmailSettings: () => get('/api/settings/email'),

  /** Save email settings */
  saveEmailSettings: (settings: { sender: string; password: string; receivers: string[]; sender_name: string }) =>
    post('/api/settings/email', settings),

  /** Send test email */
  sendTestEmail: (to: string) => post('/api/settings/email/test', { to }),
}
