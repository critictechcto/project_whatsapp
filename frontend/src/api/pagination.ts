import { useMemo } from 'react'
import { useInfiniteQuery, type InfiniteData, type QueryKey } from '@tanstack/react-query'
import type { CursorPage } from './types'

/** Extracts the `cursor` query param from a `next`/`previous` URL returned by the API. */
export function cursorFromUrl(url: string | null | undefined): string | undefined {
  if (!url) return undefined
  try {
    return new URL(url, 'http://localhost').searchParams.get('cursor') ?? undefined
  } catch {
    return undefined
  }
}

export type CursorQueryOptions<T> = {
  queryKey: QueryKey
  /** Fetch one page. Pass `cursor` as the `cursor` query param (undefined for the first page). */
  queryFn: (context: { cursor: string | undefined; signal: AbortSignal }) => Promise<CursorPage<T>>
  enabled?: boolean
  staleTime?: number
  refetchInterval?: number | false
}

/**
 * `useInfiniteQuery` over the API's cursor pagination. `items` is every loaded row;
 * render a "Load more" button with `hasNextPage` / `fetchNextPage` (the `Table` component does).
 *
 * ```ts
 * const contacts = useCursorQuery({
 *   queryKey: contactKeys.list(workspaceId, { search }),
 *   queryFn: ({ cursor, signal }) =>
 *     unwrap(api.GET('/api/v1/contacts/', { params: { query: { cursor, search } }, signal })),
 * })
 * ```
 */
export function useCursorQuery<T>({ queryKey, queryFn, enabled, staleTime, refetchInterval }: CursorQueryOptions<T>) {
  const query = useInfiniteQuery<CursorPage<T>, Error, InfiniteData<CursorPage<T>, string | undefined>, QueryKey, string | undefined>({
    queryKey,
    queryFn: ({ pageParam, signal }) => queryFn({ cursor: pageParam, signal }),
    initialPageParam: undefined,
    getNextPageParam: (lastPage) => cursorFromUrl(lastPage.next),
    enabled,
    staleTime,
    refetchInterval,
  })

  const items = useMemo(() => query.data?.pages.flatMap((page) => page.results) ?? [], [query.data])

  return { ...query, items }
}
