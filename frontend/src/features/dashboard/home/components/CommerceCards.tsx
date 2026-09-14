import { useQueryClient } from '@tanstack/react-query'
import { ArrowRight } from 'lucide-react'
import { Link } from 'react-router'
import { formatPaise } from '../../../../lib/money'
import { useRealtimeEvent } from '../../../../lib/realtime/hooks'
import { useWorkspace } from '../../../../lib/workspace'
import { isCommerceUnavailable, orderSummaryKey, storeProgress, storeStepLabel, useOrderSummary, useStoreChecklist } from '../api'
import { Card, CardError, CardLoading, Stat } from './OverviewCards'

/** Refetches the order summary when an order is created or changes status. */
function useOrderSummaryRealtime() {
  const queryClient = useQueryClient()
  const { workspaceId } = useWorkspace()
  const refresh = () => void queryClient.invalidateQueries({ queryKey: orderSummaryKey(workspaceId) })
  useRealtimeEvent('order.created', refresh)
  useRealtimeEvent('order.updated', refresh)
}

/**
 * Today's orders and what needs the seller. Hidden when the workspace can't use commerce, and for a
 * store that isn't live and has no open orders (the store setup card covers that case).
 */
export function OrdersTodayCard() {
  useOrderSummaryRealtime()
  const summary = useOrderSummary()
  const checklist = useStoreChecklist()

  if (summary.isError && isCommerceUnavailable(summary.error)) return null
  const data = summary.data
  const storeOff = checklist.data ? !storeProgress(checklist.data.items).storeEnabled : false
  const quiet = data && data.today_count === 0 && data.open_count === 0 && data.needs_attention_count === 0 && data.awaiting_payment_count === 0
  if (storeOff && quiet) return null

  return (
    <Card title="Orders today" link={{ to: 'orders', label: 'All orders' }}>
      {summary.isError ? (
        <CardError error={summary.error} onRetry={() => void summary.refetch()} />
      ) : !data ? (
        <CardLoading />
      ) : (
        <div className="flex flex-col gap-4">
          <div className="grid grid-cols-2 gap-4">
            <Stat label="Orders" value={data.today_count.toLocaleString('en-IN')} to="orders" />
            <Stat label="Revenue" value={formatPaise(data.today_revenue_paise)} />
          </div>
          <div className="grid grid-cols-3 gap-3 border-t border-line-2 pt-4">
            <Stat label="Open" value={data.open_count.toLocaleString('en-IN')} to="orders?stage=open" />
            <Stat label="Needs attention" value={data.needs_attention_count.toLocaleString('en-IN')} to="orders?status=needs_attention" />
            <Stat label="Awaiting payment" value={data.awaiting_payment_count.toLocaleString('en-IN')} to="orders?status=pending_payment" />
          </div>
          <p className="text-[12.5px] text-muted">Revenue counts confirmed orders placed today, excluding cancelled and expired ones.</p>
        </div>
      )}
    </Card>
  )
}

/**
 * Store setup progress and the next step. Admins get links into the store area; other roles see the
 * progress only. Hidden once every step is done, or when commerce isn't available.
 */
export function StoreSetupCard() {
  const { can } = useWorkspace()
  const checklist = useStoreChecklist()
  const canEdit = can('admin')

  if (checklist.isError && isCommerceUnavailable(checklist.error)) return null
  const progress = checklist.data ? storeProgress(checklist.data.items) : null
  if (progress && (progress.total === 0 || progress.done === progress.total)) return null

  return (
    <Card title="Store setup" link={canEdit ? { to: 'store', label: 'Open store' } : undefined}>
      {checklist.isError ? (
        <CardError error={checklist.error} onRetry={() => void checklist.refetch()} />
      ) : !progress ? (
        <CardLoading />
      ) : (
        <div className="flex flex-col gap-3">
          <p className="text-sm text-ink-2">Sell on WhatsApp: buyers browse, order and pay inside the chat.</p>
          <div className="flex items-center gap-3">
            <div
              className="h-1.5 flex-1 overflow-hidden rounded-full bg-line-2"
              role="progressbar"
              aria-label="Store setup progress"
              aria-valuemin={0}
              aria-valuemax={progress.total}
              aria-valuenow={progress.done}
            >
              <div className="h-full rounded-full bg-accent" style={{ width: `${(progress.done / progress.total) * 100}%` }} />
            </div>
            <span className="shrink-0 font-mono text-[12px] text-muted">
              {progress.done} of {progress.total} done
            </span>
          </div>
          {progress.next && (
            <div className="rounded-lg border border-line-2 bg-paper/60 px-3 py-2.5">
              <p className="font-mono text-[10.5px] uppercase tracking-[0.1em] text-muted">Next step</p>
              <p className="mt-0.5 text-sm font-medium text-ink">{storeStepLabel(progress.next.key)}</p>
              {progress.next.detail && <p className="mt-0.5 text-[13px] text-muted">{progress.next.detail}</p>}
              {canEdit ? (
                <Link to="store" className="mt-2 inline-flex items-center gap-1 text-sm font-medium text-accent-2 underline-offset-2 hover:underline">
                  Continue setup
                  <ArrowRight className="size-3.5" aria-hidden="true" />
                </Link>
              ) : (
                <p className="mt-2 text-[12.5px] text-muted">An admin can finish setting up the store.</p>
              )}
            </div>
          )}
        </div>
      )}
    </Card>
  )
}
