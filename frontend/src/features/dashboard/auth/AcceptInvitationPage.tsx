import { useMutation, useQueryClient } from '@tanstack/react-query'
import { MailCheck } from 'lucide-react'
import { Link, useNavigate, useSearchParams } from 'react-router'
import { api, unwrap } from '../../../api/client'
import { queryKeys } from '../../../api/queryKeys'
import { errorMessage } from '../../../api/errors'
import { Button, buttonClasses } from '../../../components/app'
import { AuthLayout } from './AuthLayout'
import { FormError } from './FormError'
import { useHasSession, useMe, writeLastWorkspace } from './session'

/** `/app/invitations/accept?token=…` from the invitation email. Signed-out users log in or register first. */
export function AcceptInvitationPage() {
  const [params] = useSearchParams()
  const token = params.get('token') ?? ''
  const hasSession = useHasSession()
  const me = useMe()
  const queryClient = useQueryClient()
  const navigate = useNavigate()

  const accept = useMutation({
    mutationFn: () => unwrap(api.POST('/api/v1/workspaces/invitations/accept/', { body: { token } })),
    onSuccess: async (result) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.me }),
        queryClient.invalidateQueries({ queryKey: queryKeys.workspaces }),
      ])
      writeLastWorkspace(result.workspace.id)
      navigate(`/app/w/${result.workspace.id}`, { replace: true })
    },
  })

  const here = `/app/invitations/accept?token=${encodeURIComponent(token)}`

  if (!token) {
    return (
      <AuthLayout title="Invitation link is incomplete" description="Open the link from your invitation email again, or ask for a new invitation.">
        <Link to="/app" className={buttonClasses('secondary', 'md', 'w-full')}>
          Go to the app
        </Link>
      </AuthLayout>
    )
  }

  if (!hasSession) {
    return (
      <AuthLayout title="You've been invited" description="Log in or create an account with the email address the invitation was sent to.">
        <div className="flex flex-col gap-2.5">
          <Link to={`/app/login?next=${encodeURIComponent(here)}`} className={buttonClasses('primary', 'md', 'w-full')}>
            Log in to accept
          </Link>
          <Link to={`/app/register?next=${encodeURIComponent(here)}`} className={buttonClasses('secondary', 'md', 'w-full')}>
            Create an account
          </Link>
        </div>
      </AuthLayout>
    )
  }

  return (
    <AuthLayout
      title="Join the workspace"
      description={me.data ? `You're signed in as ${me.data.email}.` : undefined}
    >
      <div className="flex flex-col gap-4">
        <div className="flex items-center gap-3 text-sm text-muted">
          <MailCheck className="size-5 text-accent" aria-hidden="true" />
          Accepting adds this workspace to your account.
        </div>
        <FormError message={accept.isError ? errorMessage(accept.error, 'This invitation could not be accepted.') : undefined} />
        <Button loading={accept.isPending} onClick={() => accept.mutate()} className="w-full">
          Accept invitation
        </Button>
      </div>
    </AuthLayout>
  )
}
