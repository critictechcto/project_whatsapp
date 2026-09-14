import { ArrowRight } from 'lucide-react'
import { useId, type ReactNode } from 'react'
import { Link } from 'react-router'
import { errorMessage } from '../../../../api/errors'
import { Button, Skeleton, StatusBadge } from '../../../../components/app'
import { formatDate } from '../../../../lib/datetime'
import { useWorkspace } from '../../../../lib/workspace'
import {
  campaignProgress,
  countLabel,
  isNotImplemented,
  RECENT_CAMPAIGNS,
  tierLabel,
  trialDaysLeft,
  useConversationCounts,
  usePhoneNumbers,
  useRecentCampaigns,
  useSubscription,
  useTemplateSummary,
} from '../api'

export type CardProps = {
  title: string
  link?: { to: string; label: string }
  children: ReactNode
}

export function Card({ title, link, children }: CardProps) {
  const headingId = useId()
  return (
    <section aria-labelledby={headingId} className="flex min-w-0 flex-col rounded-xl border border-line bg-card p-5">
      <div className="flex items-center justify-between gap-3">
        <h2 id={headingId} className="font-display text-base font-semibold tracking-[-0.01em] text-ink">
          {title}
        </h2>
        {link && (
          <Link to={link.to} className="inline-flex shrink-0 items-center gap-1 text-[13px] font-medium text-accent-2 underline-offset-2 hover:underline">
            {link.label}
            <ArrowRight className="size-3.5" aria-hidden="true" />
          </Link>
        )}
      </div>
      <div className="mt-4 flex flex-1 flex-col">{children}</div>
    </section>
  )
}

export function CardLoading() {
  return (
    <div className="flex flex-col gap-2" aria-busy="true" aria-label="Loading">
      <Skeleton className="h-5 w-2/3" />
      <Skeleton className="h-4 w-1/2" />
      <Skeleton className="h-4 w-3/5" />
    </div>
  )
}

export function CardError({ error, onRetry }: { error: unknown; onRetry: () => void }) {
  return (
    <div className="flex flex-col items-start gap-2">
      <p className="text-sm text-muted">Couldn&apos;t load this. {errorMessage(error)}</p>
      <Button variant="secondary" size="sm" onClick={onRetry}>
        Try again
      </Button>
    </div>
  )
}

type Queryish = { isPending: boolean; isError: boolean; error: unknown; refetch: () => Promise<unknown> }

/** Loading and error states shared by the cards. Returns null when the card should render its data. */
function queryState(queries: Queryish[]): 'hidden' | ReactNode | null {
  if (queries.some((query) => query.isError && isNotImplemented(query.error))) return 'hidden'
  const failed = queries.find((query) => query.isError)
  if (failed) return <CardError error={failed.error} onRetry={() => queries.forEach((query) => query.isError && void query.refetch())} />
  if (queries.some((query) => query.isPending)) return <CardLoading />
  return null
}

export function Stat({ label, value, to }: { label: string; value: string; to?: string }) {
  const content = (
    <>
      <span className="block font-display text-2xl font-semibold tracking-[-0.02em] text-ink">{value}</span>
      <span className="mt-0.5 block text-[13px] text-muted">{label}</span>
    </>
  )
  return to ? (
    <Link to={to} className="-m-2 rounded-lg p-2 hover:bg-paper">
      {content}
    </Link>
  ) : (
    <div>{content}</div>
  )
}

export function ConnectionCard() {
  const phones = usePhoneNumbers()
  const state = queryState([phones])
  if (state === 'hidden') return null
  const numbers = phones.data?.results ?? []
  return (
    <Card title="WhatsApp connection" link={{ to: 'whatsapp', label: numbers.length ? 'Manage' : 'Connect' }}>
      {state ??
        (numbers.length === 0 ? (
          <p className="text-sm text-muted">No number connected yet. Connect one with Meta&apos;s Embedded Signup to start messaging.</p>
        ) : (
          <ul className="flex flex-col gap-4">
            {numbers.slice(0, 3).map((number) => {
              const tier = tierLabel(number.messaging_limit_tier)
              return (
                <li key={number.id} className="flex flex-col gap-1.5">
                  <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                    <span className="font-mono text-sm font-medium text-ink">{number.display_phone_number}</span>
                    {number.is_default && numbers.length > 1 && <span className="text-[12px] text-muted">Default</span>}
                  </div>
                  {number.verified_name && <p className="text-[13px] text-ink-2">{number.verified_name}</p>}
                  <div className="flex flex-wrap items-center gap-2">
                    <StatusBadge status={number.quality_rating} />
                    {number.registration_status !== 'registered' && <StatusBadge status={number.registration_status} />}
                  </div>
                  <p className="text-[13px] text-muted">
                    {tier
                      ? tier === 'Unlimited'
                        ? 'Messaging limit: unlimited, as set by Meta.'
                        : `Messaging limit: up to ${tier} customers in a rolling 24 hours, as set by Meta.`
                      : 'Messaging limit not reported by Meta yet.'}
                  </p>
                </li>
              )
            })}
            {numbers.length > 3 && <li className="text-[13px] text-muted">and {numbers.length - 3} more</li>}
          </ul>
        ))}
    </Card>
  )
}

