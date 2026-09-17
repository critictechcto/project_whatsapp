import { formatNumber } from '../../../lib/format'
import type { Schemas } from '../../../api/types'

/** Decimal 0-1 as a string (`"0.9612"`), or null when the denominator is 0. */
type DecimalRate = string | null
type AnalyticsSource = Schemas['AnalyticsMessageSourceEnum']
type AnalyticsPaymentMethod = Schemas['AnalyticsPaymentMethodRow']['payment_method']

const percent = new Intl.NumberFormat('en-IN', { minimumFractionDigits: 1, maximumFractionDigits: 1 })

/** `"0.9612"` → `"96.1%"`; null or unparsable → `"—"`. */
export function formatRate(rate: DecimalRate | number | undefined): string {
  if (rate === null || rate === undefined || rate === '') return '—'
  const value = typeof rate === 'number' ? rate : Number(rate)
  return Number.isFinite(value) ? `${percent.format(value * 100)}%` : '—'
}

export { formatNumber }

export type Delta = {
  direction: 'up' | 'down' | 'flat'
  /** e.g. "12.5%" or "1.2 pts"; null when there is nothing to compare with (previous period was 0). */
  text: string | null
}

/**
 * Change of a count vs the previous period, as a percent with one decimal. No percent when the previous
 * value is 0 (growth from nothing has no meaningful percent), only the direction.
 */
export function countDelta(current: number, previous: number): Delta {
  const direction = current > previous ? 'up' : current < previous ? 'down' : 'flat'
  if (previous === 0) return { direction, text: null }
  const change = Math.abs(((current - previous) / previous) * 100)
  return { direction: percent.format(change) === '0.0' ? 'flat' : direction, text: `${percent.format(change)}%` }
}

/** Change of a rate in percentage points ("1.2 pts"); no text when either period has no rate. */
export function rateDelta(current: DecimalRate, previous: DecimalRate): Delta {
  if (current === null || previous === null) return { direction: 'flat', text: null }
  const points = (Number(current) - Number(previous)) * 100
  if (!Number.isFinite(points)) return { direction: 'flat', text: null }
  const text = percent.format(Math.abs(points))
  const direction = text === '0.0' ? 'flat' : points > 0 ? 'up' : 'down'
  return { direction, text: `${text} pts` }
}

/** Plain-language labels of common Meta Cloud API error codes on failed messages. */
export const failureCodeLabels: Record<string, string> = {
  '131026': 'Message undeliverable (number not on WhatsApp or unable to receive)',
  '131047': 'Re-engagement needed: more than 24 hours since the customer last replied',
  '131048': 'Spam rate limit hit',
  '131049': 'Per-user marketing limit reached',
  '131050': 'Customer stopped marketing messages',
  '131056': 'Too many messages to the same number (pair rate limit)',
  '130472': "Customer's number is part of a Meta experiment",
}

/** Label of a failure code; unknown codes show the raw code. */
export function failureLabel(code: string): string {
  if (!code) return 'Unknown error'
  return failureCodeLabels[code] ?? `Error ${code}`
}

export const sourceLabels: Record<AnalyticsSource, string> = {
  inbox: 'Inbox replies',
  campaign: 'Campaigns',
  automation: 'Automations',
  api: 'API',
  commerce: 'Store and orders',
}

export function sourceLabel(source: string): string {
  return sourceLabels[source as AnalyticsSource] ?? humanize(source)
}

const categoryLabels: Record<string, string> = {
  marketing: 'Marketing',
  utility: 'Utility',
  authentication: 'Authentication',
  '': 'Non-template messages',
}

export function categoryLabel(category: string): string {
  return categoryLabels[category.toLowerCase()] ?? humanize(category)
}

export const paymentMethodLabels: Record<AnalyticsPaymentMethod, string> = {
  online: 'Paid online',
  cod: 'Cash on delivery',
  '': 'Not chosen',
}

const orderStatusLabels: Record<string, string> = {
  draft: 'Cart started',
  awaiting_confirmation: 'Confirming prices',
  awaiting_address: 'Awaiting address',
  awaiting_payment_method: 'Choosing payment',
  pending_payment: 'Awaiting payment',
  confirmed: 'Confirmed',
  packed: 'Packed',
  shipped: 'Shipped',
  delivered: 'Delivered',
  cancelled: 'Cancelled',
  expired: 'Expired',
  needs_attention: 'Needs attention',
}

export function orderStatusLabel(status: string): string {
  return orderStatusLabels[status] ?? humanize(status)
}

const roleLabels: Record<string, string> = { owner: 'Owner', admin: 'Admin', agent: 'Agent', viewer: 'Viewer' }

export function roleLabel(role: string): string {
  return roleLabels[role] ?? humanize(role)
}

function humanize(value: string): string {
  const words = value.replace(/_/g, ' ').trim()
  return words ? words[0].toUpperCase() + words.slice(1).toLowerCase() : '—'
}
