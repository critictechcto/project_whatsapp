import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Check, Circle, ExternalLink } from 'lucide-react'
import { useRef, useState } from 'react'
import { Link } from 'react-router'
import { api, unwrap } from '../../../api/client'
import { errorMessage, isApiError } from '../../../api/errors'
import { queryKeys } from '../../../api/queryKeys'
import { Button, buttonClasses, Dialog, Spinner } from '../../../components/app'
import { EmbeddedSignupCancelled, useFacebookSdk } from '../../../lib/integrations/facebook'
import { cn } from '../../../lib/cn'
import { useWorkspace } from '../../../lib/workspace'
import { actionErrorMessage } from '../settings/ui/hooks'
import { Notice } from '../settings/ui/Notice'
import { setupSteps, type SetupStepState } from './meta'
import { useSignupConfig, whatsappKeys } from './queries'

type Phase =
  | { kind: 'intro'; message?: string }
  | { kind: 'meta' }
  | { kind: 'saving' }
  | { kind: 'progress'; accountId: string }
  | { kind: 'error'; message: string; quota: boolean }

export function ConnectWhatsAppDialog({ onClose }: { onClose: () => void }) {
  const { workspaceId } = useWorkspace()
  const queryClient = useQueryClient()
  const [phase, setPhase] = useState<Phase>({ kind: 'intro' })
  const config = useSignupConfig(true)
  const sdk = useFacebookSdk(config.data)
  const busy = phase.kind === 'meta' || phase.kind === 'saving'

  async function start() {
    if (!config.data) return
    setPhase({ kind: 'meta' })
    let result
    try {
      result = await sdk.launcher.launch(config.data)
    } catch (error) {
      if (error instanceof EmbeddedSignupCancelled) {
        setPhase({ kind: 'intro', message: 'The Facebook window was closed before signup finished, so nothing was connected.' })
      } else {
        setPhase({ kind: 'error', message: errorMessage(error, "Meta's signup didn't finish. Please try again."), quota: false })
      }
      return
    }

    setPhase({ kind: 'saving' })
    try {
      const account = await unwrap(
        api.POST('/api/v1/whatsapp/embedded-signup/', {
          body: {
            code: result.code,
            waba_id: result.waba_id,
            phone_number_id: result.phone_number_id || undefined,
            business_id: result.business_id || undefined,
            coexistence: false,
          },
        }),
      )
      queryClient.setQueryData(whatsappKeys.detail(workspaceId, account.id), account)
      void queryClient.invalidateQueries({ queryKey: whatsappKeys.custom(workspaceId, 'accounts') })
      setPhase({ kind: 'progress', accountId: account.id })
    } catch (error) {
      setPhase({ kind: 'error', message: actionErrorMessage(error), quota: isApiError(error, 'quota_exceeded') })
    }
  }

  return (
    <Dialog
      open
      onOpenChange={(open) => !open && !busy && onClose()}
      dismissible={!busy}
      title="Connect WhatsApp"
      description="Connect a number through Meta's Embedded Signup."
      footer={
        phase.kind === 'intro' || phase.kind === 'error' ? (
          <>
            <Button variant="secondary" onClick={onClose}>
              Cancel
            </Button>
            <Button
              onClick={() => void start()}
              disabled={!config.data || !sdk.ready}
              loading={config.isPending || (!sdk.ready && !sdk.error)}
            >
              {phase.kind === 'error' ? 'Try again' : 'Continue with Facebook'}
            </Button>
          </>
        ) : phase.kind === 'progress' ? null : undefined
      }
    >
      {phase.kind === 'intro' || phase.kind === 'error' ? (
        <div className="flex flex-col gap-4 text-sm">
          {phase.kind === 'intro' && phase.message && (
            <Notice tone="info" role="status">
              {phase.message}
            </Notice>
          )}
          {phase.kind === 'error' && (
            <Notice
              tone="danger"
              role="alert"
              title="Couldn't connect"
              action={
                phase.quota ? (
                  <Link to={`/app/w/${workspaceId}/billing/plans`} className={buttonClasses('secondary', 'sm')} onClick={onClose}>
                    See plans
                  </Link>
                ) : undefined
              }
            >
              {phase.message}
            </Notice>
          )}
          {config.isError && (
            <Notice tone="danger" role="alert" title="Signup isn't available right now">
              {actionErrorMessage(config.error)}
            </Notice>
          )}
          {sdk.error && (
            <Notice tone="danger" role="alert" title="Couldn't load Facebook's signup window">
              Check that your browser or an ad blocker isn't blocking connect.facebook.net, then reload the page.
            </Notice>
          )}
          <p className="text-ink-2">A Facebook window opens where you:</p>
          <ol className="ml-5 list-decimal space-y-1.5 text-ink-2">
            <li>Log in and choose or create your Meta Business portfolio.</li>
            <li>Choose or create a WhatsApp Business Account and set the display name customers see.</li>
            <li>Add your number and verify it with a code sent by SMS or voice call.</li>
          </ol>
          <p className="text-[13px] text-muted">
            Use a number that can receive the code. A number already in use on the WhatsApp app or another provider may need to
            be moved first, depending on what Meta currently allows. Meta reviews display names, which can take some time.
          </p>
          <a
            href="https://developers.facebook.com/docs/whatsapp/embedded-signup"
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1 text-[13px] text-accent hover:underline"
          >
            About Embedded Signup on Meta's site
            <ExternalLink className="size-3.5" aria-hidden="true" />
          </a>
        </div>
      ) : phase.kind === 'meta' ? (
        <Waiting label="Finish the steps in the Facebook window." hint="If you don't see it, check whether your browser blocked a pop-up." />
      ) : phase.kind === 'saving' ? (
        <Waiting label="Connecting your account…" />
      ) : (
        <SetupProgress accountId={phase.accountId} onClose={onClose} onRetry={() => setPhase({ kind: 'intro' })} />
      )}
    </Dialog>
  )
}

