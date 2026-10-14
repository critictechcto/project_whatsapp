import type { Schemas } from '../../../api/types'
import { hasRole } from '../../../lib/roles'
import type { MockMembership } from '../../../mocks/db'
import { authorize, errorResponse, http, mockDelay, validationError } from '../../../mocks/utils'
import type { AreaMockHandlers } from '../registry/types'

/**
 * Onboarding handlers (docs/contracts/onboarding.md). Like the backend's data migration, seeded
 * memberships count as welcomed; memberships created in this session (a new workspace) are not.
 */
type Flags = { welcome_completed: boolean; tour_completed: boolean; checklist_dismissed: boolean }

const sessionStart = Date.now()
const flags = new Map<string, Flags>()
const goals = new Map<string, Schemas['Onboarding']['goal']>()
const GOALS = ['sell', 'marketing', 'support', '']

function flagsOf(membership: MockMembership): Flags {
  let state = flags.get(membership.id)
  if (!state) {
    const seeded = Date.parse(membership.created_at) < sessionStart
    state = { welcome_completed: seeded, tour_completed: seeded, checklist_dismissed: false }
    flags.set(membership.id, state)
  }
  return state
}

function onboardingOf(membership: MockMembership): Schemas['Onboarding'] {
  return {
    goal: goals.get(membership.workspace_id) ?? '',
    ...flagsOf(membership),
    can_set_goal: hasRole(membership.role, 'admin'),
  }
}

/** Test helper: forget all onboarding state (seeded members become welcomed again). */
export function resetOnboardingMocks() {
  flags.clear()
  goals.clear()
}

/** Test helper: set a workspace's goal as if an admin had chosen it. */
export function setMockWorkspaceGoal(workspaceId: string, goal: Schemas['Onboarding']['goal']) {
  goals.set(workspaceId, goal)
}

/** Test helper: the stored flags of a membership (as the next GET would return them). */
export function mockOnboardingFlags(membership: MockMembership): Readonly<Flags> {
  return { ...flagsOf(membership) }
}

export const handlers: AreaMockHandlers = [
  http.get('/api/v1/workspaces/onboarding/', ({ request, response }) => {
    const ctx = authorize(request)
    if (ctx instanceof Response) return response.untyped(ctx)
    return response(200).json(onboardingOf(ctx.membership))
  }),

  http.patch('/api/v1/workspaces/onboarding/', async ({ request, response }) => {
    await mockDelay(150)
    const ctx = authorize(request)
    if (ctx instanceof Response) return response.untyped(ctx)
    const body = (await request.json()) as Schemas['PatchedOnboardingRequest']
    if (body.goal !== undefined) {
      if (!GOALS.includes(body.goal)) {
        return response.untyped(validationError({ goal: [`"${body.goal}" is not a valid choice.`] }))
      }
      if (!hasRole(ctx.membership.role, 'admin')) {
        return response.untyped(errorResponse(403, 'insufficient_role', 'Only admins and owners can set the workspace goal.'))
      }
      goals.set(ctx.workspace.id, body.goal)
    }
    const state = flagsOf(ctx.membership)
    for (const flag of ['welcome_completed', 'tour_completed', 'checklist_dismissed'] as const) {
      if (typeof body[flag] === 'boolean') state[flag] = body[flag]
    }
    return response(200).json(onboardingOf(ctx.membership))
  }),
]
