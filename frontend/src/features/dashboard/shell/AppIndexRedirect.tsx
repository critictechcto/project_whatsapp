import { Navigate } from 'react-router'
import { readLastWorkspace, useMe } from '../auth/session'

/** `/app`: last used workspace, else the first one, else workspace creation. */
export function AppIndexRedirect() {
  const me = useMe()
  const memberships = me.data?.memberships ?? []
  const last = readLastWorkspace()
  const target = memberships.find((m) => m.workspace_id === last) ?? memberships[0]
  return <Navigate to={target ? `/app/w/${target.workspace_id}` : '/app/workspaces/new'} replace />
}
