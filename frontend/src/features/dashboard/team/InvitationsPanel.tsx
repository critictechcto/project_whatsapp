import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Mail, MoreHorizontal, RotateCw, UserPlus, XCircle } from 'lucide-react'
import { useState } from 'react'
import { api, unwrap } from '../../../api/client'
import type { Invitation } from '../../../api/types'
import { Button, DropdownMenu, EmptyState, Table, useToast, type Column } from '../../../components/app'
import { formatDate } from '../../../lib/datetime'
import { useWorkspace } from '../../../lib/workspace'
import { FormError } from '../auth/FormError'
import { ConfirmDialog } from '../settings/ui/ConfirmDialog'
import { actionErrorMessage } from '../settings/ui/hooks'
import { Notice } from '../settings/ui/Notice'
import { teamKeys, type InvitationsQuery } from './queries'
import { RoleBadge } from './RoleBadge'

type InvitationsPanelProps = { query: InvitationsQuery; onInvite: () => void }

export function InvitationsPanel({ query, onInvite }: InvitationsPanelProps) {
  const { workspaceId, timeZone } = useWorkspace()
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const [revoking, setRevoking] = useState<Invitation | null>(null)

  // There is no resend endpoint: creating an invitation for the same email replaces the open one
  // and sends a fresh link.
  const resend = useMutation({
    mutationFn: (invitation: Invitation) =>
      unwrap(api.POST('/api/v1/workspaces/invitations/', { body: { email: invitation.email, role: invitation.role } })),
    onSuccess: (invitation) => {
      void queryClient.invalidateQueries({ queryKey: teamKeys.all(workspaceId) })
      toast({ title: `Invitation resent to ${invitation.email}`, description: 'The earlier link no longer works.', tone: 'success' })
    },
    onError: (error) => toast({ title: "Couldn't resend the invitation", description: actionErrorMessage(error), tone: 'error' }),
  })

  const revoke = useMutation({
    mutationFn: (invitation: Invitation) =>
      unwrap(api.DELETE('/api/v1/workspaces/invitations/{id}/', { params: { path: { id: invitation.id } } })),
    onSuccess: (_data, invitation) => {
      void queryClient.invalidateQueries({ queryKey: teamKeys.all(workspaceId) })
      toast({ title: `Invitation for ${invitation.email} revoked`, tone: 'success' })
      setRevoking(null)
    },
  })

  const columns: Column<Invitation>[] = [
    {
      id: 'email',
      header: 'Email',
      cell: (invitation) => (
        <div className="min-w-0">
          <p className="truncate font-medium text-ink">{invitation.email}</p>
          <p className="truncate text-[13px] text-muted sm:hidden">Expires {formatDate(invitation.expires_at, timeZone)}</p>
        </div>
      ),
    },
    { id: 'role', header: 'Role', cell: (invitation) => <RoleBadge role={invitation.role ?? 'agent'} /> },
    {
      id: 'invited_by',
      header: 'Invited by',
      hideOnMobile: true,
      cell: (invitation) => (
        <span className="text-muted">{invitation.invited_by.full_name || invitation.invited_by.email}</span>
      ),
    },
    {
      id: 'expires',
      header: 'Expires',
      hideOnMobile: true,
      cell: (invitation) => <span className="text-muted">{formatDate(invitation.expires_at, timeZone)}</span>,
    },
    {
      id: 'actions',
      header: <span className="sr-only">Actions</span>,
      align: 'right',
      cell: (invitation) => (
        <DropdownMenu
          trigger={<MoreHorizontal className="size-4" aria-hidden="true" />}
          triggerLabel={`Actions for ${invitation.email}`}
          triggerVariant="ghost"
          triggerSize="icon-sm"
          placement="bottom-end"
          items={[
            {
              id: 'resend',
              label: 'Resend invitation',
              icon: <RotateCw className="size-4" aria-hidden="true" />,
              disabled: resend.isPending,
              onSelect: () => resend.mutate(invitation),
            },
            {
              id: 'revoke',
              label: 'Revoke invitation',
              danger: true,
              icon: <XCircle className="size-4" aria-hidden="true" />,
              onSelect: () => {
                revoke.reset()
                setRevoking(invitation)
              },
            },
          ]}
        />
      ),
    },
  ]

  if (query.isError) {
    return (
      <Notice
        tone="danger"
        role="alert"
        title="Couldn't load invitations"
        action={
          <Button variant="secondary" size="sm" onClick={() => void query.refetch()}>
            Try again
          </Button>
        }
      >
        {actionErrorMessage(query.error)}
      </Notice>
    )
  }

  return (
    <>
      <Table
        caption="Pending invitations"
        columns={columns}
        rows={query.items}
        getRowId={(invitation) => invitation.id}
        loading={query.isPending}
        hasNextPage={query.hasNextPage}
        isFetchingNextPage={query.isFetchingNextPage}
        onLoadMore={() => void query.fetchNextPage()}
        empty={
          <EmptyState
            icon={<Mail className="size-5" aria-hidden="true" />}
            title="No pending invitations"
            description="Invite teammates to share the inbox and run campaigns together."
            action={
              <Button variant="secondary" icon={<UserPlus className="size-4" aria-hidden="true" />} onClick={onInvite}>
                Invite teammate
              </Button>
            }
          />
        }
      />

      <ConfirmDialog
        open={revoking !== null}
        onOpenChange={(open) => !open && setRevoking(null)}
        title="Revoke this invitation?"
        description={revoking ? `The link sent to ${revoking.email} will stop working.` : undefined}
        confirmLabel="Revoke"
        loading={revoke.isPending}
        onConfirm={() => revoking && revoke.mutate(revoking)}
      >
        <FormError message={revoke.isError ? actionErrorMessage(revoke.error) : undefined} />
      </ConfirmDialog>
    </>
  )
}
