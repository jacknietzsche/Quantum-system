import { describe, it, expect } from 'vitest'
import { formatMoney, formatPercent } from '../datetime'

describe('formatMoney', () => {
  it('formats whole numbers', () => {
    expect(formatMoney(1000)).toBe('1,000.00')
  })

  it('formats large numbers with commas', () => {
    expect(formatMoney(1234567.89)).toBe('1,234,567.89')
  })

  it('formats zero', () => {
    expect(formatMoney(0)).toBe('0.00')
  })

  it('formats negative numbers', () => {
    expect(formatMoney(-500.5)).toBe('-500.50')
  })

  it('formats small decimals', () => {
    expect(formatMoney(0.1)).toBe('0.10')
  })
})

describe('formatPercent', () => {
  it('adds + prefix for positive', () => {
    expect(formatPercent(5.5)).toBe('+5.50%')
  })

  it('adds - prefix for negative', () => {
    expect(formatPercent(-3.2)).toBe('-3.20%')
  })

  it('handles zero', () => {
    expect(formatPercent(0)).toBe('+0.00%')
  })

  it('handles large positive', () => {
    expect(formatPercent(150)).toBe('+150.00%')
  })

  it('always shows two decimal places', () => {
    expect(formatPercent(1)).toBe('+1.00%')
  })
})
