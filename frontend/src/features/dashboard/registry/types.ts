import type { LucideIcon } from 'lucide-react'
import type { HttpHandler } from 'msw'
import type { RouteObject } from 'react-router'
import type { Role } from '../../../lib/roles'

/** Route metadata read by the shell (document title, role gate). */
export type AreaRouteHandle = {
  /** Page title, shown in the document title. */
  title?: string
  /** Members below this role see a "no access" state instead of the page. */
  minRole?: Role
}

/**
 * A route inside `/app/w/:workspaceId/`. Paths are relative (`'templates'`, `'templates/:id'`).
 * Always use `lazy` so each area stays in its own chunk.
 */
export type AreaRoute = RouteObject & { handle?: AreaRouteHandle }

export type NavGroup = 'main' | 'manage'

export type NavItem = {
  id: string
  label: string
  /** Relative to `/app/w/:workspaceId/`; `''` is the workspace home. */
  to: string
  icon: LucideIcon
  /** Sort order within the group, ascending. */
  order: number
  group?: NavGroup
  /** Hidden for members below this role. Default `viewer`. */
  minRole?: Role
  /** Only active on an exact match (used by home). */
  end?: boolean
}

export type AreaMockHandlers = HttpHandler[]
