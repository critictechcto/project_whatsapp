import { describe, expect, it } from 'vitest'
import { formatPaise, paiseToRupeesString, parseRupeesToPaise } from './money'

describe('formatPaise', () => {
  it('shows paise only when non-zero by default', () => {
    expect(formatPaise(145000)).toBe('₹1,450')
    expect(formatPaise(145050)).toBe('₹1,450.50')
    expect(formatPaise(145005)).toBe('₹1,450.05')
    expect(formatPaise(0)).toBe('₹0')
  })

  it('uses Indian digit grouping', () => {
    expect(formatPaise(10000000)).toBe('₹1,00,000')
    expect(formatPaise(123456789)).toBe('₹12,34,567.89')
  })

  it('honours fixed decimals', () => {
    expect(formatPaise(145000, { decimals: 2 })).toBe('₹1,450.00')
    expect(formatPaise(145050, { decimals: 0 })).toBe('₹1,451')
    expect(formatPaise(145049, { decimals: 0 })).toBe('₹1,450')
    expect(formatPaise(145050, { decimals: 'auto' })).toBe('₹1,450.50')
  })
})

describe('paiseToRupeesString', () => {
  it('always has two decimals and no grouping', () => {
    expect(paiseToRupeesString(145050)).toBe('1450.50')
    expect(paiseToRupeesString(145000)).toBe('1450.00')
    expect(paiseToRupeesString(5)).toBe('0.05')
    expect(paiseToRupeesString(10000000)).toBe('100000.00')
    expect(paiseToRupeesString(-250)).toBe('-2.50')
  })
})

describe('parseRupeesToPaise', () => {
  it.each([
    ['1450', 145000],
    ['1,450.5', 145050],
    ['₹ 1450.50', 145050],
    ['₹1,00,000', 10000000],
    ['100,000.25', 10000025],
    ['  249  ', 24900],
    ['0.05', 5],
    ['.5', 50],
    ['0', 0],
  ])('parses %j', (input, expected) => {
    expect(parseRupeesToPaise(input)).toBe(expected)
  })

  it.each(['', '₹', '1450.505', '-10', '₹-10', 'abc', '12abc', '1.2.3', '1450.', '1,,450', ',450', '1,4', '1e3', 'Rs 10'])(
    'rejects %j',
    (input) => {
      expect(parseRupeesToPaise(input)).toBeNull()
    },
  )

  it('round-trips with paiseToRupeesString', () => {
    for (const paise of [0, 5, 99, 100, 24950, 145050, 9999999]) {
      expect(parseRupeesToPaise(paiseToRupeesString(paise))).toBe(paise)
    }
  })
})
