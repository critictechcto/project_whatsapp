import { Megaphone, Plus } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router'
import { api, unwrap } from '../../../api/client'
import { errorMessage } from '../../../api/errors'
import { useCursorQuery } from '../../../api/pagination'
import {
  Button,
  buttonClasses,
  EmptyState,
  PageHeader,
  StatusBadge,
  statusInfo,
  Table,
  Tabs,
  type Column,
  type TabOption,
} from '../../../components/app'
import { formatDateTime } from '../../../lib/datetime'
import { formatNumber } from '../../../lib/format'
import { useWorkspace } from '../../../lib/workspace'
import { campaignKeys, campaignStatuses, useCampaignProgress, type Campaign, type CampaignStatus } from './api'
import { CampaignProgress } from './components/CampaignProgress'
import { Notice } from './components/Notice'

type Filter = 'all' | CampaignStatus

const filters: readonly TabOption<Filter>[] = [
  { value: 'all', label: 'All' },
  ...campaignStatuses.map((status) => ({ value: status, label: statusInfo(status).label })),
]

function timing(campaign: Campaign, timeZone: string) {
  if (campaign.started_at) return { label: 'Started', at: formatDateTime(campaign.started_at, timeZone) }
  if (campaign.scheduled_at) return { label: 'Scheduled for', at: formatDateTime(campaign.scheduled_at, timeZone) }
  return { label: 'Created', at: formatDateTime(campaign.created_at, timeZone) }
}

export function CampaignsPage() {
  const { workspaceId, timeZone, can } = useWorkspace()
  const [filter, setFilter] = useState<Filter>('all')
  const status = filter === 'all' ? undefined : filter
  const base = `/app/w/${workspaceId}/campaigns`
  const canManage = can('admin')

  useCampaignProgress(workspaceId)

  const campaigns = useCursorQuery<Campaign>({
    queryKey: campaignKeys.list(workspaceId, { status }),
    queryFn: ({ cursor, signal }) => unwrap(api.GET('/api/v1/campaigns/', { params: { query: { status, cursor } }, signal })),
  })

  const newButton = canManage ? (
    <Link to={`${base}/new`} className={buttonClasses('primary')}>
      <Plus className="size-4" aria-hidden="true" />
      New campaign
    </Link>
  ) : null

  const columns: Column<Campaign>[] = [
    {
      id: 'name',
      header: 'Campaign',
      cell: (campaign) => (
        <div className="min-w-0">
          <Link to={`${base}/${campaign.id}`} className="font-medium text-ink underline-offset-4 hover:underline">
            {campaign.name}
          </Link>
          <p className="truncate font-mono text-[12px] text-muted">{campaign.template.name}</p>
        </div>
      ),
    },
    { id: 'status', header: 'Status', cell: (campaign) => <StatusBadge status={campaign.status} /> },
    {
      id: 'when',
      header: 'When',
      hideOnMobile: true,
      cell: (campaign) => {
        const when = timing(campaign, timeZone)
        return (
          <span className="text-[13px] leading-5">
            <span className="block text-muted">{when.label}</span>
            {when.at}
          </span>
        )
      },
    },
    { id: 'progress', header: 'Progress', cell: (campaign) => <CampaignProgress stats={campaign.stats} status={campaign.status} /> },
    {
      id: 'failed',
      header: 'Failed',
      align: 'right',
      hideOnMobile: true,
      cell: (campaign) => (
        <span className={campaign.stats.failed > 0 ? 'font-mono text-signal' : 'font-mono text-muted'}>{formatNumber(campaign.stats.failed)}</span>
      ),
    },
  ]

  const filterLabel = filters.find((item) => item.value === filter)?.label

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Campaigns"
        description="Send an approved template to tagged contacts now or at a set time, and follow delivery as Meta reports it."
        actions={newButton}
      />

      <Tabs label="Filter campaigns by status" items={filters} value={filter} onValueChange={setFilter} />

      {campaigns.isError ? (
        <Notice
          tone="error"
          title="Couldn't load campaigns"
          action={
            <Button variant="secondary" size="sm" onClick={() => void campaigns.refetch()}>
              Try again
            </Button>
          }
        >
          {errorMessage(campaigns.error)}
        </Notice>
      ) : (
        <Table
          caption="Campaigns"
          columns={columns}
          rows={campaigns.items}
          getRowId={(campaign) => campaign.id}
          loading={campaigns.isPending}
          hasNextPage={campaigns.hasNextPage}
          isFetchingNextPage={campaigns.isFetchingNextPage}
          onLoadMore={() => void campaigns.fetchNextPage()}
          empty={
            filter === 'all' ? (
              <EmptyState
                icon={<Megaphone className="size-5" aria-hidden="true" />}
                title="No campaigns yet"
                description="A campaign sends one approved template to the contacts you choose. Only contacts who agreed to hear from you should be included."
                action={newButton}
              />
            ) : (
              <EmptyState title={`No ${filterLabel?.toString().toLowerCase()} campaigns`} description="Try another status." />
            )
          }
        />
      )}
    </div>
  )
}
