import type { Tone } from '../../../components/app'
import { formatDate } from '../../../lib/datetime'
import { formatPaise } from '../../../lib/money'
import type { OfferAppliesTo, OfferClaimStatus, OfferCode } from './types'

export const appliesToLabels: Record<OfferAppliesTo, string> = {
  all: 'Everything',
  products: 'Products only',
  services: 'Services only',
}

export const claimStatusInfo: Record<OfferClaimStatus, { label: string; tone: Tone; description: string }> = {
  claimed: { label: 'Sent', tone: 'blue', description: 'Got the offer, not used yet' },
  applied: { label: 'In an order', tone: 'amber', description: 'Applied to an order that is not complete yet' },
  redeemed: { label: 'Redeemed', tone: 'green', description: 'Used in a completed order or at the counter' },
  expired: { label: 'Expired', tone: 'neutral', description: 'The offer ended before it was used' },
}

export const claimStatuses = Object.keys(claimStatusInfo) as OfferClaimStatus[]

/** "15% off (up to ₹300)", "₹100 off", "No discount". Adds the minimum order when there is one. */
export function discountSummary(offer: Pick<OfferCode, 'discount_type' | 'discount_value' | 'max_discount_paise' | 'min_order_paise'>): string {
  let text: string
  if (offer.discount_type === 'percent') {
    text = `${offer.discount_value ?? 0}% off`
    if (offer.max_discount_paise) text += ` (up to ${formatPaise(offer.max_discount_paise)})`
  } else if (offer.discount_type === 'amount') {
    text = `${formatPaise(offer.discount_value ?? 0)} off`
  } else {
    return 'Message only'
  }
  const minOrder = offer.min_order_paise ?? 0
  if (minOrder > 0) text += ` on ${formatPaise(minOrder)}+`
  return text
}

/** "Any time", "Until 5 Nov 2026", "From 20 Oct 2026", "20 Oct – 5 Nov 2026". */
export function validitySummary(offer: Pick<OfferCode, 'starts_at' | 'ends_at'>, timeZone?: string): string {
  const { starts_at: start, ends_at: end } = offer
  if (!start && !end) return 'Any time'
  if (!start) return `Until ${formatDate(end, timeZone)}`
  if (!end) return `From ${formatDate(start, timeZone)}`
  return `${formatDate(start, timeZone)} – ${formatDate(end, timeZone)}`
}

/** Whether the code can be used now: active and within its dates. */
export function offerState(offer: Pick<OfferCode, 'is_active' | 'starts_at' | 'ends_at'>, now = Date.now()): 'live' | 'off' | 'scheduled' | 'ended' {
  if (!offer.is_active) return 'off'
  if (offer.starts_at && new Date(offer.starts_at).getTime() > now) return 'scheduled'
  if (offer.ends_at && new Date(offer.ends_at).getTime() < now) return 'ended'
  return 'live'
}

export const offerStateInfo: Record<ReturnType<typeof offerState>, { label: string; tone: Tone }> = {
  live: { label: 'Live', tone: 'green' },
  off: { label: 'Off', tone: 'neutral' },
  scheduled: { label: 'Scheduled', tone: 'blue' },
  ended: { label: 'Ended', tone: 'neutral' },
}

/** `+919876543210` → `+91 98765 43210`; other numbers stay as they are. */
export function formatPhone(e164: string): string {
  const match = /^\+91(\d{5})(\d{5})$/.exec(e164)
  return match ? `+91 ${match[1]} ${match[2]}` : e164
}

/**
 * A typed phone number → E.164, or null. Ten-digit Indian mobiles get `+91`; spaces, dashes and a
 * leading `0` are ignored.
 */
export function normalisePhone(input: string): string | null {
  const compact = input.replace(/[\s()-]/g, '')
  if (/^\+\d{8,15}$/.test(compact)) return compact
  const digits = compact.replace(/^0+/, '')
  if (/^[6-9]\d{9}$/.test(digits)) return `+91${digits}`
  if (/^91[6-9]\d{9}$/.test(digits)) return `+${digits}`
  return null
}
