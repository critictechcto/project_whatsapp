import type { Tone } from '../../../components/app'
import { hasRole, type Role } from '../../../lib/roles'

/** What each role can do, in plain words (mirrors the backend role checks). */
export const roleDescriptions: Record<Role, string> = {
  owner: 'Full access, including billing, plan changes and deleting the workspace.',
  admin: 'Manages the team, WhatsApp numbers, templates and workspace settings.',
  agent: 'Handles conversations in the inbox and works with contacts.',
  viewer: "Can see conversations, contacts and reports, but can't change anything.",
}

export const roleTones: Record<Role, Tone> = {
  owner: 'green',
  admin: 'blue',
  agent: 'neutral',
  viewer: 'neutral',
}

/** Roles an admin or owner can hand out here. Ownership isn't transferred from this screen. */
export const assignableRoles: readonly Role[] = ['admin', 'agent', 'viewer']

export type MemberTarget = { role: Role; isSelf: boolean }

/** Admins and owners change other members' roles; the owner's role is locked. */
export function canChangeRole(actor: Role, target: MemberTarget): boolean {
  return hasRole(actor, 'admin') && !target.isSelf && target.role !== 'owner'
}

/** Admins remove other members; only an owner can remove another owner. */
export function canRemove(actor: Role, target: MemberTarget): boolean {
  if (target.isSelf || !hasRole(actor, 'admin')) return false
  return target.role !== 'owner' || actor === 'owner'
}

/**
 * Admins and owners change the role on an open invitation (by sending a fresh one); only an owner
 * can replace an invitation for an owner, as on the backend.
 */
export function canChangeInvitationRole(actor: Role, invitedRole: Role): boolean {
  return hasRole(actor, 'admin') && (invitedRole !== 'owner' || actor === 'owner')
}
