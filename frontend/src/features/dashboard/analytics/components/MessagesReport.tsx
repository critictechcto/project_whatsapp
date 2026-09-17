import { MessageSquare } from 'lucide-react'
import { useState } from 'react'
import { EmptyState, LazyTrendChart, Table, type Column } from '../../../../components/app'
import { cn } from '../../../../lib/cn'
import { useMessagesReport } from '../api'
import { categoryLabel, failureCodeLabels, failureLabel, formatNumber, formatRate, sourceLabel } from '../format'
import { formatDayLabel, formatRangeLabel } from '../range'
import type { AnalyticsCategoryRow, AnalyticsMessagePoint, AnalyticsSourceRow, DateRange } from '../types'
import { Panel, ReportError, ReportHeader, ReportSkeleton, ShareBar } from './ReportStates'

type Metric = Exclude<keyof AnalyticsMessagePoint, 'date'>

const metrics: { value: Metric; label: string }[] = [
  { value: 'sent', label: 'Sent' },
  { value: 'delivered', label: 'Delivered' },
  { value: 'read', label: 'Read' },
  { value: 'failed', label: 'Failed' },
  { value: 'received', label: 'Received' },
]

const num = (value: number) => <span className="tabular-nums">{formatNumber(value)}</span>

export function MessagesReport({ range }: { range: DateRange }) {
  const report = useMessagesReport(range)
  const [metric, setMetric] = useState<Metric>('sent')

  const header = (
    <ReportHeader
      title="Messages"
      description="Messages sent from every part of UpChatz and replies received, by the day they were created."
      report="messages"
      range={range}
    />
  )

  if (report.isPending) {
    return (
      <div className="flex flex-col gap-5">
        {header}
        <ReportSkeleton blocks={3} />
      </div>
    )
  }
  if (report.isError) {
    return (
      <div className="flex flex-col gap-5">
        {header}
        <ReportError title="Couldn't load the messages report" error={report.error} onRetry={() => void report.refetch()} />
      </div>
    )
  }

  const data = report.data
  const hasMessages = data.series.some((point) => point.sent + point.delivered + point.read + point.failed + point.received > 0)
  if (!hasMessages) {
    return (
      <div className="flex flex-col gap-5">
        {header}
        <EmptyState
          icon={<MessageSquare />}
          title="No messages in this period"
          description="Messages sent and received in this date range will show up here. Try a longer range."
        />
      </div>
    )
  }

  const metricLabel = metrics.find((item) => item.value === metric)!.label
  const sourceColumns: Column<AnalyticsSourceRow>[] = [
    { id: 'source', header: 'Source', cell: (row) => <span className="whitespace-nowrap text-ink">{sourceLabel(row.source)}</span> },
    { id: 'sent', header: 'Sent', align: 'right', cell: (row) => num(row.sent) },
    { id: 'delivered', header: 'Delivered', align: 'right', hideOnMobile: true, cell: (row) => num(row.delivered) },
    { id: 'read', header: 'Read', align: 'right', hideOnMobile: true, cell: (row) => num(row.read) },
    { id: 'failed', header: 'Failed', align: 'right', hideOnMobile: true, cell: (row) => num(row.failed) },
    { id: 'delivery_rate', header: 'Delivery', align: 'right', cell: (row) => <span className="tabular-nums">{formatRate(row.delivery_rate)}</span> },
    { id: 'read_rate', header: 'Read rate', align: 'right', cell: (row) => <span className="tabular-nums">{formatRate(row.read_rate)}</span> },
  ]
  const categoryColumns: Column<AnalyticsCategoryRow>[] = [
    { id: 'category', header: 'Category', cell: (row) => <span className="text-ink">{categoryLabel(row.category)}</span> },
    { id: 'sent', header: 'Sent', align: 'right', cell: (row) => num(row.sent) },
    { id: 'delivered', header: 'Delivered', align: 'right', hideOnMobile: true, cell: (row) => num(row.delivered) },
    { id: 'read', header: 'Read', align: 'right', cell: (row) => num(row.read) },
    { id: 'failed', header: 'Failed', align: 'right', cell: (row) => num(row.failed) },
  ]
  const failureMax = Math.max(0, ...data.failure_reasons.map((row) => row.count))
  const failureTotal = data.failure_reasons.reduce((sum, row) => sum + row.count, 0)

  return (
    <div className="flex flex-col gap-6">
      {header}

      <Panel
        title="Daily trend"
        description={`${metricLabel} messages per day`}
        actions={
          <div role="group" aria-label="Chart metric" className="flex max-w-full gap-1 overflow-x-auto rounded-lg border border-line bg-card p-1">
            {metrics.map((item) => (
              <button
                key={item.value}
                type="button"
                aria-pressed={metric === item.value}
                onClick={() => setMetric(item.value)}
                className={cn(
                  'h-9 shrink-0 rounded-md px-2.5 text-[13px] font-medium transition-colors sm:h-7',
                  metric === item.value ? 'bg-ink text-paper' : 'text-muted hover:text-ink',
                )}
              >
                {item.label}
              </button>
            ))}
          </div>
        }
      >
        <div className="rounded-xl border border-line bg-card p-3 sm:p-4">
          <LazyTrendChart
            data={data.series.map((point) => ({ label: formatDayLabel(point.date), value: point[metric] }))}
            label={`${metricLabel} messages per day, ${formatRangeLabel(range)}`}
            valueFormatter={formatNumber}
          />
        </div>
      </Panel>

      <div className="grid gap-6 2xl:grid-cols-2">
        <Panel title="By source" description="Where outbound messages came from">
          <Table
            caption="Outbound messages by source"
            columns={sourceColumns}
            rows={data.by_source}
            getRowId={(row) => row.source}
            empty={<p className="rounded-xl border border-dashed border-line px-4 py-6 text-center text-sm text-muted">No outbound messages in this period.</p>}
          />
        </Panel>
        <Panel title="By category" description="Template messages by Meta category">
          <Table
            caption="Outbound messages by template category"
            columns={categoryColumns}
            rows={data.by_category}
            getRowId={(row) => row.category || 'none'}
            empty={<p className="rounded-xl border border-dashed border-line px-4 py-6 text-center text-sm text-muted">No outbound messages in this period.</p>}
          />
        </Panel>
      </div>

      <Panel title="Why messages failed" description="Top error codes Meta returned for failed messages">
        {data.failure_reasons.length === 0 ? (
          <p className="rounded-xl border border-dashed border-line px-4 py-6 text-center text-sm text-muted">No failed messages in this period.</p>
        ) : (
          <ul aria-label="Failure reasons" className="divide-y divide-line-2 overflow-hidden rounded-xl border border-line bg-card">
            {data.failure_reasons.map((row) => (
              <li key={row.error_code || 'unknown'} className="flex flex-col gap-2 px-4 py-3 sm:flex-row sm:items-center sm:gap-4">
                <div className="min-w-0 flex-1">
                  <p className="text-sm text-ink">{failureLabel(row.error_code)}</p>
                  {row.error_code && row.error_code in failureCodeLabels && <p className="font-mono text-[12px] text-muted">Code {row.error_code}</p>}
                </div>
                <div className="flex items-center gap-3 sm:w-64">
                  <ShareBar value={row.count} max={failureMax} tone="signal" />
                  <span className="w-20 shrink-0 text-right text-sm tabular-nums text-ink">
                    {formatNumber(row.count)}
                    <span className="block text-[12px] text-muted">{formatRate(failureTotal ? row.count / failureTotal : null)}</span>
                  </span>
                </div>
              </li>
            ))}
          </ul>
        )}
      </Panel>
    </div>
  )
}
