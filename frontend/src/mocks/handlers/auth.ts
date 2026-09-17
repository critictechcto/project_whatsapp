import { HttpResponse } from 'msw'
import type { Schemas } from '../../api/types'
import { db, type MockUser } from '../db'
import { authenticate, errorResponse, http, issueTokens, mockDelay, nowIso, uuid, validationError } from '../utils'

function publicUser(user: MockUser): Schemas['User'] {
  return {
    id: user.id,
    email: user.email,
    full_name: user.full_name,
    date_joined: user.date_joined,
    email_verified_at: user.email_verified_at,
  }
}

export function meFor(user: MockUser): Schemas['Me'] {
  return {
    ...publicUser(user),
    memberships: db.memberships
      .filter((membership) => membership.user_id === user.id)
      .flatMap((membership) => {
        const workspace = db.workspaces.find((candidate) => candidate.id === membership.workspace_id)
        return workspace
          ? [
              {
                workspace_id: workspace.id,
                workspace_name: workspace.name,
                workspace_slug: workspace.slug,
                role: membership.role,
              },
            ]
          : []
      }),
  }
}

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

const MOCK_REFRESH_RE = /^mock-refresh\.([0-9a-f-]{36})\.[0-9a-f-]{36}$/

/**
 * The browser demo rebuilds the mock database on every page load, which forgets issued refresh
 * tokens. A well-formed token for a seeded user that was never rotated or logged out in this page
 * load keeps the demo session alive across reloads and deep links.
 */
function restoredSessionUser(refresh: string): string | undefined {
  const userId = MOCK_REFRESH_RE.exec(refresh)?.[1]
  if (!userId || db.revokedRefreshTokens.has(refresh)) return undefined
  return db.users.some((user) => user.id === userId) ? userId : undefined
}

export const authHandlers = [
  http.post('/api/v1/auth/token/', async ({ request, response }) => {
    await mockDelay()
    const body = (await request.json()) as Partial<Schemas['TokenObtainPairRequest']>
    const user = db.users.find((candidate) => candidate.email.toLowerCase() === String(body.email ?? '').toLowerCase())
    if (!user || user.password !== body.password) {
      return response.untyped(
        errorResponse(401, 'no_active_account', 'No active account found with the given credentials'),
      )
    }
    return response(200).json(issueTokens(user.id))
  }),

  http.post('/api/v1/auth/token/refresh/', async ({ request, response }) => {
    const body = (await request.json()) as Partial<Schemas['TokenRefreshRequest']>
    const userId = body.refresh ? (db.refreshTokens.get(body.refresh) ?? restoredSessionUser(body.refresh)) : undefined
    if (!body.refresh || !userId) {
      return response.untyped(errorResponse(401, 'token_not_valid', 'Token is invalid or expired'))
    }
    db.refreshTokens.delete(body.refresh)
    db.revokedRefreshTokens.add(body.refresh)
    return response(200).json(issueTokens(userId))
  }),

  http.post('/api/v1/auth/register/', async ({ request, response }) => {
    await mockDelay()
    const body = (await request.json()) as Partial<Schemas['RegisterRequest']>
    const email = String(body.email ?? '').trim()
    const errors: Record<string, string[]> = {}
    if (!EMAIL_RE.test(email)) errors.email = ['Enter a valid email address.']
    else if (db.users.some((user) => user.email.toLowerCase() === email.toLowerCase())) {
      errors.email = ['A user with that email already exists.']
    }
    if (String(body.password ?? '').length < 8) {
      errors.password = ['This password is too short. It must contain at least 8 characters.']
    }
    if (Object.keys(errors).length) return response.untyped(validationError(errors))

    const user: MockUser = {
      id: uuid(),
      email,
      full_name: String(body.full_name ?? ''),
      date_joined: nowIso(),
      email_verified_at: null,
      password: String(body.password),
    }
    db.users.push(user)
    return response(201).json({ user: publicUser(user), tokens: issueTokens(user.id) })
  }),

  http.post('/api/v1/auth/logout/', async ({ request, response }) => {
    const body = (await request.json()) as Partial<Schemas['TokenBlacklistRequest']>
    if (body.refresh) {
      db.refreshTokens.delete(body.refresh)
      db.revokedRefreshTokens.add(body.refresh)
    }
    return response(200).empty()
  }),

  http.get('/api/v1/auth/me/', ({ request, response }) => {
    const user = authenticate(request)
    if (user instanceof Response) return response.untyped(user)
    return response(200).json(meFor(user))
  }),

  http.patch('/api/v1/auth/me/', async ({ request, response }) => {
    const user = authenticate(request)
    if (user instanceof Response) return response.untyped(user)
    const body = (await request.json()) as Schemas['PatchedMeRequest']
    if (typeof body.full_name === 'string') user.full_name = body.full_name
    return response(200).json(meFor(user))
  }),

  http.post('/api/v1/auth/password/change/', async ({ request, response }) => {
    const user = authenticate(request)
    if (user instanceof Response) return response.untyped(user)
    const body = (await request.json()) as Partial<Schemas['PasswordChangeRequest']>
    if (body.current_password !== user.password) {
      return response.untyped(validationError({ current_password: ['Your current password is incorrect.'] }))
    }
    user.password = String(body.new_password ?? '')
    return response.untyped(new HttpResponse(null, { status: 204 }))
  }),
]
