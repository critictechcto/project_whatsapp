import { afterEach, describe, expect, it, vi } from 'vitest'
import { configureRefresh, refreshAccessToken, RefreshRejectedError } from './refresh'
import { REFRESH_TOKEN_KEY, tokenStore } from './tokens'

function deferred() {
  let resolve!: () => void
  const promise = new Promise<void>((r) => {
    resolve = r
  })
  return { promise, resolve }
}

/** Minimal exclusive, FIFO stand-in for the Web Locks API. */
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

afterEach(() => {
  Reflect.deleteProperty(navigator, 'locks')
})

describe('refreshAccessToken', () => {
  it('shares one refresh request between concurrent callers', async () => {
    const gate = deferred()
    const refresh = vi.fn(async (token: string) => {
      await gate.promise
      return { access: 'access-2', refresh: `${token}-rotated` }
    })
    configureRefresh({ refresh })
    tokenStore.set({ access: 'access-1', refresh: 'refresh-1' })

    const calls = [refreshAccessToken('access-1'), refreshAccessToken('access-1'), refreshAccessToken('access-1')]
    gate.resolve()

    await expect(Promise.all(calls)).resolves.toEqual(['access-2', 'access-2', 'access-2'])
    expect(refresh).toHaveBeenCalledTimes(1)
    expect(refresh).toHaveBeenCalledWith('refresh-1')
    expect(tokenStore.getRefresh()).toBe('refresh-1-rotated')
  })

  it('returns the current token without a request when it was already refreshed', async () => {
    const refresh = vi.fn(async () => ({ access: 'unused', refresh: 'unused' }))
    configureRefresh({ refresh })
    tokenStore.set({ access: 'newer', refresh: 'refresh-1' })

    await expect(refreshAccessToken('stale')).resolves.toBe('newer')
    expect(refresh).not.toHaveBeenCalled()
  })

  it('waits for the cross-tab lock and uses the refresh token another tab rotated', async () => {
    const locks = installLocks()
    const refresh = vi.fn(async (token: string) => ({ access: 'access-mine', refresh: `${token}-next` }))
    configureRefresh({ refresh })
    tokenStore.set({ access: 'stale', refresh: 'refresh-old' })

    // Another tab holds the lock and rotates the shared refresh token.
    const otherTab = deferred()
    const held = locks.request('upchatz-token-refresh', async () => {
      await otherTab.promise
      window.localStorage.setItem(REFRESH_TOKEN_KEY, 'refresh-from-other-tab')
    })
    const mine = refreshAccessToken('stale')
    otherTab.resolve()
    await held

    await expect(mine).resolves.toBe('access-mine')
    expect(refresh).toHaveBeenCalledTimes(1)
    // Never the blacklisted token.
    expect(refresh).toHaveBeenCalledWith('refresh-from-other-tab')
  })

  it('ends the session when the refresh token is rejected', async () => {
    const onSessionEnded = vi.fn()
    configureRefresh({
      refresh: async () => {
        throw new RefreshRejectedError()
      },
      onSessionEnded,
    })
    tokenStore.set({ access: 'access-1', refresh: 'refresh-1' })

    await expect(refreshAccessToken('access-1')).rejects.toBeInstanceOf(RefreshRejectedError)
    expect(tokenStore.hasSession()).toBe(false)
    expect(onSessionEnded).toHaveBeenCalledOnce()
  })
})
