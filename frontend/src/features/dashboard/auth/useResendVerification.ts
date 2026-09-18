import { useMutation } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { api, unwrap } from '../../../api/client'
import { errorMessage, isApiError } from '../../../api/errors'
import { useToast } from '../../../components/app/toastContext'

/** How long the resend button stays disabled after a send. */
export const RESEND_COOLDOWN_MS = 60_000

/**
 * Sends a new email-confirmation link to the signed-in user (`POST /auth/email/verify/request/`),
 * toasts the outcome and disables resending for a minute after a successful send.
 */
export function useResendVerification() {
  const { toast } = useToast()
  const [coolingDown, setCoolingDown] = useState(false)

  useEffect(() => {
    if (!coolingDown) return
    const timer = window.setTimeout(() => setCoolingDown(false), RESEND_COOLDOWN_MS)
    return () => window.clearTimeout(timer)
  }, [coolingDown])

  const mutation = useMutation({
    mutationFn: () => unwrap(api.POST('/api/v1/auth/email/verify/request/')),
    onSuccess: () => {
      setCoolingDown(true)
      toast({ title: 'Sent — check your inbox', tone: 'success' })
    },
    onError: (error) => {
      const throttled = isApiError(error) && error.status === 429
      toast({ title: throttled ? 'Too many requests, try again later' : errorMessage(error), tone: 'error' })
    },
  })

  return {
    resend: () => mutation.mutate(),
    sending: mutation.isPending,
    /** True while sending or during the cooldown. */
    disabled: mutation.isPending || coolingDown,
  }
}
