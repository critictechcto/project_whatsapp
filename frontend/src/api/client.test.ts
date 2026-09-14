import { afterEach, describe, expect, it } from 'vitest'
import { tokenStore } from '../lib/auth/tokens'
import { server } from '../mocks/node'
import { DEMO_EMAIL, ids } from '../mocks/seed'
import { issueTokens } from '../mocks/utils'
import { signIn } from '../test/render'
import { api, setActiveWorkspaceId, unwrap } from './client'
import { ApiError } from './errors'

const expiredAccess = `mock-access.${ids.demoUser}.1`

afterEach(() => {
  server.events.removeAllListeners()
})

function countRequests(pathname: string) {
  const seen: string[] = []
  server.events.on('request:start', ({ request }) => {
    if (new URL(request.url).pathname === pathname) seen.push(request.method)
  })
  return seen
}

describe('api client', () => {
  it('refreshes once for concurrent 401s and retries each request', async () => {
    tokenStore.set({ access: expiredAccess, refresh: issueTokens(ids.demoUser).refresh })
    const refreshes = countRequests('/api/v1/auth/token/refresh/')

    const [me, workspaces] = await Promise.all([
      unwrap(api.GET('/api/v1/auth/me/')),
      unwrap(api.GET('/api/v1/workspaces/')),
    ])

    expect(me.email).toBe(DEMO_EMAIL)
    expect(workspaces.results.map((workspace) => workspace.name)).toContain('Sharma Sweets')
    expect(refreshes).toHaveLength(1)
  })

  it('refreshes before the first request after a reload (refresh token only)', async () => {
    window.localStorage.setItem('upchatz.refresh', issueTokens(ids.demoUser).refresh)
    const me = await unwrap(api.GET('/api/v1/auth/me/'))
    expect(me.email).toBe(DEMO_EMAIL)
    expect(tokenStore.getAccess()).toMatch(/^mock-access\./)
  })

  it('ends the session when the refresh token is rejected', async () => {
    tokenStore.set({ access: expiredAccess, refresh: 'mock-refresh.unknown' })
    const error = await unwrap(api.GET('/api/v1/auth/me/')).catch((e: unknown) => e)
    expect(error).toBeInstanceOf(ApiError)
    expect((error as ApiError).status).toBe(401)
    expect(tokenStore.hasSession()).toBe(false)
  })

  it('sends the active workspace as X-Workspace-ID', async () => {
    signIn()
    setActiveWorkspaceId(ids.sharmaSweets)
    const page = await unwrap(api.GET('/api/v1/contacts/', { params: { query: { page_size: 5 } } }))
    expect(page.results.length).toBeGreaterThan(0)
  })
})
