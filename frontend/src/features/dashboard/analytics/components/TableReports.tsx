import { FileText, Megaphone, UsersRound } from 'lucide-react'
import type { ReactNode } from 'react'
import { Link } from 'react-router'
import { EmptyState, StatusBadge, Table, type Column } from '../../../../components/app'
import { formatDateTime } from '../../../../lib/datetime'
import { useWorkspace } from '../../../../lib/workspace'
import { useCampaignsReport, useTeamReport, useTemplatesReport } from '../api'
import { categoryLabel, formatNumber, formatRate, roleLabel } from '../format'
import type { Schemas } from '../../../../api/types'
import type { AnalyticsReport } from '../api'
import type { DateRange } from '../range'

type AnalyticsCampaignRow = Schemas['AnalyticsCampaignRow']
type AnalyticsTeamRow = Schemas['AnalyticsTeamRow']
type AnalyticsTemplateRow = Schemas['AnalyticsTemplateRow']
import { ReportError, ReportHeader, ReportSkeleton } from './ReportStates'

const num = (value: number) => <span className="tabular-nums">{formatNumber(value)}</span>
const pct = (value: string | null) => <span className="whitespace-nowrap tabular-nums">{formatRate(value)}</span>

type Queryish<T> = { isPending: boolean; isError: boolean; error: unknown; data?: T; refetch: () => Promise<unknown> }

/** Header, loading, error and empty handling shared by the table reports. */
function TableReport<Row>({
  report,
  range,
  query,
  title,
  description,
  errorTitle,
  empty,
  children,
}: {
  report: AnalyticsReport
  range: DateRange
  query: Queryish<{ results: Row[] }>
  title: string
  description: string
  errorTitle: string
  empty: ReactNode
  children: (rows: Row[]) => ReactNode
}) {
  return (
    <div className="flex flex-col gap-5">
      <ReportHeader title={title} description={description} report={report} range={range} />
      {query.isPending ? (
        <ReportSkeleton blocks={1} />
      ) : query.isError || !query.data ? (
        <ReportError title={errorTitle} error={query.error} onRetry={() => void query.refetch()} />
      ) : query.data.results.length === 0 ? (
        empty
      ) : (
        children(query.data.results)
      )}
    </div>
  )
}

export function TemplatesReport({ range }: { range: DateRange }) {
  const query = useTemplatesReport(range)
  const columns: Column<AnalyticsTemplateRow>[] = [
    {
      id: 'name',
      header: 'Template',
      cell: (row) => (
        <div className="min-w-0">
          <p className="font-mono text-[13px] text-ink">{row.name}</p>
          <p className="text-[12px] text-muted">
            {categoryLabel(row.category)} · {row.language}
          </p>
        </div>
      ),
    },
    { id: 'sent', header: 'Sent', align: 'right', cell: (row) => num(row.sent) },
    { id: 'delivered', header: 'Delivered', align: 'right', hideOnMobile: true, cell: (row) => num(row.delivered) },
    { id: 'read', header: 'Read', align: 'right', hideOnMobile: true, cell: (row) => num(row.read) },
    { id: 'failed', header: 'Failed', align: 'right', hideOnMobile: true, cell: (row) => num(row.failed) },
    { id: 'delivery_rate', header: 'Delivery', align: 'right', cell: (row) => pct(row.delivery_rate) },
    { id: 'read_rate', header: 'Read rate', align: 'right', cell: (row) => pct(row.read_rate) },
  ]
  return (
    <TableReport
      report="templates"
      range={range}
      query={query}
      title="Templates"
      description="Template messages sent in this period, by template and language. Top 50 by messages sent."
      errorTitle="Couldn't load the templates report"
      empty={<EmptyState icon={<FileText />} title="No template messages in this period" description="Campaigns, order updates and other template sends will show up here." />}
    >
      {(rows) => <Table caption="Template performance" columns={columns} rows={rows} getRowId={(row) => `${row.name}:${row.language}`} />}
    </TableReport>
  )
}

export function CampaignsReport({ range }: { range: DateRange }) {
  const { workspaceId, timeZone } = useWorkspace()
  const query = useCampaignsReport(range)
  const columns: Column<AnalyticsCampaignRow>[] = [
    {
      id: 'name',
      header: 'Campaign',
      cell: (row) => (
        <div className="min-w-0 max-w-[16rem]">
          <Link to={`/app/w/${workspaceId}/campaigns/${row.id}`} className="font-medium text-ink underline-offset-4 hover:underline">
            {row.name}
          </Link>
          <p className="whitespace-nowrap text-[12px] text-muted">Started {formatDateTime(row.started_at, timeZone)}</p>
        </div>
      ),
    },
    { id: 'status', header: 'Status', hideOnMobile: true, cell: (row) => <StatusBadge status={row.status} /> },
    { id: 'total', header: 'Recipients', align: 'right', hideOnMobile: true, cell: (row) => num(row.total_count) },
    { id: 'sent', header: 'Sent', align: 'right', cell: (row) => num(row.sent_count) },
    { id: 'failed', header: 'Failed', align: 'right', hideOnMobile: true, cell: (row) => num(row.failed_count) },
    { id: 'delivery_rate', header: 'Delivery', align: 'right', cell: (row) => pct(row.delivery_rate) },
    { id: 'read_rate', header: 'Read rate', align: 'right', cell: (row) => pct(row.read_rate) },
    { id: 'reply_rate', header: 'Reply rate', align: 'right', cell: (row) => pct(row.reply_rate) },
  ]
  return (
    <TableReport
      report="campaigns"
      range={range}
      query={query}
      title="Campaigns"
      description="Campaigns that started in this period, newest first. Numbers cover each whole campaign, including sends after the period."
      errorTitle="Couldn't load the campaigns report"
      empty={<EmptyState icon={<Megaphone />} title="No campaigns started in this period" description="Campaigns you launch will show their delivery, read and reply rates here." />}
    >
      {(rows) => <Table caption="Campaign performance" columns={columns} rows={rows} getRowId={(row) => row.id} />}
    </TableReport>
  )
}

export function TeamReport({ range }: { range: DateRange }) {
  const query = useTeamReport(range)
  const columns: Column<AnalyticsTeamRow>[] = [
    {
      id: 'name',
      header: 'Member',
      cell: (row) => (
        <div className="min-w-0 max-w-[16rem]">
          <p className="truncate text-ink">{row.name || row.email}</p>
          <p className="truncate text-[12px] text-muted">
            {roleLabel(row.role)}
            <span className="hidden sm:inline"> · {row.email}</span>
          </p>
        </div>
      ),
    },
    { id: 'messages_sent', header: 'Replies sent', align: 'right', cell: (row) => num(row.messages_sent) },
    { id: 'assigned', header: 'Assigned', align: 'right', cell: (row) => num(row.conversations_assigned) },
    { id: 'closed', header: 'Closed', align: 'right', cell: (row) => num(row.conversations_closed) },
  ]
  return (
    <TableReport
      report="team"
      range={range}
      query={query}
      title="Team"
      description="Inbox replies each member sent in this period, and the conversations assigned to them with activity in the period."
      errorTitle="Couldn't load the team report"
      empty={<EmptyState icon={<UsersRound />} title="No team activity in this period" />}
    >
      {(rows) => <Table caption="Team activity" columns={columns} rows={rows} getRowId={(row) => row.user_id} />}
    </TableReport>
  )
}