export function ConversationsCard() {
  const { open, unassigned } = useConversationCounts()
  const state = queryState([open, unassigned])
  if (state === 'hidden') return null
  return (
    <Card title="Conversations" link={{ to: 'inbox', label: 'Open inbox' }}>
      {state ??
        (open.data && unassigned.data && (
          <div className="grid grid-cols-2 gap-4">
            <Stat label="Open" value={countLabel(open.data)} to="inbox?status=open" />
            <Stat label="Open and unassigned" value={countLabel(unassigned.data)} to="inbox?status=open&assignee=none" />
          </div>
        ))}
    </Card>
  )
}

export function CampaignsCard() {
  const campaigns = useRecentCampaigns()
  const state = queryState([campaigns])
  if (state === 'hidden') return null
  const recent = campaigns.data?.results.slice(0, RECENT_CAMPAIGNS) ?? []
  return (
    <Card title="Recent campaigns" link={{ to: 'campaigns', label: 'All campaigns' }}>
      {state ??
        (recent.length === 0 ? (
          <div className="flex flex-col items-start gap-2">
            <p className="text-sm text-muted">No campaigns yet.</p>
            <Link to="campaigns/new" className="text-sm font-medium text-accent-2 underline-offset-2 hover:underline">
              Create a campaign
            </Link>
          </div>
        ) : (
          <ul className="flex flex-col gap-3.5">
            {recent.map((campaign) => {
              const progress = campaignProgress(campaign.stats)
              return (
                <li key={campaign.id} className="flex flex-col gap-1.5">
                  <div className="flex items-center justify-between gap-2">
                    <Link to={`campaigns/${campaign.id}`} className="min-w-0 truncate text-sm font-medium text-ink underline-offset-2 hover:underline">
                      {campaign.name}
                    </Link>
                    <StatusBadge status={campaign.status} />
                  </div>
                  {progress.total > 0 && (
                    <>
                      <div
                        className="h-1.5 overflow-hidden rounded-full bg-line-2"
                        role="progressbar"
                        aria-label={`${campaign.name} progress`}
                        aria-valuemin={0}
                        aria-valuemax={100}
                        aria-valuenow={progress.percent}
                      >
                        <div className="h-full rounded-full bg-accent" style={{ width: `${progress.percent}%` }} />
                      </div>
                      <p className="text-[12.5px] text-muted">
                        {progress.processed.toLocaleString('en-IN')} of {progress.total.toLocaleString('en-IN')} recipients processed
                      </p>
                    </>
                  )}
                </li>
              )
            })}
          </ul>
        ))}
    </Card>
  )
}

export function TemplatesCard() {
  const summary = useTemplateSummary()
  const state = queryState([summary])
  if (state === 'hidden') return null
  const data = summary.data
  const suffix = data?.truncated ? '+' : ''
  return (
    <Card title="Templates" link={{ to: 'templates', label: 'All templates' }}>
      {state ??
        (data &&
          (data.total === 0 ? (
            <div className="flex flex-col items-start gap-2">
              <p className="text-sm text-muted">No templates yet. Meta must approve a template before you can start conversations with it.</p>
              <Link to="templates" className="text-sm font-medium text-accent-2 underline-offset-2 hover:underline">
                Open templates
              </Link>
            </div>
          ) : (
            <div className="grid grid-cols-2 gap-4 sm:grid-cols-4 md:grid-cols-2">
              <Stat label="Approved" value={`${data.approved}${suffix}`} to="templates?status=APPROVED" />
              <Stat label="In review" value={`${data.pending}${suffix}`} to="templates?status=PENDING" />
              <Stat label="Rejected" value={`${data.rejected}${suffix}`} to="templates?status=REJECTED" />
              <Stat label="Paused or disabled" value={`${data.attention}${suffix}`} />
            </div>
          )))}
    </Card>
  )
}

/** Plan and trial status. Hidden entirely when billing can't be loaded. */
export function SubscriptionCard() {
  const { timeZone } = useWorkspace()
  const subscription = useSubscription()
  if (subscription.isError) return null
  const data = subscription.data
  const daysLeft = data?.status === 'trialing' ? trialDaysLeft(data.trial_ends_at) : null
  return (
    <Card title="Plan" link={{ to: 'billing', label: 'Billing' }}>
      {!data ? (
        <CardLoading />
      ) : (
        <div className="flex flex-col gap-2">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-display text-lg font-semibold tracking-[-0.01em] text-ink">{data.plan.name}</span>
            <StatusBadge status={data.status} />
          </div>
          {daysLeft !== null && (
            <p className="text-sm text-ink-2">
              {daysLeft === 0 ? 'Your trial ends today.' : `${daysLeft} ${daysLeft === 1 ? 'day' : 'days'} left in your trial.`}
            </p>
          )}
          {data.status !== 'trialing' && data.current_period_end && (
            <p className="text-[13px] text-muted">
              {data.cancel_at_period_end ? 'Ends' : 'Renews'} on {formatDate(data.current_period_end, timeZone)}
            </p>
          )}
        </div>
      )}
    </Card>
  )
}
