import { HttpResponse } from 'msw'
import type { RoleEnum, Schemas } from '../../api/types'
import { db, type MockInvitation, type MockMembership, type MockWorkspace } from '../db'
import {
  authenticate,
  authorize,
  errorResponse,
  http,
  mockDelay,
  notFound,
  nowIso,
  paginate,
  uuid,
  validationError,
} from '../utils'

function toWorkspace(workspace: MockWorkspace, role: RoleEnum): Schemas['Workspace'] {
  return { ...workspace, my_role: role }
}

function toMembership(membership: MockMembership): Schemas['Membership'] {
  const user = db.users.find((candidate) => candidate.id === membership.user_id)!
  return {
    id: membership.id,
    role: membership.role,
    created_at: membership.created_at,
    user: { id: user.id, email: user.email, full_name: user.full_name },
  }
}

function toInvitation(invitation: MockInvitation): Schemas['Invitation'] {
  const { workspace_id: _workspace, token: _token, ...rest } = invitation
  return rest
}

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

const noContent = () => new HttpResponse(null, { status: 204 })

export const workspaceHandlers = [
  http.get('/api/v1/workspaces/', ({ request, response }) => {
    const user = authenticate(request)
    if (user instanceof Response) return response.untyped(user)
    const items = db.memberships
      .filter((membership) => membership.user_id === user.id)
      .flatMap((membership) => {
        const workspace = db.workspaces.find((candidate) => candidate.id === membership.workspace_id)
        return workspace ? [toWorkspace(workspace, membership.role)] : []
      })
    return response(200).json(paginate(request, items))
  }),

  http.post('/api/v1/workspaces/', async ({ request, response }) => {
    await mockDelay()
    const user = authenticate(request)
    if (user instanceof Response) return response.untyped(user)
    const body = (await request.json()) as Partial<Schemas['WorkspaceRequest']>
    const name = String(body.name ?? '').trim()
    if (!name) return response.untyped(validationError({ name: ['This field may not be blank.'] }))

    const workspace: MockWorkspace = {
      id: uuid(),
      name,
      slug: uniqueSlug(name),
      time_zone: body.time_zone || 'Asia/Kolkata',
      created_at: nowIso(),
    }
    db.workspaces.push(workspace)
    db.memberships.push({ id: uuid(), workspace_id: workspace.id, user_id: user.id, role: 'owner', created_at: nowIso() })
    return response(201).json(toWorkspace(workspace, 'owner'))
  }),

  http.get('/api/v1/workspaces/{id}/', ({ request, params, response }) => {
    const user = authenticate(request)
    if (user instanceof Response) return response.untyped(user)
    const membership = db.memberships.find((m) => m.workspace_id === params.id && m.user_id === user.id)
    const workspace = db.workspaces.find((candidate) => candidate.id === params.id)
    if (!membership || !workspace) return response.untyped(notFound())
    return response(200).json(toWorkspace(workspace, membership.role))
  }),

  http.patch('/api/v1/workspaces/{id}/', async ({ request, params, response }) => {
    const user = authenticate(request)
    if (user instanceof Response) return response.untyped(user)
    const membership = db.memberships.find((m) => m.workspace_id === params.id && m.user_id === user.id)
    const workspace = db.workspaces.find((candidate) => candidate.id === params.id)
    if (!membership || !workspace) return response.untyped(notFound())
    if (membership.role !== 'owner' && membership.role !== 'admin') {
      return response.untyped(errorResponse(403, 'insufficient_role', 'Your role does not allow this action.'))
    }
    const body = (await request.json()) as Schemas['PatchedWorkspaceRequest']
    if (typeof body.name === 'string') workspace.name = body.name
    if (typeof body.time_zone === 'string') workspace.time_zone = body.time_zone
    return response(200).json(toWorkspace(workspace, membership.role))
  }),

  http.delete('/api/v1/workspaces/{id}/', ({ request, params, response }) => {
    const user = authenticate(request)
    if (user instanceof Response) return response.untyped(user)
    const membership = db.memberships.find((m) => m.workspace_id === params.id && m.user_id === user.id)
    if (!membership) return response.untyped(notFound())
    if (membership.role !== 'owner') {
      return response.untyped(errorResponse(403, 'insufficient_role', 'Only the owner can delete a workspace.'))
    }
    db.workspaces = db.workspaces.filter((workspace) => workspace.id !== params.id)
    db.memberships = db.memberships.filter((m) => m.workspace_id !== params.id)
    return response.untyped(noContent())
  }),

  http.get('/api/v1/workspaces/members/', ({ request, query, response }) => {
    const ctx = authorize(request)
    if (ctx instanceof Response) return response.untyped(ctx)
    const role = query.get('role')
    const search = (query.get('search') ?? '').toLowerCase()
    const items = db.memberships
      .filter((m) => m.workspace_id === ctx.workspace.id && (!role || m.role === role))
      .map(toMembership)
      .filter((m) => !search || `${m.user.full_name} ${m.user.email}`.toLowerCase().includes(search))
    return response(200).json(paginate(request, items))
  }),

  http.get('/api/v1/workspaces/members/{id}/', ({ request, params, response }) => {
    const ctx = authorize(request)
    if (ctx instanceof Response) return response.untyped(ctx)
    const membership = db.memberships.find((m) => m.id === params.id && m.workspace_id === ctx.workspace.id)
    if (!membership) return response.untyped(notFound())
    return response(200).json(toMembership(membership))
  }),

  http.patch('/api/v1/workspaces/members/{id}/', async ({ request, params, response }) => {
    const ctx = authorize(request, 'admin')
    if (ctx instanceof Response) return response.untyped(ctx)
    const membership = db.memberships.find((m) => m.id === params.id && m.workspace_id === ctx.workspace.id)
    if (!membership) return response.untyped(notFound())
    const body = (await request.json()) as Schemas['PatchedMembershipRequest']
    if (membership.role === 'owner' || body.role === 'owner') {
      return response.untyped(errorResponse(409, 'owner_role_locked', 'Ownership cannot be changed here.'))
    }
    if (body.role) membership.role = body.role
    return response(200).json(toMembership(membership))
  }),

  http.delete('/api/v1/workspaces/members/{id}/', ({ request, params, response }) => {
    const ctx = authorize(request)
    if (ctx instanceof Response) return response.untyped(ctx)
    const membership = db.memberships.find((m) => m.id === params.id && m.workspace_id === ctx.workspace.id)
    if (!membership) return response.untyped(notFound())
    const isSelf = membership.user_id === ctx.user.id
    if (!isSelf && ctx.membership.role !== 'owner' && ctx.membership.role !== 'admin') {
      return response.untyped(errorResponse(403, 'insufficient_role', 'Your role does not allow this action.'))
    }
    if (membership.role === 'owner') {
      return response.untyped(errorResponse(409, 'owner_cannot_leave', 'The owner cannot be removed.'))
    }
    db.memberships = db.memberships.filter((m) => m.id !== membership.id)
    return response.untyped(noContent())
  }),

  http.get('/api/v1/workspaces/invitations/', ({ request, response }) => {
    const ctx = authorize(request, 'admin')
    if (ctx instanceof Response) return response.untyped(ctx)
    const items = db.invitations
      .filter((invitation) => invitation.workspace_id === ctx.workspace.id && invitation.status === 'pending')
      .map(toInvitation)
    return response(200).json(paginate(request, items))
  }),

  http.post('/api/v1/workspaces/invitations/', async ({ request, response }) => {
    await mockDelay()
    const ctx = authorize(request, 'admin')
    if (ctx instanceof Response) return response.untyped(ctx)
    const body = (await request.json()) as Partial<Schemas['InvitationRequest']>
    const email = String(body.email ?? '').trim()
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      return response.untyped(validationError({ email: ['Enter a valid email address.'] }))
    }
    const invitation: MockInvitation = {
      id: uuid(),
      workspace_id: ctx.workspace.id,
      token: uuid(),
      email,
      role: body.role ?? 'agent',
      status: 'pending',
      invited_by: { id: ctx.user.id, email: ctx.user.email, full_name: ctx.user.full_name },
      expires_at: new Date(Date.now() + 7 * 86_400_000).toISOString(),
      created_at: nowIso(),
    }
    db.invitations.push(invitation)
    return response(201).json(toInvitation(invitation))
  }),

  http.delete('/api/v1/workspaces/invitations/{id}/', ({ request, params, response }) => {
    const ctx = authorize(request, 'admin')
    if (ctx instanceof Response) return response.untyped(ctx)
    const invitation = db.invitations.find((i) => i.id === params.id && i.workspace_id === ctx.workspace.id)
    if (!invitation) return response.untyped(notFound())
    invitation.status = 'revoked'
    return response.untyped(noContent())
  }),

  http.post('/api/v1/workspaces/invitations/accept/', async ({ request, response }) => {
    await mockDelay()
    const user = authenticate(request)
    if (user instanceof Response) return response.untyped(user)
    const body = (await request.json()) as Partial<Schemas['InvitationAcceptRequest']>
    const invitation = db.invitations.find((i) => i.token === body.token && i.status === 'pending')
    if (!invitation) {
      return response.untyped(errorResponse(400, 'invitation_invalid', 'This invitation is invalid or has expired.'))
    }
    if (invitation.email.toLowerCase() !== user.email.toLowerCase()) {
      return response.untyped(errorResponse(403, 'invitation_email_mismatch', 'This invitation was sent to a different email address.'))
    }
    const workspace = db.workspaces.find((candidate) => candidate.id === invitation.workspace_id)!
    invitation.status = 'accepted'
    if (!db.memberships.some((m) => m.workspace_id === workspace.id && m.user_id === user.id)) {
      db.memberships.push({ id: uuid(), workspace_id: workspace.id, user_id: user.id, role: invitation.role ?? 'agent', created_at: nowIso() })
    }
    return response(200).json({
      workspace: { id: workspace.id, name: workspace.name, slug: workspace.slug },
      role: invitation.role ?? 'agent',
    })
  }),

  http.post('/api/v1/inbox/ws-ticket/', ({ request, response }) => {
    const ctx = authorize(request)
    if (ctx instanceof Response) return response.untyped(ctx)
    return response(200).json({ ticket: `mock-ticket.${uuid()}`, expires_in: 30, path: '/ws/v1/' })
  }),
]
