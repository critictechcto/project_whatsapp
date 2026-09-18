import createClient from 'openapi-fetch'
import { env } from '../config/env'
import { configureRefresh, ensureAccessToken, refreshAccessToken, RefreshRejectedError } from '../lib/auth/refresh'
import { tokenStore } from '../lib/auth/tokens'
import { ApiError } from './errors'
import type { AppPaths, Schemas } from './types'

export const WORKSPACE_HEADER = 'X-Workspace-ID'
export const IDEMPOTENCY_HEADER = 'Idempotency-Key'
/** CSRF guard the API requires on the refresh-cookie endpoints (forces a CORS preflight). */
export const AUTH_CSRF_HEADER = 'X-UpChatz-Auth'

let activeWorkspaceId: string | null = null

/** Set by the workspace route layout; injected as `X-Workspace-ID` when a request doesn't set it. */
export function setActiveWorkspaceId(workspaceId: string | null) {
  activeWorkspaceId = workspaceId
}

export function getActiveWorkspaceId() {
  return activeWorkspaceId
}

/** A fresh key for idempotent POSTs. Create it once per user intent (e.g. when a form mounts), not per retry. */
export function newIdempotencyKey(): string {
  return crypto.randomUUID()
}

/** Headers for an idempotent POST: `api.POST(path, { body, headers: idempotencyHeaders(key) })`. */
export function idempotencyHeaders(key: string): Record<string, string> {
  return { [IDEMPOTENCY_HEADER]: key }
}

/** The refresh cookie is scoped to this path; requests under it send cookies cross-origin. */
const AUTH_PATH_PREFIX = '/api/v1/auth/'
const REFRESH_PATH = '/api/v1/auth/token/refresh/'
const LOGOUT_PATH = '/api/v1/auth/logout/'
/** Endpoints that never take a Bearer token and never trigger refresh-and-retry. */
const PUBLIC_AUTH_PATHS = [
  '/api/v1/auth/token/',
  REFRESH_PATH,
  '/api/v1/auth/register/',
  LOGOUT_PATH,
  // Links from emails work signed out, so they never send or refresh a session.
  '/api/v1/auth/email/verify/',
  '/api/v1/auth/password/reset/',
  '/api/v1/auth/password/reset/confirm/',
]

function pathOf(url: string) {
  return new URL(url).pathname
}

function isPublicAuthRequest(url: string) {
  return PUBLIC_AUTH_PATHS.includes(pathOf(url))
}

function withAuthHeaders(request: Request): Request {
  const path = pathOf(request.url)
  const headers = new Headers(request.headers)
  const token = tokenStore.getAccess()
  if (token && !PUBLIC_AUTH_PATHS.includes(path)) headers.set('Authorization', `Bearer ${token}`)
  if (activeWorkspaceId && !headers.has(WORKSPACE_HEADER)) headers.set(WORKSPACE_HEADER, activeWorkspaceId)
  if (path === REFRESH_PATH || path === LOGOUT_PATH) headers.set(AUTH_CSRF_HEADER, '1')
  // Login/register must accept the Set-Cookie and refresh/logout must send it, also cross-origin.
  const credentials: RequestCredentials = path.startsWith(AUTH_PATH_PREFIX) ? 'include' : request.credentials
  return new Request(request, { headers, credentials })
}

/**
 * Fetch with auth: attaches the Bearer token and workspace header, refreshes before sending when a
 * session may exist but no access token is in memory (after a reload), and on 401 refreshes once
 * and retries once.
 */
export async function authFetch(request: Request): Promise<Response> {
  const isPublic = isPublicAuthRequest(request.url)

  // Falls through without a token: the request goes out unauthenticated and the API answers 401.
  if (!isPublic) await ensureAccessToken()

  const retry = request.clone()
  const sentWith = tokenStore.getAccess()
  const response = await globalThis.fetch(withAuthHeaders(request))

  if (response.status !== 401 || isPublic || !tokenStore.mayRefresh()) return response

  try {
    await refreshAccessToken(sentWith)
  } catch {
    return response
  }
  return globalThis.fetch(withAuthHeaders(retry))
}

async function refreshWithCookie(): Promise<{ access: string }> {
  const response = await globalThis.fetch(
    withAuthHeaders(new Request(`${env.apiUrl}${REFRESH_PATH}`, { method: 'POST' })),
  )
  // 401: no or rejected cookie. 403: the CSRF checks refused the request; retrying can't help.
  if (response.status === 401 || response.status === 403) throw new RefreshRejectedError()
  if (!response.ok) throw await ApiError.fromResponse(response)
  const data = (await response.json()) as Schemas['AccessToken']
  return { access: data.access }
}

configureRefresh({ refresh: refreshWithCookie })

/** Ends the server session: blacklists the refresh cookie's token and clears the cookie. */
export async function logoutRequest(): Promise<void> {
  await globalThis.fetch(withAuthHeaders(new Request(`${env.apiUrl}${LOGOUT_PATH}`, { method: 'POST' })))
}

/**
 * Typed API client generated from `backend/openapi.yml`.
 *
 * ```ts
 * const templates = await unwrap(api.GET('/api/v1/templates/', { params: { query: { status: 'APPROVED' } } }))
 * ```
 */
export const api = createClient<AppPaths>({
  baseUrl: env.apiUrl,
  fetch: (request) => authFetch(request),
})

type ApiResult<T> = { data?: T; error?: unknown; response: Response }

/** Resolves to `data`, or throws `ApiError` (with the parsed envelope) for non-2xx responses. */
export async function unwrap<T>(promise: Promise<ApiResult<T>>): Promise<T> {
  const { data, error, response } = await promise
  if (!response.ok) throw new ApiError(response.status, error ?? null)
  return data as T
}

/**
 * Untyped escape hatch for endpoints not in `openapi.yml` yet (or multipart uploads).
 * Goes through the same auth/workspace handling. Throws `ApiError` for non-2xx.
 */
export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers)
  if (init.body && typeof init.body === 'string' && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }
  const response = await authFetch(new Request(`${env.apiUrl}${path}`, { ...init, headers }))
  if (!response.ok) throw await ApiError.fromResponse(response)
  if (response.status === 204) return undefined as T
  const text = await response.text()
  return (text ? JSON.parse(text) : undefined) as T
}
