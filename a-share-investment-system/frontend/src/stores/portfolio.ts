import { defineStore } from 'pinia'
import { ref } from 'vue'
import { get, post, put } from '@/api/request'
import type { PortfolioType, PortfolioHoldings, PortfolioSummary, NavPoint } from '@/types/portfolio'

export const usePortfolioStore = defineStore('portfolio', () => {
  const activeType = ref<PortfolioType>('value')
  const holdings = ref<PortfolioHoldings | null>(null)
  const summaries = ref<Record<PortfolioType, PortfolioSummary> | null>(null)
  const nav = ref<NavPoint[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)
  const tradeHistory = ref<any[]>([])

  async function fetchHoldings(type?: PortfolioType) {
    loading.value = true
    error.value = null
    try {
      const t = type || activeType.value
      const res = await get('/api/portfolio/holdings', { type: t })
      holdings.value = res as PortfolioHoldings
      activeType.value = t
    } catch (e: any) {
      error.value = e.message || 'Failed to load holdings'
    } finally {
      loading.value = false
    }
  }

  async function fetchAllSummaries() {
    try {
      const res = await get('/api/portfolio/all-summaries')
      summaries.value = (res as any).summaries
    } catch (e: any) {
      console.error('Failed to load summaries:', e)
    }
  }

  async function fetchNav(type: PortfolioType, limit = 30) {
    try {
      const res = await get('/api/portfolio/nav', { type, limit })
      nav.value = (res as any).nav || []
    } catch (e: any) {
      console.error('Failed to load nav:', e)
    }
  }

  async function addPosition(data: { portfolio_type: string; stock_code: string; stock_name: string; buy_price: number; quantity: number; buy_reason?: string }) {
    const res = await post('/api/portfolio/holdings', data)
    await fetchHoldings()
    return res
  }

  async function sellPosition(stockCode: string, data: { portfolio_type: string; sell_price: number; sell_reason?: string }) {
    const res = await put(`/api/portfolio/holdings/${stockCode}/sell`, data)
    await fetchHoldings()
    return res
  }

  async function resetPortfolio(portfolioType?: PortfolioType) {
    const res = await post('/api/portfolio/reset', { portfolio_type: portfolioType || null })
    await fetchHoldings()
    await fetchAllSummaries()
    return res
  }

  async function switchPortfolio(type: PortfolioType) {
    activeType.value = type
    await Promise.all([
      fetchHoldings(type),
      fetchNav(type),
    ])
  }

  return {
    activeType, holdings, summaries, nav, loading, error, tradeHistory,
    fetchHoldings, fetchAllSummaries, fetchNav,
    addPosition, sellPosition, resetPortfolio, switchPortfolio,
  }
})
