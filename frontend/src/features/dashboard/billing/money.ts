import { site } from '../../../config/site'

const exact = new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', minimumFractionDigits: 2, maximumFractionDigits: 2 })
const whole = new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', minimumFractionDigits: 0, maximumFractionDigits: 0 })

/** Paise → "₹11,788.20" with Indian digit grouping. */
export function formatPaise(paise: number): string {
  return exact.format(paise / 100)
}

/** Paise → "₹2,499" when whole rupees, otherwise with paise. */
export function formatPlanPrice(paise: number): string {
  return paise % 100 === 0 ? whole.format(paise / 100) : exact.format(paise / 100)
}

/** Amount including GST at the configured rate, rounded to the paisa. */
export function withGst(paise: number, rate: number = site.gstRate): number {
  return Math.round((paise * (100 + rate)) / 100)
}
