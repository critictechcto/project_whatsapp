import type { QueryClient } from '@tanstack/react-query'
import type { NavigateFunction } from 'react-router'
import { queryKeys } from '../../../api/queryKeys'
import type { Me } from '../../../api/types'

/**
 * After leaving or deleting a workspace: drop it from the cached memberships first (so `/app`
 * doesn't redirect straight back), then go to `/app`, then refresh from the server.
 */
export function exitWorkspace(queryClient: QueryClient, navigate: NavigateFunction, workspaceId: string) {
  queryClient.setQueryData<Me>(queryKeys.me, (me) =>
    me ? { ...me, memberships: me.memberships.filter((m) => m.workspace_id !== workspaceId) } : me,
  )
  navigate('/app', { replace: true })
  queryClient.removeQueries({ queryKey: queryKeys.workspace(workspaceId) })
  queryClient.removeQueries({ queryKey: [...queryKeys.workspaces, workspaceId] })
  void queryClient.invalidateQueries({ queryKey: queryKeys.workspaces })
  void queryClient.invalidateQueries({ queryKey: queryKeys.me })
}
