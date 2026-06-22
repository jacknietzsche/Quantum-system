export type PortfolioType = 'limit_up' | 'momentum' | 'value'

export interface PortfolioConfig {
  label: string
  color: string
  icon: string
  desc: string
}

export const PORTFOLIO_CONFIGS: Record<PortfolioType, PortfolioConfig> = {
  limit_up: { label: '涨停狙击', color: '#ef4444', icon: '\u{1F525}', desc: '超短博弈' },
  momentum: { label: '中期趋势', color: '#f59e0b', icon: '\u{1F4C8}', desc: '顺势跟踪' },
  value: { label: '长期价值', color: '#10b981', icon: '\u{1F48E}', desc: '价值投资' },
}

export const PORTFOLIO_TYPES: PortfolioType[] = ['limit_up', 'momentum', 'value']

export interface Position {
  stock_code: string
  stock_name: string
  buy_date: string
  buy_price: number
  quantity: number
  current_price: number
  cost_value: number
  current_value: number
  profit_loss: number
  profit_loss_pct: number
  industry: string
  trend: string
}

export interface PortfolioSummary {
  portfolio_type: PortfolioType
  total_asset: number
  cash: number
  total_value: number
  total_cost: number
  position_count: number
  total_return_pct: number
  total_pnl: number
  pnl_pct: number
  win_rate: number
  total_trades: number
}

export interface PortfolioHoldings {
  positions: Position[]
  cash: number
  total_asset: number
  position_count: number
  portfolio_type: PortfolioType
}

export interface NavPoint {
  date: string
  total_asset: number
  cash: number
  stock_value: number
  daily_return_pct: number
  cumulative_return_pct?: number
  position_count?: number
}
