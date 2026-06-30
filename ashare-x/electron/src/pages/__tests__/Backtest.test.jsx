import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import Backtest from '../Backtest'
import { mockBacktestStrategies, mockBacktestResult } from '../../test/apiMock'

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

describe('Backtest', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockGet.mockResolvedValue(mockBacktestStrategies)
    mockPost.mockResolvedValue(mockBacktestResult)
  })

  it('renders title and input fields', () => {
    render(<Backtest />)
    expect(screen.getByText('策略回测')).toBeInTheDocument()
    expect(screen.getByText('股票代码')).toBeInTheDocument()
    expect(screen.getByText('回测天数')).toBeInTheDocument()
    expect(screen.getByText('初始资金')).toBeInTheDocument()
  })

  it('loads strategies on mount', async () => {
    render(<Backtest />)
    await waitFor(() => {
      expect(screen.getByDisplayValue('ma_cross')).toBeInTheDocument()
    })
  })

  it('displays backtest results after running', async () => {
    render(<Backtest />)
    await waitFor(() => expect(screen.getByDisplayValue('ma_cross')).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: /运行回测/ }))
    await waitFor(() => {
      expect(screen.getByText('回测结果')).toBeInTheDocument()
      expect(screen.getByText('总收益率')).toBeInTheDocument()
      expect(screen.getByText('最大回撤')).toBeInTheDocument()
      expect(screen.getByText('夏普比率')).toBeInTheDocument()
    })
  })

  it('shows loading state when running', async () => {
    render(<Backtest />)
    await waitFor(() => expect(screen.getByDisplayValue('ma_cross')).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: /运行回测/ }))
    expect(screen.getByText('回测中...')).toBeInTheDocument()
  })
})
