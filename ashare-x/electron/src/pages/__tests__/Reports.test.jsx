import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import Reports from '../Reports'
import { mockReports } from '../../test/apiMock'

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

describe('Reports', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockGet.mockResolvedValue({ reports: mockReports, total: mockReports.length })
  })

  it('renders title and filter input', () => {
    render(<Reports />)
    expect(screen.getByText('历史报告')).toBeInTheDocument()
    expect(screen.getByPlaceholderText(/股票代码/)).toBeInTheDocument()
  })

  it('loads and displays report list', async () => {
    render(<Reports />)
    await waitFor(() => {
      expect(screen.getByText('600519')).toBeInTheDocument()
      expect(screen.getByText('000858')).toBeInTheDocument()
    })
  })

  it('shows report detail when clicked', async () => {
    render(<Reports />)
    await waitFor(() => expect(screen.getByText('600519')).toBeInTheDocument())
    fireEvent.click(screen.getByText('600519'))
    await waitFor(() => {
      expect(screen.getByText(/分析报告/)).toBeInTheDocument()
      expect(screen.getByText('Strong fundamentals and positive momentum')).toBeInTheDocument()
    })
  })

  it('filters reports by ticker', async () => {
    render(<Reports />)
    await waitFor(() => expect(screen.getByText('600519')).toBeInTheDocument())
    const input = screen.getByPlaceholderText(/股票代码/)
    fireEvent.change(input, { target: { value: '600519' } })
    expect(screen.getByText('600519')).toBeInTheDocument()
    expect(screen.queryByText('000858')).not.toBeInTheDocument()
  })

  it('has refresh button', () => {
    render(<Reports />)
    expect(screen.getByText('刷新')).toBeInTheDocument()
  })
})
