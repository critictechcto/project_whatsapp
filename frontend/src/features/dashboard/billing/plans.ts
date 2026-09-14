import { ANNUAL_MONTHS_CHARGED, plans as sitePlans } from '../../../config/site'
import type { Schemas } from '../../../api/types'

export type Plan = Schemas['Plan']
export type Subscription = Schemas['Subscription']
export type BillingInterval = Schemas['BillingIntervalEnum']

const grouping = new Intl.NumberFormat('en-IN')

const nouns: Record<string, [string, string]> = {
  whatsapp_numbers: ['WhatsApp number', 'WhatsApp numbers'],
  members: ['team member', 'team members'],
  contacts: ['contact', 'contacts'],
}

/** "2 WhatsApp numbers", "1,00,000 contacts", "Unlimited contacts". */
export function limitLabel(key: string, value: number | null): string {
  const [one, many] = nouns[key] ?? [key.replace(/_/g, ' '), key.replace(/_/g, ' ')]
  if (value === null) return `Unlimited ${many}`
  return `${grouping.format(value)} ${value === 1 ? one : many}`
}

export const usageLabels: Record<string, string> = {
  whatsapp_numbers: 'WhatsApp numbers',
  members: 'Team members',
  contacts: 'Contacts',
}

export function planPricePaise(plan: Plan, interval: BillingInterval): number {
  return interval === 'annual' ? plan.annual_price_paise : plan.monthly_price_paise
}

export const intervalLabels: Record<BillingInterval, string> = { monthly: 'Monthly', annual: 'Annual' }

export const freeMonthsLabel = `${12 - ANNUAL_MONTHS_CHARGED} months free`

/** Marketing blurb and "recommended" flag from `config/site.ts` (prices always come from the API). */
export function planCopy(planId: string) {
  return sitePlans.find((plan) => plan.id === planId)
}

/** Whole days until `iso` (0 when it's today or past), or null. */
export function daysUntil(iso: string | null | undefined): number | null {
  if (!iso) return null
  return Math.max(0, Math.ceil((new Date(iso).getTime() - Date.now()) / 86_400_000))
}

export function isFutureDate(iso: string | null | undefined): boolean {
  return Boolean(iso) && new Date(iso as string).getTime() > Date.now()
}
