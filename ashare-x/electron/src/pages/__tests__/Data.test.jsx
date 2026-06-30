import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import Data from '../Data'
import { mockDataStats, mockDataHealth, mockKline } from '../../test/apiMock'

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

describe('Data page', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockGet.mockImplementation(async (url) => {
      if (url === '/data/stats') return mockDataStats
      if (url === '/data/health') return mockDataHealth
      if (url.startsWith('/data/kline')) return { code: '600519', kline: mockKline, total: mockKline.length }
      return {}
    })
    mockPost.mockResolvedValue({ status: 'ok' })
  })

  it('renders title and sections', () => {
    render(<Data />)
    expect(screen.getByText('数据管理')).toBeInTheDocument()
    expect(screen.getByText('数据源健康')).toBeInTheDocument()
    expect(screen.getByText('K线查询')).toBeInTheDocument()
  })

  it('loads and displays stats', async () => {
    render(<Data />)
    await waitFor(() => {
      expect(screen.getByText('331342')).toBeInTheDocument()
      expect(screen.getByText('4500')).toBeInTheDocument()
      expect(screen.getByText('125.3 MB')).toBeInTheDocument()
    })
  })

  it('loads and displays data health sources', async () => {
    render(<Data />)
    await waitFor(() => {
      expect(screen.getByText('SQLite数据库')).toBeInTheDocument()
      expect(screen.getByText('腾讯行情')).toBeInTheDocument()
    })
  })

  it('renders refresh button', () => {
    render(<Data />)
    expect(screen.getByRole('button', { name: /刷新数据/ })).toBeInTheDocument()
  })

  it('queries kline when clicking search button', async () => {
    render(<Data />)
    await waitFor(() => expect(screen.getByRole('button', { name: '查询' })).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: '查询' }))
    await waitFor(() => {
      expect(mockGet).toHaveBeenCalledWith(expect.stringContaining('/data/kline'))
    })
  })
})
