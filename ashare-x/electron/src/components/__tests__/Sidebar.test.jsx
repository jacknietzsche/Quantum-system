import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import Sidebar from '../Sidebar'

describe('Sidebar', () => {
  it('renders all 8 nav items', () => {
    render(<Sidebar active="dashboard" onChange={() => {}} open={false} onToggle={() => {}} />)
    expect(screen.getByText('AShare-X')).toBeInTheDocument()
    // Check nav items exist
    expect(screen.getByText('控制台')).toBeInTheDocument()
    expect(screen.getByText('个股分析')).toBeInTheDocument()
    expect(screen.getByText('智能选股')).toBeInTheDocument()
    expect(screen.getByText('策略回测')).toBeInTheDocument()
    expect(screen.getByText('交易计划')).toBeInTheDocument()
    expect(screen.getByText('数据管理')).toBeInTheDocument()
    expect(screen.getByText('历史报告')).toBeInTheDocument()
    expect(screen.getByText('系统设置')).toBeInTheDocument()
  })

  it('highlights active nav item', () => {
    render(<Sidebar active="analysis" onChange={() => {}} open={false} onToggle={() => {}} />)
    const activeBtn = screen.getByText('个股分析').closest('button')
    expect(activeBtn.className).toContain('bg-slate-800')
    expect(activeBtn.className).toContain('text-sky-400')
  })

  it('calls onChange when nav item clicked', () => {
    const onChange = vi.fn()
    render(<Sidebar active="dashboard" onChange={onChange} open={false} onToggle={() => {}} />)
    fireEvent.click(screen.getByText('智能选股'))
    expect(onChange).toHaveBeenCalledWith('screening')
  })

  it('shows version text', () => {
    render(<Sidebar active="dashboard" onChange={() => {}} open={false} onToggle={() => {}} />)
    expect(screen.getByText('AShare-X v0.1.0')).toBeInTheDocument()
  })
})
