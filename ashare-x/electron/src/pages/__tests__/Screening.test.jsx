import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import Screening from '../Screening'
import { mockScreeningStocks } from '../../test/apiMock'

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

describe('Screening', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockGet.mockResolvedValue({ stocks: mockScreeningStocks, style: 'balanced', total: 2 })
  })

  it('renders title and style selector', () => {
    render(<Screening />)
    expect(screen.getByText('智能选股')).toBeInTheDocument()
    expect(screen.getByText('均衡')).toBeInTheDocument()
    expect(screen.getByText('价值')).toBeInTheDocument()
  })

  it('renders run button', () => {
    render(<Screening />)
    expect(screen.getByRole('button', { name: /运行选股/ })).toBeInTheDocument()
  })

  it('displays screening results after running', async () => {
    render(<Screening />)
    fireEvent.click(screen.getByRole('button', { name: /运行选股/ }))
    await waitFor(() => {
      expect(screen.getByText('600519')).toBeInTheDocument()
      expect(screen.getByText('贵州茅台')).toBeInTheDocument()
    })
  })

  it('renders table headers in results', async () => {
    render(<Screening />)
    fireEvent.click(screen.getByRole('button', { name: /运行选股/ }))
    await waitFor(() => {
      expect(screen.getByText('排名')).toBeInTheDocument()
      expect(screen.getByText('代码')).toBeInTheDocument()
      expect(screen.getByText('名称')).toBeInTheDocument()
    })
  })
})
