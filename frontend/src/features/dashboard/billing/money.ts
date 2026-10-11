import type { Schemas } from '../../../api/types'
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

/** Amount including GST at the given rate, rounded to the paisa. */
export function withGst(paise: number, rate: number = site.gstRate): number {
  return Math.round((paise * (100 + rate)) / 100)
}

/** GST added to plan prices at checkout: the API's rate once loaded, else the site default (0 = none). */
export function gstRateOf(subscription: Schemas['Subscription'] | undefined): number {
  return subscription?.gst_rate_percent ?? site.gstRate
}

/** " + 18% GST" after a plan price, or nothing when GST isn't charged. */
export function gstSuffix(rate: number): string {
  return rate > 0 ? ` + ${rate}% GST` : ''
}
