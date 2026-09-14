import { describe, expect, it } from 'vitest'
import { billingProfileSchema, gstinError, normalizeGstin, stateCodeError, stateFromGstin } from './gst'
import { formatPaise, formatPlanPrice, withGst } from './money'

describe('GSTIN validation', () => {
  it('allows an empty GSTIN', () => {
    expect(gstinError('')).toBeNull()
    expect(stateCodeError('', '29')).toBeNull()
  })

  it('accepts a well-formed GSTIN regardless of case and spaces', () => {
    expect(normalizeGstin(' 29aakfk4821m1z3 ')).toBe('29AAKFK4821M1Z3')
    expect(gstinError('29aakfk4821m1z3')).toBeNull()
  })

  it('rejects malformed GSTINs', () => {
    expect(gstinError('29AAKFK4821M1Z')).toBe('A GSTIN has 15 characters.')
    expect(gstinError('29AAKFK4821M1X3')).toMatch(/valid GSTIN/)
    expect(gstinError('99AAKFK4821M1Z3')).toMatch(/state code/)
  })

  it('requires the state to match the first two digits', () => {
    expect(stateCodeError('29AAKFK4821M1Z3', '29')).toBeNull()
    expect(stateCodeError('29AAKFK4821M1Z3', '27')).toBe('Must match the first two digits of the GSTIN.')
    expect(stateCodeError('', '')).toBe('Choose a state.')
  })

  it('derives the state from a valid GSTIN', () => {
    expect(stateFromGstin('08AABCS1429B1ZX')).toBe('08')
    expect(stateFromGstin('08AABCS')).toBeNull()
  })

  it('puts the mismatch on state_code in the form schema', () => {
    const result = billingProfileSchema.safeParse({
      legal_name: 'Kaveri Dental Clinic LLP',
      gstin: '29AAKFK4821M1Z3',
      email: 'accounts@kaveridental.in',
      address_line1: '14, 2nd Cross',
      address_line2: '',
      city: 'Bengaluru',
      state_code: '33',
      postal_code: '560038',
    })
    expect(result.success).toBe(false)
    expect(result.error?.issues.map((issue) => issue.path.join('.'))).toEqual(['state_code'])
  })
})

describe('money', () => {
  it('formats paise as rupees with Indian grouping', () => {
    expect(formatPaise(1178820)).toBe('₹11,788.20')
    expect(formatPaise(10_000_000)).toBe('₹1,00,000.00')
    expect(formatPlanPrice(249900)).toBe('₹2,499')
    expect(formatPlanPrice(2499000)).toBe('₹24,990')
  })

  it('adds GST', () => {
    expect(withGst(99900)).toBe(117882)
  })
})
