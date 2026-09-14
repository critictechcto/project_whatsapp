import { useState } from 'react'
import { api, unwrap } from '../../../../api/client'
import { errorMessage } from '../../../../api/errors'
import { useCursorQuery } from '../../../../api/pagination'
import { EmptyState, StatusBadge, statusInfo, Table, Tabs, type Column, type TabOption } from '../../../../components/app'
import { formatDateTime } from '../../../../lib/datetime'
import { useWorkspace } from '../../../../lib/workspace'
import { campaignKeys, recipientStatuses, type CampaignRecipient, type CampaignStatus, type RecipientStatus } from '../api'
import { recipientDetail } from '../recipientText'
import { Notice } from './Notice'

type Filter = 'all' | RecipientStatus

const filters: readonly TabOption<Filter>[] = [
  { value: 'all', label: 'All' },
  ...recipientStatuses.map((status) => ({ value: status, label: statusInfo(status).label })),
]

export function RecipientsTable({ campaignId, campaignStatus }: { campaignId: string; campaignStatus: CampaignStatus }) {
  const { workspaceId, timeZone } = useWorkspace()
  const [filter, setFilter] = useState<Filter>('all')
  const status = filter === 'all' ? undefined : filter

  const recipients = useCursorQuery<CampaignRecipient>({
    queryKey: campaignKeys.custom(workspaceId, 'recipients', campaignId, { status }),
    queryFn: ({ cursor, signal }) =>
      unwrap(api.GET('/api/v1/campaigns/{id}/recipients/', { params: { path: { id: campaignId }, query: { status, cursor } }, signal })),
  })

  const columns: Column<CampaignRecipient>[] = [
    {
      id: 'contact',
      header: 'Contact',
      cell: (recipient) => (
        <div className="min-w-0">
          <p className="truncate font-medium text-ink">{recipient.contact.name || recipient.contact.phone_e164}</p>
          {recipient.contact.name && <p className="font-mono text-[12px] text-muted">{recipient.contact.phone_e164}</p>}
        </div>
      ),
    },
    { id: 'status', header: 'Status', cell: (recipient) => <StatusBadge status={recipient.status} /> },
    {
      id: 'detail',
      header: 'Details',
      className: 'min-w-56',
      cell: (recipient) => {
        const detail = recipientDetail(recipient)
        return detail ? (
          <span className="text-[13px] leading-5 text-ink-2">
            {detail}
            {recipient.error_code && <span className="ml-1.5 font-mono text-[11.5px] text-muted">({recipient.error_code})</span>}
          </span>
        ) : (
          <span className="text-muted">—</span>
        )
      },
    },
    {
      id: 'updated',
      header: 'Updated',
      hideOnMobile: true,
      cell: (recipient) => <span className="text-[13px] text-muted">{formatDateTime(recipient.updated_at, timeZone)}</span>,
    },
  ]

  const notStarted = campaignStatus === 'draft' || campaignStatus === 'scheduled'

  return (
    <section aria-labelledby="campaign-recipients-heading" className="flex flex-col gap-3">
      <h2 id="campaign-recipients-heading" className="font-display text-lg font-semibold tracking-[-0.01em] text-ink">
        Recipients
      </h2>
      <Tabs label="Filter recipients by status" items={filters} value={filter} onValueChange={setFilter} />
      {recipients.isError ? (
        <Notice tone="error" title="Couldn't load recipients">
          {errorMessage(recipients.error)}
        </Notice>
      ) : (
        <Table
          caption="Campaign recipients"
          columns={columns}
          rows={recipients.items}
          getRowId={(recipient) => recipient.id}
          loading={recipients.isPending}
          hasNextPage={recipients.hasNextPage}
          isFetchingNextPage={recipients.isFetchingNextPage}
          onLoadMore={() => void recipients.fetchNextPage()}
          empty={
            notStarted ? (
              <EmptyState title="No recipients yet" description="The audience is locked in and listed here when the campaign starts sending." />
            ) : (
              <EmptyState title="No recipients with this status" />
            )
          }
        />
      )}
    </section>
  )
}
