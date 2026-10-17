/** Offer code types, from the generated schema (`docs/contracts/services-and-offers.md`, "Offers"). */
import type { paths } from '../../../api/schema'
import type { Schemas } from '../../../api/types'

export type OfferDiscountType = Schemas['OfferDiscountTypeEnum']
export type OfferAppliesTo = Schemas['OfferAppliesToEnum']
export type OfferClaimStatus = Schemas['OfferClaimStatusEnum']

export type OfferCode = Schemas['OfferCode']
/** A catalog item an `items` offer applies to. */
export type OfferItem = Schemas['OfferItem']
/** Body of `POST codes/`; `PATCH codes/{id}/` takes any part of it. */
export type OfferCodeWrite = Schemas['OfferCodeRequest']
export type OfferClaim = Schemas['OfferClaim']
export type OfferStats = Schemas['OfferStats']
export type OfferStatsDay = Schemas['OfferStatsDay']

/** `POST claims/{id}/redeem/`. */
export type RedeemClaimBody = Schemas['RedeemClaimRequest']
/** `POST redeem/` (counter redemption). */
export type RedeemAtCounterBody = Schemas['CounterRedeemRequest']

export type OfferClaimFilters = Omit<NonNullable<paths['/api/v1/offers/claims/']['get']['parameters']['query']>, 'cursor' | 'page_size'>
