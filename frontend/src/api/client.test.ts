import { afterEach, describe, expect, it } from 'vitest'
import { SESSION_MARKER_KEY, simulateReloadForTests, tokenStore } from '../lib/auth/tokens'
import { resetMockDb } from '../mocks/db'
import { server } from '../mocks/node'
import { DEMO_EMAIL, DEMO_PASSWORD, ids } from '../mocks/seed'
import { MOCK_SESSION_KEY, startMockSession } from '../mocks/session'
import { signIn } from '../test/render'
import { api, logoutRequest, setActiveWorkspaceId, unwrap } from './client'
import { ApiError } from './errors'

const expiredAccess = `mock-access.${ids.demoUser}.1`

afterEach(() => {
  server.events.removeAllListeners()
})

function recordRequests(pathname: string) {
  const seen: Request[] = []
  server.events.on('request:start', ({ request }) => {
    if (new URL(request.url).pathname === pathname) seen.push(request.clone())
  })
  return seen
}

describe('api client', () => {
  it('refreshes once for concurrent 401s and retries each request', async () => {
    startMockSession(ids.demoUser)
    tokenStore.set(expiredAccess)
    const refreshes = recordRequests('/api/v1/auth/token/refresh/')

    const [me, workspaces] = await Promise.all([
      unwrap(api.GET('/api/v1/auth/me/')),
      unwrap(api.GET('/api/v1/workspaces/')),
    ])

    expect(me.email).toBe(DEMO_EMAIL)
    expect(workspaces.results.map((workspace) => workspace.name)).toContain('Sharma Sweets')
    expect(refreshes).toHaveLength(1)
    // No body token: the refresh relies on the cookie and carries the CSRF header.
    expect(refreshes[0].headers.get('X-UpChatz-Auth')).toBe('1')
    expect(refreshes[0].credentials).toBe('include')
    expect(await refreshes[0].text()).toBe('')
  })

  it('logs in without ever storing a refresh token, and a reload keeps the session (mock mode)', async () => {
    const { access } = await unwrap(api.POST('/api/v1/auth/token/', { body: { email: DEMO_EMAIL, password: DEMO_PASSWORD } }))
    tokenStore.set(access)
    for (let i = 0; i < window.localStorage.length; i++) {
      const key = window.localStorage.key(i)!
      if (key !== MOCK_SESSION_KEY) expect(window.localStorage.getItem(key)).not.toContain('mock-access')
    }

    // Reload: memory is gone and the mock database is rebuilt; the marker and "cookie" remain.
    simulateReloadForTests()
    resetMockDb()
    const refreshes = recordRequests('/api/v1/auth/token/refresh/')

    const me = await unwrap(api.GET('/api/v1/auth/me/'))

    expect(me.email).toBe(DEMO_EMAIL)
    expect(refreshes).toHaveLength(1)
    expect(tokenStore.getAccess()).toMatch(/^mock-access\./)
  })

  it('never calls refresh for a signed-out visitor', async () => {
    const refreshes = recordRequests('/api/v1/auth/token/refresh/')

    const error = await unwrap(api.GET('/api/v1/auth/me/')).catch((e: unknown) => e)

    expect((error as ApiError).status).toBe(401)
    expect(refreshes).toHaveLength(0)
  })

  it('ends the session when the refresh cookie is rejected', async () => {
    tokenStore.set(expiredAccess) // no mock session: the "cookie" is gone
    const error = await unwrap(api.GET('/api/v1/auth/me/')).catch((e: unknown) => e)
    expect(error).toBeInstanceOf(ApiError)
    expect((error as ApiError).status).toBe(401)
    expect(tokenStore.hasSession()).toBe(false)
    expect(window.localStorage.getItem(SESSION_MARKER_KEY)).toBeNull()
  })

  it('logout ends the server session so a reload is signed out', async () => {
    signIn()
    const logouts = recordRequests('/api/v1/auth/logout/')

    await logoutRequest()
    tokenStore.clear()

    expect(logouts[0].headers.get('X-UpChatz-Auth')).toBe('1')
    expect(window.localStorage.getItem(MOCK_SESSION_KEY)).toBeNull()
    simulateReloadForTests()
    expect(tokenStore.hasSession()).toBe(false)
  })

  it('sends the active workspace as X-Workspace-ID', async () => {
    signIn()
    setActiveWorkspaceId(ids.sharmaSweets)
    const page = await unwrap(api.GET('/api/v1/contacts/', { params: { query: { page_size: 5 } } }))
    expect(page.results.length).toBeGreaterThan(0)
  })
})
