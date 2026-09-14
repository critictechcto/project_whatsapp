import { ShoppingBag } from 'lucide-react'
import { useMemo } from 'react'
import { Link, useLocation } from 'react-router'
import { errorMessage } from '../../../api/errors'
import { Button, EmptyState, PageHeader, Table, Tabs, type Column } from '../../../components/app'
import { formatDateTime } from '../../../lib/datetime'
import { formatPaise } from '../../../lib/money'
import { useWorkspace } from '../../../lib/workspace'
import { useNewOrderAlerts, useOrders, useOrderSummary, useOrderUpdates, type OrderListItem } from './api'
import { OrderFiltersBar } from './components/OrderFiltersBar'
import { OrderStatusBadge, PaymentBadge } from './components/OrderBadges'
import { Notice } from './components/Notice'
import { SummaryStrip } from './components/SummaryStrip'
import { hasActiveFilters, orderListQuery, orderTabs, useOrderFilters, type OrderTab } from './filters'
import { formatPhone, itemsLabel } from './format'
import { sourceLabels } from './labels'

export function OrdersPage() {
  const { workspaceId, timeZone } = useWorkspace()
  const location = useLocation()
  const { filters, setFilters } = useOrderFilters()
  const query = useMemo(() => orderListQuery(filters, timeZone), [filters, timeZone])
  const orders = useOrders(workspaceId, query)
  const summary = useOrderSummary(workspaceId)
  const base = `/app/w/${workspaceId}/orders`

  useNewOrderAlerts(workspaceId)
  useOrderUpdates(workspaceId)

  const tabs = orderTabs.map((tab) =>
    tab.value === 'attention' && summary.data?.needs_attention_count ? { ...tab, count: summary.data.needs_attention_count } : tab,
  )

  const columns: Column<OrderListItem>[] = [
    {
      id: 'number',
      header: 'Order',
      cell: (order) => (
        <div className="min-w-0">
          <Link
            to={`${base}/${order.id}`}
            state={{ listSearch: location.search }}
            className="font-mono text-[13px] font-medium text-ink underline-offset-4 hover:underline"
          >
            {order.number}
          </Link>
          <span className="block whitespace-nowrap text-[12px] text-muted">{formatDateTime(order.created_at, timeZone)}</span>
        </div>
      ),
    },
    {
      id: 'customer',
      header: 'Customer',
      cell: (order) => (
        <div className="min-w-0 max-w-[14rem]">
          <p className="truncate text-ink">{order.contact.name || formatPhone(order.contact.phone_e164)}</p>
          {order.contact.name && <p className="truncate text-[12px] text-muted">{formatPhone(order.contact.phone_e164)}</p>}
        </div>
      ),
    },
    {
      id: 'items',
      header: 'Items',
      hideOnMobile: true,
      cell: (order) => <span className="whitespace-nowrap text-muted">{itemsLabel(order.item_count)}</span>,
    },
    {
      id: 'total',
      header: 'Total',
      align: 'right',
      cell: (order) => <span className="whitespace-nowrap tabular-nums text-ink">{formatPaise(order.total_paise)}</span>,
    },
    {
      id: 'status',
      header: 'Status',
      cell: (order) => (
        <div className="flex flex-col items-start gap-1">
          <OrderStatusBadge status={order.status} />
          <PaymentBadge status={order.payment_status} />
        </div>
      ),
    },
    {
      id: 'source',
      header: 'Source',
      hideOnMobile: true,
      cell: (order) => <span className="whitespace-nowrap text-muted">{sourceLabels[order.source]}</span>,
    },
  ]

  const filtered = hasActiveFilters(filters)
  const tabLabel = orderTabs.find((tab) => tab.value === filters.tab)?.label ?? ''

  const emptyState =
    filters.tab === 'all' && !filtered ? (
      <EmptyState
        icon={<ShoppingBag />}
        title="No orders yet"
        description="Orders appear here when buyers check out, whether they pay online or choose cash on delivery."
      />
    ) : filtered ? (
      <EmptyState
        title="No orders match these filters"
        description="Try a different search, payment filter or date range."
        action={
          <Button variant="secondary" onClick={() => setFilters({ payment: '', method: '', from: '', to: '', q: '' })}>
            Clear filters
          </Button>
        }
      />
    ) : (
      <EmptyState title={`No orders in ${tabLabel.toLowerCase()}`} description="Orders show up here as they move along." />
    )

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Orders"
        description="Orders your buyers place on WhatsApp. Mark them packed, shipped and delivered here; each change notifies the buyer."
      />

      <SummaryStrip workspaceId={workspaceId} onShowAttention={() => setFilters({ tab: 'attention' })} />

      <div className="flex flex-col gap-4">
        <Tabs<OrderTab> label="Order stage" items={tabs} value={filters.tab} onValueChange={(tab) => setFilters({ tab })} />
        <OrderFiltersBar filters={filters} setFilters={setFilters} />
      </div>

      {orders.isError ? (
        <Notice
          tone="error"
          title="Couldn't load orders"
          action={
            <Button variant="secondary" size="sm" onClick={() => void orders.refetch()}>
              Try again
            </Button>
          }
        >
          {errorMessage(orders.error)}
        </Notice>
      ) : (
        <Table
          caption="Orders"
          columns={columns}
          rows={orders.items}
          getRowId={(order) => order.id}
          loading={orders.isPending}
          hasNextPage={orders.hasNextPage}
          isFetchingNextPage={orders.isFetchingNextPage}
          onLoadMore={() => void orders.fetchNextPage()}
          empty={emptyState}
        />
      )}
    </div>
  )
}
