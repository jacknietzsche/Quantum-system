import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import Dashboard from '../Dashboard'
import { mockHealth } from '../../test/apiMock'

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

describe('Dashboard', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockGet.mockResolvedValue(mockHealth)
  })

  it('renders title and loading state initially', () => {
    render(<Dashboard />)
    expect(screen.getByText('控制台')).toBeInTheDocument()
  })

  it('renders stat cards after data loads', async () => {
    render(<Dashboard />)
    await waitFor(() => {
      expect(screen.getByText('服务状态')).toBeInTheDocument()
      expect(screen.getByText('版本')).toBeInTheDocument()
      expect(screen.getByText('数据总量')).toBeInTheDocument()
      expect(screen.getByText('累计报告')).toBeInTheDocument()
    })
  })

  it('displays health data values', async () => {
    render(<Dashboard />)
    await waitFor(() => {
      expect(screen.getByText('ok')).toBeInTheDocument()
      expect(screen.getByText('0.1.0')).toBeInTheDocument()
      expect(screen.getByText('331342')).toBeInTheDocument()
      expect(screen.getByText('18')).toBeInTheDocument()
    })
  })

  it('handles API error gracefully', async () => {
    mockGet.mockRejectedValueOnce(new Error('Network error'))
    render(<Dashboard />)
    await waitFor(() => {
      expect(screen.getByText('未知')).toBeInTheDocument()
    })
  })
})
