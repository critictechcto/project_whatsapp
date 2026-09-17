import { describe, expect, it } from 'vitest'
import { env } from '../../config/env'
import { resetMockDb } from '../db'
import { DEMO_EMAIL, DEMO_PASSWORD, ids } from '../seed'
import { MOCK_SESSION_KEY, readMockSession, startMockSession } from '../session'

const url = (path: string) => `${env.apiUrl}${path}`
const refresh = (headers: Record<string, string> = { 'X-UpChatz-Auth': '1' }) =>
  fetch(url('/api/v1/auth/token/refresh/'), { method: 'POST', headers })
const logout = () => fetch(url('/api/v1/auth/logout/'), { method: 'POST', headers: { 'X-UpChatz-Auth': '1' } })

describe('mock auth (stands in for the HttpOnly refresh cookie)', () => {
  it('login returns only an access token and starts a mock session', async () => {
    const response = await fetch(url('/api/v1/auth/token/'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: DEMO_EMAIL, password: DEMO_PASSWORD }),
    })

    expect(response.status).toBe(200)
    expect(Object.keys(await response.json())).toEqual(['access'])
    expect(readMockSession()?.userId).toBe(ids.demoUser)
  })

  it('keeps a session alive after the mock database is rebuilt (page reload) and rotates it', async () => {
    const before = startMockSession(ids.demoUser)
    resetMockDb()

    const restored = await refresh()
    expect(restored.status).toBe(200)
    expect(Object.keys(await restored.json())).toEqual(['access'])
    expect(readMockSession()?.id).not.toBe(before.id)
  })

  it('refuses refresh without the CSRF header, without a session, and after logout', async () => {
    startMockSession(ids.demoUser)
    expect((await refresh({})).status).toBe(403)
    expect(window.localStorage.getItem(MOCK_SESSION_KEY)).toBeNull()
    expect((await refresh()).status).toBe(401)

    startMockSession(ids.demoUser)
    expect((await logout()).status).toBe(204)
    expect((await refresh()).status).toBe(401)
  })

  it('ignores a session for a user that does not exist', async () => {
    startMockSession('00000000-0000-4000-8000-000000000000')
    expect((await refresh()).status).toBe(401)
  })
})
