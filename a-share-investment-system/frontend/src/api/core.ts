import { get, post, put, del } from './request'

export const portfolioApi = {
  getHoldings: (type: string) => get('/api/portfolio/holdings', { type }),
  getSummary: (type: string) => get('/api/portfolio/summary', { type }),
  getAllSummaries: () => get('/api/portfolio/all-summaries'),
  addHolding: (data: any) => post('/api/portfolio/holdings', data),
  sellHolding: (code: string, data: any) => put(`/api/portfolio/holdings/${code}/sell`, data),
  reset: (data: any) => post('/api/portfolio/reset', data),
  getNav: (type: string, limit?: number) => get('/api/portfolio/nav', { type, limit }),
  getTrades: (type: string, limit?: number) => get('/api/portfolio/trades', { type, limit }),
  getHoldingsMap: (type: string) => get('/api/portfolio/holdings-map', { type }),
}

export const dbApi = {
  getStats: () => get('/api/db/stats'),
  getStockInfo: (params: any) => get('/api/db/stockinfo', params),
  getSnapshots: () => get('/api/db/snapshots'),
  getHotStocks: (limit?: number) => get('/api/db/hot-stocks', { limit }),
  getLhb: () => get('/api/db/lhb'),
  getIndustryDistribution: (limit?: number) => get('/api/db/industry-distribution', { limit }),
  getDataQuality: () => get('/api/db/data-quality'),
  sourceTest: () => get('/api/db/source-test'),
  addStock: (data: any) => post('/api/db/stockinfo', data),
  refresh: (data: any) => post('/api/db/refresh', data),
  updateStock: (code: string, data: any) => put(`/api/db/stockinfo/${code}`, data),
  deleteStock: (code: string) => del(`/api/db/stockinfo/${code}`),
  getDataByDate: (params: any) => get('/api/db/data-by-date', params),
  getTableInfo: (params: any) => get('/api/db/table-info', params),
  refreshFinancials: (maxStocks?: number) => post('/api/db/refresh-financials', { max_stocks: maxStocks || 500 }),
  refreshIndustry: () => post('/api/db/refresh-industry'),
}
