import '@testing-library/jest-dom/vitest'
import { cleanup, configure } from '@testing-library/react'
import { afterAll, afterEach, beforeAll, beforeEach } from 'vitest'
import { setActiveWorkspaceId } from '../api/client'
import { resetRefreshState } from '../lib/auth/refresh'
import { tokenStore } from '../lib/auth/tokens'
import { clearSubscriptions } from '../lib/realtime/registry'
import { resetMockDb } from '../mocks/db'
import { server } from '../mocks/node'
import { mockRealtime } from '../mocks/realtime'

// Lazy route chunks can take over 1 s to load when the whole suite runs in parallel.
configure({ asyncUtilTimeout: 5_000 })

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
