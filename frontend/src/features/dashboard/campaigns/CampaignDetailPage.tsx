import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Link, useParams } from 'react-router'
import { api, unwrap } from '../../../api/client'
import { errorMessage, isApiError } from '../../../api/errors'
import { Button, buttonClasses, EmptyState, PageHeader, PageSpinner, StatusBadge, useToast } from '../../../components/app'
import { formatDateTime, timeZoneName } from '../../../lib/datetime'
import { useWorkspace } from '../../../lib/workspace'
import { campaignKeys, storeCampaign, useCampaign, useCampaignProgress, type Campaign } from './api'
import { campaignError, type FriendlyError } from './campaignErrors'
import { CampaignFunnel } from './components/CampaignFunnel'
import { CampaignStatsGrid } from './components/CampaignStatsGrid'
import { ConfirmDialog } from './components/ConfirmDialog'
import { Notice } from './components/Notice'
import { RecipientsTable } from './components/RecipientsTable'
import { actionCopy, allowedActions, isEditable, type CampaignAction } from './status'

function runAction(id: string, action: CampaignAction): Promise<Campaign> {
  const options = { params: { path: { id } } }
  if (action === 'pause') return unwrap(api.POST('/api/v1/campaigns/{id}/pause/', options))
  if (action === 'resume') return unwrap(api.POST('/api/v1/campaigns/{id}/resume/', options))
  return unwrap(api.POST('/api/v1/campaigns/{id}/cancel/', options))
}

const categoryLabels = { MARKETING: 'Marketing', UTILITY: 'Utility', AUTHENTICATION: 'Authentication' } as const

export function CampaignDetailPage() {
  const { id = '' } = useParams()
  const { workspaceId, timeZone, can } = useWorkspace()
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const campaign = useCampaign(workspaceId, id)
  const [pending, setPending] = useState<CampaignAction | null>(null)
  const [alert, setAlert] = useState<FriendlyError | null>(null)
  const base = `/app/w/${workspaceId}/campaigns`

  useCampaignProgress(workspaceId)

  const transition = useMutation({
    mutationFn: (action: CampaignAction) => runAction(id, action),
    onSuccess: (updated, action) => {
      storeCampaign(queryClient, workspaceId, updated)
      void queryClient.invalidateQueries({ queryKey: campaignKeys.custom(workspaceId, 'recipients', id) })
      setPending(null)
      toast({ title: actionCopy[action].success })
    },
    onError: (error) => {
      setPending(null)
      setAlert(campaignError(error))
      void queryClient.invalidateQueries({ queryKey: campaignKeys.detail(workspaceId, id) })
    },
  })

  if (campaign.isPending) return <PageSpinner />

  if (campaign.isError) {
    const missing = isApiError(campaign.error) && campaign.error.status === 404
    return (
      <EmptyState
        title={missing ? 'Campaign not found' : "Couldn't load this campaign"}
        description={missing ? 'It may have been deleted, or it belongs to another workspace.' : errorMessage(campaign.error)}
        action={
          <Link to={base} className={buttonClasses('secondary')}>
            Back to campaigns
          </Link>
        }
      />
    )
  }

  const data = campaign.data
  const actions = can('admin') ? allowedActions[data.status] : []
  const copy = pending ? actionCopy[pending] : null
  const zone = timeZoneName(timeZone)

  const schedule: { label: string; value: string }[] = [
    { label: 'Scheduled for', value: data.scheduled_at ? formatDateTime(data.scheduled_at, timeZone) : data.status === 'draft' ? 'Not set' : 'Sent on launch' },
    { label: 'Started', value: data.started_at ? formatDateTime(data.started_at, timeZone) : '—' },
    { label: data.status === 'cancelled' ? 'Cancelled' : 'Finished', value: data.completed_at ? formatDateTime(data.completed_at, timeZone) : '—' },
    { label: 'Created by', value: data.created_by.full_name || data.created_by.email },
  ]

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        eyebrow={
          <Link to={base} className="hover:text-ink">
            Campaigns
          </Link>
        }
        title={data.name}
        actions={
          (actions.length > 0 || (can('admin') && isEditable(data.status))) && (
            <>
              {can('admin') && isEditable(data.status) && (
                <Link to={`${base}/${data.id}/edit`} className={buttonClasses('secondary')}>
                  {data.status === 'draft' ? 'Continue editing' : 'Edit'}
                </Link>
              )}
              {actions.map((action) => (
                <Button
                  key={action}
                  variant={actionCopy[action].danger ? 'secondary' : 'primary'}
                  onClick={() => {
                    setAlert(null)
                    setPending(action)
                  }}
                >
                  {actionCopy[action].label}
                </Button>
              ))}
            </>
          )
        }
      />

      <div className="flex flex-wrap items-center gap-x-3 gap-y-2 text-sm text-muted">
        <StatusBadge status={data.status} />
        <span>
          <span className="font-mono text-[13px] text-ink">{data.template.name}</span> · {categoryLabels[data.template.category]} template
        </span>
        <span>From {data.phone_number.display_phone_number}</span>
      </div>

      {alert && (
        <Notice
          tone="error"
          action={
            alert.billing ? (
              <Link to={`/app/w/${workspaceId}/billing`} className={buttonClasses('secondary', 'sm')}>
                View plans
              </Link>
            ) : undefined
          }
        >
          {alert.message}
        </Notice>
      )}

      {data.last_error && (data.status === 'paused' || data.status === 'failed') && (
        <Notice tone="warning" title={data.status === 'paused' ? 'Sending paused' : 'Campaign stopped'}>
          {data.last_error}
        </Notice>
      )}

      {data.status === 'draft' && (
        <Notice title="Not launched yet">This draft hasn't sent anything. Finish the steps and confirm consent to launch it.</Notice>
      )}
      {data.status === 'scheduled' && data.scheduled_at && (
        <Notice title="Scheduled">
          Sending starts {formatDateTime(data.scheduled_at, timeZone)} ({zone}). You can edit or cancel it until then.
        </Notice>
      )}

      <dl className="grid grid-cols-1 gap-x-6 gap-y-3 rounded-xl border border-line bg-card px-5 py-4 text-sm sm:grid-cols-2 lg:grid-cols-4">
        {schedule.map((item) => (
          <div key={item.label}>
            <dt className="text-[12px] text-muted">{item.label}</dt>
            <dd className="text-ink">{item.value}</dd>
          </div>
        ))}
      </dl>
      <p className="-mt-4 text-[12px] text-muted">Times are shown in {zone}.</p>

      <CampaignStatsGrid stats={data.stats} />
      <CampaignFunnel stats={data.stats} />
      <RecipientsTable campaignId={data.id} campaignStatus={data.status} />

      <ConfirmDialog
        open={pending !== null}
        onOpenChange={(open) => {
          if (!open && !transition.isPending) setPending(null)
        }}
        title={copy?.title ?? ''}
        description={copy?.description}
        confirmLabel={copy?.confirm ?? ''}
        danger={copy?.danger}
        loading={transition.isPending}
        onConfirm={() => {
          if (pending) transition.mutate(pending)
        }}
      />
    </div>
  )
}
