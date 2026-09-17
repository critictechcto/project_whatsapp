import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { configureRefresh, ensureAccessToken, REFRESH_LOCK_NAME, refreshAccessToken, RefreshRejectedError } from './refresh'
import { AUTH_CHANNEL_NAME, resetAuthChannel, SESSION_MARKER_KEY, simulateReloadForTests, tokenStore } from './tokens'

function deferred() {
  let resolve!: () => void
  const promise = new Promise<void>((r) => {
    resolve = r
  })
  return { promise, resolve }
}

/** Minimal exclusive, FIFO stand-in for the Web Locks API (shared by "tabs" in one test). */
function installLocks() {
  let tail: Promise<unknown> = Promise.resolve()
  const locks = {
    request<T>(_name: string, callback: () => Promise<T>): Promise<T> {
      const run = tail.then(callback)
      tail = run.catch(() => undefined)
      return run
    },
  }
  Object.defineProperty(navigator, 'locks', { value: locks, configurable: true })
  return locks
}

/** In-memory BroadcastChannel: delivers to every other instance with the same name. */
class FakeBroadcastChannel {
  static instances = new Set<FakeBroadcastChannel>()
  private readonly listeners = new Set<(event: MessageEvent) => void>()
  constructor(readonly name: string) {
    FakeBroadcastChannel.instances.add(this)
  }
  addEventListener(_type: 'message', listener: (event: MessageEvent) => void) {
    this.listeners.add(listener)
  }
  postMessage(data: unknown) {
    for (const other of FakeBroadcastChannel.instances) {
      if (other === this || other.name !== this.name) continue
      for (const listener of other.listeners) listener({ data } as MessageEvent)
    }
  }
  close() {
    FakeBroadcastChannel.instances.delete(this)
  }
}

let originalChannel: typeof BroadcastChannel | undefined

beforeEach(() => {
  originalChannel = globalThis.BroadcastChannel
  FakeBroadcastChannel.instances.clear()
  globalThis.BroadcastChannel = FakeBroadcastChannel as unknown as typeof BroadcastChannel
  resetAuthChannel()
})

afterEach(() => {
  Reflect.deleteProperty(navigator, 'locks')
  resetAuthChannel()
  globalThis.BroadcastChannel = originalChannel as typeof BroadcastChannel
})

describe('refreshAccessToken', () => {
  it('shares one refresh request between concurrent callers in a tab', async () => {
    const gate = deferred()
    const refresh = vi.fn(async () => {
      await gate.promise
      return { access: 'access-2' }
    })
    configureRefresh({ refresh })
    tokenStore.set('access-1')

    const calls = [refreshAccessToken('access-1'), refreshAccessToken('access-1'), refreshAccessToken('access-1')]
    gate.resolve()

    await expect(Promise.all(calls)).resolves.toEqual(['access-2', 'access-2', 'access-2'])
    expect(refresh).toHaveBeenCalledTimes(1)
    expect(tokenStore.getAccess()).toBe('access-2')
  })

  it('returns the current token without a request when it was already refreshed', async () => {
    const refresh = vi.fn(async () => ({ access: 'unused' }))
    configureRefresh({ refresh })
    tokenStore.set('newer')

    await expect(refreshAccessToken('stale')).resolves.toBe('newer')
    expect(refresh).not.toHaveBeenCalled()
  })

  it('waits for another tab holding the lock and reuses the token it broadcast (one network refresh)', async () => {
    const locks = installLocks()
    const refresh = vi.fn(async () => ({ access: 'access-mine' }))
    configureRefresh({ refresh })
    tokenStore.set('stale')
    const otherTab = new FakeBroadcastChannel(AUTH_CHANNEL_NAME)

    // The other tab takes the lock first, refreshes (one network call) and shares the token.
    const otherRefresh = deferred()
    const held = locks.request(REFRESH_LOCK_NAME, async () => {
      await otherRefresh.promise
      otherTab.postMessage({ type: 'access', access: 'access-from-other-tab' })
    })
    const mine = refreshAccessToken('stale')
    otherRefresh.resolve()
    await held

    await expect(mine).resolves.toBe('access-from-other-tab')
    expect(refresh).not.toHaveBeenCalled()
  })

  it('shares its fresh token with other tabs', async () => {
    installLocks()
    configureRefresh({ refresh: async () => ({ access: 'fresh' }) })
    tokenStore.set('stale')
    const otherTab = new FakeBroadcastChannel(AUTH_CHANNEL_NAME)
    const received: unknown[] = []
    otherTab.addEventListener('message', (event) => received.push(event.data))

    await refreshAccessToken('stale')

    expect(received).toEqual([{ type: 'access', access: 'fresh' }])
  })

  it('falls back to the in-tab single flight without Web Locks or BroadcastChannel', async () => {
    Reflect.deleteProperty(globalThis, 'BroadcastChannel')
    resetAuthChannel()
    const refresh = vi.fn(async () => ({ access: 'fresh' }))
    configureRefresh({ refresh })
    tokenStore.set('stale')

    await expect(Promise.all([refreshAccessToken('stale'), refreshAccessToken('stale')])).resolves.toEqual(['fresh', 'fresh'])
    expect(refresh).toHaveBeenCalledTimes(1)
  })

  it('ends the session in every tab when the refresh cookie is rejected', async () => {
    const onSessionEnded = vi.fn()
    configureRefresh({
      refresh: async () => {
        throw new RefreshRejectedError()
      },
      onSessionEnded,
    })
    tokenStore.set('access-1')
    const otherTab = new FakeBroadcastChannel(AUTH_CHANNEL_NAME)
    const received: unknown[] = []
    otherTab.addEventListener('message', (event) => received.push(event.data))

    await expect(refreshAccessToken('access-1')).rejects.toBeInstanceOf(RefreshRejectedError)
    expect(tokenStore.hasSession()).toBe(false)
    expect(window.localStorage.getItem(SESSION_MARKER_KEY)).toBeNull()
    expect(onSessionEnded).toHaveBeenCalledOnce()
    expect(received).toContainEqual({ type: 'logout' })
  })
})

describe('session bootstrap (ensureAccessToken)', () => {
  it('never calls the API for a signed-out visitor (no marker)', async () => {
    const refresh = vi.fn(async () => ({ access: 'unused' }))
    configureRefresh({ refresh })

    await expect(ensureAccessToken()).resolves.toBeNull()
    expect(refresh).not.toHaveBeenCalled()
    expect(tokenStore.hasSession()).toBe(false)
  })

  it('refreshes once after a reload when the marker says a session may exist', async () => {
    const refresh = vi.fn(async () => ({ access: 'restored' }))
    configureRefresh({ refresh })
    tokenStore.set('before-reload')
    simulateReloadForTests()
    expect(tokenStore.getAccess()).toBeNull()
    expect(tokenStore.hasSession()).toBe(true)

    const results = await Promise.all([ensureAccessToken(), ensureAccessToken()])

    expect(results).toEqual(['restored', 'restored'])
    expect(refresh).toHaveBeenCalledTimes(1)
  })

  it('clears the marker when the bootstrap refresh is rejected', async () => {
    configureRefresh({
      refresh: async () => {
        throw new RefreshRejectedError()
      },
    })
    window.localStorage.setItem(SESSION_MARKER_KEY, '1')

    await expect(ensureAccessToken()).resolves.toBeNull()
    expect(window.localStorage.getItem(SESSION_MARKER_KEY)).toBeNull()
    expect(tokenStore.hasSession()).toBe(false)
  })
})
