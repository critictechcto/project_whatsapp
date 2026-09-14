import { useState } from 'react'
import { Link, useLocation, useParams } from 'react-router'
import { errorMessage, isApiError } from '../../../api/errors'
import { buttonClasses, EmptyState, PageHeader, PageSpinner } from '../../../components/app'
import { formatDateTime } from '../../../lib/datetime'
import { useWorkspace } from '../../../lib/workspace'
import { useOrder, useOrderUpdates } from './api'
import { AddressCard, CustomerCard, ItemsCard, PaymentCard, TrackingCard } from './components/DetailCards'
import { NotesCard } from './components/NotesCard'
import { Notice } from './components/Notice'
import { OrderActions } from './components/OrderActions'
import { OrderStatusBadge, PaymentBadge } from './components/OrderBadges'
import { OrderTimeline } from './components/OrderTimeline'
import { isCheckoutStatus, sourceLabels } from './labels'

export function OrderDetailPage() {
  const { orderId = '' } = useParams()
  const { workspaceId, timeZone } = useWorkspace()
  const location = useLocation()
  const order = useOrder(workspaceId, orderId)
  const [actionError, setActionError] = useState<string | null>(null)

  useOrderUpdates(workspaceId)

  const listSearch = (location.state as { listSearch?: string } | null)?.listSearch ?? ''
  const listUrl = `/app/w/${workspaceId}/orders${listSearch}`

  if (order.isPending) return <PageSpinner />

  if (order.isError) {
    const missing = isApiError(order.error) && order.error.status === 404
    return (
      <EmptyState
        title={missing ? 'Order not found' : "Couldn't load this order"}
        description={missing ? 'It may belong to another workspace.' : errorMessage(order.error)}
        action={
          <Link to={listUrl} className={buttonClasses('secondary')}>
            Back to orders
          </Link>
        }
      />
    )
  }

  const data = order.data

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        eyebrow={
          <Link to={listUrl} className="hover:text-ink">
            Orders
          </Link>
        }
        title={data.number}
        actions={<OrderActions order={data} onError={setActionError} onSuccess={() => setActionError(null)} />}
      />

      <div className="-mt-2 flex flex-wrap items-center gap-x-3 gap-y-2 text-sm text-muted">
        <OrderStatusBadge status={data.status} />
        <PaymentBadge status={data.payment_status} />
        <span>
          Placed <time dateTime={data.created_at}>{formatDateTime(data.created_at, timeZone)}</time>
        </span>
        <span>via {sourceLabels[data.source]}</span>
      </div>

      {actionError && (
        <Notice tone="error" title="Couldn't update the order">
          {actionError}
        </Notice>
      )}

      {data.status === 'needs_attention' && (
        <Notice tone="warning" title="Paid after the checkout expired">
          Confirm the order if you can still fulfil it. If you can&apos;t, cancel it and refund the buyer in your payment gateway.
        </Notice>
      )}
      {isCheckoutStatus(data.status) && (
        <Notice title="The buyer is still checking out">
          {data.expires_at
            ? `If they don't finish by ${formatDateTime(data.expires_at, timeZone)}, the checkout expires and reserved items go back to stock.`
            : 'The order is confirmed once they pay or choose cash on delivery.'}
        </Notice>
      )}
      {data.status === 'expired' && <Notice title="Checkout expired">The buyer didn&apos;t finish paying in time, so the order wasn&apos;t placed.</Notice>}
      {data.status === 'cancelled' && (
        <Notice title={`Cancelled ${formatDateTime(data.cancelled_at, timeZone)}`}>{data.cancel_reason || 'No reason was given.'}</Notice>
      )}

      <div className="grid gap-6 lg:grid-cols-3 lg:items-start">
        <div className="lg:col-span-2">
          <ItemsCard order={data} />
        </div>
        <div className="flex flex-col gap-6 lg:col-start-3 lg:row-span-2 lg:row-start-1">
          <CustomerCard order={data} />
          <AddressCard order={data} />
          <PaymentCard order={data} />
          <TrackingCard order={data} />
          <NotesCard key={data.notes} order={data} />
        </div>
        <div className="lg:col-span-2">
          <OrderTimeline order={data} />
        </div>
      </div>
    </div>
  )
}
