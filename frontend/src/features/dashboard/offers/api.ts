/** Offers API calls (`/api/v1/offers/`). */
import { useQuery } from '@tanstack/react-query'
import { api, unwrap } from '../../../api/client'
import { isApiError } from '../../../api/errors'
import { cursorFromUrl, useCursorQuery } from '../../../api/pagination'
import { workspaceKeys } from '../../../api/queryKeys'
import type { Schemas } from '../../../api/types'
import type { OfferClaim, OfferClaimFilters, OfferCodeWrite, RedeemAtCounterBody, RedeemClaimBody } from './types'

export const offerKeys = workspaceKeys('offers')

const pathOf = (id: string) => ({ params: { path: { id } } })

export const offersApi = {
  listCodes: (signal?: AbortSignal) => unwrap(api.GET('/api/v1/offers/codes/', { params: { query: { page_size: 100 } }, signal })),
  getCode: (id: string, signal?: AbortSignal) => unwrap(api.GET('/api/v1/offers/codes/{id}/', { ...pathOf(id), signal })),
  createCode: (body: OfferCodeWrite) => unwrap(api.POST('/api/v1/offers/codes/', { body })),
  updateCode: (id: string, body: Partial<OfferCodeWrite>) => unwrap(api.PATCH('/api/v1/offers/codes/{id}/', { ...pathOf(id), body })),
  deleteCode: (id: string) => unwrap(api.DELETE('/api/v1/offers/codes/{id}/', pathOf(id))),
  stats: (id: string, signal?: AbortSignal) => unwrap(api.GET('/api/v1/offers/codes/{id}/stats/', { ...pathOf(id), signal })),
  listClaims: (filters: OfferClaimFilters & { cursor?: string }, signal?: AbortSignal) =>
    unwrap(api.GET('/api/v1/offers/claims/', { params: { query: { ...filters, phone: filters.phone || undefined } }, signal })),
  redeemClaim: (id: string, body: RedeemClaimBody) => unwrap(api.POST('/api/v1/offers/claims/{id}/redeem/', { ...pathOf(id), body })),
  redeemAtCounter: (body: RedeemAtCounterBody) => unwrap(api.POST('/api/v1/offers/redeem/', { body })),
}

export type OfferCatalogItem = Schemas['Product']

/** Catalog items for choosing what an offer applies to (active and inactive, in catalog order). */
export function useOfferCatalogItems(workspaceId: string) {
  return useQuery({
    queryKey: offerKeys.custom(workspaceId, 'catalog-items'),
    queryFn: async ({ signal }) => {
      const items: OfferCatalogItem[] = []
      let cursor: string | undefined
      for (let page = 0; page < 20; page++) {
        const data = await unwrap(api.GET('/api/v1/catalog/products/', { params: { query: { page_size: 200, cursor } }, signal }))
        items.push(...data.results)
        cursor = cursorFromUrl(data.next)
        if (!cursor) break
      }
      return items
    },
    staleTime: 60_000,
  })
}

/** Every code. Workspaces have a handful, so one page is enough. */
export function useOfferCodes(workspaceId: string) {
  return useQuery({
    queryKey: offerKeys.list(workspaceId, { page_size: 100 }),
    queryFn: async ({ signal }) => (await offersApi.listCodes(signal)).results,
  })
}

export function useOfferCode(workspaceId: string, id: string | undefined) {
  return useQuery({
    queryKey: offerKeys.detail(workspaceId, id ?? ''),
    queryFn: ({ signal }) => offersApi.getCode(id ?? '', signal),
    enabled: Boolean(id),
  })
}

export function useOfferStats(workspaceId: string, id: string) {
  return useQuery({
    queryKey: offerKeys.custom(workspaceId, 'stats', id),
    queryFn: ({ signal }) => offersApi.stats(id, signal),
  })
}

export function useOfferClaims(workspaceId: string, filters: OfferClaimFilters) {
  return useCursorQuery<OfferClaim>({
    queryKey: offerKeys.custom(workspaceId, 'claims', filters),
    queryFn: ({ cursor, signal }) => offersApi.listClaims({ ...filters, cursor }, signal),
  })
}

/** The plan doesn't include commerce (409 `feature_not_available`). */
export function isCommerceUnavailable(error: unknown): boolean {
  return isApiError(error) && (error.code === 'feature_not_available' || error.code === 'commerce_not_enabled')
}
