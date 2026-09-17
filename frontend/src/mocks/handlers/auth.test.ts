import { describe, expect, it } from 'vitest'
import { api } from '../../api/client'
import { db, resetMockDb } from '../db'
import { ids } from '../seed'
import { issueTokens } from '../utils'

const refresh = (token: string) => api.POST('/api/v1/auth/token/refresh/', { body: { refresh: token } })

describe('mock refresh tokens', () => {
  it('keep a demo session alive after the mock database is rebuilt (page reload)', async () => {
    const { refresh: token } = issueTokens(ids.demoUser)
    resetMockDb()
    expect(db.refreshTokens.size).toBe(0)

    const restored = await refresh(token)
    expect(restored.response.status).toBe(200)
    // Rotated: the old token can't be used again.
    expect((await refresh(token)).response.status).toBe(401)
  })

  it('reject logged-out, malformed and unknown-user tokens', async () => {
    const { refresh: token } = issueTokens(ids.demoUser)
    await api.POST('/api/v1/auth/logout/', { body: { refresh: token } })
    expect((await refresh(token)).response.status).toBe(401)
    expect((await refresh('mock-refresh.unknown')).response.status).toBe(401)
    expect((await refresh(`mock-refresh.00000000-0000-4000-8000-000000000000.${crypto.randomUUID()}`)).response.status).toBe(401)
  })
})
