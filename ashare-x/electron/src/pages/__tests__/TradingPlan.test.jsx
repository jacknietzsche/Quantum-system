import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import TradingPlan from '../TradingPlan'
import {
  mockTradingPlan,
  mockTradingPlanHistory,
  mockRebalance,
} from '../../test/apiMock'

const { mockGet, mockPost, mockPut } = vi.hoisted(() => ({
  mockGet: vi.fn(),
  mockPost: vi.fn(),
  mockPut: vi.fn(),
}))

vi.mock('../../api', () => ({
  default: {
    get: mockGet,
    post: mockPost,
    put: mockPut,
  },
}))

describe('TradingPlan', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockGet.mockImplementation(async (url) => {
      if (url === '/trading-plan/today') return { ok: true, plan: mockTradingPlan }
      if (url === '/trading-plan/history?limit=10') return { ok: true, history: mockTradingPlanHistory, total: 2 }
      return {}
    })
    mockPost.mockImplementation(async (url) => {
      if (url === '/trading-plan/run') return { job_id: 'plan123', status: 'running' }
      if (url === '/portfolio/rebalance') return mockRebalance
      if (url === '/trading-plan/send-email') return { ok: true }
      return {}
    })
  })

  it('renders title and action buttons', () => {
    render(<TradingPlan />)
    expect(screen.getByText('每日交易计划')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /运行每日分析/ })).toBeInTheDocument()
  })

  it('displays today plan after load', async () => {
    render(<TradingPlan />)
    await waitFor(() => {
      expect(screen.getByText('BULL')).toBeInTheDocument()
      expect(screen.getByText('市场整体偏多，可适当加仓')).toBeInTheDocument()
    })
  })

  it('renders history section', async () => {
    render(<TradingPlan />)
    await waitFor(() => {
      expect(screen.getByText('历史计划')).toBeInTheDocument()
    })
  })

  it('shows action suggestion after plan loads', async () => {
    render(<TradingPlan />)
    await waitFor(() => {
      expect(screen.getByText('操作建议')).toBeInTheDocument()
      expect(screen.getByText(/INITIAL_BUY/)).toBeInTheDocument()
      expect(screen.getByText(/600519/)).toBeInTheDocument()
    })
  })

  it('clicking run button triggers plan run API call', async () => {
    render(<TradingPlan />)
    await waitFor(() => expect(screen.getByRole('button', { name: /运行每日分析/ })).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: /运行每日分析/ }))
    await waitFor(() => {
      expect(mockPost).toHaveBeenCalledWith('/trading-plan/run', { fast_mode: true })
    })
  })

  it('clicking rebalance triggers rebalance API call', async () => {
    render(<TradingPlan />)
    await waitFor(() => expect(screen.getByRole('button', { name: /再平衡/ })).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: /再平衡/ }))
    await waitFor(() => {
      expect(mockPost).toHaveBeenCalledWith('/portfolio/rebalance')
    })
  })
})
