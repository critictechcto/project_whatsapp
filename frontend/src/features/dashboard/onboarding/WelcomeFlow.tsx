import { FloatingFocusManager, FloatingOverlay, FloatingPortal, useDismiss, useFloating, useInteractions, useRole } from '@floating-ui/react'
import { ArrowLeft, Check, Megaphone, MessagesSquare, ShoppingBag, type LucideIcon } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router'
import { Button } from '../../../components/app'
import { PreviewBubble } from '../../../components/app/whatsapp/PreviewBubble'
import { site } from '../../../config/site'
import { cn } from '../../../lib/cn'
import { usePrefersReducedMotion } from '../../../lib/motion'
import { roleLabels, type Role } from '../../../lib/roles'
import { useWorkspace } from '../../../lib/workspace'
import { useMe } from '../auth/session'
import { useUpdateOnboarding, type Onboarding, type WorkspaceGoal } from './api'
import { goalOptions, goalSteps, type GoalKey } from './goalSteps'
import { useTour } from './tour/useTour'
import './welcome.css'

type StepKind = 'welcome' | 'goal' | 'plan' | 'role'

const goalIcons: Record<WorkspaceGoal, LucideIcon> = { sell: ShoppingBag, marketing: Megaphone, support: MessagesSquare }

const roleSummaries: Record<Role, string> = {
  owner: 'You can do everything here, including billing and closing the workspace.',
  admin: 'You can connect numbers, manage templates, campaigns, the store and the team.',
  agent: 'You can reply to customer chats in the shared inbox and work with contacts.',
  viewer: 'You can view chats, contacts and reports, without sending or changing anything.',
}

/** The little chat that opens the flow: a buyer asks, the business answers, an order is confirmed. */
function ChatScene({ animate }: { animate: boolean }) {
  const pop = (index: number) => (animate ? { className: 'chat-pop', style: { animationDelay: `${0.25 + index * 0.7}s` } } : {})
  return (
    <div aria-hidden="true" className="welcome-scene mx-auto flex w-full max-w-sm flex-col gap-2 rounded-xl border border-line bg-wallpaper p-4">
      <div {...pop(0)}>
        <PreviewBubble framed={false} direction="inbound" time="10:02" caption="">
          <p className="px-2.5 pt-1.5 text-ink">Hi! Is this available?</p>
        </PreviewBubble>
      </div>
      <div {...pop(1)}>
        <PreviewBubble framed={false} time="10:02" status="read" caption="">
          <p className="px-2.5 pt-1.5 text-ink">Yes, it's in stock. Tap below to order.</p>
        </PreviewBubble>
      </div>
      <div {...pop(2)}>
        <PreviewBubble framed={false} time="10:05" status="read" caption="">
          <p className="px-2.5 pt-2 font-semibold text-ink">Order confirmed</p>
          <p className="px-2.5 pt-0.5 text-ink">Paid ₹480. We'll deliver it today by 6 pm.</p>
        </PreviewBubble>
      </div>
    </div>
  )
}

function StepDots({ index, total }: { index: number; total: number }) {
  return (
    <div className="flex items-center gap-2">
      <p className="font-mono text-[12px] text-muted">
        Step {index + 1} of {total}
      </p>
      <span aria-hidden="true" className="flex gap-1">
        {Array.from({ length: total }, (_, i) => (
          <span key={i} className={cn('h-1.5 rounded-full transition-[width,background-color]', i === index ? 'w-5 bg-accent' : 'w-1.5 bg-line')} />
        ))}
      </span>
    </div>
  )
}

/**
 * Full-screen welcome shown once per person per workspace (docs/contracts/onboarding.md).
 * Owners and admins choose the workspace goal; invited teammates get a shorter version.
 * Skipping (Esc or "Skip") counts as seen.
 */
