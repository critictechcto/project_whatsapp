/**
 * Session state in the browser.
 *
 * - The access token lives in memory only (lost on reload, recovered with a refresh).
 * - The refresh token is an HttpOnly cookie that script can never read; the API sets, rotates
 *   and clears it on `/api/v1/auth/`.
 * - A non-secret marker in localStorage (`upchatz.session` = `1`) says a session may exist, so a
 *   reload tries one refresh while signed-out visitors go straight to login without a 401.
 * - Tabs share the fresh access token over a BroadcastChannel and log out together when the
 *   marker is removed (the `storage` event).
 */

export const SESSION_MARKER_KEY = 'upchatz.session'
/** Where the refresh token used to be stored. Removed on load. */
export const LEGACY_REFRESH_KEY = 'upchatz.refresh'
export const AUTH_CHANNEL_NAME = 'upchatz-auth'

type Listener = () => void

type AuthMessage = { type: 'access'; access: string } | { type: 'logout' }

let accessToken: string | null = null
/** This tab signed in or refreshed: lets refresh work even when localStorage is unavailable. */
let sessionInTab = false
const listeners = new Set<Listener>()

function notify() {
  for (const listener of listeners) listener()
}

function readMarker(): boolean {
  try {
    return window.localStorage.getItem(SESSION_MARKER_KEY) === '1'
  } catch {
    return false
  }
}

function writeMarker(present: boolean) {
  try {
    if (present) window.localStorage.setItem(SESSION_MARKER_KEY, '1')
    else window.localStorage.removeItem(SESSION_MARKER_KEY)
  } catch {
    // Storage can be unavailable (private mode); the session then lasts for this tab only.
  }
}

/** Removes the refresh token older builds kept in localStorage. */
export function removeLegacyRefreshToken() {
  try {
    window.localStorage.removeItem(LEGACY_REFRESH_KEY)
  } catch {
    // ignore
  }
}

if (typeof window !== 'undefined') removeLegacyRefreshToken()

let channel: BroadcastChannel | null | undefined

function authChannel(): BroadcastChannel | null {
  if (channel !== undefined) return channel
  channel = typeof BroadcastChannel === 'function' ? new BroadcastChannel(AUTH_CHANNEL_NAME) : null
  channel?.addEventListener('message', (event: MessageEvent<AuthMessage>) => handleMessage(event.data))
  // Node (tests) keeps the process alive for an open channel; browsers have no `unref`.
  ;(channel as { unref?: () => void } | null)?.unref?.()
  return channel
}

function post(message: AuthMessage) {
  try {
    authChannel()?.postMessage(message)
  } catch {
    // A closed channel: other tabs catch up on their next refresh.
  }
}

function handleMessage(message: AuthMessage | null | undefined) {
  if (!message || typeof message !== 'object') return
  if (message.type === 'access' && typeof message.access === 'string') {
    if (accessToken === message.access) return
    accessToken = message.access
    sessionInTab = true
    notify()
  } else if (message.type === 'logout') {
    endLocally()
  }
}

let onRemoteLogout: (() => void) | null = null

function endLocally() {
  accessToken = null
  sessionInTab = false
  notify()
  onRemoteLogout?.()
}

export const tokenStore = {
  getAccess(): string | null {
    return accessToken
  },
  /** True when this tab holds an access token or another page load left a session marker. */
  hasSession(): boolean {
    return Boolean(accessToken || readMarker())
  },
  /** True when a refresh may recover a session (the marker is set). */
  mayRefresh(): boolean {
    return sessionInTab || readMarker()
  },
  /** Stores a new access token (login, register, refresh) and marks the session. */
  set(access: string, { broadcast = false }: { broadcast?: boolean } = {}) {
    accessToken = access
    sessionInTab = true
    writeMarker(true)
    authChannel() // listen for tokens other tabs refresh from now on
    if (broadcast) post({ type: 'access', access })
    notify()
  },
  /** Ends the session in this tab and every other tab. */
  clear() {
    const had = accessToken !== null || sessionInTab || readMarker()
    accessToken = null
    sessionInTab = false
    writeMarker(false)
    if (had) {
      post({ type: 'logout' })
      notify()
    }
  },
  /** Called when the session changes in this tab or another one. */
  subscribe(listener: Listener): () => void {
    authChannel()
    listeners.add(listener)
    return () => listeners.delete(listener)
  },
}

/**
 * Follows other tabs: logout (the marker removed, or a `logout` broadcast) ends this tab's session;
 * a login elsewhere (the marker set) lets this tab's guards pick the session up.
 */
export function syncSessionAcrossTabs(onLogout: () => void): () => void {
  authChannel()
  const handler = (event: StorageEvent) => {
    if (event.key !== SESSION_MARKER_KEY && event.key !== null) return
    if (event.newValue === null) {
      endLocally()
    } else if (event.oldValue === null) {
      notify()
    }
  }
  onRemoteLogout = onLogout
  window.addEventListener('storage', handler)
  return () => {
    window.removeEventListener('storage', handler)
    if (onRemoteLogout === onLogout) onRemoteLogout = null
  }
}

/** Test helper: forgets the channel so a test can install a fake `BroadcastChannel`. */
export function resetAuthChannel() {
  channel?.close()
  channel = undefined
}

/** Test helper: drops this tab's in-memory state but keeps localStorage, like a page reload. */
export function simulateReloadForTests() {
  accessToken = null
  sessionInTab = false
  resetAuthChannel()
}
