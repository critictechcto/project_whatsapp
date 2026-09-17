import { tokenStore } from './tokens'

/**
 * Asks the API for a new access token using the HttpOnly refresh cookie (which the API rotates).
 * Must throw `RefreshRejectedError` when the session is over (no cookie, expired, revoked).
 */
export type RefreshFn = () => Promise<{ access: string }>

/** The refresh cookie was rejected (missing, expired, blacklisted). The session is over. */
export class RefreshRejectedError extends Error {
  constructor(message = 'Session expired') {
    super(message)
    this.name = 'RefreshRejectedError'
  }
}

export const REFRESH_LOCK_NAME = 'upchatz-refresh'

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

  // Another caller, or another tab while we waited for the lock (its token arrives over the
  // BroadcastChannel), already refreshed: reuse that token instead of rotating the cookie again.
  const current = tokenStore.getAccess()
  if (current && current !== staleAccess) return current

  try {
    const { access } = await refreshFn()
    tokenStore.set(access, { broadcast: true })
    return access
  } catch (error) {
    if (error instanceof RefreshRejectedError) {
      // Without the lock another tab may have refreshed meanwhile; keep its session.
      const after = tokenStore.getAccess()
      if (!after || after === staleAccess) {
        tokenStore.clear()
        onSessionEnded?.()
      }
    }
    throw error
  }
}

/**
 * Returns a fresh access token. Concurrent callers in this tab share one request, and the Web
 * Locks API (when available) serialises refreshes across tabs: every refresh rotates the cookie
 * and blacklists the old token, so a tab waits for another tab's refresh and reuses its token.
 * Without Web Locks this falls back to the in-tab single flight.
 *
 * @param staleAccess the access token that just failed; if the store already holds a different
 *   one, it is returned without a network call.
 */
export function refreshAccessToken(staleAccess: string | null = tokenStore.getAccess()): Promise<string> {
  if (inFlight) return inFlight

  const locks = lockManager()
  const run = locks ? locks.request(REFRESH_LOCK_NAME, () => performRefresh(staleAccess)) : performRefresh(staleAccess)

  inFlight = run.finally(() => {
    inFlight = null
  })
  return inFlight
}

/**
 * Session bootstrap for requests: when there is no access token in memory but the session marker
 * says a session may exist (after a reload), refreshes once. Signed-out visitors (no marker)
 * never call the API. Resolves to the access token, or null when there is no session.
 */
export async function ensureAccessToken(): Promise<string | null> {
  const current = tokenStore.getAccess()
  if (current) return current
  if (!tokenStore.mayRefresh()) return null
  try {
    return await refreshAccessToken(null)
  } catch {
    return null
  }
}

/** Test helper. */
export function resetRefreshState() {
  inFlight = null
}
