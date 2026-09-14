/**
 * Token storage.
 *
 * - The access token lives in memory only (lost on reload, recovered via refresh).
 * - The refresh token lives in localStorage so the session survives reloads and is shared by tabs.
 * - Removing the refresh token in one tab logs out every tab (the `storage` event).
 */

export const REFRESH_TOKEN_KEY = 'upchatz.refresh'

type Listener = () => void

let accessToken: string | null = null
const listeners = new Set<Listener>()

function notify() {
  for (const listener of listeners) listener()
}

function readStorage(): string | null {
  try {
    return window.localStorage.getItem(REFRESH_TOKEN_KEY)
  } catch {
    return null
  }
}

export const tokenStore = {
  getAccess(): string | null {
    return accessToken
  },
  getRefresh(): string | null {
    return readStorage()
  },
  hasSession(): boolean {
    return Boolean(accessToken || readStorage())
  },
  set(tokens: { access: string; refresh?: string | null }) {
    accessToken = tokens.access
    if (tokens.refresh) {
      try {
        window.localStorage.setItem(REFRESH_TOKEN_KEY, tokens.refresh)
      } catch {
        // Storage can be unavailable (private mode); the session then lasts for this tab only.
      }
    }
    notify()
  },
  /** Clears both tokens. Other tabs see the storage removal and log out too. */
  clear() {
    const had = accessToken !== null || readStorage() !== null
    accessToken = null
    try {
      window.localStorage.removeItem(REFRESH_TOKEN_KEY)
    } catch {
      // ignore
    }
    if (had) notify()
  },
  /** Called when the session changes in this tab or another one. */
  subscribe(listener: Listener): () => void {
    listeners.add(listener)
    return () => listeners.delete(listener)
  },
}

/**
 * Listens for logout (refresh token removed) in other tabs.
 * A rotated refresh token written by another tab is picked up lazily on the next refresh.
 */
export function syncLogoutAcrossTabs(onLogout: () => void): () => void {
  const handler = (event: StorageEvent) => {
    if (event.key !== REFRESH_TOKEN_KEY && event.key !== null) return
    if (event.newValue === null) {
      accessToken = null
      notify()
      onLogout()
    }
  }
  window.addEventListener('storage', handler)
  return () => window.removeEventListener('storage', handler)
}
