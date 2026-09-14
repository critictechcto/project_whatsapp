import { createContext, useContext } from 'react'
import type { Workspace } from '../api/types'
import { hasRole, type Role } from './roles'

export type WorkspaceContextValue = {
  workspace: Workspace
  /** Shortcut for `workspace.id`. */
  workspaceId: string
  role: Role
  /** IANA zone used for display and scheduling, e.g. `Asia/Kolkata`. */
  timeZone: string
  can: (minRole: Role) => boolean
}

export const WorkspaceContext = createContext<WorkspaceContextValue | null>(null)

/** Current workspace inside `/app/w/:workspaceId/*`. Throws outside the workspace layout. */
export function useWorkspace(): WorkspaceContextValue {
  const value = useContext(WorkspaceContext)
  if (!value) throw new Error('useWorkspace() must be used inside the workspace layout')
  return value
}

/** Like `useWorkspace` but returns null outside a workspace (for shared components). */
export function useOptionalWorkspace(): WorkspaceContextValue | null {
  return useContext(WorkspaceContext)
}

export function workspaceContextValue(workspace: Workspace): WorkspaceContextValue {
  return {
    workspace,
    workspaceId: workspace.id,
    role: workspace.my_role,
    timeZone: workspace.time_zone || 'Asia/Kolkata',
    can: (minRole) => hasRole(workspace.my_role, minRole),
  }
}
