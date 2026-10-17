import { Megaphone, Pencil, Store, Users } from 'lucide-react'
import { useEffect, useState, type ReactNode } from 'react'
import { Link, useParams } from 'react-router'
import { errorMessage, isApiError } from '../../../api/errors'
import {
  Button,
  buttonClasses,
  EmptyState,
  Field,
  Input,
  LazyTrendChart,
  PageHeader,
  PageSpinner,
  Select,
  Skeleton,
  StatusBadge,
  Table,
  type Column,
} from '../../../components/app'
import { formatDateTime } from '../../../lib/datetime'
import { formatNumber } from '../../../lib/format'
import { formatPaise } from '../../../lib/money'
import { useWorkspace } from '../../../lib/workspace'
import { Notice } from '../campaigns/components/Notice'
import { isCommerceUnavailable, useOfferClaims, useOfferCode, useOfferStats } from './api'
import { OffersUpgradePanel } from './components/OffersUpgradePanel'
import { RedeemClaimDialog, RedeemCounterDialog } from './components/RedeemDialogs'
import { appliesToLabels, claimStatuses, claimStatusInfo, discountSummary, formatPhone, offerState, offerStateInfo, validitySummary } from './format'
import type { OfferClaim, OfferClaimStatus, OfferCode, OfferStats } from './types'

export function OfferDetailPage() {
  const { id = '' } = useParams()
  const { workspaceId } = useWorkspace()
  const offer = useOfferCode(workspaceId, id)

  if (offer.isPending) return <PageSpinner />
  if (offer.isError) {
    if (isCommerceUnavailable(offer.error)) return <OffersUpgradePanel />
    const missing = isApiError(offer.error) && offer.error.status === 404
    return (
      <EmptyState
        title={missing ? 'Offer code not found' : "Couldn't load this offer code"}
        description={missing ? 'It may have been deleted.' : errorMessage(offer.error)}
        action={
          <Link to={`/app/w/${workspaceId}/offers`} className={buttonClasses('secondary')}>
            Back to offers
          </Link>
        }
      />
    )
  }
  return <OfferDetail offer={offer.data} />
}

function OfferDetail({ offer }: { offer: OfferCode }) {
  const { workspaceId, timeZone, can } = useWorkspace()
  const [redeemOpen, setRedeemOpen] = useState(false)
  const base = `/app/w/${workspaceId}/offers`
  const state = offerStateInfo[offerState(offer)]

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        eyebrow={
          <Link to={base} className="hover:text-ink">
            Offers
          </Link>
        }
        title={<span className="font-mono">{offer.code}</span>}
        description={
          <>
            {offer.title} · {discountSummary(offer)}
            {offer.discount_type !== 'none' && offer.applies_to !== 'all' ? ` · ${appliesToLabels[offer.applies_to ?? 'all']}` : ''} ·{' '}
            {validitySummary(offer, timeZone)}
          </>
        }
        actions={
          <>
            <StatusBadge tone={state.tone}>{state.label}</StatusBadge>
            {can('agent') && (
              <Button variant="secondary" className="min-h-11 sm:min-h-0" icon={<Store className="size-4" aria-hidden="true" />} onClick={() => setRedeemOpen(true)}>
                Redeem at counter
              </Button>
            )}
            {can('admin') && (
              <Link to={`${base}/${offer.id}/edit`} className={buttonClasses('primary', 'md', 'min-h-11 sm:min-h-0')}>
                <Pencil className="size-4" aria-hidden="true" />
                Edit
              </Link>
            )}
          </>
        }
      />

      <StatsSection offerId={offer.id} />
      <ClaimsSection offer={offer} />

      <RedeemCounterDialog open={redeemOpen} onOpenChange={setRedeemOpen} defaultCode={offer.code} />
    </div>
  )
}

function Tile({ label, value, icon }: { label: string; value: ReactNode; icon?: ReactNode }) {
  return (
    <div className="rounded-xl border border-line bg-card p-4">
      <dt className="flex items-center gap-1.5 text-[13px] text-muted">
        {icon}
        {label}
      </dt>
      <dd className="mt-1 font-display text-2xl font-semibold tracking-[-0.02em] text-ink">{value}</dd>
    </div>
  )
}

const shortDay = new Intl.DateTimeFormat('en-IN', { day: 'numeric', month: 'short', timeZone: 'UTC' })

