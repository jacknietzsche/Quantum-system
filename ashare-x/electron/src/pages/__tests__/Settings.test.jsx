import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import Settings from '../Settings'
import { mockSettings } from '../../test/apiMock'

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

describe('Settings', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockGet.mockResolvedValue(mockSettings)
    mockPut.mockResolvedValue({ status: 'ok', message: '设置已保存' })
  })

  it('renders title and sections', () => {
    render(<Settings />)
    expect(screen.getByText('系统设置')).toBeInTheDocument()
    expect(screen.getByText('模型接入')).toBeInTheDocument()
    expect(screen.getByText('交易计划邮件推送')).toBeInTheDocument()
  })

  it('loads settings on mount', async () => {
    render(<Settings />)
    // Wait for API call to complete and settings to populate
    await waitFor(() => {
      expect(mockGet).toHaveBeenCalledWith('/settings')
    })
    // Verify budget field loaded from mock data
    await waitFor(() => {
      const budgetInput = screen.getByDisplayValue('100')
      expect(budgetInput).toBeInTheDocument()
    })
  })

  it('renders LLM provider dropdown with options', () => {
    render(<Settings />)
    expect(screen.getByText('DeepSeek')).toBeInTheDocument()
    expect(screen.getByText('Qwen')).toBeInTheDocument()
    expect(screen.getByText('Zhipu')).toBeInTheDocument()
  })

  it('renders save button', () => {
    render(<Settings />)
    expect(screen.getByText('保存设置')).toBeInTheDocument()
  })

  it('clicking save calls PUT /settings', async () => {
    render(<Settings />)
    await waitFor(() => expect(screen.getByText('保存设置')).toBeInTheDocument())
    fireEvent.click(screen.getByText('保存设置'))
    await waitFor(() => {
      expect(mockPut).toHaveBeenCalledWith('/settings', expect.any(Object))
    })
  })

  it('shows saved indicator after successful save', async () => {
    render(<Settings />)
    await waitFor(() => expect(screen.getByText('保存设置')).toBeInTheDocument())
    fireEvent.click(screen.getByText('保存设置'))
    await waitFor(() => {
      expect(screen.getByText('已保存')).toBeInTheDocument()
    })
  })
})
