import { useMutation, useQueryClient } from '@tanstack/react-query'
import { MoreHorizontal, RefreshCw, Unplug } from 'lucide-react'
import { useState } from 'react'
import { api, unwrap } from '../../../api/client'
import { queryKeys } from '../../../api/queryKeys'
import { DropdownMenu, StatusBadge, useToast } from '../../../components/app'
import { formatRelative } from '../../../lib/datetime'
import { useWorkspace } from '../../../lib/workspace'
import { FormError } from '../auth/FormError'
import { ConfirmDialog } from '../settings/ui/ConfirmDialog'
import { actionErrorMessage } from '../settings/ui/hooks'
import { Notice } from '../settings/ui/Notice'
import { SectionCard } from '../settings/ui/SectionCard'
import { onboardingBadges } from './meta'
import { PhoneNumbersTable } from './PhoneNumbersTable'
import { isOnboardingInProgress, type WhatsAppAccount } from './queries'

export function AccountCard({ account }: { account: WhatsAppAccount }) {
  const { workspaceId, can } = useWorkspace()
  const isAdmin = can('admin')
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const [confirmDisconnect, setConfirmDisconnect] = useState(false)
  const name = account.name || 'WhatsApp Business Account'
  const onboarding = onboardingBadges[account.onboarding_status]

  const refreshWorkspace = () => queryClient.invalidateQueries({ queryKey: queryKeys.workspace(workspaceId) })

  const resync = useMutation({
    mutationFn: () => unwrap(api.POST('/api/v1/whatsapp/accounts/{id}/resync/', { params: { path: { id: account.id } } })),
    onSuccess: () => {
      void refreshWorkspace()
      toast({ title: 'Synced with Meta', description: 'Numbers, quality ratings and limits are up to date.', tone: 'success' })
    },
    onError: (error) => toast({ title: "Couldn't sync with Meta", description: actionErrorMessage(error), tone: 'error' }),
  })

  const disconnect = useMutation({
    mutationFn: () => unwrap(api.DELETE('/api/v1/whatsapp/accounts/{id}/', { params: { path: { id: account.id } } })),
    onSuccess: () => {
      void refreshWorkspace()
      setConfirmDisconnect(false)
      toast({ title: `${name} was disconnected`, tone: 'success' })
    },
  })

  return (
    <SectionCard
      id={`waba-${account.id}`}
      title={name}
      description={
        <span className="flex flex-wrap items-center gap-x-3 gap-y-1">
          <span>
            WABA ID <span className="font-mono text-[12.5px]">{account.waba_id}</span>
          </span>
          {account.subscribed_at && <span>Connected {formatRelative(account.subscribed_at)}</span>}
        </span>
      }
      actions={
        <div className="flex items-center gap-2">
          <StatusBadge status={account.status} />
          {account.onboarding_status !== 'completed' && <StatusBadge tone={onboarding.tone}>{onboarding.label}</StatusBadge>}
          {isAdmin && (
            <DropdownMenu
              trigger={<MoreHorizontal className="size-4" aria-hidden="true" />}
              triggerLabel={`Actions for ${name}`}
              triggerVariant="ghost"
              triggerSize="icon-sm"
              placement="bottom-end"
              items={[
                {
                  id: 'resync',
                  label: 'Sync with Meta',
                  icon: <RefreshCw className="size-4" aria-hidden="true" />,
                  disabled: resync.isPending,
                  onSelect: () => resync.mutate(),
                },
                { type: 'separator', id: 'sep' },
                {
                  id: 'disconnect',
                  label: 'Disconnect',
                  danger: true,
                  icon: <Unplug className="size-4" aria-hidden="true" />,
                  onSelect: () => {
                    disconnect.reset()
                    setConfirmDisconnect(true)
                  },
                },
              ]}
            />
          )}
        </div>
      }
    >
      <div className="flex flex-col gap-4">
        {isOnboardingInProgress(account) && (
          <Notice tone="info" role="status" title="Setup is still running">
            We're finishing the connection with Meta. This page updates on its own.
          </Notice>
        )}
        {account.last_error && (
          <Notice tone={account.onboarding_status === 'failed' ? 'danger' : 'warning'} title="Meta reported a problem">
            {account.last_error}
          </Notice>
        )}
        {account.status === 'restricted' && (
          <Notice tone="warning" title="Account restricted by Meta">
            Meta has restricted this account, so some messages may not send. Check Meta Business Suite for details and next steps.
          </Notice>
        )}
        <PhoneNumbersTable numbers={account.phone_numbers} />
      </div>

      <ConfirmDialog
        open={confirmDisconnect}
        onOpenChange={setConfirmDisconnect}
        title={`Disconnect ${name}?`}
        description="Messages will stop sending and arriving here for its numbers. The account and numbers stay in your Meta Business portfolio, so you can connect them again later."
        confirmLabel="Disconnect"
        loading={disconnect.isPending}
        onConfirm={() => disconnect.mutate()}
      >
        <FormError message={disconnect.isError ? actionErrorMessage(disconnect.error) : undefined} />
      </ConfirmDialog>
    </SectionCard>
  )
}
