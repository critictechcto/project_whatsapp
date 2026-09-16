import '@testing-library/jest-dom/vitest'
import { cleanup, configure, getConfig } from '@testing-library/react'
import { afterAll, afterEach, beforeAll, beforeEach } from 'vitest'
import { setActiveWorkspaceId } from '../api/client'
import { resetRefreshState } from '../lib/auth/refresh'
import { tokenStore } from '../lib/auth/tokens'
import { clearSubscriptions } from '../lib/realtime/registry'
import { resetMockDb } from '../mocks/db'
import { server } from '../mocks/node'
import { mockRealtime } from '../mocks/realtime'

const defaultGetElementError = getConfig().getElementError

configure({
  // Lazy route chunks can take over 1 s to load when the whole suite runs in parallel.
  asyncUtilTimeout: 5_000,
  /*
   * The default error pretty-prints the whole DOM. Inside `waitFor`/`findBy*` every failed poll (each
   * mutation batch and every 50 ms) built that message and threw it away, which on a dashboard page
   * cost more CPU than the queries themselves and starved parallel workers into timeouts. While a
   * poll runs, Testing Library sets `_disableExpensiveErrorDiagnostics`; skip the DOM then. A timeout
   * still reports the DOM: waitFor's `onTimeout` calls this again outside the poll.
   */
  getElementError(message, container) {
    if (!(getConfig() as { _disableExpensiveErrorDiagnostics?: boolean })._disableExpensiveErrorDiagnostics) {
      return defaultGetElementError(message, container)
    }
    const error = new Error(message ?? '')
    error.name = 'TestingLibraryElementError'
    return error
  },
})

beforeAll(() => {
  server.listen({ onUnhandledRequest: 'error' })
})

beforeEach(() => {
  resetMockDb()
})

afterEach(() => {
  cleanup()
  server.resetHandlers()
  tokenStore.clear()
  resetRefreshState()
  setActiveWorkspaceId(null)
  clearSubscriptions()
  mockRealtime.reset()
  window.localStorage.clear()
})

afterAll(() => {
  server.close()
})

// jsdom lacks these; UI kit components use them.
if (!window.matchMedia) {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: (query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    }),
  })
}

if (!Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = function scrollIntoView() {}
}
