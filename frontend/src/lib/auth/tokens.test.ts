import { afterEach, describe, expect, it, vi } from 'vitest'

afterEach(() => {
  vi.resetModules()
})

async function freshTokens() {
  vi.resetModules()
  return import('./tokens')
}

describe('token store', () => {
  it('removes the refresh token older builds left in localStorage', async () => {
    window.localStorage.setItem('upchatz.refresh', 'legacy-refresh-token')

    const { LEGACY_REFRESH_KEY } = await freshTokens()

    expect(window.localStorage.getItem(LEGACY_REFRESH_KEY)).toBeNull()
  })

  it('keeps the access token in memory only and marks the session in localStorage', async () => {
    const { SESSION_MARKER_KEY, tokenStore } = await freshTokens()

    tokenStore.set('secret-access')

    expect(window.localStorage.getItem(SESSION_MARKER_KEY)).toBe('1')
    for (let i = 0; i < window.localStorage.length; i++) {
      const key = window.localStorage.key(i)!
      expect(window.localStorage.getItem(key)).not.toContain('secret-access')
    }
    expect(tokenStore.getAccess()).toBe('secret-access')
  })

  it('logout clears state and signals other tabs', async () => {
    const { AUTH_CHANNEL_NAME, SESSION_MARKER_KEY, tokenStore } = await freshTokens()
    const posted: unknown[] = []
    const OriginalChannel = globalThis.BroadcastChannel
    globalThis.BroadcastChannel = class {
      constructor(readonly name: string) {}
      addEventListener() {}
      postMessage(data: unknown) {
        if (this.name === AUTH_CHANNEL_NAME) posted.push(data)
      }
      close() {}
    } as unknown as typeof BroadcastChannel
    try {
      const listener = vi.fn()
      tokenStore.subscribe(listener)
      tokenStore.set('access')

      tokenStore.clear()

      expect(tokenStore.getAccess()).toBeNull()
      expect(tokenStore.hasSession()).toBe(false)
      expect(window.localStorage.getItem(SESSION_MARKER_KEY)).toBeNull()
      expect(posted).toEqual([{ type: 'logout' }])
      expect(listener).toHaveBeenCalledTimes(2)
    } finally {
      globalThis.BroadcastChannel = OriginalChannel
    }
  })

  it('ends this tab when another tab removes the marker, and picks up a login elsewhere', async () => {
    const { SESSION_MARKER_KEY, syncSessionAcrossTabs, tokenStore } = await freshTokens()
    tokenStore.set('access')
    const onLogout = vi.fn()
    const listener = vi.fn()
    tokenStore.subscribe(listener)
    const stop = syncSessionAcrossTabs(onLogout)

    window.localStorage.removeItem(SESSION_MARKER_KEY)
    window.dispatchEvent(new StorageEvent('storage', { key: SESSION_MARKER_KEY, oldValue: '1', newValue: null }))
    expect(tokenStore.getAccess()).toBeNull()
    expect(onLogout).toHaveBeenCalledOnce()

    listener.mockClear()
    window.localStorage.setItem(SESSION_MARKER_KEY, '1')
    window.dispatchEvent(new StorageEvent('storage', { key: SESSION_MARKER_KEY, oldValue: null, newValue: '1' }))
    expect(listener).toHaveBeenCalled()
    expect(tokenStore.hasSession()).toBe(true)
    stop()
  })
})
