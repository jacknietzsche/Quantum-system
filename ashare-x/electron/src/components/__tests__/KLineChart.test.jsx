import { describe, it, expect } from 'vitest'
import { render } from '@testing-library/react'
import KLineChart from '../KLineChart'

describe('KLineChart', () => {
  it('renders nothing when data is empty', () => {
    const { container } = render(<KLineChart data={[]} height={360} />)
    expect(container.firstChild).toBeNull()
  })

  it('renders nothing when data is null/undefined', () => {
    const { container } = render(<KLineChart data={null} height={360} />)
    expect(container.firstChild).toBeNull()
  })

  it('renders chart container when data is provided', () => {
    const data = [
      { date: '2024-01-01', open: 100, high: 105, low: 98, close: 103 },
      { date: '2024-01-02', open: 103, high: 108, low: 102, close: 107 },
    ]
    const { container } = render(<KLineChart data={data} height={360} />)
    // The chart container div should exist
    expect(container.firstChild).not.toBeNull()
  })
})
