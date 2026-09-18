import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { api, unwrap } from '../../../api/client'
import type { Invitation } from '../../../api/types'
import { Button, Dialog, useToast } from '../../../components/app'
import { formatDate } from '../../../lib/datetime'
import { roleLabels, type Role } from '../../../lib/roles'
import { useWorkspace } from '../../../lib/workspace'
import { FormError } from '../auth/FormError'
import { actionErrorMessage } from '../settings/ui/hooks'
import { teamKeys } from './queries'
import { RoleOptions } from './RoleOptions'

type ChangeInvitationRoleDialogProps = { invitation: Invitation; onClose: () => void }

/**
 * The API has no update for an invitation, so a role change sends a fresh invitation to the same
 * email with the new role; the backend revokes the open one, so its link stops working.
 */
export function ChangeInvitationRoleDialog({ invitation, onClose }: ChangeInvitationRoleDialogProps) {
  const { workspaceId, timeZone } = useWorkspace()
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const current: Role = invitation.role ?? 'agent'
  const [role, setRole] = useState<Role>(current)

  const reinvite = useMutation({
    mutationFn: (next: Role) =>
      unwrap(api.POST('/api/v1/workspaces/invitations/', { body: { email: invitation.email, role: next } })),
    onSuccess: (created) => {
      void queryClient.invalidateQueries({ queryKey: teamKeys.all(workspaceId) })
      toast({
        title: `Invitation updated for ${created.email}`,
        description: `They'll join as ${roleLabels[created.role ?? role]}. A new link was emailed and works until ${formatDate(created.expires_at, timeZone)}.`,
        tone: 'success',
      })
      onClose()
    },
  })

  return (
    <Dialog
      open
      onOpenChange={(next) => !next && !reinvite.isPending && onClose()}
      dismissible={!reinvite.isPending}
      size="sm"
      title="Change invited role"
      description={invitation.email}
      footer={
        <>
          <Button variant="secondary" disabled={reinvite.isPending} onClick={onClose}>
            Cancel
          </Button>
          <Button loading={reinvite.isPending} disabled={role === current} onClick={() => reinvite.mutate(role)}>
            Send new invitation
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-3">
        <p className="text-[13px] text-muted">
          We'll email {invitation.email} a fresh invitation with the new role. The link in the earlier email will stop
          working.
        </p>
        <FormError message={reinvite.isError ? actionErrorMessage(reinvite.error) : undefined} />
        <RoleOptions name="invitation-role" value={role} current={current} onChange={setRole} disabled={reinvite.isPending} />
      </div>
    </Dialog>
  )
}
