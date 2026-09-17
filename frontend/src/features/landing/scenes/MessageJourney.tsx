import { useEffect, useRef, useState, type CSSProperties } from 'react'
import { Check, CheckCheck, Clock3, MessageSquareText } from 'lucide-react'
import { site } from '../../../config/site'
import { cn } from '../../../lib/cn'
import { usePrefersReducedMotion } from '../../../lib/motion'
import { useOnScreen } from '../lib/useOnScreen'

/*
 * "What happens when you hit send": business → UpChatz → WhatsApp Cloud API → customer's phone,
 * with statuses flowing back. One discrete step clock drives everything; CSS transitions do the
 * in-between motion, so only transforms and opacity animate. Large screens get a 3D diorama;
 * smaller screens get the same list with a vertical rail.
 */

const STEP_MS = 950
const LOOP_STEPS = 14
/** Everything delivered and read, no packets in flight — the reduced-motion state. */
const FINAL_STEP = 10

type HopKind = 'message' | 'sent' | 'delivered' | 'read'
/** A packet travelling between neighbouring stations during step `at`. */
type Hop = { kind: HopKind; from: number; to: number; at: number }

const hops: Hop[] = [
  { kind: 'message', from: 0, to: 1, at: 1 },
  { kind: 'message', from: 1, to: 2, at: 3 },
  { kind: 'message', from: 2, to: 3, at: 4 },
  { kind: 'sent', from: 2, to: 1, at: 5 },
  { kind: 'sent', from: 1, to: 0, at: 6 },
  { kind: 'delivered', from: 2, to: 1, at: 6 },
  { kind: 'delivered', from: 1, to: 0, at: 7 },
  { kind: 'read', from: 2, to: 1, at: 8 },
  { kind: 'read', from: 1, to: 0, at: 9 },
]

type DeliveryStatus = 'ready' | 'sending' | 'sent' | 'delivered' | 'read'

function statusAt(step: number): DeliveryStatus {
  if (step >= 10) return 'read'
  if (step >= 8) return 'delivered'
  if (step >= 7) return 'sent'
  if (step >= 1) return 'sending'
  return 'ready'
}

const statusLabel: Record<DeliveryStatus, string> = {
  ready: 'Ready to send',
  sending: 'Sending…',
  sent: 'Sent',
  delivered: 'Delivered',
  read: 'Read',
}

const stations = [
  {
    title: 'Your business',
    body: 'Send a campaign from the dashboard, or trigger a single message from your own system through the API.',
  },
  {
    title: site.name,
    body: 'Checks opt-in, template approval and your messaging limit, then queues the send and paces it for you.',
  },
  {
    title: 'WhatsApp Cloud API',
    body: 'Meta’s official platform accepts the message and delivers it to the customer’s WhatsApp.',
  },
  {
    title: 'Customer’s phone',
    body: 'The message arrives in WhatsApp. Sent, delivered and read statuses flow back to your dashboard.',
  },
]

const checks = ['Opted in', 'Template approved', 'Inside messaging limit']

function useJourneyStep(active: boolean) {
  const reduced = usePrefersReducedMotion()
  const [step, setStep] = useState(0)

  useEffect(() => {
    if (reduced || !active) return
    const timer = window.setInterval(() => setStep((current) => (current + 1) % LOOP_STEPS), STEP_MS)
    return () => window.clearInterval(timer)
  }, [active, reduced])

  return reduced ? FINAL_STEP : step
}

function hopState(hop: Hop, step: number) {
  if (step < hop.at || step === 0) return 'idle'
  return step === hop.at ? 'moving' : 'done'
}

/* ---------- Small pieces shared by both layouts ---------- */

function Ticks({ status, className }: { status: DeliveryStatus; className?: string }) {
  if (status === 'ready' || status === 'sending') return <Clock3 className={cn('text-muted', className)} />
  if (status === 'sent') return <Check className={cn('text-muted', className)} />
  return <CheckCheck className={cn(status === 'read' ? 'text-[#2f7fc1]' : 'text-muted', className)} />
}

