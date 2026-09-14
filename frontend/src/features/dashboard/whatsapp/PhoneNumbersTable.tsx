import { useMutation, useQueryClient } from '@tanstack/react-query'
import { MoreHorizontal, RefreshCw, RotateCcw, Star } from 'lucide-react'
import { api, unwrap } from '../../../api/client'
import { queryKeys } from '../../../api/queryKeys'
import type { PhoneNumber } from '../../../api/types'
import { DropdownMenu, StatusBadge, Table, useToast, type Column, type MenuEntry } from '../../../components/app'
import { formatRelative } from '../../../lib/datetime'
import { useWorkspace } from '../../../lib/workspace'
import { actionErrorMessage } from '../settings/ui/hooks'
import { nameStatusBadge, qualityExplanations, tierLabel } from './meta'

type NumberAction = 'set-default' | 'refresh' | 'retry-registration'

const actionCopy: Record<NumberAction, { success: string; failure: string }> = {
  'set-default': { success: 'Default number updated', failure: "Couldn't change the default number" },
  refresh: { success: 'Number refreshed from Meta', failure: "Couldn't refresh the number" },
  'retry-registration': { success: 'Registration retried', failure: "Couldn't retry registration" },
}

export function PhoneNumbersTable({ numbers }: { numbers: readonly PhoneNumber[] }) {
  const { workspaceId, can } = useWorkspace()
  const isAdmin = can('admin')
  const queryClient = useQueryClient()
  const { toast } = useToast()

  const action = useMutation({
    mutationFn: ({ id, kind }: { id: string; kind: NumberAction }) => {
      const params = { params: { path: { id } } }
      if (kind === 'set-default') return unwrap(api.POST('/api/v1/whatsapp/phone-numbers/{id}/set-default/', params))
      if (kind === 'refresh') return unwrap(api.POST('/api/v1/whatsapp/phone-numbers/{id}/refresh/', params))
      return unwrap(api.POST('/api/v1/whatsapp/phone-numbers/{id}/retry-registration/', params))
    },
    onSuccess: (number, { kind }) => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.workspace(workspaceId) })
      toast({
        title: actionCopy[kind].success,
        description: kind === 'set-default' ? `New conversations and campaigns use ${number.display_phone_number} unless you pick another.` : undefined,
        tone: 'success',
      })
    },
    onError: (error, { kind }) => toast({ title: actionCopy[kind].failure, description: actionErrorMessage(error), tone: 'error' }),
  })

  const columns: Column<PhoneNumber>[] = [
    {
      id: 'number',
      header: 'Number',
      cell: (number) => {
        const nameBadge = nameStatusBadge(number.name_status)
        return (
          <div className="min-w-0">
            <p className="flex flex-wrap items-center gap-2">
              <span className="font-mono text-[13.5px] font-medium text-ink">{number.display_phone_number}</span>
              {number.is_default && <StatusBadge tone="blue">Default</StatusBadge>}
            </p>
            <p className="mt-0.5 flex flex-wrap items-center gap-2 text-[13px] text-muted">
              <span className="truncate">{number.verified_name || 'No display name yet'}</span>
              {nameBadge && <StatusBadge tone={nameBadge.tone}>{nameBadge.label}</StatusBadge>}
            </p>
          </div>
        )
      },
    },
    {
      id: 'quality',
      header: 'Quality',
      className: 'sm:max-w-[16rem]',
      cell: (number) => (
        <div>
          <StatusBadge status={number.quality_rating} />
          <p className="mt-1 text-[12.5px] leading-snug text-muted">{qualityExplanations[number.quality_rating]}</p>
        </div>
      ),
    },
    {
      id: 'limit',
      header: 'Messaging limit',
      hideOnMobile: true,
      cell: (number) => (
        <div>
          <p className="text-ink">{tierLabel(number.messaging_limit_tier)}</p>
          <p className="text-[12.5px] text-muted">Set by Meta</p>
        </div>
      ),
    },
    {
      id: 'status',
      header: 'Status',
      cell: (number) => (
        <div>
          <StatusBadge status={number.registration_status} />
          {number.last_error && <p className="mt-1 text-[12.5px] text-signal">{number.last_error}</p>}
          <p className="mt-1 text-[12.5px] text-muted">
            {number.last_synced_at ? `Synced ${formatRelative(number.last_synced_at)}` : 'Not synced yet'}
          </p>
        </div>
      ),
    },
  ]

  if (isAdmin) {
    columns.push({
      id: 'actions',
      header: <span className="sr-only">Actions</span>,
      align: 'right',
      cell: (number) => {
        const busy = action.isPending && action.variables?.id === number.id
        const items: MenuEntry[] = [
          {
            id: 'default',
            label: number.is_default ? 'Default number' : 'Set as default',
            icon: <Star className="size-4" aria-hidden="true" />,
            disabled: busy || number.is_default || number.registration_status !== 'registered',
            onSelect: () => action.mutate({ id: number.id, kind: 'set-default' }),
          },
          {
            id: 'refresh',
            label: 'Refresh from Meta',
            icon: <RefreshCw className="size-4" aria-hidden="true" />,
            disabled: busy,
            onSelect: () => action.mutate({ id: number.id, kind: 'refresh' }),
          },
        ]
        if (number.registration_status === 'failed' || number.registration_status === 'pending') {
          items.push({
            id: 'retry',
            label: 'Retry registration',
            icon: <RotateCcw className="size-4" aria-hidden="true" />,
            disabled: busy,
            onSelect: () => action.mutate({ id: number.id, kind: 'retry-registration' }),
          })
        }
        return (
          <DropdownMenu
            trigger={<MoreHorizontal className="size-4" aria-hidden="true" />}
            triggerLabel={`Actions for ${number.display_phone_number}`}
            triggerVariant="ghost"
            triggerSize="icon-sm"
            placement="bottom-end"
            items={items}
          />
        )
      },
    })
  }

  return (
    <Table
      caption="Phone numbers"
      columns={columns}
      rows={numbers}
      getRowId={(number) => number.id}
      empty={<p className="px-1 py-3 text-sm text-muted">No phone numbers on this account yet. Numbers added in Meta appear here after a sync.</p>}
    />
  )
}
