import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, Store, TicketPercent } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router'
import { errorMessage } from '../../../api/errors'
import { Button, buttonClasses, EmptyState, PageHeader, StatusBadge, Switch, Table, useToast, type Column } from '../../../components/app'
import { formatNumber } from '../../../lib/format'
import { useWorkspace } from '../../../lib/workspace'
import { Notice } from '../campaigns/components/Notice'
import { isCommerceUnavailable, offerKeys, offersApi, useOfferCodes } from './api'
import { OffersUpgradePanel } from './components/OffersUpgradePanel'
import { RedeemCounterDialog } from './components/RedeemDialogs'
import { discountSummary, offerState, offerStateInfo, validitySummary } from './format'
import type { OfferCode } from './types'

export function OffersPage() {
  const { workspaceId, timeZone, can } = useWorkspace()
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const codes = useOfferCodes(workspaceId)
  const [redeemOpen, setRedeemOpen] = useState(false)
  const canManage = can('admin')
  const canRedeem = can('agent')
  const base = `/app/w/${workspaceId}/offers`
  const listKey = offerKeys.list(workspaceId, { page_size: 100 })

  const toggle = useMutation({
    mutationFn: ({ offer, active }: { offer: OfferCode; active: boolean }) => offersApi.updateCode(offer.id, { is_active: active }),
    onMutate: async ({ offer, active }) => {
      await queryClient.cancelQueries({ queryKey: listKey })
      const previous = queryClient.getQueryData<OfferCode[]>(listKey)
      queryClient.setQueryData<OfferCode[]>(listKey, (current) => current?.map((item) => (item.id === offer.id ? { ...item, is_active: active } : item)))
      return { previous }
    },
    onError: (error, _vars, context) => {
      if (context?.previous) queryClient.setQueryData(listKey, context.previous)
      toast({ title: "Couldn't update the offer", description: errorMessage(error), tone: 'error' })
    },
    onSettled: () => queryClient.invalidateQueries({ queryKey: offerKeys.all(workspaceId) }),
  })

  const activeControl = (offer: OfferCode) =>
    canManage ? (
      <Switch
        checked={offer.is_active}
        onCheckedChange={(active) => toggle.mutate({ offer, active })}
        label={`Active: ${offer.code}`}
        hideLabel
      />
    ) : (
      <StateBadge offer={offer} />
    )

  const columns: Column<OfferCode>[] = [
    {
      id: 'code',
      header: 'Code',
      cell: (offer) => (
        <div className="min-w-0">
          <Link to={`${base}/${offer.id}`} className="font-mono font-medium text-ink underline-offset-4 hover:underline">
            {offer.code}
          </Link>
          <p className="truncate text-[13px] text-muted">{offer.title}</p>
        </div>
      ),
    },
    { id: 'discount', header: 'Offer', cell: (offer) => <span className="text-[13px]">{discountSummary(offer)}</span> },
    {
      id: 'validity',
      header: 'Valid',
      cell: (offer) => (
        <div className="flex flex-col items-start gap-1">
          <span className="text-[13px] text-muted">{validitySummary(offer, timeZone)}</span>
          {canManage && <StateBadge offer={offer} />}
        </div>
      ),
    },
    { id: 'sent', header: 'People sent', align: 'right', cell: (offer) => <span className="font-mono">{formatNumber(offer.claims_count)}</span> },
    { id: 'redeemed', header: 'Redeemed', align: 'right', cell: (offer) => <span className="font-mono">{formatNumber(offer.redeemed_count)}</span> },
    { id: 'active', header: canManage ? 'Active' : 'Status', cell: activeControl },
  ]

  const newCode = canManage ? (
    <Link to={`${base}/new`} className={buttonClasses('primary', 'md', 'min-h-11 sm:min-h-0')}>
      <Plus className="size-4" aria-hidden="true" />
      New code
    </Link>
  ) : null

  const locked = codes.isError && isCommerceUnavailable(codes.error)
  const list = codes.data ?? []

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Offers"
        description="Codes customers send on WhatsApp, like DIWALI. They get your reply, and the discount at checkout or at your counter."
        actions={
          locked ? null : (
            <>
              {canRedeem && (
                <Button variant="secondary" className="min-h-11 sm:min-h-0" icon={<Store className="size-4" aria-hidden="true" />} onClick={() => setRedeemOpen(true)}>
                  Redeem at counter
                </Button>
              )}
              {newCode}
            </>
          )
        }
      />

      {locked ? (
        <OffersUpgradePanel />
      ) : codes.isError ? (
        <Notice
          tone="error"
          title="Couldn't load offer codes"
          action={
            <Button variant="secondary" size="sm" onClick={() => void codes.refetch()}>
              Try again
            </Button>
          }
        >
          {errorMessage(codes.error)}
        </Notice>
      ) : !codes.isPending && list.length === 0 ? (
        <EmptyState
          icon={<TicketPercent className="size-5" aria-hidden="true" />}
          title="No offer codes yet"
          description="Create a code like DIWALI and share it in your ads, posters and status. Every customer who sends it is counted here."
          action={newCode}
        />
      ) : (
        <>
          <div className="hidden md:block">
            <Table caption="Offer codes" columns={columns} rows={list} getRowId={(offer) => offer.id} loading={codes.isPending} />
          </div>
          <ul aria-label="Offer codes" className="flex flex-col gap-3 md:hidden">
            {list.map((offer) => (
              <li key={offer.id} className="rounded-xl border border-line bg-card p-4">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <Link to={`${base}/${offer.id}`} className="inline-flex min-h-11 items-center font-mono text-base font-medium text-ink underline-offset-4 hover:underline">
                      {offer.code}
                    </Link>
                    <p className="truncate text-[13px] text-muted">{offer.title}</p>
                  </div>
                  {activeControl(offer)}
                </div>
                <p className="mt-2 text-sm text-ink">{discountSummary(offer)}</p>
                <p className="text-[13px] text-muted">{validitySummary(offer, timeZone)}</p>
                <dl className="mt-3 grid grid-cols-2 gap-2 border-t border-line-2 pt-3 text-[13px]">
                  <div>
                    <dt className="text-muted">People sent</dt>
                    <dd className="font-mono text-ink">{formatNumber(offer.claims_count)}</dd>
                  </div>
                  <div>
                    <dt className="text-muted">Redeemed</dt>
                    <dd className="font-mono text-ink">{formatNumber(offer.redeemed_count)}</dd>
                  </div>
                </dl>
              </li>
            ))}
          </ul>
        </>
      )}

      <RedeemCounterDialog open={redeemOpen} onOpenChange={setRedeemOpen} />
    </div>
  )
}

function StateBadge({ offer }: { offer: OfferCode }) {
  const info = offerStateInfo[offerState(offer)]
  return <StatusBadge tone={info.tone}>{info.label}</StatusBadge>
}
