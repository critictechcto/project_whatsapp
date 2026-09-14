import { HttpResponse } from 'msw'
import { createOpenApiHttp } from 'openapi-msw'
import type { paths } from '../api/schema'
import type { CursorPage, RoleEnum } from '../api/types'
import { env } from '../config/env'
import { hasRole } from '../lib/roles'
import { db, type MockMembership, type MockUser, type MockWorkspace } from './db'

/**
 * Typed MSW `http` for paths in `openapi.yml`:
 * `http.get('/api/v1/templates/', ({ request, query, response }) => response(200).json(page))`.
 * For endpoints not in the schema yet use `http.untyped.get(apiUrl('/api/v1/inbox/conversations/'), ...)`.
 */
export const http = createOpenApiHttp<paths>({ baseUrl: env.apiUrl })

/** Absolute URL for untyped handlers. */
export function apiUrl(path: string) {
  return `${env.apiUrl}${path}`
}

export function uuid(): string {
  return crypto.randomUUID()
}

export function nowIso(): string {
  return new Date().toISOString()
}

/** `{"error": {"code", "message", "details"}}` response. Return it via `response.untyped(...)`. */
export function errorResponse(status: number, code: string, message: string, details: unknown = null): MockErrorResponse {
  return HttpResponse.json({ error: { code, message, details: details as JsonValue } }, { status })
}

type JsonValue = string | number | boolean | null | JsonValue[] | { [key: string]: JsonValue }

export type MockErrorResponse = HttpResponse<{ error: { code: string; message: string; details: JsonValue } }>

/** 400 `invalid` with DRF-style field errors, e.g. `validationError({ email: ['Enter a valid email address.'] })`. */
export function validationError(details: Record<string, unknown>) {
  return errorResponse(400, 'invalid', 'Invalid input.', details)
}

export function notFound() {
  return errorResponse(404, 'not_found', 'Not found.')
}

/**
 * Cursor pagination over an in-memory array. The cursor is the offset, base64-encoded;
 * `next`/`previous` are absolute URLs like the real API.
 */
export function paginate<T>(request: Request, items: readonly T[], defaultPageSize = 20): CursorPage<T> {
  const url = new URL(request.url)
  const pageSize = Math.min(Number(url.searchParams.get('page_size')) || defaultPageSize, 200)
  const cursor = url.searchParams.get('cursor')
  let offset = 0
  if (cursor) {
    const decoded = Number(atob(cursor))
    offset = Number.isFinite(decoded) && decoded > 0 ? decoded : 0
  }

  const pageUrl = (nextOffset: number) => {
    const target = new URL(url)
    target.searchParams.set('cursor', btoa(String(nextOffset)))
    return target.toString()
  }

  return {
    next: offset + pageSize < items.length ? pageUrl(offset + pageSize) : null,
    previous: offset > 0 ? pageUrl(Math.max(0, offset - pageSize)) : null,
    results: items.slice(offset, offset + pageSize),
  }
}

const ACCESS_TTL_MS = 15 * 60 * 1000

/** Mock JWTs are opaque strings: `mock-access.<userId>.<expiresAtMs>`. */
export function issueTokens(userId: string) {
  const access = `mock-access.${userId}.${Date.now() + ACCESS_TTL_MS}`
  const refresh = `mock-refresh.${userId}.${uuid()}`
  db.refreshTokens.set(refresh, userId)
  return { access, refresh }
}

function notAuthenticated() {
  return errorResponse(401, 'not_authenticated', 'Authentication credentials were not provided.')
}

/** Resolves the Bearer token to a user, or returns a 401 response. */
export function authenticate(request: Request): MockUser | MockErrorResponse {
  const header = request.headers.get('Authorization') ?? ''
  const match = /^Bearer mock-access\.([^.]+)\.(\d+)$/.exec(header)
  if (!match) return notAuthenticated()
  if (Number(match[2]) < Date.now()) {
    return errorResponse(401, 'token_not_valid', 'Given token not valid for any token type')
  }
  const user = db.users.find((candidate) => candidate.id === match[1])
  return user ?? notAuthenticated()
}

export type WorkspaceContext = { user: MockUser; workspace: MockWorkspace; membership: MockMembership }

/**
 * Authenticates and resolves `X-Workspace-ID` like `WorkspaceScopedMixin`: non-members get 404,
 * too-low roles get 403 `insufficient_role`.
 *
 * ```ts
 * const ctx = authorize(request, 'admin')
 * if (ctx instanceof Response) return response.untyped(ctx)
 * ```
 */
export function authorize(request: Request, minRole: RoleEnum = 'viewer'): WorkspaceContext | MockErrorResponse {
  const user = authenticate(request)
  if (user instanceof Response) return user
  const workspaceId = request.headers.get('X-Workspace-ID')
  const workspace = db.workspaces.find((candidate) => candidate.id === workspaceId)
  const membership = db.memberships.find((m) => m.workspace_id === workspaceId && m.user_id === user.id)
  if (!workspace || !membership) return notFound()
  if (!hasRole(membership.role, minRole)) {
    return errorResponse(403, 'insufficient_role', 'Your role does not allow this action.')
  }
  return { user, workspace, membership }
}

/** Simulated latency for mock mode in the browser (skipped in tests). */
export async function mockDelay(ms = 250) {
  if (import.meta.env.MODE === 'test') return
  await new Promise((resolve) => setTimeout(resolve, ms))
}