function StatsSection({ offerId }: { offerId: string }) {
  const { workspaceId } = useWorkspace()
  const stats = useOfferStats(workspaceId, offerId)

  return (
    <section aria-labelledby="offer-stats-title" className="flex flex-col gap-4">
      <h2 id="offer-stats-title" className="sr-only">
        Results
      </h2>
      {stats.isError ? (
        <Notice
          tone="error"
          title="Couldn't load the results"
          action={
            <Button variant="secondary" size="sm" onClick={() => void stats.refetch()}>
              Try again
            </Button>
          }
        >
          {errorMessage(stats.error)}
        </Notice>
      ) : stats.isPending ? (
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-6">
          {Array.from({ length: 6 }, (_, i) => (
            <Skeleton key={i} className="h-20" />
          ))}
        </div>
      ) : (
        <StatsBody stats={stats.data} />
      )}
    </section>
  )
}

function StatsBody({ stats }: { stats: OfferStats }) {
  const chartData = stats.daily.map((day) => ({ label: shortDay.format(new Date(`${day.date}T00:00:00Z`)), value: day.claims }))
  const hasDaily = stats.daily.some((day) => day.claims > 0 || day.redeemed > 0)
  return (
    <>
      <dl className="grid grid-cols-2 gap-3 lg:grid-cols-6">
        <Tile label="People sent" value={formatNumber(stats.claims)} icon={<Users className="size-3.5" aria-hidden="true" />} />
        <Tile label="From ads" value={formatNumber(stats.from_ads)} icon={<Megaphone className="size-3.5" aria-hidden="true" />} />
        <Tile label="In open orders" value={formatNumber(stats.applied)} />
        <Tile label="Redeemed" value={formatNumber(stats.redeemed)} />
        <Tile label="Discount given" value={formatPaise(stats.discount_paise, { decimals: 0 })} />
        <Tile label="Revenue" value={formatPaise(stats.revenue_paise, { decimals: 0 })} />
      </dl>
      {hasDaily && (
        <div className="rounded-xl border border-line bg-card p-4">
          <p className="mb-2 text-[13px] text-muted">People who sent the code, per day</p>
          <LazyTrendChart data={chartData} label={`People who sent the code per day, last ${stats.daily.length} days`} height={180} />
        </div>
      )}
    </>
  )
}

function useDebounced<T>(value: T, delay = 300): T {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(value), delay)
    return () => window.clearTimeout(timer)
  }, [value, delay])
  return debounced
}

