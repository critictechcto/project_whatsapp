import { useQuery, useQueryClient, type QueryClient } from '@tanstack/react-query'
import { useSyncExternalStore } from 'react'
import { api, setActiveWorkspaceId, unwrap } from '../../../api/client'
import { queryKeys } from '../../../api/queryKeys'
import type { Me } from '../../../api/types'
import { resetRefreshState } from '../../../lib/auth/refresh'
import { tokenStore } from '../../../lib/auth/tokens'

export const LAST_WORKSPACE_KEY = 'upchatz.lastWorkspace'

export function readLastWorkspace(): string | null {
  try {
    return window.localStorage.getItem(LAST_WORKSPACE_KEY)
  } catch {
    return null
  }
}

export function writeLastWorkspace(workspaceId: string) {
  try {
    window.localStorage.setItem(LAST_WORKSPACE_KEY, workspaceId)
  } catch {
    // ignore
  }
}

/** True while this tab holds an access or refresh token. Re-renders on login/logout in any tab. */
export function useHasSession(): boolean {
  return useSyncExternalStore(tokenStore.subscribe, tokenStore.hasSession, () => false)
}

export function meQueryOptions() {
  return {
    queryKey: queryKeys.me,
    queryFn: ({ signal }: { signal: AbortSignal }) => unwrap(api.GET('/api/v1/auth/me/', { signal })),
    staleTime: 60_000,
  }
}

/** The signed-in user with their workspace memberships. */
export function useMe() {
  const hasSession = useHasSession()
  return useQuery({ ...meQueryOptions(), enabled: hasSession })
}

/** Stores tokens from login/register and primes the `me` query. */
export async function startSession(queryClient: QueryClient, tokens: { access: string; refresh: string }): Promise<Me> {
  queryClient.clear()
  tokenStore.set(tokens)
  return queryClient.fetchQuery(meQueryOptions())
}

/** Local logout without calling the API (other tab logged out, session revoked, refresh rejected). */
export function endSessionLocally(queryClient: QueryClient) {
  tokenStore.clear()
  resetRefreshState()
  setActiveWorkspaceId(null)
  queryClient.clear()
}

export function useLogout() {
  const queryClient = useQueryClient()
  return async () => {
    const refresh = tokenStore.getRefresh()
    if (refresh) {
      // Best effort: blacklist the refresh token. Log out locally even if this fails.
      await api.POST('/api/v1/auth/logout/', { body: { refresh } }).catch(() => undefined)
    }
    endSessionLocally(queryClient)
  }
}

/** Validates a `?next=` value: only paths inside the app, never other origins. */
export function safeNext(next: string | null): string | null {
  if (!next || !next.startsWith('/app') || next.startsWith('//')) return null
  return next
}
