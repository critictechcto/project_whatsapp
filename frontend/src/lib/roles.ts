export type Role = 'owner' | 'admin' | 'agent' | 'viewer'

const rank: Record<Role, number> = { viewer: 0, agent: 1, admin: 2, owner: 3 }

export const roleLabels: Record<Role, string> = {
  owner: 'Owner',
  admin: 'Admin',
  agent: 'Agent',
  viewer: 'Viewer',
}

/** True when `role` is at least `minRole` (owner > admin > agent > viewer). */
export function hasRole(role: Role | null | undefined, minRole: Role = 'viewer'): boolean {
  if (!role) return false
  return rank[role] >= rank[minRole]
}
