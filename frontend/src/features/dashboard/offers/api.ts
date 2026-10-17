/**
 * Offers API calls. The endpoints aren't in `openapi.yml` yet, so they go through `apiFetch` (same
 * auth and workspace header as the typed client).
 *
 * TODO: switch to generated types after api:types — replace each `apiFetch` call with the typed
 * `unwrap(api.GET|POST|PATCH|DELETE('/api/v1/offers/...'))` and import the types from `api/types`.
 */
import { useQuery } from '@tanstack/react-query'
import { apiFetch } from '../../../api/client'
import { isApiError } from '../../../api/errors'
import { useCursorQuery } from '../../../api/pagination'
import { workspaceKeys } from '../../../api/queryKeys'
import type { CursorPage } from '../../../api/types'
import type {
  OfferClaim,
  OfferClaimFilters,
  OfferCode,
  OfferCodeWrite,
  OfferStats,
  RedeemAtCounterBody,
  RedeemClaimBody,
} from './types'

export const offerKeys = workspaceKeys('offers')

const BASE = '/api/v1/offers'

function query(params: Record<string, string | number | undefined>): string {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) if (value !== undefined && value !== '') search.set(key, String(value))
  const text = search.toString()
  return text ? `?${text}` : ''
}

const json = (method: string, body?: unknown): RequestInit => ({ method, body: body === undefined ? undefined : JSON.stringify(body) })

export const offersApi = {
  listCodes: (signal?: AbortSignal) => apiFetch<CursorPage<OfferCode>>(`${BASE}/codes/${query({ page_size: 100 })}`, { signal }),
  getCode: (id: string, signal?: AbortSignal) => apiFetch<OfferCode>(`${BASE}/codes/${encodeURIComponent(id)}/`, { signal }),
  createCode: (body: OfferCodeWrite) => apiFetch<OfferCode>(`${BASE}/codes/`, json('POST', body)),
  updateCode: (id: string, body: Partial<OfferCodeWrite>) => apiFetch<OfferCode>(`${BASE}/codes/${encodeURIComponent(id)}/`, json('PATCH', body)),
  deleteCode: (id: string) => apiFetch<void>(`${BASE}/codes/${encodeURIComponent(id)}/`, { method: 'DELETE' }),
  stats: (id: string, signal?: AbortSignal) => apiFetch<OfferStats>(`${BASE}/codes/${encodeURIComponent(id)}/stats/`, { signal }),
  listClaims: (filters: OfferClaimFilters & { cursor?: string }, signal?: AbortSignal) =>
    apiFetch<CursorPage<OfferClaim>>(`${BASE}/claims/${query(filters)}`, { signal }),
  redeemClaim: (id: string, body: RedeemClaimBody) => apiFetch<OfferClaim>(`${BASE}/claims/${encodeURIComponent(id)}/redeem/`, json('POST', body)),
  redeemAtCounter: (body: RedeemAtCounterBody) => apiFetch<OfferClaim>(`${BASE}/redeem/`, json('POST', body)),
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
