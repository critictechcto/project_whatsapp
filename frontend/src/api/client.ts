import createClient from 'openapi-fetch'
import { env } from '../config/env'
import { configureRefresh, refreshAccessToken, RefreshRejectedError } from '../lib/auth/refresh'
import { tokenStore } from '../lib/auth/tokens'
import { ApiError } from './errors'
import type { AppPaths, Schemas } from './types'

export const WORKSPACE_HEADER = 'X-Workspace-ID'
export const IDEMPOTENCY_HEADER = 'Idempotency-Key'

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

const PUBLIC_AUTH_PATHS = ['/api/v1/auth/token/', '/api/v1/auth/token/refresh/', '/api/v1/auth/register/']

function isPublicAuthRequest(url: string) {
  const { pathname } = new URL(url)
  return PUBLIC_AUTH_PATHS.includes(pathname)
}

function withAuthHeaders(request: Request): Request {
  const headers = new Headers(request.headers)
  const token = tokenStore.getAccess()
  if (token && !isPublicAuthRequest(request.url)) headers.set('Authorization', `Bearer ${token}`)
  if (activeWorkspaceId && !headers.has(WORKSPACE_HEADER)) headers.set(WORKSPACE_HEADER, activeWorkspaceId)
  return new Request(request, { headers })
}

/**
 * Fetch with auth: attaches the Bearer token and workspace header, refreshes before sending when
 * only a refresh token is available (after a reload), and on 401 refreshes once and retries once.
 */
export async function authFetch(request: Request): Promise<Response> {
  const isPublic = isPublicAuthRequest(request.url)

  if (!isPublic && !tokenStore.getAccess() && tokenStore.getRefresh()) {
    try {
      await refreshAccessToken(null)
    } catch {
      // Fall through: the request goes out unauthenticated and the API answers 401.
    }
  }

  const retry = request.clone()
  const sentWith = tokenStore.getAccess()
  const response = await globalThis.fetch(withAuthHeaders(request))

  if (response.status !== 401 || isPublic || !tokenStore.getRefresh()) return response

  try {
    await refreshAccessToken(sentWith)
  } catch {
    return response
  }
  return globalThis.fetch(withAuthHeaders(retry))
}

async function refreshTokens(refresh: string): Promise<{ access: string; refresh: string }> {
  const response = await globalThis.fetch(`${env.apiUrl}/api/v1/auth/token/refresh/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ refresh }),
  })
  if (response.status === 400 || response.status === 401) throw new RefreshRejectedError()
  if (!response.ok) throw await ApiError.fromResponse(response)
  const data = (await response.json()) as Schemas['TokenRefresh']
  return { access: data.access, refresh: data.refresh }
}

configureRefresh({ refresh: refreshTokens })

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
