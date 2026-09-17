import type { RoleEnum, Schemas } from '../api/types'
import {
  DEMO_EMAIL,
  DEMO_INVITE_TOKEN,
  DEMO_PASSWORD,
  daysAgo,
  ids,
  seedMemberships,
  seedUsers,
  seedWorkspaces,
} from './seed'

/** Schema types mark server fields readonly; the mock database mutates them. */
export type Mutable<T> = { -readonly [K in keyof T]: T[K] }

export type MockUser = Mutable<Schemas['User']> & { password: string }
export type MockWorkspace = Mutable<Omit<Schemas['Workspace'], 'my_role'>>
export type MockMembership = { id: string; workspace_id: string; user_id: string; role: RoleEnum; created_at: string }
export type MockInvitation = Mutable<Schemas['Invitation']> & { workspace_id: string; token: string }

export type MockDb = {
  users: MockUser[]
  workspaces: MockWorkspace[]
  memberships: MockMembership[]
  invitations: MockInvitation[]
  /**
   * A new object on every `resetMockDb()`. Area mock state caches key on its identity to rebuild
   * after a reset. (The mock refresh session lives in `mocks/session.ts`, outside the database.)
   */
  generation: object
}

function daysFromNow(days: number): string {
  return new Date(Date.now() + days * 86_400_000).toISOString()
}

function membershipId(index: number) {
  return `9c2e4a6b-1d3f-4b5a-8c7e-${String(index + 1).padStart(12, '0')}`
}

function build(): MockDb {
  const users: MockUser[] = seedUsers.map((user) => ({ ...user, email_verified_at: user.date_joined, password: DEMO_PASSWORD }))
  const priya = users.find((user) => user.id === ids.priya)!
  const farhan = users.find((user) => user.id === ids.farhan)!

  return {
    users,
    workspaces: seedWorkspaces.map((workspace) => ({ ...workspace })),
    memberships: seedMemberships.map((membership, index) => ({ ...membership, id: membershipId(index) })),
    invitations: [
      {
        id: '3f8b2d6a-4c1e-4a9b-9d7f-5e2c8a1b3d41',
        workspace_id: ids.sharmaSweets,
        token: 'sharma-invite-token',
        email: 'kavya.iyer@gmail.com',
        role: 'agent',
        status: 'pending',
        invited_by: { id: priya.id, email: priya.email, full_name: priya.full_name },
        // Accepting checks the real clock, so pending invitations expire relative to now, not SEED_NOW.
        expires_at: daysFromNow(5),
        created_at: daysAgo(2),
      },
      {
        id: '3f8b2d6a-4c1e-4a9b-9d7f-5e2c8a1b3d42',
        workspace_id: ids.anandTextiles,
        token: DEMO_INVITE_TOKEN,
        email: DEMO_EMAIL,
        role: 'agent',
        status: 'pending',
        invited_by: { id: farhan.id, email: farhan.email, full_name: farhan.full_name },
        expires_at: daysFromNow(6),
        created_at: daysAgo(1),
      },
    ],
    generation: {},
  }
}

/** The in-memory mock database. Mutated by handlers; reset between tests. */
export const db: MockDb = build()

export function resetMockDb() {
  Object.assign(db, build())
}
