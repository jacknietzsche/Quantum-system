import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import Analysis from '../Analysis'
import { mockAnalysisJob } from '../../test/apiMock'

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

// Mock EventSource for SSE
class MockEventSource {
  constructor(url) {
    this.url = url
    this.listeners = {}
    this.closed = false
    setTimeout(() => {
      this._emit('progress', { progress: 50 })
      this._emit('agent_status', { agent: 'market_analyst', label: '市场分析师', status: 'in_progress' })
      this._emit('done', { status: 'completed' })
    }, 10)
  }
  addEventListener(event, handler) {
    if (!this.listeners[event]) this.listeners[event] = []
    this.listeners[event].push(handler)
  }
  removeEventListener(event, handler) {
    if (this.listeners[event]) {
      this.listeners[event] = this.listeners[event].filter(h => h !== handler)
    }
  }
  _emit(event, data) {
    if (this.listeners[event]) {
      this.listeners[event].forEach(h => h({ data: JSON.stringify(data) }))
    }
  }
  close() { this.closed = true }
}

vi.stubGlobal('EventSource', MockEventSource)

describe('Analysis', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockPost.mockResolvedValue(mockAnalysisJob)
    mockGet.mockResolvedValue({ status: 'completed', result: { action: 'Buy', confidence: 85 } })
  })

  it('renders title and input fields', () => {
    render(<Analysis />)
    expect(screen.getByText('个股分析')).toBeInTheDocument()
    expect(screen.getByText('股票代码')).toBeInTheDocument()
    expect(screen.getByText('快速模式')).toBeInTheDocument()
  })

  it('has default ticker 600519', () => {
    render(<Analysis />)
    expect(screen.getByDisplayValue('600519')).toBeInTheDocument()
  })

  it('renders start analysis button', () => {
    render(<Analysis />)
    expect(screen.getByRole('button', { name: /启动分析/ })).toBeInTheDocument()
  })

  it('starts analysis when button clicked', async () => {
    render(<Analysis />)
    fireEvent.click(screen.getByRole('button', { name: /启动分析/ }))
    await waitFor(() => {
      expect(mockPost).toHaveBeenCalledWith('/analysis', {
        ticker: '600519',
        fast_mode: false,
        enable_masters: false,
      })
    })
  })

  it('validates stock code - does not call API for invalid code', () => {
    render(<Analysis />)
    const input = screen.getByDisplayValue('600519')
    fireEvent.change(input, { target: { value: 'invalid' } })
    fireEvent.click(screen.getByRole('button', { name: /启动分析/ }))
    expect(mockPost).not.toHaveBeenCalled()
  })
})
