import { describe, it, expect } from 'vitest'
import {
  isValidStockCode,
  normalizeStockCode,
  validateStockCode,
  validatePositiveNumber,
} from '../validation'

describe('isValidStockCode', () => {
  it('returns true for valid SH codes', () => {
    expect(isValidStockCode('600519')).toBe(true)
    expect(isValidStockCode('601318')).toBe(true)
    expect(isValidStockCode('603259')).toBe(true)
    expect(isValidStockCode('688981')).toBe(true)
  })

  it('returns true for valid SZ codes', () => {
    expect(isValidStockCode('000001')).toBe(true)
    expect(isValidStockCode('002594')).toBe(true)
    expect(isValidStockCode('300750')).toBe(true)
    expect(isValidStockCode('301236')).toBe(true)
  })

  it('returns false for invalid codes', () => {
    expect(isValidStockCode('')).toBe(false)
    expect(isValidStockCode(null)).toBe(false)
    expect(isValidStockCode(undefined)).toBe(false)
    expect(isValidStockCode('12345')).toBe(false) // too short
    expect(isValidStockCode('1234567')).toBe(false) // too long
    expect(isValidStockCode('500000')).toBe(false) // fund prefix
    expect(isValidStockCode('abc123')).toBe(false) // non-numeric
  })
})

describe('normalizeStockCode', () => {
  it('trims whitespace', () => {
    expect(normalizeStockCode('  600519  ')).toBe('600519')
  })
  it('handles empty/null', () => {
    expect(normalizeStockCode('')).toBe('')
    expect(normalizeStockCode(null)).toBe('')
  })
})

describe('validateStockCode', () => {
  it('returns empty string for valid code', () => {
    expect(validateStockCode('600519')).toBe('')
  })
  it('returns error for empty input', () => {
    expect(validateStockCode('')).not.toBe('')
  })
  it('returns error for non-6-digit code', () => {
    expect(validateStockCode('12345')).not.toBe('')
  })
  it('returns error for unsupported prefix', () => {
    expect(validateStockCode('500000')).not.toBe('')
  })
})

describe('validatePositiveNumber', () => {
  it('returns empty string for valid positive number', () => {
    expect(validatePositiveNumber(30)).toBe('')
    expect(validatePositiveNumber('30')).toBe('')
  })
  it('returns error for empty/null/NaN', () => {
    expect(validatePositiveNumber('')).not.toBe('')
    expect(validatePositiveNumber(null)).not.toBe('')
    expect(validatePositiveNumber('abc')).not.toBe('')
  })
  it('returns error for zero or negative', () => {
    expect(validatePositiveNumber(0)).not.toBe('')
    expect(validatePositiveNumber(-5)).not.toBe('')
  })
})