/** A message or status in flight. `compact` drops the label for the narrow vertical rail. */
function Packet({ kind, compact = false }: { kind: HopKind; compact?: boolean }) {
  if (kind === 'message') {
    return (
      <span
        className={cn(
          'grid place-items-center rounded-md bg-accent text-white shadow-[inset_0_1px_0_rgb(255_255_255/0.25),0_6px_10px_-6px_rgb(16_39_31/0.6)]',
          compact ? 'size-5' : 'size-7',
        )}
      >
        <MessageSquareText className={compact ? 'size-3' : 'size-3.5'} />
      </span>
    )
  }
  if (compact) {
    return (
      <span className="grid size-5 place-items-center rounded-full border border-line bg-card shadow-[0_4px_8px_-4px_rgb(16_39_31/0.45)]">
        <Ticks status={kind} className="size-3" />
      </span>
    )
  }
  return (
    <span className="flex items-center gap-1 whitespace-nowrap rounded-full border border-line bg-card px-2 py-0.5 font-mono text-[9.5px] shadow-[0_6px_10px_-6px_rgb(16_39_31/0.45)]">
      <Ticks status={kind} className="size-3" />
      {kind}
    </span>
  )
}

/** Moves its packet across the parent box along one axis. */
function Runner({ hop, step, axis }: { hop: Hop; step: number; axis: 'x' | 'y' }) {
  const state = hopState(hop, step)
  const forward = hop.to > hop.from

  return (
    <span
      className="journey-runner"
      data-axis={axis}
      data-state={state}
      data-direction={forward ? 'forward' : 'back'}
    >
      <span className="journey-packet">
        <Packet kind={hop.kind} compact={axis === 'y'} />
      </span>
    </span>
  )
}

/* ---------- 3D diorama (lg and up) ---------- */

const POST_CENTERS = ['12.5%', '37.5%', '62.5%', '87.5%']

function BusinessPanel({ status }: { status: DeliveryStatus }) {
  return (
    <div className="flex h-full flex-col rounded-xl border border-line bg-card p-3 shadow-[inset_0_1px_0_rgb(255_255_255/0.9)]">
      <p className="font-mono text-[9.5px] uppercase tracking-[0.12em] text-muted">Campaign</p>
      <p className="mt-0.5 truncate font-mono text-[11px]">order_shipped</p>
      <div className="mt-2.5 flex-1 rounded-md bg-wallpaper p-2">
        <p className="rounded-md rounded-tr-sm bg-bubble px-2 py-1.5 text-[10px] leading-snug">
          Hi Priya, your order #SR-20418 has shipped.
          <span className="mt-0.5 flex justify-end">
            <Ticks status={status} className="size-3" />
          </span>
        </p>
      </div>
      <p className="mt-2 flex items-center gap-1.5 text-[10.5px] font-medium">
        <span className={cn('size-1.5 rounded-full', status === 'ready' ? 'bg-line' : 'bg-accent')} />
        {statusLabel[status]}
      </p>
    </div>
  )
}

function ChecksPanel({ step }: { step: number }) {
  const checked = step >= 2
  return (
    <div className="flex h-full flex-col rounded-xl border border-ink bg-ink p-3 text-paper shadow-[inset_0_1px_0_rgb(255_255_255/0.12)]">
      <p className="font-mono text-[9.5px] uppercase tracking-[0.12em] text-paper/60">{site.name}</p>
      <ul className="mt-2.5 space-y-2 text-[10.5px]">
        {checks.map((check, i) => (
          <li key={check} className="flex items-center gap-2">
            <span className="relative size-4 shrink-0 rounded-full border border-paper/25">
              <span
                className={cn(
                  'journey-pop absolute -inset-px grid place-items-center rounded-full bg-[#8fd0ab] text-ink',
                  checked && 'is-on',
                )}
                style={{ '--pop-delay': `${i * 140}ms` } as CSSProperties}
              >
                <Check className="size-2.5" />
              </span>
            </span>
            {check}
          </li>
        ))}
      </ul>
      <p className="mt-auto border-t border-paper/10 pt-2 text-[10px] text-paper/60">
        {step >= 3 ? 'Queued and paced' : 'Checking…'}
      </p>
    </div>
  )
}

