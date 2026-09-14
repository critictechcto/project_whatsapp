import { tokenStore } from './tokens'

/** Exchanges a refresh token for a new pair. Must throw `RefreshRejectedError` when the token is invalid. */
export type RefreshFn = (refreshToken: string) => Promise<{ access: string; refresh: string }>

/** The refresh token was rejected (expired, blacklisted). The session is over. */
export class RefreshRejectedError extends Error {
  constructor(message = 'Session expired') {
    super(message)
    this.name = 'RefreshRejectedError'
  }
}

const LOCK_NAME = 'upchatz-token-refresh'

let refreshFn: RefreshFn | null = null
let inFlight: Promise<string> | null = null
let onSessionEnded: (() => void) | null = null

export function configureRefresh(options: { refresh: RefreshFn; onSessionEnded?: () => void }) {
  refreshFn = options.refresh
  onSessionEnded = options.onSessionEnded ?? null
}

type LockManagerLike = {
  request<T>(name: string, callback: () => Promise<T>): Promise<T>
}

function lockManager(): LockManagerLike | null {
  if (typeof navigator === 'undefined') return null
  const locks = (navigator as Navigator & { locks?: LockManagerLike }).locks
  return locks && typeof locks.request === 'function' ? locks : null
}

async function performRefresh(staleAccess: string | null): Promise<string> {
  if (!refreshFn) throw new Error('configureRefresh() was not called')

  // Another caller (or another tab, while we waited for the lock) may already have refreshed.
  const current = tokenStore.getAccess()
  if (current && current !== staleAccess) return current

  // Read the refresh token inside the lock: another tab may have rotated it.
  const refresh = tokenStore.getRefresh()
  if (!refresh) {
    tokenStore.clear()
    onSessionEnded?.()
    throw new RefreshRejectedError('No refresh token')
  }

  try {
    const tokens = await refreshFn(refresh)
    tokenStore.set(tokens)
    return tokens.access
  } catch (error) {
    if (error instanceof RefreshRejectedError) {
      // Only end the session if nobody rotated the token while our request was out.
      if (tokenStore.getRefresh() === refresh) {
        tokenStore.clear()
        onSessionEnded?.()
      }
    }
    throw error
  }
}

/**
 * Returns a fresh access token. Concurrent callers in this tab share one request, and
 * `navigator.locks` (when available) serialises refreshes across tabs, because the backend
 * rotates and blacklists refresh tokens: two parallel refreshes with the same token would
 * log the user out.
 *
 * @param staleAccess the access token that just failed; if the store already holds a different
 *   one, it is returned without a network call.
 */
export function refreshAccessToken(staleAccess: string | null = tokenStore.getAccess()): Promise<string> {
  if (inFlight) return inFlight

  const locks = lockManager()
  const run = locks ? locks.request(LOCK_NAME, () => performRefresh(staleAccess)) : performRefresh(staleAccess)

  inFlight = run.finally(() => {
    inFlight = null
  })
  return inFlight
}

/** Test helper. */
export function resetRefreshState() {
  inFlight = null
}
