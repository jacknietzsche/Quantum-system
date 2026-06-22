import { get } from './request'

export interface MarketState {
  summary: string
  confidence: number
  regime: string
  strategy_weights: {
    value: number
    growth: number
    defensive: number
  }
  risk_level: string
}

export interface AgentHealthEntry {
  name: string
  display_name: string
  accuracy_7d: number
  accuracy_30d: number
  accuracy_all: number
  total_picks: number
  correct_picks: number
}

export interface AgentHealth {
  agents: AgentHealthEntry[]
}

export interface MemoryCalendarDay {
  trade_date: string
  regime: string
  picks_count: number
  correct_count: number
  avg_return: number
  market_return: number
  reflection: string
}

export interface MemoryCalendar {
  days: MemoryCalendarDay[]
}

export interface SimilarMarketDay {
  trade_date: string
  similarity: number
  regime: string
  strategy: string
  result: number
}

export interface SimilarMarkets {
  similar_days: SimilarMarketDay[]
}

export const aiApi = {
  getMarketState: () => get<MarketState>('/api/ai/market-state'),
  getAgentHealth: () => get<AgentHealth>('/api/ai/agent-health'),
  getMemoryCalendar: (days?: number) => get<MemoryCalendar>('/api/ai/memory/calendar', { days: days || 30 }),
  getSimilarMarkets: (date: string) => get<SimilarMarkets>('/api/ai/memory/similar', { date }),
}

// ── 新: 市场诊断 (Stage 0 输出) ──

export interface MarketDiagnosis {
  status: string
  state: 'BULL' | 'BEAR' | 'SHOCK' | 'VOLATILE'
  confidence: number
  weights: {
    trend: number
    capital: number
    fundamental: number
    defensive: number
  }
  summary: string
  timestamp: string
  details?: {
    breadth: { up: number; down: number; limit_up: number; limit_down: number; total: number }
    sectors: { top: { name: string; change: number }[]; bottom: { name: string; change: number }[] }
    volatility: number
    limit_up_count: number
  }
}

export const screeningApi = {
  marketState: (forceRefresh = false) => get<MarketDiagnosis>('/api/screening/market-state', { force_refresh: forceRefresh }),
}

// ── QuantAgent API ──

export interface QuantAgentState {
  status: string
  current_phase: string | null
  thoughts_count: number
  final_picks_count: number
  error: string
}

export interface QuantDecision {
  status: string
  date: string
  picks_count: number
  picks: any[]
  summary: string
  warnings: string[]
}

export const quantApi = {
  runCycle: (force = false) => get<QuantDecision>('/api/quant-agent/daily-cycle', { force }),
  getState: () => get<QuantAgentState>('/api/quant-agent/state'),
  getDecision: (date: string) => get<any>(`/api/quant-agent/decision/${date}`),
  listDecisions: (limit = 10) => get<{ decisions: any[] }>('/api/quant-agent/decisions', { limit }),
}