function CloudApiPanel({ step }: { step: number }) {
  const accepted = step >= 4
  const reporting = step >= 5 && step <= 9
  return (
    <div className="flex h-full flex-col rounded-xl border border-line bg-card p-3 shadow-[inset_0_1px_0_rgb(255_255_255/0.9)]">
      <p className="font-mono text-[9.5px] uppercase tracking-[0.12em] text-muted">WhatsApp Cloud API</p>
      <p className="mt-0.5 text-[10px] text-muted">by Meta</p>
      <div className="mt-2.5 rounded-md border border-line-2 px-2 py-1.5">
        <p className="flex items-center justify-between text-[10.5px] font-medium">
          Message
          <span className={cn('text-[10px]', accepted ? 'text-accent-2' : 'text-muted')}>
            {accepted ? 'Accepted' : 'Waiting'}
          </span>
        </p>
        <p className="mt-0.5 truncate font-mono text-[9px] text-muted">wamid.HBgMOTE5ODAw…</p>
      </div>
      <p className="mt-auto flex items-center gap-1.5 text-[10px] text-muted">
        <span className={cn('size-1.5 rounded-full', reporting ? 'bg-accent' : 'bg-line')} />
        Status webhooks
      </p>
    </div>
  )
}

function PhonePanel({ step }: { step: number }) {
  const opened = step >= 7
  const notified = step >= 5 && !opened
  return (
    <div className="mx-auto h-full w-[58%] rounded-[1.1rem] bg-ink p-1 shadow-[inset_0_0_0_1px_rgb(255_255_255/0.14)]">
      <div className="relative flex h-full flex-col overflow-hidden rounded-[0.85rem] bg-wallpaper">
        <span className="mx-auto mt-1 h-1.5 w-8 shrink-0 rounded-full bg-ink" />
        <div className={cn('journey-fade absolute inset-x-1.5 top-5 rounded-md bg-card/95 p-1.5', notified ? 'opacity-100' : 'opacity-0')}>
          <p className="text-[8px] font-semibold">Sharma Retail</p>
          <p className="text-[8px] leading-tight text-muted">Hi Priya, your order #SR-20418 has shipped.</p>
        </div>
        <div className={cn('journey-fade flex flex-1 flex-col', opened ? 'opacity-100' : 'opacity-0')}>
          <p className="mt-1 border-b border-line-2 bg-card px-1.5 py-1 text-[8px] font-semibold">Sharma Retail</p>
          <p className="m-1.5 mt-auto rounded-md rounded-tl-sm bg-white px-1.5 py-1 text-[8px] leading-tight">
            Hi Priya, your order #SR-20418 has shipped.
          </p>
        </div>
      </div>
    </div>
  )
}

function Diorama({ step }: { step: number }) {
  const status = statusAt(step)
  const panels = [
    <BusinessPanel key="business" status={status} />,
    <ChecksPanel key="checks" step={step} />,
    <CloudApiPanel key="api" step={step} />,
    <PhonePanel key="phone" step={step} />,
  ]

  return (
    <div aria-hidden="true" className="journey-stage relative hidden h-[270px] lg:block">
      <div className="journey-floor">
        {POST_CENTERS.map((left) => (
          <span key={`tile-${left}`} className="journey-tile" style={{ left }} />
        ))}

        {[0, 1, 2].map((segment) => (
          <span key={`lane-${segment}`} className="journey-lane" data-lane="forward" style={{ left: POST_CENTERS[segment] }}>
            {hops
              .filter((hop) => hop.from === segment && hop.to === segment + 1)
              .map((hop) => (
                <Runner key={`${hop.kind}-${hop.at}`} hop={hop} step={step} axis="x" />
              ))}
          </span>
        ))}
        {[0, 1].map((segment) => (
          <span key={`return-${segment}`} className="journey-lane" data-lane="back" style={{ left: POST_CENTERS[segment] }}>
            {hops
              .filter((hop) => hop.to === segment && hop.from === segment + 1)
              .map((hop) => (
                <Runner key={`${hop.kind}-${hop.at}`} hop={hop} step={step} axis="x" />
              ))}
          </span>
        ))}

        {panels.map((panel, i) => (
          <span key={`post-${POST_CENTERS[i]}`} className="journey-post" style={{ left: POST_CENTERS[i] }}>
            <span className="journey-post-shadow" style={i === 3 ? { insetInline: '22%' } : undefined} />
            <span className="journey-post-face">{panel}</span>
          </span>
        ))}
      </div>
    </div>
  )
}

