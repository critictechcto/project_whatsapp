import { useEffect, useState } from 'react'
import type { components } from '../../../api/schema'
import { env } from '../../../config/env'

/**
 * Plan prices for the landing page. Razorpay plans are the only source of prices: the backend reads
 * them and serves them without authentication at `GET /api/v1/billing/public-plans/`
 * (docs/contracts/billing-razorpay.md). This uses plain `fetch` so the landing bundle never pulls in the
 * dashboard's API client.
 */

type PublicPlansResponse = components['schemas']['PublicPlans']

/** Rupee prices of one plan, before GST; null when that interval can't be bought right now. */
export type PlanPrices = { monthly: number | null; annual: number | null }

export type PublicPrices = {
  gstRatePercent: number
  /** Keyed by plan id ('starter', 'growth', 'pro'), matching `plans` in config/site.ts. */
  byPlan: Record<string, PlanPrices>
}

export type PublicPricesState =
  | { status: 'loading' }
  | { status: 'ready'; prices: PublicPrices }
  | { status: 'unavailable' }

/** Where the prices come from, or null when this build shows none (mock mode without VITE_PRICING_API_URL). */
export function publicPlansUrl(): string | null {
  const origin = env.pricingApiUrl
  return origin === null ? null : `${origin}/api/v1/billing/public-plans/`
}

const toRupees = (paise: unknown) => (typeof paise === 'number' && Number.isFinite(paise) && paise > 0 ? paise / 100 : null)

/** Reads the API response defensively: anything unexpected becomes "no price" rather than a wrong one. */
export function parsePublicPlans(body: unknown): PublicPrices {
  const data = body as Partial<PublicPlansResponse> | null
  if (!data || !Array.isArray(data.plans)) throw new Error('Unexpected public plans response')
  const byPlan: Record<string, PlanPrices> = {}
  for (const plan of data.plans) {
    if (!plan || typeof plan.id !== 'string') continue
    byPlan[plan.id] = { monthly: toRupees(plan.monthly_price_paise), annual: toRupees(plan.annual_price_paise) }
  }
  const gst = data.gst_rate_percent
  return { gstRatePercent: typeof gst === 'number' && gst >= 0 ? gst : 0, byPlan }
}

export async function fetchPublicPrices(url: string, signal?: AbortSignal): Promise<PublicPrices> {
  // Public data: no cookies and no auth headers (the endpoint answers with Access-Control-Allow-Origin: *).
  const response = await fetch(url, { credentials: 'omit', headers: { Accept: 'application/json' }, signal })
  if (!response.ok) throw new Error(`Public plans request failed with ${response.status}`)
  return parsePublicPlans(await response.json())
}

/**
 * Months free on annual billing, from a plan's two prices: 12 minus what a year costs in months,
 * rounded. Null when either price is unknown or the year saves nothing.
 */
export function monthsFree(prices: PlanPrices | undefined): number | null {
  if (!prices?.monthly || !prices.annual) return null
  const free = Math.round(12 - prices.annual / prices.monthly)
  return free > 0 ? free : null
}

/**
 * Prices for the pricing section. Always 'loading' on the server and on the first client render (so
 * hydration matches); the request starts in an effect after hydration.
 */
export function usePublicPrices(): PublicPricesState {
  const [state, setState] = useState<PublicPricesState>({ status: 'loading' })

  useEffect(() => {
    const url = publicPlansUrl()
    if (!url) {
      setState({ status: 'unavailable' })
      return
    }
    const controller = new AbortController()
    fetchPublicPrices(url, controller.signal).then(
      (prices) => setState({ status: 'ready', prices }),
      () => {
        if (!controller.signal.aborted) setState({ status: 'unavailable' })
      },
    )
    return () => controller.abort()
  }, [])

  return state
}
