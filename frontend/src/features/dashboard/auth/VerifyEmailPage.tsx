import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef } from 'react'
import { Link, useSearchParams } from 'react-router'
import { api, unwrap } from '../../../api/client'
import { errorMessage, isApiError } from '../../../api/errors'
import { queryKeys } from '../../../api/queryKeys'
import { Button } from '../../../components/app/Button'
import { Spinner } from '../../../components/app/Spinner'
import { buttonClasses } from '../../../components/app/styles'
import { AuthLayout } from './AuthLayout'
import { FormError } from './FormError'
import { useHasSession } from './session'
import { useResendVerification } from './useResendVerification'

/**
 * `/app/verify-email?token=…` from the confirmation email. Works signed in or out: it confirms the
 * address on load (the endpoint is idempotent) and never redirects.
 */
export function VerifyEmailPage() {
  const [params] = useSearchParams()
  const token = params.get('token') ?? ''
  const hasSession = useHasSession()
  const queryClient = useQueryClient()

  const verify = useMutation({
    mutationFn: (value: string) => unwrap(api.POST('/api/v1/auth/email/verify/', { body: { token: value } })),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.me }),
  })

  // One request per token, also under StrictMode's double effects.
  const sentFor = useRef<string | null>(null)
  const { mutate } = verify
  useEffect(() => {
    if (!token || sentFor.current === token) return
    sentFor.current = token
    mutate(token)
  }, [token, mutate])

  const continueLink = hasSession ? (
    <Link to="/app" className={buttonClasses('primary', 'md', 'w-full')}>
      Go to the dashboard
    </Link>
  ) : (
    <Link to="/app/login" className={buttonClasses('primary', 'md', 'w-full')}>
      Log in
    </Link>
  )

  if (verify.isSuccess) {
    return (
      <AuthLayout title="Email confirmed" description="Thanks — your email address is confirmed.">
        {continueLink}
      </AuthLayout>
    )
  }

  const invalid = !token || (verify.isError && isApiError(verify.error, 'invalid'))
  if (invalid) return <VerifyFailed hasSession={hasSession} />

  if (verify.isError) {
    return (
      <AuthLayout title="We couldn't confirm your email">
        <div className="flex flex-col gap-4">
          <FormError message={errorMessage(verify.error)} />
          <Button className="w-full" loading={verify.isPending} onClick={() => verify.mutate(token)}>
            Try again
          </Button>
        </div>
      </AuthLayout>
    )
  }

  return (
    <AuthLayout title="Confirming your email">
      <div role="status" className="flex items-center gap-3 text-sm text-muted">
        <Spinner size="sm" label={null} />
        Confirming your email address…
      </div>
    </AuthLayout>
  )
}

function VerifyFailed({ hasSession }: { hasSession: boolean }) {
  const resend = useResendVerification()
  return (
    <AuthLayout
      title="This link is invalid or has expired"
      description={
        hasSession
          ? 'Confirmation links expire after a while. Send yourself a new one.'
          : 'Confirmation links expire after a while. Log in to send yourself a new one.'
      }
    >
      {hasSession ? (
        <div className="flex flex-col gap-2.5">
          <Button className="w-full" loading={resend.sending} disabled={resend.disabled} onClick={resend.resend}>
            Send a new link
          </Button>
          <Link to="/app" className={buttonClasses('secondary', 'md', 'w-full')}>
            Go to the dashboard
          </Link>
        </div>
      ) : (
        <Link to="/app/login" className={buttonClasses('primary', 'md', 'w-full')}>
          Log in
        </Link>
      )}
    </AuthLayout>
  )
}