/* ---------- Compact inline states for the vertical layout ---------- */

function InlineState({ index, step }: { index: number; step: number }) {
  const chip = 'inline-flex items-center gap-1.5 rounded-full border border-line bg-card px-2.5 py-1 text-[12px]'
  const status = statusAt(step)

  if (index === 0) {
    return (
      <span className={chip}>
        <Ticks status={status} className="size-3.5" />
        {statusLabel[status]}
      </span>
    )
  }
  if (index === 1) {
    return (
      <span className={chip}>
        <Check className={cn('size-3.5', step >= 2 ? 'text-accent-2' : 'text-line')} />
        {step >= 2 ? 'Checks passed' : 'Checking…'}
      </span>
    )
  }
  if (index === 2) {
    return (
      <span className={chip}>
        <span className={cn('size-1.5 rounded-full', step >= 4 ? 'bg-accent' : 'bg-line')} />
        {step >= 4 ? 'Accepted' : 'Waiting'}
      </span>
    )
  }
  return (
    <span className={chip}>
      <span className={cn('size-1.5 rounded-full', step >= 5 ? 'bg-accent' : 'bg-line')} />
      {step >= 7 ? 'Opened' : step >= 5 ? 'Notification received' : 'Waiting'}
    </span>
  )
}

export function MessageJourney() {
  const rootRef = useRef<HTMLDivElement>(null)
  const onScreen = useOnScreen(rootRef, '0px')
  const step = useJourneyStep(onScreen)

  return (
    <div ref={rootRef}>
      <Diorama step={step} />

      <ol className="grid gap-0 lg:mt-2 lg:grid-cols-4">
        {stations.map((station, i) => (
          <li key={station.title} className="grid grid-cols-[1.75rem_minmax(0,1fr)] gap-x-4 lg:block lg:px-[7%]">
            <div aria-hidden="true" className="relative flex flex-col items-center lg:hidden">
              <span className="grid size-7 shrink-0 place-items-center rounded-full border border-line bg-card font-mono text-[10.5px]">
                {i + 1}
              </span>
              {i < stations.length - 1 && (
                <span className="journey-rail relative my-1 w-px flex-1 bg-line">
                  {hops
                    .filter((hop) => Math.min(hop.from, hop.to) === i)
                    .map((hop) => (
                      <Runner key={`${hop.kind}-${hop.at}`} hop={hop} step={step} axis="y" />
                    ))}
                </span>
              )}
            </div>
            <div className={cn('min-w-0', i < stations.length - 1 && 'pb-9 lg:pb-0')}>
              <h4 className="pt-0.5 text-[16px] font-semibold tracking-[-0.01em] lg:pt-0">
                <span className="mr-2 hidden font-mono text-[11px] font-normal text-muted lg:inline">
                  {String(i + 1).padStart(2, '0')}
                </span>
                {station.title}
              </h4>
              <p className="mt-1.5 text-[14.5px] leading-relaxed text-muted">{station.body}</p>
              <div aria-hidden="true" className="mt-3 lg:hidden">
                <InlineState index={i} step={step} />
              </div>
            </div>
          </li>
        ))}
      </ol>
    </div>
  )
}
