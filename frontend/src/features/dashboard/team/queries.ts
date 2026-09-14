import { api, unwrap } from '../../../api/client'
import { useCursorQuery } from '../../../api/pagination'
import { workspaceKeys } from '../../../api/queryKeys'
import type { Invitation, Membership } from '../../../api/types'
import { useWorkspace } from '../../../lib/workspace'

/** Query keys for this area: `['ws', workspaceId, 'team', ...]`. */
export const teamKeys = workspaceKeys('team')

export function invitationsKey(workspaceId: string) {
  return teamKeys.custom(workspaceId, 'invitations')
}

export function useMembers(search: string) {
  const { workspaceId } = useWorkspace()
  return useCursorQuery<Membership>({
    queryKey: teamKeys.list(workspaceId, { search }),
    queryFn: ({ cursor, signal }) =>
      unwrap(api.GET('/api/v1/workspaces/members/', { params: { query: { cursor, search: search || undefined } }, signal })),
  })
}

/** Pending invitations (admin+ only; the API returns 403 for other roles). */
export function useInvitations(enabled: boolean) {
  const { workspaceId } = useWorkspace()
  return useCursorQuery<Invitation>({
    queryKey: invitationsKey(workspaceId),
    queryFn: ({ cursor, signal }) => unwrap(api.GET('/api/v1/workspaces/invitations/', { params: { query: { cursor } }, signal })),
    enabled,
  })
}

export type InvitationsQuery = ReturnType<typeof useInvitations>
