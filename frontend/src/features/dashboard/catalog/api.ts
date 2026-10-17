import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useCallback } from 'react'
import { api, apiFetch, unwrap } from '../../../api/client'
import { cursorFromUrl, useCursorQuery } from '../../../api/pagination'
import { workspaceKeys } from '../../../api/queryKeys'
import { useRealtimeEvent } from '../../../lib/realtime/hooks'
import { useWorkspace } from '../../../lib/workspace'
import type { paths } from '../../../api/schema'
import type { Schemas } from '../../../api/types'
import type {
  Collection,
  MetaCatalog,
  MetaReviewStatus,
  Product,
  ProductAvailability,
  ProductImportResult,
  ProductKind,
  ProductWriteRequest,
  WhatsAppAccount,
} from './lib/types'

/** Every catalog query key starts with `['ws', workspaceId, 'catalog']`. */
export const catalogKeys = workspaceKeys('catalog')

export type ProductFilters = {
  search?: string
  /** Collection id, or `none` for products without a collection. */
  collection?: string
  isActive?: boolean
  availability?: ProductAvailability
  review?: MetaReviewStatus
  kind?: ProductKind
}

type ProductPage = { next?: string | null; previous?: string | null; results: Product[] }

// TODO(api:types): the generated Product has no `kind`/`duration_minutes` and the list query no `kind` yet.
// These casts isolate that; delete them after `npm run api:types`.
type GeneratedProductQuery = NonNullable<paths['/api/v1/catalog/products/']['get']['parameters']['query']>
const asProduct = (product: Schemas['Product']) => product as Product
const asProductPage = (page: { next?: string | null; previous?: string | null; results: Schemas['Product'][] }) => page as ProductPage
const asWriteBody = (body: ProductWriteRequest) => body as Schemas['ProductWriteRequest']

export function fetchProduct(id: string, signal?: AbortSignal): Promise<Product> {
  return unwrap(api.GET('/api/v1/catalog/products/{id}/', { params: { path: { id } }, signal })).then(asProduct)
}

export function createProduct(body: ProductWriteRequest): Promise<Product> {
  return unwrap(api.POST('/api/v1/catalog/products/', { body: asWriteBody(body) })).then(asProduct)
}

export function updateProduct(id: string, body: ProductWriteRequest): Promise<Product> {
  return unwrap(api.PATCH('/api/v1/catalog/products/{id}/', { params: { path: { id } }, body: asWriteBody(body) })).then(asProduct)
}

const MAX_PAGES = 50

/** Loads every page of a cursor list (used for small lists and full reorder lists). */
async function fetchAll<T>(fetchPage: (cursor: string | undefined) => Promise<{ next?: string | null; results: T[] }>): Promise<T[]> {
  const items: T[] = []
  let cursor: string | undefined
  for (let page = 0; page < MAX_PAGES; page++) {
    const data = await fetchPage(cursor)
    items.push(...data.results)
    cursor = cursorFromUrl(data.next)
    if (!cursor) break
  }
  return items
}

export function useProducts(filters: ProductFilters) {
  const { workspaceId } = useWorkspace()
  const query = {
    page_size: 50,
    search: filters.search || undefined,
    collection: filters.collection || undefined,
    is_active: filters.isActive,
    availability: filters.availability,
    meta_review_status: filters.review,
    kind: filters.kind,
  }
  return useCursorQuery<Product>({
    queryKey: catalogKeys.list(workspaceId, { resource: 'products', ...query }),
    queryFn: ({ cursor, signal }) =>
      unwrap(
        api.GET('/api/v1/catalog/products/', { params: { query: { ...query, cursor } as GeneratedProductQuery }, signal }),
      ).then(asProductPage),
  })
}

/** Every product in position order, for reordering. */
export function useAllProducts(enabled: boolean) {
  const { workspaceId } = useWorkspace()
  return useQuery({
    queryKey: catalogKeys.list(workspaceId, { resource: 'products', all: true }),
    queryFn: ({ signal }) =>
      fetchAll((cursor) =>
        unwrap(api.GET('/api/v1/catalog/products/', { params: { query: { page_size: 200, cursor } }, signal })).then(asProductPage),
      ),
    enabled,
  })
}

export function useProduct(id: string | undefined) {
  const { workspaceId } = useWorkspace()
  return useQuery({
    queryKey: catalogKeys.detail(workspaceId, id ?? ''),
    queryFn: ({ signal }) => fetchProduct(id ?? '', signal),
    enabled: Boolean(id),
  })
}

export function useCollections() {
  const { workspaceId } = useWorkspace()
  return useQuery<Collection[]>({
    queryKey: catalogKeys.custom(workspaceId, 'collections'),
    queryFn: ({ signal }) =>
      fetchAll((cursor) => unwrap(api.GET('/api/v1/catalog/collections/', { params: { query: { page_size: 200, cursor } }, signal }))),
  })
}

export function useMetaCatalogs() {
  const { workspaceId } = useWorkspace()
  return useQuery<MetaCatalog[]>({
    queryKey: catalogKeys.custom(workspaceId, 'meta-catalogs'),
    queryFn: async ({ signal }) => (await unwrap(api.GET('/api/v1/catalog/meta-catalogs/', { params: { query: { page_size: 50 } }, signal }))).results,
  })
}

/** Catalogs in the seller's Meta business for one WABA. Errors (e.g. missing permissions) are shown, not retried. */
export function useAvailableCatalogs(wabaId: string, enabled: boolean) {
  const { workspaceId } = useWorkspace()
  return useQuery({
    queryKey: catalogKeys.custom(workspaceId, 'available-catalogs', wabaId),
    queryFn: ({ signal }) => unwrap(api.GET('/api/v1/catalog/meta-catalogs/available/', { params: { query: { waba_id: wabaId } }, signal })),
    enabled: enabled && Boolean(wabaId),
    retry: false,
  })
}

export function useWhatsAppAccounts(enabled = true) {
  const { workspaceId } = useWorkspace()
  return useQuery<WhatsAppAccount[]>({
    queryKey: catalogKeys.custom(workspaceId, 'whatsapp-accounts'),
    queryFn: async ({ signal }) => (await unwrap(api.GET('/api/v1/whatsapp/accounts/', { params: { query: { page_size: 50 } }, signal }))).results,
    enabled,
  })
}

/** Invalidates every catalog query of the workspace. */
export function useInvalidateCatalog() {
  const { workspaceId } = useWorkspace()
  const queryClient = useQueryClient()
  return useCallback(() => queryClient.invalidateQueries({ queryKey: catalogKeys.all(workspaceId) }), [queryClient, workspaceId])
}

/** Refetches catalog data when the server reports Meta sync progress. */
export function useCatalogSyncRefresh() {
  const invalidate = useInvalidateCatalog()
  useRealtimeEvent('catalog.sync', () => {
    void invalidate()
  })
}

/** `POST products/{id}/image/` as multipart. */
export function uploadProductImage(id: string, file: File): Promise<Product> {
  const body = new FormData()
  body.append('file', file, file.name)
  return apiFetch<Product>(`/api/v1/catalog/products/${encodeURIComponent(id)}/image/`, { method: 'POST', body })
}

/** `POST products/import/` as multipart. */
export function importProducts(file: File): Promise<ProductImportResult> {
  const body = new FormData()
  body.append('file', file, file.name)
  return apiFetch<ProductImportResult>('/api/v1/catalog/products/import/', { method: 'POST', body })
}
