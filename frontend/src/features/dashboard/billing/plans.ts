import { plans as sitePlans } from '../../../config/site'
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

const featureLabels: Record<string, string> = {
  scheduled_campaigns: 'Scheduled campaigns',
  keyword_automations: 'Keyword automations',
  api_access: 'API access',
  commerce: 'Sell on WhatsApp',
  analytics: 'Analytics reports',
}

/** Display name of a plan feature key ("scheduled_campaigns" -> "Scheduled campaigns"). */
export function featureLabel(key: string): string {
  if (featureLabels[key]) return featureLabels[key]
  const words = key.replace(/_/g, ' ')
  return words.charAt(0).toUpperCase() + words.slice(1)
}

export const usageLabels: Record<string, string> = {
  whatsapp_numbers: 'WhatsApp numbers',
  members: 'Team members',
  contacts: 'Contacts',
}

/** Price before GST for an interval, or null when that interval can't be bought right now. */
export function planPricePaise(plan: Plan, interval: BillingInterval): number | null {
  return interval === 'annual' ? plan.annual_price_paise : plan.monthly_price_paise
}

export const intervalLabels: Record<BillingInterval, string> = { monthly: 'Monthly', annual: 'Annual' }

/**
 * "2 months free" from a plan's two prices (12 minus what a year costs in months, rounded), or null
 * when either price is unknown or annual billing saves nothing.
 */
export function freeMonthsLabel(plan: Plan): string | null {
  const { monthly_price_paise: monthly, annual_price_paise: annual } = plan
  if (!monthly || !annual) return null
  const free = Math.round(12 - annual / monthly)
  if (free <= 0) return null
  return `${free} ${free === 1 ? 'month' : 'months'} free`
}

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
