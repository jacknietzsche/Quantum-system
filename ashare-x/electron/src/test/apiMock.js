/**
 * API mock data matching backend response shapes.
 * Used by frontend component tests to avoid real HTTP calls.
 */

export const mockHealth = {
  status: 'ok',
  version: '0.1.0',
  data_count: 331342,
  reports: 18,
}

export const mockSettings = {
  llm_provider: 'deepseek',
  base_url: 'https://api.deepseek.com',
  quick_think_model: 'deepseek-chat',
  deep_think_model: 'deepseek-reasoner',
  api_key: 'sk-****',
  debate_rounds: 2,
  risk_rounds: 2,
  output_language: 'zh',
  monthly_budget_rmb: 100,
  email_sender: '123456@qq.com',
  email_password: '***',
  email_recipient: '654321@qq.com',
  email_smtp_host: 'smtp.qq.com',
  email_smtp_port: 465,
  email_use_ssl: true,
  has_api_key: true,
  has_email_password: true,
}

export const mockScreeningStocks = [
  {
    stock_code: '600519',
    stock_name: '贵州茅台',
    score: 85.5,
    rank: 1,
    factors: { value: 90, growth: 80, momentum: 75, quality: 95 },
  },
  {
    stock_code: '000858',
    stock_name: '五粮液',
    score: 78.3,
    rank: 2,
    factors: { value: 70, growth: 85, momentum: 80, quality: 78 },
  },
]

export const mockBacktestStrategies = {
  strategies: [
    { name: 'ma_cross', description: '均线交叉策略' },
    { name: 'rsi', description: 'RSI超买超卖策略' },
    { name: 'bollinger', description: '布林带策略' },
  ],
}

export const mockBacktestResult = {
  total_return: '15.23%',
  benchmark_return: '10.00%',
  excess_return: '5.23%',
  annualized_return: '14.80%',
  sharpe: 1.23,
  max_drawdown: '-5.67%',
  per_stock: {
    '600519': {
      total_return: '15.23%',
      sharpe: 1.5,
      max_drawdown: '-5.67%',
      total_trades: 10,
      win_rate: '60.0%',
    },
  },
  trades: [{ code: '600519', total_return: '15.23%', total_trades: 10 }],
  stock_count: 1,
}

export const mockDataStats = {
  kline_count: 331342,
  stock_count: 4500,
  db_size: '125.3 MB',
}

export const mockDataHealth = {
  status: 'healthy',
  message: '数据源连接正常',
  sources: [
    { name: 'SQLite数据库', status: 'healthy', last_update: '2024-01-01', record_count: 331342 },
    { name: '腾讯行情', status: 'healthy', last_update: 'N/A', record_count: 0 },
    { name: '新浪行情', status: 'warning', last_update: 'N/A', record_count: 0 },
  ],
}

export const mockKline = [
  { date: '2024-01-01', open: 100.0, high: 105.0, low: 98.0, close: 103.0, volume: 50000 },
  { date: '2024-01-02', open: 103.0, high: 108.0, low: 102.0, close: 107.0, volume: 60000 },
  { date: '2024-01-03', open: 107.0, high: 110.0, low: 105.0, close: 109.0, volume: 45000 },
]

export const mockReports = [
  {
    id: 'rpt-001',
    ticker: '600519',
    action: 'Buy',
    created_at: '2024-01-15',
    confidence: 85,
    position_pct: 10,
    thesis: 'Strong fundamentals and positive momentum',
  },
  {
    id: 'rpt-002',
    ticker: '000858',
    action: 'Hold',
    created_at: '2024-01-14',
    confidence: 60,
    position_pct: 5,
    thesis: 'Mixed signals, wait for confirmation',
  },
]

export const mockTradingPlan = {
  date: '2024-01-15',
  market_state: 'BULL',
  summary: '市场整体偏多，可适当加仓',
  actions: [
    {
      action: 'INITIAL_BUY',
      stock_code: '600519',
      stock_name: '贵州茅台',
      confidence: 85,
      reasoning: '技术面突破，基本面优秀',
    },
  ],
}

export const mockTradingPlanHistory = [
  { date: '2024-01-14', actions: [{ action: 'HOLD', stock_code: '600519' }] },
  { date: '2024-01-13', actions: [] },
]

export const mockAnalysisJob = {
  job_id: 'abc12345',
  ticker: '600519',
  status: 'running',
}

export const mockPortfolio = {
  holdings: [],
  total_assets: 1000000,
  cash: 1000000,
  holding_count: 0,
}

export const mockRebalance = {
  market_state: 'BULL',
  position_cap: 0.3,
  operations: [],
  message: '再平衡完成',
}
