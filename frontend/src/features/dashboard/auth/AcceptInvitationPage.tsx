import { useMutation, useQueryClient } from '@tanstack/react-query'
import { MailCheck } from 'lucide-react'
import { Link, useNavigate, useSearchParams } from 'react-router'
import { api, unwrap } from '../../../api/client'
import { queryKeys } from '../../../api/queryKeys'
import { ApiError, errorMessage } from '../../../api/errors'
import { Button, buttonClasses, useToast } from '../../../components/app'
import { roleLabels } from '../../../lib/roles'
import { AuthLayout } from './AuthLayout'
import { FormError } from './FormError'
import { useHasSession, useLogout, useMe, writeLastWorkspace } from './session'

type Problem = 'invalid' | 'mismatch' | null

/** Classifies accept errors: the backend sends `invalid` (token field) or 403 for another account's invite. */
function invitationProblem(error: unknown): Problem {
  if (!(error instanceof ApiError)) return null
  if (error.code === 'invitation_invalid' || error.status === 404) return 'invalid'
  if (error.code === 'invalid' && 'token' in error.fieldErrors) return 'invalid'
  if (error.status === 403) return 'mismatch'
  return null
}

/** `/app/invitations/accept?token=…` from the invitation email. Signed-out users log in or register first. */
export function AcceptInvitationPage() {
  const [params] = useSearchParams()
  const token = params.get('token') ?? ''
  const hasSession = useHasSession()
  const me = useMe()
  const logout = useLogout()
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const { toast } = useToast()

  const accept = useMutation({
    mutationFn: () => unwrap(api.POST('/api/v1/workspaces/invitations/accept/', { body: { token } })),
    onSuccess: async (result) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.me }),
        queryClient.invalidateQueries({ queryKey: queryKeys.workspaces }),
      ])
      writeLastWorkspace(result.workspace.id)
      toast({ title: `You joined ${result.workspace.name}`, description: `Your role is ${roleLabels[result.role]}.`, tone: 'success' })
      navigate(`/app/w/${result.workspace.id}`, { replace: true })
    },
  })

  const here = `/app/invitations/accept?token=${encodeURIComponent(token)}`
  const goToApp = (
    <Link to="/app" className={buttonClasses('secondary', 'md', 'w-full')}>
      Go to the app
    </Link>
  )

  if (!token) {
    return (
      <AuthLayout title="Invitation link is incomplete" description="Open the link from your invitation email again, or ask for a new invitation.">
        {goToApp}
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

  const problem = accept.isError ? invitationProblem(accept.error) : null

  if (problem === 'invalid') {
    return (
      <AuthLayout
        title="This invitation can't be used"
        description="It may have expired, been revoked, or already been accepted. Ask a workspace admin to send you a new invitation."
      >
        {goToApp}
      </AuthLayout>
    )
  }

  if (problem === 'mismatch') {
    return (
      <AuthLayout
        title="This invitation is for another email"
        description={
          me.data
            ? `You're signed in as ${me.data.email}. Log in with the address the invitation was sent to.`
            : 'Log in with the address the invitation was sent to.'
        }
      >
        <div className="flex flex-col gap-2.5">
          <Button
            className="w-full"
            onClick={() => void logout().then(() => navigate(`/app/login?next=${encodeURIComponent(here)}`, { replace: true }))}
          >
            Log out and switch account
          </Button>
          {goToApp}
        </div>
      </AuthLayout>
    )
  }

  return (
    <AuthLayout title="Join the workspace" description={me.data ? `You're signed in as ${me.data.email}.` : undefined}>
      <div className="flex flex-col gap-4">
        <div className="flex items-center gap-3 text-sm text-muted">
          <MailCheck className="size-5 shrink-0 text-accent" aria-hidden="true" />
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
