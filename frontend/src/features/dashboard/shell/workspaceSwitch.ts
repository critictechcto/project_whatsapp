import type { QueryClient } from '@tanstack/react-query'
import { setActiveWorkspaceId } from '../../../api/client'
import { clearWorkspaceQueries } from '../../../api/queryKeys'
import { writeLastWorkspace } from '../auth/session'

const lastWorkspace = new WeakMap<QueryClient, string>()

/**
 * Makes `workspaceId` the active workspace. Switching from another workspace drops every
 * workspace-scoped query first, so no data from the previous tenant can render.
 */
export function enterWorkspace(queryClient: QueryClient, workspaceId: string) {
  const previous = lastWorkspace.get(queryClient)
  if (previous && previous !== workspaceId) clearWorkspaceQueries(queryClient)
  lastWorkspace.set(queryClient, workspaceId)
  setActiveWorkspaceId(workspaceId)
  writeLastWorkspace(workspaceId)
}

export function leaveWorkspace() {
  setActiveWorkspaceId(null)
}
