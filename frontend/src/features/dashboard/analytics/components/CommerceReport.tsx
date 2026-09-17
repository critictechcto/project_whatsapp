import { ShoppingBag } from 'lucide-react'
import { useState } from 'react'
import { EmptyState, LazyTrendChart, Table, type Column } from '../../../../components/app'
import { cn } from '../../../../lib/cn'
import { formatPaise } from '../../../../lib/money'
import type { useCommerceReport } from '../api'
import { formatNumber, orderStatusLabel, paymentMethodLabels } from '../format'
import { formatDayLabel, formatRangeLabel } from '../range'
import type { Schemas } from '../../../../api/types'
import type { DateRange } from '../range'

type AnalyticsPaymentMethodRow = Schemas['AnalyticsPaymentMethodRow']
type AnalyticsProductRow = Schemas['AnalyticsProductRow']
import { Panel, ReportError, ReportHeader, ReportSkeleton, ShareBar } from './ReportStates'

type Metric = 'revenue_paise' | 'orders'

const rupees = (paise: number) => formatPaise(paise, { decimals: 0 })
const compactInr = new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', notation: 'compact', maximumFractionDigits: 1 })
/** Short axis labels (₹28K, ₹1.2L) so they fit the chart gutter. */
const compactRupees = (paise: number) => compactInr.format(paise / 100)

/** Commerce report; the page fetches it up front to know whether to show the tab. */
export function CommerceReport({ range, query }: { range: DateRange; query: ReturnType<typeof useCommerceReport> }) {
  const [metric, setMetric] = useState<Metric>('revenue_paise')
  const header = (
    <ReportHeader
      title="Commerce"
      description="Orders placed on WhatsApp in this period. Revenue counts orders paid online or with cash collected."
      report="commerce"
      range={range}
    />
  )

  if (query.isPending) {
    return (
      <div className="flex flex-col gap-5">
        {header}
        <ReportSkeleton blocks={2} />
      </div>
    )
  }
  if (query.isError) {
    return (
      <div className="flex flex-col gap-5">
        {header}
        <ReportError title="Couldn't load the commerce report" error={query.error} onRetry={() => void query.refetch()} />
      </div>
    )
  }

  const data = query.data
  if (data.orders === 0) {
    return (
      <div className="flex flex-col gap-5">
        {header}
        <EmptyState icon={<ShoppingBag />} title="No orders in this period" description="Orders buyers place through your WhatsApp store will show up here." />
      </div>
    )
  }

  const stats = [
    { label: 'Orders', value: formatNumber(data.orders) },
    { label: 'Paid orders', value: formatNumber(data.paid_orders) },
    { label: 'Revenue', value: rupees(data.revenue_paise) },
    { label: 'Average order', value: data.average_order_paise === null ? '—' : rupees(data.average_order_paise) },
  ]
  const statusMax = Math.max(0, ...data.by_status.map((row) => row.count))
  const methodColumns: Column<AnalyticsPaymentMethodRow>[] = [
    { id: 'method', header: 'Payment', cell: (row) => <span className="whitespace-nowrap text-ink">{paymentMethodLabels[row.payment_method] ?? row.payment_method}</span> },
    { id: 'orders', header: 'Orders', align: 'right', cell: (row) => <span className="tabular-nums">{formatNumber(row.orders)}</span> },
    { id: 'revenue', header: 'Revenue', align: 'right', cell: (row) => <span className="whitespace-nowrap tabular-nums">{rupees(row.revenue_paise)}</span> },
  ]
  const productColumns: Column<AnalyticsProductRow>[] = [
    { id: 'name', header: 'Product', cell: (row) => <span className="text-ink">{row.name}</span> },
    { id: 'quantity', header: 'Qty', align: 'right', cell: (row) => <span className="tabular-nums">{formatNumber(row.quantity)}</span> },
    { id: 'revenue', header: 'Revenue', align: 'right', cell: (row) => <span className="whitespace-nowrap tabular-nums">{rupees(row.revenue_paise)}</span> },
  ]
  const metricLabel = metric === 'orders' ? 'Orders' : 'Revenue'

  return (
    <div className="flex flex-col gap-6">
      {header}

      <dl aria-label="Commerce totals" className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {stats.map((stat) => (
          <div key={stat.label} className="flex min-w-0 flex-col gap-1 rounded-xl border border-line bg-card px-4 py-3">
            <dt className="text-[12px] text-muted">{stat.label}</dt>
            <dd className="truncate font-display text-xl font-semibold tabular-nums tracking-[-0.01em] text-ink">{stat.value}</dd>
          </div>
        ))}
      </dl>

      <Panel
        title="Daily trend"
        description={`${metricLabel} per day`}
        actions={
          <div role="group" aria-label="Chart metric" className="flex gap-1 rounded-lg border border-line bg-card p-1">
            {(['revenue_paise', 'orders'] as const).map((value) => (
              <button
                key={value}
                type="button"
                aria-pressed={metric === value}
                onClick={() => setMetric(value)}
                className={cn(
                  'h-9 rounded-md px-2.5 text-[13px] font-medium transition-colors sm:h-7',
                  metric === value ? 'bg-ink text-paper' : 'text-muted hover:text-ink',
                )}
              >
                {value === 'orders' ? 'Orders' : 'Revenue'}
              </button>
            ))}
          </div>
        }
      >
        <div className="rounded-xl border border-line bg-card p-3 sm:p-4">
          <LazyTrendChart
            data={data.series.map((point) => ({ label: formatDayLabel(point.date), value: point[metric] }))}
            label={`${metricLabel} per day, ${formatRangeLabel(range)}`}
            valueFormatter={metric === 'orders' ? formatNumber : compactRupees}
          />
        </div>
      </Panel>

      <div className="grid gap-6 lg:grid-cols-2">
        <Panel title="Orders by status" description="Where this period's orders are now">
          <ul aria-label="Orders by status" className="divide-y divide-line-2 overflow-hidden rounded-xl border border-line bg-card">
            {data.by_status.map((row) => (
              <li key={row.status} className="flex items-center gap-3 px-4 py-2.5">
                <span className="w-36 shrink-0 text-sm text-ink">{orderStatusLabel(row.status)}</span>
                <ShareBar value={row.count} max={statusMax} />
                <span className="w-12 shrink-0 text-right text-sm tabular-nums text-ink">{formatNumber(row.count)}</span>
              </li>
            ))}
          </ul>
        </Panel>
        <Panel title="By payment method">
          <Table caption="Orders by payment method" columns={methodColumns} rows={data.by_payment_method} getRowId={(row) => row.payment_method || 'none'} />
        </Panel>
      </div>

      <Panel title="Top products" description="By revenue from paid orders">
        <Table
          caption="Top products by revenue"
          columns={productColumns}
          rows={data.top_products}
          getRowId={(row) => row.product_id ?? row.name}
          empty={<p className="rounded-xl border border-dashed border-line px-4 py-6 text-center text-sm text-muted">No paid orders in this period.</p>}
        />
      </Panel>
    </div>
  )
}
