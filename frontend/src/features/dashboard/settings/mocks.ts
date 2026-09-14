import { HttpResponse } from 'msw'
import type { Schemas } from '../../../api/types'
import { db, type MockUser, type MockWorkspace } from '../../../mocks/db'
import { authenticate, errorResponse, http, mockDelay, notFound, nowIso, uuid, validationError } from '../../../mocks/utils'
import type { AreaMockHandlers } from '../registry/types'
import { isKnownTimeZone } from '../workspaces/timeZones'

/**
 * Profile and workspace-settings handlers with the backend's validation
 * (they override the shared auth/workspace fallbacks).
 */

function meFor(user: MockUser): Schemas['Me'] {
  return {
    id: user.id,
    email: user.email,
    full_name: user.full_name,
    date_joined: user.date_joined,
    email_verified_at: user.email_verified_at,
    memberships: db.memberships
      .filter((membership) => membership.user_id === user.id)
      .flatMap((membership) => {
        const workspace = db.workspaces.find((candidate) => candidate.id === membership.workspace_id)
        return workspace
          ? [{ workspace_id: workspace.id, workspace_name: workspace.name, workspace_slug: workspace.slug, role: membership.role }]
          : []
      }),
  }
}

const COMMON_PASSWORDS = new Set(['password', 'password1', '12345678', '123456789', 'qwerty123', 'iloveyou', 'india123'])

function slugify(name: string) {
  return (
    name
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/^-+|-+$/g, '')
      .slice(0, 48) || 'workspace'
  )
}

function uniqueSlug(name: string) {
  const base = slugify(name)
  let slug = base
  let n = 2
  while (db.workspaces.some((workspace) => workspace.slug === slug)) slug = `${base}-${n++}`
  return slug
}

function workspaceErrors(body: { name?: unknown; time_zone?: unknown }, partial: boolean): Record<string, string[]> {
  const errors: Record<string, string[]> = {}
  if (!partial || body.name !== undefined) {
    const name = String(body.name ?? '').trim()
    if (!name) errors.name = ['This field may not be blank.']
    else if (name.length > 120) errors.name = ['Ensure this field has no more than 120 characters.']
  }
  if (body.time_zone !== undefined && !isKnownTimeZone(String(body.time_zone))) {
    errors.time_zone = ['Unknown time zone.']
  }
  return errors
}

export const handlers: AreaMockHandlers = [
  http.patch('/api/v1/auth/me/', async ({ request, response }) => {
    await mockDelay()
    const user = authenticate(request)
    if (user instanceof Response) return response.untyped(user)
    const body = (await request.json()) as Schemas['PatchedMeRequest']
    if (typeof body.full_name === 'string') {
      if (body.full_name.length > 150) {
        return response.untyped(validationError({ full_name: ['Ensure this field has no more than 150 characters.'] }))
      }
      user.full_name = body.full_name.trim()
    }
    return response(200).json(meFor(user))
  }),

  http.post('/api/v1/auth/password/change/', async ({ request, response }) => {
    await mockDelay()
    const user = authenticate(request)
    if (user instanceof Response) return response.untyped(user)
    const body = (await request.json()) as Partial<Schemas['PasswordChangeRequest']>
    if (body.current_password !== user.password) {
      return response.untyped(validationError({ current_password: ['Your current password is incorrect.'] }))
    }
    const next = String(body.new_password ?? '')
    const problems: string[] = []
    if (next.length < 8) problems.push('This password is too short. It must contain at least 8 characters.')
    if (COMMON_PASSWORDS.has(next.toLowerCase())) problems.push('This password is too common.')
    if (/^\d+$/.test(next)) problems.push('This password is entirely numeric.')
    if (next && user.email.toLowerCase().startsWith(next.toLowerCase())) problems.push('The password is too similar to the email address.')
    if (problems.length) return response.untyped(validationError({ new_password: problems }))
    user.password = next
    return response.untyped(new HttpResponse(null, { status: 204 }))
  }),

  http.post('/api/v1/workspaces/', async ({ request, response }) => {
    await mockDelay()
    const user = authenticate(request)
    if (user instanceof Response) return response.untyped(user)
    const body = (await request.json()) as Partial<Schemas['WorkspaceRequest']>
    const errors = workspaceErrors(body, false)
    if (Object.keys(errors).length) return response.untyped(validationError(errors))

    const name = String(body.name).trim()
    const workspace: MockWorkspace = {
      id: uuid(),
      name,
      slug: uniqueSlug(name),
      time_zone: body.time_zone || 'Asia/Kolkata',
      created_at: nowIso(),
    }
    db.workspaces.push(workspace)
    db.memberships.push({ id: uuid(), workspace_id: workspace.id, user_id: user.id, role: 'owner', created_at: nowIso() })
    return response(201).json({ ...workspace, my_role: 'owner' })
  }),

  http.patch('/api/v1/workspaces/{id}/', async ({ request, params, response }) => {
    await mockDelay()
    const user = authenticate(request)
    if (user instanceof Response) return response.untyped(user)
    const membership = db.memberships.find((m) => m.workspace_id === params.id && m.user_id === user.id)
    const workspace = db.workspaces.find((candidate) => candidate.id === params.id)
    if (!membership || !workspace) return response.untyped(notFound())
    if (membership.role !== 'owner' && membership.role !== 'admin') {
      return response.untyped(errorResponse(403, 'insufficient_role', 'Your role does not allow this action.'))
    }
    const body = (await request.json()) as Schemas['PatchedWorkspaceRequest']
    const errors = workspaceErrors(body, true)
    if (Object.keys(errors).length) return response.untyped(validationError(errors))
    if (typeof body.name === 'string') workspace.name = body.name.trim()
    if (typeof body.time_zone === 'string') workspace.time_zone = body.time_zone
    return response(200).json({ ...workspace, my_role: membership.role })
  }),
]
