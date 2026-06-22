export type ScreenStyle = 'limit_up' | 'momentum' | 'value' | 'hybrid'

export interface StyleConfig {
  label: string
  color: string
  desc: string
}

export const STYLE_CONFIGS: Record<ScreenStyle, StyleConfig> = {
  limit_up: { label: '涨停狙击', color: '#ef4444', desc: '日频短线博弈' },
  momentum: { label: '中期趋势', color: '#f59e0b', desc: '日频顺势跟踪' },
  value: { label: '长期价值', color: '#10b981', desc: '基本面深度+日频择时' },
  hybrid: { label: '混合均衡', color: '#3b82f6', desc: '综合打分（默认）' },
}

export interface StyleMetrics {
  turnover_rate?: number
  daily_volume_ratio?: number
  consecutive_limit_ups?: number
}

export interface Recommendation {
  rank: number
  stock_code: string
  stock_name: string
  score: number
  signal: string
  industry: string
  pe: number | null
  roe: number | null
  confidence: string
  reasoning: string
  style_metrics?: StyleMetrics
  in_portfolio?: boolean
  holding_qty?: number
  holding_pnl_pct?: number
  signal_note?: string

  // === 新增增强字段 ===
  masters_used?: string[]       // 大师评分列表 e.g. ["buffett(85)", "lynch(78)"]
  stage4_verdict?: string       // 辩论裁决 "买入"/"卖出"/"持有"
  stage4_confidence?: number    // 辩论置信度 0~1
  stage4_analyzed?: boolean     // 是否经过Stage4辩论
}

// 日志条目类型
export interface LogEntry {
  ts: string
  level: string
  module: string
  msg: string
}

export interface Stage4Analysis {
  stock_code: string
  stock_name: string
  research?: {
    fundamental?: string
    technical?: string
    capital?: string
    sentiment?: string
  }
  debate?: {
    bull_claims?: Array<{ source: string; claim: string }>
    bear_claims?: Array<{ source: string; claim: string }>
    verdict?: string
    confidence?: number
  }
  risk?: {
    risk_score: number
    risk_level: string
    risk_factors: string[]
  }
  signal?: {
    action: string
    confidence: number
    reasoning: string
  }
  error?: string
}

export interface PipelineStats {
  stage3_total: number
  stage3_errors: number
  stage3_pass: number
  avg_score: number
  signal_distribution: Record<string, number>
  stage4_count: number
  pipeline_time_s: number
}

export interface ScreeningData {
  total_screened: number
  filter_passed: number
  stage3_recommended: number
  stage4_enhanced?: number
  recommendations: Recommendation[]
  style: ScreenStyle
  stage4_analyses?: Stage4Analysis[]
  pipeline_stats?: PipelineStats
  market_state?: {
    regime: string
    strategy_bias?: string
    ai_insight?: {
      interpretation?: string
      confidence?: number
    }
  }
  orchestrator_insight?: string
}

export type TabStyle = { name: ScreenStyle; label: string }
export const ALL_STYLES: TabStyle[] = [
  { name: 'limit_up', label: '🔥 涨停狙击' },
  { name: 'momentum', label: '📈 中期趋势' },
  { name: 'value', label: '💎 长期价值' },
  { name: 'hybrid', label: '⚖️ 混合均衡' },
]