function Waiting({ label, hint }: { label: string; hint?: string }) {
  return (
    <div role="status" className="flex flex-col items-center gap-3 py-6 text-center">
      <Spinner size="lg" label={label} />
      <p className="text-sm font-medium text-ink">{label}</p>
      {hint && <p className="text-[13px] text-muted">{hint}</p>}
    </div>
  )
}

function SetupProgress({ accountId, onClose, onRetry }: { accountId: string; onClose: () => void; onRetry: () => void }) {
  const { workspaceId } = useWorkspace()
  const queryClient = useQueryClient()
  const refreshed = useRef(false)

  const account = useQuery({
    queryKey: whatsappKeys.detail(workspaceId, accountId),
    queryFn: async ({ signal }) => {
      const data = await unwrap(api.GET('/api/v1/whatsapp/accounts/{id}/', { params: { path: { id: accountId } }, signal }))
      if ((data.onboarding_status === 'completed' || data.onboarding_status === 'failed') && !refreshed.current) {
        // Refresh everything that lists numbers (inbox, campaigns, usage) once setup settles.
        refreshed.current = true
        void queryClient.invalidateQueries({ queryKey: queryKeys.workspace(workspaceId) })
      }
      return data
    },
    refetchInterval: (query) => {
      const status = query.state.data?.onboarding_status
      return status === 'completed' || status === 'failed' ? false : 1500
    },
  })

  const status = account.data?.onboarding_status ?? null
  const steps = setupSteps(status)
  const number = account.data?.phone_numbers[0]

  if (status === 'completed') {
    return (
      <div className="flex flex-col gap-4">
        <Steps steps={steps} />
        <Notice tone="success" role="status" title="WhatsApp is connected">
          {number ? `${number.display_phone_number} is ready to send and receive messages.` : 'Your account is ready.'} Meta may
          still be reviewing the display name.
        </Notice>
        <div className="flex justify-end">
          <Button onClick={onClose}>Done</Button>
        </div>
      </div>
    )
  }

  if (status === 'failed') {
    return (
      <div className="flex flex-col gap-4">
        <Notice tone="danger" role="alert" title="Setup didn't finish">
          {account.data?.last_error || 'Meta returned an error while setting up the number.'}
        </Notice>
        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={onClose}>
            Close
          </Button>
          <Button onClick={onRetry}>Start again</Button>
        </div>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-4">
      <Steps steps={steps} />
      <p role="status" className="text-[13px] text-muted">
        {account.isError
          ? `Still waiting for an update: ${actionErrorMessage(account.error)}`
          : status === 'registering'
            ? 'Registering your number with the WhatsApp Cloud API…'
            : 'Connecting your WhatsApp Business Account…'}
      </p>
      <div className="flex items-center justify-between gap-3">
        <p className="text-[12.5px] text-muted">You can close this. Setup continues in the background.</p>
        <Button variant="secondary" onClick={onClose}>
          Close
        </Button>
      </div>
    </div>
  )
}

const stepIcons: Record<SetupStepState, typeof Check> = { done: Check, current: Circle, pending: Circle }

function Steps({ steps }: { steps: { label: string; state: SetupStepState }[] }) {
  return (
    <ol className="flex flex-col gap-2.5" aria-label="Setup progress">
      {steps.map((step) => {
        const Icon = stepIcons[step.state]
        return (
          <li key={step.label} className="flex items-center gap-3 text-sm">
            <span
              className={cn(
                'grid size-6 shrink-0 place-items-center rounded-full border',
                step.state === 'done' && 'border-accent bg-accent text-white',
                step.state === 'current' && 'border-accent text-accent',
                step.state === 'pending' && 'border-line text-muted',
              )}
            >
              {step.state === 'current' ? <Spinner size="sm" label="In progress" /> : <Icon className="size-3.5" aria-hidden="true" />}
            </span>
            <span className={cn(step.state === 'pending' ? 'text-muted' : 'text-ink')}>
              {step.label}
              <span className="sr-only">{step.state === 'done' ? ' (done)' : step.state === 'current' ? ' (in progress)' : ''}</span>
            </span>
          </li>
        )
      })}
    </ol>
  )
}
