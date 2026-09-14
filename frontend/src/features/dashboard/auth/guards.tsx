import { Navigate, Outlet, useLocation, useSearchParams } from 'react-router'
import { PageSpinner } from '../../../components/app/Spinner'
import { safeNext, useHasSession, useMe } from './session'
import { SessionError } from '../shell/RouteError'

/** Signed-out users go to `/app/login?next=<current path>`. */
export function RequireAuth() {
  const hasSession = useHasSession()
  const location = useLocation()
  const me = useMe()

  if (!hasSession) {
    const next = `${location.pathname}${location.search}`
    return <Navigate to={`/app/login?next=${encodeURIComponent(next)}`} replace />
  }
  if (me.isPending) return <PageSpinner label="Loading your account" />
  if (me.isError) return <SessionError error={me.error} onRetry={() => void me.refetch()} />
  return <Outlet />
}

/** Signed-in users skip login/register and go to `next` or `/app`. */
export function RedirectIfAuthed() {
  const hasSession = useHasSession()
  const [params] = useSearchParams()
  if (hasSession) return <Navigate to={safeNext(params.get('next')) ?? '/app'} replace />
  return <Outlet />
}
