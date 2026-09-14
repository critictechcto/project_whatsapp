import { HttpResponse } from 'msw'
import type { Schemas } from '../../../api/types'
import { db, type MockInvitation, type MockMembership } from '../../../mocks/db'
import { authenticate, authorize, errorResponse, http, mockDelay, notFound, nowIso, paginate, uuid, validationError } from '../../../mocks/utils'
import type { AreaMockHandlers } from '../registry/types'

/**
 * Team handlers with the backend's membership rules (they override the shared fallbacks):
 * owner changes need an owner, the last owner can't be demoted or removed, re-inviting replaces
 * the open invitation, and accepting an invalid token is a validation error.
 */

const INVITATION_DAYS = 7
const noContent = () => new HttpResponse(null, { status: 204 })

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

function ownerCount(workspaceId: string) {
  return db.memberships.filter((m) => m.workspace_id === workspaceId && m.role === 'owner').length
}

const lastOwner = () => errorResponse(409, 'last_owner', 'A workspace needs at least one owner.')
const ownerOnly = (message: string) => errorResponse(403, 'insufficient_role', message)
const ROLES = new Set(['owner', 'admin', 'agent', 'viewer'])

export const handlers: AreaMockHandlers = [
  // The shared handlers register `GET /workspaces/{id}/` before these static paths, which
  // would answer them with 404, so the team lists are served here.
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

  http.get('/api/v1/workspaces/invitations/', ({ request, response }) => {
    const ctx = authorize(request, 'admin')
    if (ctx instanceof Response) return response.untyped(ctx)
    const items = db.invitations
      .filter((invitation) => invitation.workspace_id === ctx.workspace.id && invitation.status === 'pending')
      .map(toInvitation)
    return response(200).json(paginate(request, items))
  }),

  http.patch('/api/v1/workspaces/members/{id}/', async ({ request, params, response }) => {
    await mockDelay()
    const ctx = authorize(request, 'admin')
    if (ctx instanceof Response) return response.untyped(ctx)
    const membership = db.memberships.find((m) => m.id === params.id && m.workspace_id === ctx.workspace.id)
    if (!membership) return response.untyped(notFound())
    const body = (await request.json()) as Schemas['PatchedMembershipRequest']
    if (!body.role || !ROLES.has(body.role)) {
      return response.untyped(validationError({ role: [`"${String(body.role)}" is not a valid choice.`] }))
    }
    const touchesOwner = membership.role === 'owner' || body.role === 'owner'
    if (touchesOwner && ctx.membership.role !== 'owner') {
      return response.untyped(ownerOnly('Only an owner can change owner roles.'))
    }
    if (membership.role === 'owner' && body.role !== 'owner' && ownerCount(ctx.workspace.id) <= 1) {
      return response.untyped(lastOwner())
    }
    membership.role = body.role
    return response(200).json(toMembership(membership))
  }),

  http.delete('/api/v1/workspaces/members/{id}/', async ({ request, params, response }) => {
    await mockDelay()
    const ctx = authorize(request)
    if (ctx instanceof Response) return response.untyped(ctx)
    const membership = db.memberships.find((m) => m.id === params.id && m.workspace_id === ctx.workspace.id)
    if (!membership) return response.untyped(notFound())
    const isSelf = membership.user_id === ctx.user.id
    if (!isSelf) {
      if (ctx.membership.role !== 'owner' && ctx.membership.role !== 'admin') {
        return response.untyped(errorResponse(403, 'insufficient_role', 'Your role does not allow this action.'))
      }
      if (membership.role === 'owner' && ctx.membership.role !== 'owner') {
        return response.untyped(ownerOnly('Only an owner can remove another owner.'))
      }
    }
    if (membership.role === 'owner' && ownerCount(ctx.workspace.id) <= 1) {
      return response.untyped(
        isSelf
          ? errorResponse(409, 'last_owner', "You're the only owner. Make someone else an owner or delete the workspace instead.")
          : lastOwner(),
      )
    }
    db.memberships = db.memberships.filter((m) => m.id !== membership.id)
    return response.untyped(noContent())
  }),

  http.post('/api/v1/workspaces/invitations/', async ({ request, response }) => {
    await mockDelay()
    const ctx = authorize(request, 'admin')
    if (ctx instanceof Response) return response.untyped(ctx)
    const body = (await request.json()) as Partial<Schemas['InvitationRequest']>
    const email = String(body.email ?? '').trim().toLowerCase()
    const role = body.role ?? 'agent'
    const errors: Record<string, string[]> = {}
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) errors.email = ['Enter a valid email address.']
    if (!ROLES.has(role)) errors.role = [`"${role}" is not a valid choice.`]
    if (Object.keys(errors).length) return response.untyped(validationError(errors))
    if (role === 'owner' && ctx.membership.role !== 'owner') {
      return response.untyped(ownerOnly('Only an owner can invite another owner.'))
    }
    const alreadyMember = db.memberships.some(
      (m) => m.workspace_id === ctx.workspace.id && db.users.find((u) => u.id === m.user_id)?.email.toLowerCase() === email,
    )
    if (alreadyMember) {
      return response.untyped(errorResponse(409, 'conflict', 'This person is already a member of the workspace.'))
    }

    // Re-inviting replaces the open invitation (a fresh token and expiry).
    for (const open of db.invitations) {
      if (open.workspace_id === ctx.workspace.id && open.status === 'pending' && open.email.toLowerCase() === email) {
        open.status = 'revoked'
      }
    }
    const invitation: MockInvitation = {
      id: uuid(),
      workspace_id: ctx.workspace.id,
      token: uuid(),
      email,
      role,
      status: 'pending',
      invited_by: { id: ctx.user.id, email: ctx.user.email, full_name: ctx.user.full_name },
      expires_at: new Date(Date.now() + INVITATION_DAYS * 86_400_000).toISOString(),
      created_at: nowIso(),
    }
    db.invitations.unshift(invitation)
    return response(201).json(toInvitation(invitation))
  }),

  http.post('/api/v1/workspaces/invitations/accept/', async ({ request, response }) => {
    await mockDelay()
    const user = authenticate(request)
    if (user instanceof Response) return response.untyped(user)
    const body = (await request.json()) as Partial<Schemas['InvitationAcceptRequest']>
    const invitation = db.invitations.find(
      (i) => i.token === body.token && i.status === 'pending' && new Date(i.expires_at).getTime() > Date.now(),
    )
    if (!invitation) {
      return response.untyped(validationError({ token: ['This invitation is invalid or has expired.'] }))
    }
    if (invitation.email.toLowerCase() !== user.email.toLowerCase()) {
      return response.untyped(
        errorResponse(403, 'permission_denied', 'This invitation was sent to a different email address.'),
      )
    }
    const workspace = db.workspaces.find((candidate) => candidate.id === invitation.workspace_id)
    if (!workspace) return response.untyped(validationError({ token: ['This invitation is invalid or has expired.'] }))
    invitation.status = 'accepted'
    const role = invitation.role ?? 'agent'
    if (!db.memberships.some((m) => m.workspace_id === workspace.id && m.user_id === user.id)) {
      db.memberships.push({ id: uuid(), workspace_id: workspace.id, user_id: user.id, role, created_at: nowIso() })
    }
    return response(200).json({ workspace: { id: workspace.id, name: workspace.name, slug: workspace.slug }, role })
  }),
]
