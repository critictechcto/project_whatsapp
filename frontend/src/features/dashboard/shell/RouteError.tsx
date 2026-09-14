import { CircleAlert, Compass, Lock } from 'lucide-react'
import { isRouteErrorResponse, Link, useRouteError } from 'react-router'
import { isApiError } from '../../../api/errors'
import { Button, buttonClasses, EmptyState } from '../../../components/app'

function isChunkLoadError(error: unknown) {
  return error instanceof Error && /dynamically imported module|Importing a module script failed|Failed to fetch/i.test(error.message)
}

/** `errorElement` for dashboard routes. */
export function RouteError() {
  const error = useRouteError()

  if (isRouteErrorResponse(error) && error.status === 404) return <NotFound />

  const chunk = isChunkLoadError(error)
  return (
    <div className="mx-auto max-w-xl px-4 py-16">
      <EmptyState
        icon={<CircleAlert />}
        title={chunk ? 'A new version is available' : 'Something went wrong'}
        description={
          chunk
            ? 'Part of the app could not load, usually because it was just updated. Reload to continue.'
            : 'This page hit an unexpected error. Reloading usually fixes it; if not, contact support.'
        }
        action={<Button onClick={() => window.location.reload()}>Reload page</Button>}
      />
    </div>
  )
}

export function NotFound() {
  return (
    <div className="mx-auto max-w-xl px-4 py-16">
      <EmptyState
        icon={<Compass />}
        title="Page not found"
        description="The link may be old, or the page may have moved."
        action={
          <Link to="/app" className={buttonClasses('secondary')}>
            Go to your workspace
          </Link>
        }
      />
    </div>
  )
}

export function NoAccess() {
  return (
    <EmptyState
      icon={<Lock />}
      title="You don't have access to this page"
      description="Your role in this workspace doesn't include it. Ask a workspace owner or admin if you need access."
    />
  )
}

/** Shown when `/auth/me/` fails for a reason other than an expired session. */
export function SessionError({ error, onRetry }: { error: unknown; onRetry: () => void }) {
  const offline = isApiError(error, 'network_error')
  return (
    <div className="mx-auto max-w-xl px-4 py-16">
      <EmptyState
        icon={<CircleAlert />}
        title={offline ? "Can't reach UpChatz" : 'Your account could not be loaded'}
        description={offline ? 'Check your internet connection and try again.' : 'Please try again in a moment.'}
        action={<Button onClick={onRetry}>Try again</Button>}
      />
    </div>
  )
}
