/**
 * Offer code types, mirroring `docs/contracts/services-and-offers.md` (section "Offers").
 *
 * TODO: switch to generated types after api:types — once `/api/v1/offers/` is in `backend/openapi.yml`,
 * replace these with `Schemas['OfferCode']`, `Schemas['OfferClaim']`, `Schemas['OfferStats']` (and the
 * request types) from `src/api/types` and delete this file's hand-written shapes.
 */

export type OfferDiscountType = 'none' | 'percent' | 'amount'
export type OfferAppliesTo = 'all' | 'products' | 'services'
export type OfferClaimStatus = 'claimed' | 'applied' | 'redeemed' | 'expired'

export type OfferCode = {
  readonly id: string
  /** 2–20 chars `[A-Za-z0-9_-]`, stored upper-case, unique per workspace. */
  code: string
  title: string
  reply_text: string
  discount_type: OfferDiscountType
  /** Percent 1–90, or paise ≥ 100 for `amount`; 0 for `none`. */
  discount_value: number
  /** Percent only; null = no cap. */
  max_discount_paise: number | null
  min_order_paise: number
  applies_to: OfferAppliesTo
  starts_at: string | null
  ends_at: string | null
  /** null = unlimited; counts applied + redeemed claims. */
  max_uses: number | null
  max_uses_per_contact: number
  is_active: boolean
  /** Read-only counters. */
  readonly claims_count: number
  readonly redeemed_count: number
  readonly created_at: string
  readonly updated_at: string
}

/** Body of `POST codes/` and `PATCH codes/{id}/`. */
export type OfferCodeWrite = Omit<OfferCode, 'id' | 'claims_count' | 'redeemed_count' | 'created_at' | 'updated_at'>

export type OfferContactSummary = {
  id: string
  name: string
  phone_e164: string
}

export type OfferClaim = {
  readonly id: string
  /** Offer code id. */
  offer: string
  contact: OfferContactSummary
  status: OfferClaimStatus
  order: { id: string; number: string } | null
  discount_paise: number
  bill_paise: number | null
  ad_source_id: string
  ad_source_url: string
  ad_headline: string
  ctwa_clid: string
  redeemed_at: string | null
  readonly created_at: string
}

export type OfferStatsDay = { date: string; claims: number; redeemed: number }

/** `GET codes/{id}/stats/`. `revenue_paise` = sum of redeemed `bill_paise`. */
export type OfferStats = {
  claims: number
  from_ads: number
  applied: number
  redeemed: number
  discount_paise: number
  revenue_paise: number
  daily: OfferStatsDay[]
}

/** `POST claims/{id}/redeem/`. */
export type RedeemClaimBody = { bill_paise?: number }

/** `POST redeem/` (counter redemption). */
export type RedeemAtCounterBody = { code: string; phone: string; bill_paise?: number }

export type OfferClaimFilters = { offer?: string; status?: OfferClaimStatus; phone?: string }
