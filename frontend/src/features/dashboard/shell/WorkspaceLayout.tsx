import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useLayoutEffect, useMemo } from 'react'
import { Outlet, useLocation, useMatches, useNavigate, useParams } from 'react-router'
import { api, unwrap } from '../../../api/client'
import { queryKeys } from '../../../api/queryKeys'
import { PageSpinner } from '../../../components/app/Spinner'
import { useToast } from '../../../components/app/toastContext'
import { site } from '../../../config/site'
import { useRealtimeConnection } from '../../../lib/realtime/hooks'
import { hasRole } from '../../../lib/roles'
import { WorkspaceContext, workspaceContextValue } from '../../../lib/workspace'
import { useMe } from '../auth/session'
import type { AreaRouteHandle } from '../registry/types'
import { AppShell } from './AppShell'
import { NoAccess, NotFound } from './RouteError'
import { enterWorkspace, leaveWorkspace } from './workspaceSwitch'

function useRouteHandle(): AreaRouteHandle {
  const matches = useMatches()
  return useMemo(() => {
    const handle: AreaRouteHandle = {}
    for (const match of matches) {
      const current = match.handle as AreaRouteHandle | undefined
      if (current?.title) handle.title = current.title
      if (current?.minRole) handle.minRole = current.minRole
    }
    return handle
  }, [matches])
}

/** `/app/w/:workspaceId/*`: checks membership, activates the workspace, runs realtime, renders the shell. */
export function WorkspaceLayout() {
  const { workspaceId = '' } = useParams()
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const { toast } = useToast()
  const me = useMe()
  const isMember = Boolean(me.data?.memberships.some((m) => m.workspace_id === workspaceId))

  // Before children fetch (their queries start in passive effects), point the client at this workspace.
  useLayoutEffect(() => {
    if (isMember) enterWorkspace(queryClient, workspaceId)
  }, [queryClient, workspaceId, isMember])
  useEffect(() => () => leaveWorkspace(), [])

  const workspace = useQuery({
    queryKey: [...queryKeys.workspaces, workspaceId],
    queryFn: ({ signal }) => unwrap(api.GET('/api/v1/workspaces/{id}/', { params: { path: { id: workspaceId } }, signal })),
    enabled: isMember,
  })

  useRealtimeConnection(isMember ? workspaceId : undefined, () => {
    // Membership or session changed server-side: refresh memberships and re-pick a workspace.
    void queryClient.invalidateQueries({ queryKey: queryKeys.workspaces })
    void queryClient.invalidateQueries({ queryKey: queryKeys.me }).then(() => navigate('/app', { replace: true }))
    toast({ title: 'Your access to this workspace changed', tone: 'info' })
  })

  const handle = useRouteHandle()
  // The area segment after the workspace id: a new area fades in, moving within one (inbox threads,
  // detail pages) does not remount it.
  const area = useLocation().pathname.split(`/w/${workspaceId}`)[1]?.split('/')[1] ?? ''
  const context = useMemo(() => (workspace.data ? workspaceContextValue(workspace.data) : null), [workspace.data])

  useEffect(() => {
    const parts = [handle.title, context?.workspace.name, site.name].filter(Boolean)
    document.title = parts.join(' · ')
  }, [handle.title, context?.workspace.name])

  if (!isMember) return <NotFound />
  if (workspace.isError) return <NotFound />
  if (!context) return <PageSpinner label="Loading workspace" />

  return (
    <WorkspaceContext.Provider value={context}>
      <AppShell>
        <div key={`${workspaceId}/${area}`} className="page-enter">
          {handle.minRole && !hasRole(context.role, handle.minRole) ? <NoAccess /> : <Outlet />}
        </div>
      </AppShell>
    </WorkspaceContext.Provider>
  )
}
