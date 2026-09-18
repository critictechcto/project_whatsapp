import { MailWarning, X } from 'lucide-react'
import { useState } from 'react'
import { Button } from '../../../components/app/Button'
import { useMe } from '../auth/session'
import { useResendVerification } from '../auth/useResendVerification'

/** sessionStorage key: the user id whose reminder was dismissed in this tab session. */
export const VERIFY_BANNER_DISMISSED_KEY = 'upchatz.verifyBannerDismissed'

function readDismissed(): string | null {
  try {
    return window.sessionStorage.getItem(VERIFY_BANNER_DISMISSED_KEY)
  } catch {
    return null
  }
}

function writeDismissed(userId: string) {
  try {
    window.sessionStorage.setItem(VERIFY_BANNER_DISMISSED_KEY, userId)
  } catch {
    // Storage unavailable: the banner stays hidden until the page reloads.
  }
}

/** Reminds a signed-in user with an unconfirmed email to confirm it. Nothing is blocked meanwhile. */
export function EmailVerificationBanner() {
  const me = useMe()
  const [dismissedFor, setDismissedFor] = useState(readDismissed)
  const user = me.data

  if (!user || user.email_verified_at || dismissedFor === user.id) return null
  return (
    <BannerContent
      email={user.email}
      onDismiss={() => {
        writeDismissed(user.id)
        setDismissedFor(user.id)
      }}
    />
  )
}

function BannerContent({ email, onDismiss }: { email: string; onDismiss: () => void }) {
  const resend = useResendVerification()
  return (
    <div role="status" className="border-b border-amber/20 bg-amber-soft">
      <div className="flex items-start gap-2.5 px-4 py-2.5 sm:items-center sm:px-8">
        <MailWarning className="mt-0.5 size-4 shrink-0 text-amber sm:mt-0" aria-hidden="true" />
        <div className="flex min-w-0 flex-1 flex-col gap-2 sm:flex-row sm:items-center sm:gap-4">
          <p className="min-w-0 flex-1 text-[13px] text-ink">
            <strong className="font-medium">Confirm your email</strong> — we sent a link to{' '}
            <span className="break-all font-medium">{email}</span>.
          </p>
          <Button
            variant="secondary"
            size="sm"
            className="self-start sm:self-auto"
            loading={resend.sending}
            disabled={resend.disabled}
            onClick={resend.resend}
          >
            Resend email
          </Button>
        </div>
        <button
          type="button"
          onClick={onDismiss}
          aria-label="Dismiss email reminder"
          className="touch-target grid size-8 shrink-0 place-items-center rounded-md text-muted hover:bg-ink/5 hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/25"
        >
          <X className="size-4" aria-hidden="true" />
        </button>
      </div>
    </div>
  )
}