export function WelcomeFlow({ onboarding }: { onboarding: Onboarding }) {
  const { workspace, workspaceId, role } = useWorkspace()
  const me = useMe()
  const tour = useTour()
  const navigate = useNavigate()
  const update = useUpdateOnboarding()
  const saveGoal = useUpdateOnboarding()
  const reducedMotion = usePrefersReducedMotion()
  const animate = !reducedMotion

  const steps: StepKind[] = onboarding.can_set_goal ? ['welcome', 'goal', 'plan'] : ['welcome', 'role']
  const [index, setIndex] = useState(0)
  const [goal, setGoal] = useState<GoalKey>(onboarding.goal ?? '')
  const [goalError, setGoalError] = useState<string | null>(null)
  const step = steps[index]

  const finish = () => update.mutate({ welcome_completed: true })

  const {
    refs: { setFloating },
    context,
  } = useFloating({ open: true, onOpenChange: (open) => !open && finish() })
  const dismiss = useDismiss(context, { outsidePress: false })
  const dialogRole = useRole(context, { role: 'dialog' })
  const { getFloatingProps } = useInteractions([dismiss, dialogRole])

  const headingRef = useRef<HTMLHeadingElement>(null)
  const firstStep = useRef(true)
  useEffect(() => {
    if (firstStep.current) {
      firstStep.current = false
      return
    }
    headingRef.current?.focus()
  }, [index])

  const firstName = me.data?.full_name?.trim().split(/\s+/)[0]
  const headingId = `welcome-heading-${step}`

  const continueFromGoal = async () => {
    setGoalError(null)
    if (goal && goal !== (onboarding.goal ?? '')) {
      try {
        await saveGoal.mutateAsync({ goal })
      } catch {
        setGoalError("Couldn't save your choice. You can continue and set it later in Settings.")
        return
      }
    }
    setIndex(index + 1)
  }

  const connect = () => {
    finish()
    navigate(`/app/w/${workspaceId}/whatsapp`)
  }
  const takeTour = () => {
    finish()
    tour.start()
  }

  return (
    <FloatingPortal>
      <FloatingOverlay lockScroll className="welcome-overlay z-[70] overflow-y-auto bg-paper">
        <FloatingFocusManager context={context} initialFocus={headingRef}>
          <div
            ref={setFloating}
            aria-modal="true"
            aria-labelledby={headingId}
            {...getFloatingProps()}
            className="mx-auto flex min-h-full w-full max-w-xl flex-col px-4 pb-8 pt-4 sm:px-6 sm:pt-8"
          >
            <div className="flex min-h-11 items-center justify-between gap-3">
              <p className="font-display text-base font-semibold tracking-[-0.02em] text-ink">{site.name}</p>
              <button
                type="button"
                onClick={finish}
                className="inline-flex min-h-11 items-center rounded-md px-3 text-sm font-medium text-muted hover:bg-ink/5 hover:text-ink"
              >
                Skip
              </button>
            </div>

            <div key={step} className={cn('flex flex-1 flex-col gap-6 pt-6 sm:pt-10', animate && 'fade-up')}>
              {step === 'welcome' && (
                <>
                  <ChatScene animate={animate} />
                  <div>
                    <h1 id={headingId} ref={headingRef} tabIndex={-1} className="font-display text-2xl font-semibold tracking-[-0.02em] text-ink focus:outline-none sm:text-3xl">
                      {firstName ? `Welcome to ${site.name}, ${firstName}.` : `Welcome to ${site.name}.`}
                    </h1>
                    <p className="mt-2 text-[15px] text-ink-2">Reply, send offers and sell on WhatsApp, all on the official WhatsApp Business Platform.</p>
                  </div>
                </>
              )}

              {step === 'goal' && (
                <div className="flex flex-col gap-3">
                  <h1 id={headingId} ref={headingRef} tabIndex={-1} className="font-display text-2xl font-semibold tracking-[-0.02em] text-ink focus:outline-none">
                    What do you want to do first?
                  </h1>
                  <p id="welcome-goal-hint" className="text-sm text-muted">
                    We'll order your setup steps around it. You can change it later in Settings.
                  </p>
                  <div role="radiogroup" aria-labelledby={headingId} aria-describedby="welcome-goal-hint" className="mt-1 flex flex-col gap-3">
                    {goalOptions.map((option) => {
                      const Icon = goalIcons[option.value]
                      const selected = goal === option.value
                      return (
                        <label
                          key={option.value}
                          className={cn(
                            'flex min-h-11 cursor-pointer items-center gap-3 rounded-xl border bg-card p-4 transition-colors has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-accent/30',
                            selected ? 'border-accent' : 'border-line hover:border-ink/30',
                          )}
                        >
                          <input
                            type="radio"
                            name="welcome-goal"
                            value={option.value}
                            checked={selected}
                            onChange={() => setGoal(option.value)}
                            className="sr-only"
                          />
                          <span
                            aria-hidden="true"
                            className={cn('grid size-10 shrink-0 place-items-center rounded-lg border', selected ? 'border-accent bg-accent-soft text-accent-2' : 'border-line-2 bg-paper text-muted')}
                          >
                            <Icon className="size-5" />
                          </span>
                          <span className="min-w-0 flex-1">
                            <span className="block font-medium text-ink">{option.title}</span>
                            <span className="mt-0.5 block text-[13px] text-muted">{option.description}</span>
                          </span>
                          <span aria-hidden="true" className={cn('grid size-5 shrink-0 place-items-center rounded-full border', selected ? 'border-accent bg-accent text-paper' : 'border-line')}>
                            {selected && <Check className="size-3.5" />}
                          </span>
                        </label>
                      )
                    })}
                  </div>
                  {goalError && (
                    <p role="alert" className="text-[13px] text-signal">
                      {goalError}
                    </p>
                  )}
                </div>
              )}

              {step === 'plan' && (
                <>
                  <div>
                    <h1 id={headingId} ref={headingRef} tabIndex={-1} className="font-display text-2xl font-semibold tracking-[-0.02em] text-ink focus:outline-none">
                      Your plan
                    </h1>
                    <p className="mt-2 text-sm text-muted">These steps wait for you on Home, in this order.</p>
                  </div>
                  <ol aria-label="Setup steps" className="flex flex-col gap-2">
                    {goalSteps(goal).map((item, i) => (
                      <li key={item.id} className={cn('flex gap-3 rounded-lg border border-line-2 bg-card px-3.5 py-2.5', animate && 'chat-pop')} style={animate ? { animationDelay: `${i * 0.06}s` } : undefined}>
                        <span className="mt-0.5 font-mono text-[12px] text-muted">{i + 1}</span>
                        <span className="min-w-0">
                          <span className="block text-sm font-medium text-ink">{item.title}</span>
                          <span className="block text-[12.5px] text-muted">{item.why}</span>
                        </span>
                      </li>
                    ))}
                  </ol>
                  <section aria-labelledby="welcome-needs" className="rounded-xl border border-line bg-paper-2 px-4 py-3.5">
                    <h2 id="welcome-needs" className="text-sm font-semibold text-ink">
                      What you'll need to connect WhatsApp
                    </h2>
                    <ul className="mt-2 flex list-disc flex-col gap-1 pl-5 text-[13px] text-ink-2">
                      <li>A phone number that can receive an SMS or a voice call</li>
                      <li>Access to your business's Facebook account</li>
                      <li>Your business details, such as its name and address</li>
                    </ul>
                    <p className="mt-2 text-[12.5px] text-muted">Meta may ask you to verify your business before raising your messaging limits.</p>
                  </section>
                </>
              )}

              {step === 'role' && (
                <div>
                  <h1 id={headingId} ref={headingRef} tabIndex={-1} className="font-display text-2xl font-semibold tracking-[-0.02em] text-ink focus:outline-none">
                    You joined {workspace.name} as {role === 'viewer' ? 'a' : 'an'} {roleLabels[role].toLowerCase()}
                  </h1>
                  <p className="mt-2 text-[15px] text-ink-2">{roleSummaries[role]}</p>
                  <p className="mt-2 text-sm text-muted">A quick tour shows where everything is.</p>
                </div>
              )}
            </div>

            <div className="mt-8 flex flex-col gap-4 border-t border-line-2 pt-4">
              <StepDots index={index} total={steps.length} />
              <div className="flex flex-col-reverse gap-2 sm:flex-row sm:items-center sm:justify-between">
                {index > 0 ? (
                  <Button variant="ghost" size="lg" icon={<ArrowLeft className="size-4" aria-hidden="true" />} onClick={() => setIndex(index - 1)}>
                    Back
                  </Button>
                ) : (
                  <span className="hidden sm:block" />
                )}
                <div className="flex flex-col-reverse gap-2 sm:flex-row">
                  {step === 'welcome' && (
                    <Button size="lg" onClick={() => setIndex(1)}>
                      {onboarding.can_set_goal ? 'Get started' : 'Continue'}
                    </Button>
                  )}
                  {step === 'goal' && (
                    <Button size="lg" loading={saveGoal.isPending} onClick={() => void continueFromGoal()}>
                      Continue
                    </Button>
                  )}
                  {step === 'plan' && (
                    <>
                      <Button variant="ghost" size="lg" onClick={finish}>
                        Go to dashboard
                      </Button>
                      <Button variant="secondary" size="lg" onClick={takeTour}>
                        Take a quick tour
                      </Button>
                      <Button size="lg" onClick={connect}>
                        Connect WhatsApp
                      </Button>
                    </>
                  )}
                  {step === 'role' && (
                    <>
                      <Button variant="secondary" size="lg" onClick={finish}>
                        Go to dashboard
                      </Button>
                      <Button size="lg" onClick={takeTour}>
                        Take a quick tour
                      </Button>
                    </>
                  )}
                </div>
              </div>
            </div>
          </div>
        </FloatingFocusManager>
      </FloatingOverlay>
    </FloatingPortal>
  )
}

export default WelcomeFlow
