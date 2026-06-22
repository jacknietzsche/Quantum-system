import { describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { usePortfolioStore } from '../portfolio'

// Mock the API module
vi.mock('@/api/request', () => ({
  get: vi.fn(),
  post: vi.fn(),
  put: vi.fn(),
}))

import { get } from '@/api/request'
const mockGet = vi.mocked(get)

describe('usePortfolioStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('has correct defaults', () => {
    const store = usePortfolioStore()
    expect(store.activeType).toBe('value')
    expect(store.holdings).toBeNull()
    expect(store.summaries).toBeNull()
    expect(store.nav).toEqual([])
    expect(store.loading).toBe(false)
    expect(store.error).toBeNull()
  })

  it('fetchHoldings sets loading state', async () => {
    mockGet.mockResolvedValue({ positions: [], cash: 100000 })
    const store = usePortfolioStore()

    const promise = store.fetchHoldings()
    expect(store.loading).toBe(true)

    await promise
    expect(store.loading).toBe(false)
    expect(store.error).toBeNull()
  })

  it('fetchHoldings stores result', async () => {
    const mockData = { positions: [{ code: '600519' }], cash: 50000 }
    mockGet.mockResolvedValue(mockData)
    const store = usePortfolioStore()

    await store.fetchHoldings()
    expect(store.holdings).toEqual(mockData)
    expect(store.activeType).toBe('value')
  })

  it('fetchHoldings with custom type', async () => {
    mockGet.mockResolvedValue({ positions: [] })
    const store = usePortfolioStore()

    await store.fetchHoldings('momentum')
    expect(store.activeType).toBe('momentum')
    expect(mockGet).toHaveBeenCalledWith('/api/portfolio/holdings', { type: 'momentum' })
  })

  it('fetchHoldings handles error', async () => {
    mockGet.mockRejectedValue(new Error('Network error'))
    const store = usePortfolioStore()

    await store.fetchHoldings()
    expect(store.error).toBe('Network error')
    expect(store.loading).toBe(false)
  })

  it('fetchAllSummaries stores result', async () => {
    mockGet.mockResolvedValue({ summaries: { value: { total: 100000 } } })
    const store = usePortfolioStore()

    await store.fetchAllSummaries()
    expect(store.summaries).toEqual({ value: { total: 100000 } })
  })

  it('fetchAllSummaries handles error silently', async () => {
    mockGet.mockRejectedValue(new Error('fail'))
    const store = usePortfolioStore()
    // Should not throw
    await store.fetchAllSummaries()
    expect(store.summaries).toBeNull()
  })
})