function ClaimsSection({ offer }: { offer: OfferCode }) {
  const { workspaceId, timeZone, can } = useWorkspace()
  const [status, setStatus] = useState<OfferClaimStatus | ''>('')
  const [phoneInput, setPhoneInput] = useState('')
  const phone = useDebounced(phoneInput.replace(/[^\d+]/g, ''))
  const claims = useOfferClaims(workspaceId, { offer: offer.id, status: status || undefined, phone: phone || undefined })
  const [redeeming, setRedeeming] = useState<OfferClaim | null>(null)
  const canRedeem = can('agent')
  const filtered = Boolean(status || phone)

  const who = (claim: OfferClaim) => claim.contact.name || formatPhone(claim.contact.phone_e164)
  const isOpen = (claim: OfferClaim) => claim.status === 'claimed' || claim.status === 'applied'
  const redeemButton = (claim: OfferClaim, className?: string) =>
    canRedeem && isOpen(claim) ? (
      <Button variant="secondary" size="sm" className={className} aria-label={`Redeem for ${who(claim)}`} onClick={() => setRedeeming(claim)}>
        Redeem
      </Button>
    ) : null
  const orderLink = (claim: OfferClaim) =>
    claim.order_id ? (
      <Link to={`/app/w/${workspaceId}/orders/${claim.order_id}`} className="font-mono text-accent-2 underline-offset-4 hover:underline">
        {claim.order_number || 'Order'}
      </Link>
    ) : (
      <span className="text-muted">—</span>
    )
  const redeemedText = (claim: OfferClaim) => {
    if (!claim.redeemed_at) return '—'
    const by = claim.redeemed_by ? claim.redeemed_by.full_name || claim.redeemed_by.email : ''
    return [formatDateTime(claim.redeemed_at, timeZone), claim.bill_paise ? `bill ${formatPaise(claim.bill_paise)}` : '', by ? `by ${by}` : '']
      .filter(Boolean)
      .join(' · ')
  }

  const columns: Column<OfferClaim>[] = [
    {
      id: 'contact',
      header: 'Customer',
      cell: (claim) => (
        <div className="min-w-0">
          <p className="font-medium text-ink">{claim.contact.name || 'New customer'}</p>
          <p className="font-mono text-[12px] text-muted">{formatPhone(claim.contact.phone_e164)}</p>
        </div>
      ),
    },
    {
      id: 'status',
      header: 'Status',
      cell: (claim) => <StatusBadge tone={claimStatusInfo[claim.status].tone}>{claimStatusInfo[claim.status].label}</StatusBadge>,
    },
    {
      id: 'ad',
      header: 'From ad',
      cell: (claim) => (claim.ad_headline ? <span className="text-[13px]">{claim.ad_headline}</span> : <span className="text-muted">—</span>),
    },
    { id: 'order', header: 'Order', cell: orderLink },
    { id: 'redeemed', header: 'Redeemed', cell: (claim) => <span className="text-[13px] text-muted">{redeemedText(claim)}</span> },
    ...(canRedeem ? [{ id: 'action', header: <span className="sr-only">Actions</span>, align: 'right' as const, cell: (claim: OfferClaim) => redeemButton(claim) }] : []),
  ]

  return (
    <section aria-labelledby="offer-claims-title" className="flex flex-col gap-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <h2 id="offer-claims-title" className="font-display text-lg font-semibold tracking-[-0.01em] text-ink">
          People who sent {offer.code}
        </h2>
        <div className="grid grid-cols-2 gap-3 sm:flex">
          <Field label="Status" hideLabel>
            <Select
              value={status}
              onChange={(event) => setStatus(event.target.value as OfferClaimStatus | '')}
              options={[{ value: '', label: 'All statuses' }, ...claimStatuses.map((value) => ({ value, label: claimStatusInfo[value].label }))]}
              className="min-h-11 sm:min-h-0"
            />
          </Field>
          <Field label="Search by phone" hideLabel>
            <Input
              type="search"
              inputMode="tel"
              value={phoneInput}
              onChange={(event) => setPhoneInput(event.target.value)}
              placeholder="Search phone"
              className="min-h-11 sm:min-h-0"
            />
          </Field>
        </div>
      </div>

      {claims.isError ? (
        <Notice
          tone="error"
          title="Couldn't load claims"
          action={
            <Button variant="secondary" size="sm" onClick={() => void claims.refetch()}>
              Try again
            </Button>
          }
        >
          {errorMessage(claims.error)}
        </Notice>
      ) : !claims.isPending && claims.items.length === 0 ? (
        <EmptyState
          title={filtered ? 'No matching claims' : 'Nobody has sent this code yet'}
          description={
            filtered
              ? 'Try another status or phone number.'
              : `Share ${offer.code} in your ads, posters and WhatsApp status. Everyone who sends it shows up here.`
          }
        />
      ) : (
        <>
          <div className="hidden md:block">
            <Table
              caption={`Claims of ${offer.code}`}
              columns={columns}
              rows={claims.items}
              getRowId={(claim) => claim.id}
              loading={claims.isPending}
              hasNextPage={claims.hasNextPage}
              isFetchingNextPage={claims.isFetchingNextPage}
              onLoadMore={() => void claims.fetchNextPage()}
            />
          </div>
          <div className="flex flex-col gap-3 md:hidden">
            <ul aria-label={`Claims of ${offer.code}`} className="flex flex-col gap-3">
              {claims.items.map((claim) => (
                <li key={claim.id} className="rounded-xl border border-line bg-card p-4">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="font-medium text-ink">{claim.contact.name || 'New customer'}</p>
                      <p className="font-mono text-[12px] text-muted">{formatPhone(claim.contact.phone_e164)}</p>
                    </div>
                    <StatusBadge tone={claimStatusInfo[claim.status].tone}>{claimStatusInfo[claim.status].label}</StatusBadge>
                  </div>
                  {claim.ad_headline && <p className="mt-2 text-[13px] text-ink">Ad: {claim.ad_headline}</p>}
                  <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[13px]">
                    {claim.order_id && <span>Order {orderLink(claim)}</span>}
                    {claim.redeemed_at && <span className="text-muted">Redeemed {redeemedText(claim)}</span>}
                  </div>
                  {redeemButton(claim, 'mt-3 min-h-11 w-full')}
                </li>
              ))}
            </ul>
            {(claims.hasNextPage || claims.isFetchingNextPage) && (
              <Button variant="secondary" className="min-h-11" loading={claims.isFetchingNextPage} onClick={() => void claims.fetchNextPage()}>
                Load more
              </Button>
            )}
          </div>
        </>
      )}

      <RedeemClaimDialog claim={redeeming} code={offer.code} onOpenChange={(open) => !open && setRedeeming(null)} />
    </section>
  )
}
