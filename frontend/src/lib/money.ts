/**
 * Money is integer paise (₹1 = 100 paise) in INR, as in `docs/contracts/wave-3-commerce.md`.
 * Formatting uses Indian digit grouping (₹1,00,000).
 */

const withDecimals = new Intl.NumberFormat('en-IN', {
  style: 'currency',
  currency: 'INR',
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
})
const wholeRupees = new Intl.NumberFormat('en-IN', {
  style: 'currency',
  currency: 'INR',
  minimumFractionDigits: 0,
  maximumFractionDigits: 0,
})

export type FormatPaiseOptions = {
  /** `'auto'` (default) shows paise only when they are non-zero; `0` rounds to whole rupees; `2` always shows paise. */
  decimals?: 'auto' | 0 | 2
}

/** Paise → `'₹1,450'` / `'₹1,450.50'` / `'₹1,00,000'`. */
export function formatPaise(paise: number, { decimals = 'auto' }: FormatPaiseOptions = {}): string {
  const whole = Math.round(paise)
  const useDecimals = decimals === 2 || (decimals === 'auto' && whole % 100 !== 0)
  return (useDecimals ? withDecimals : wholeRupees).format(whole / 100)
}

/** Paise → a plain rupee amount for inputs and CSVs: `145050` → `'1450.50'`. */
export function paiseToRupeesString(paise: number): string {
  const whole = Math.round(paise)
  const sign = whole < 0 ? '-' : ''
  const abs = Math.abs(whole)
  return `${sign}${Math.trunc(abs / 100)}.${String(abs % 100).padStart(2, '0')}`
}

// Digits with optional Indian (1,00,000) or international (100,000) grouping, then up to 2 decimals.
const RUPEES = /^(\d+|\d{1,3}(?:,\d{2,3})+)?(?:\.(\d{1,2}))?$/

/**
 * A typed rupee amount → paise. Accepts `'1450'`, `'1,450.5'` and `'₹ 1450.50'`.
 * Returns `null` for empty input, negatives, more than 2 decimals or anything else.
 */
export function parseRupeesToPaise(input: string): number | null {
  const value = input.trim().replace(/^₹\s*/, '')
  const match = RUPEES.exec(value)
  if (!match || (!match[1] && !match[2])) return null
  const rupees = match[1] ? Number(match[1].replaceAll(',', '')) : 0
  const paise = match[2] ? Number(match[2].padEnd(2, '0')) : 0
  const total = rupees * 100 + paise
  return Number.isSafeInteger(total) ? total : null
}
