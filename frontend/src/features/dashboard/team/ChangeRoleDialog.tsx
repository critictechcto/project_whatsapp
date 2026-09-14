import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { api, unwrap } from '../../../api/client'
import type { Membership } from '../../../api/types'
import { Button, Dialog, useToast } from '../../../components/app'
import { cn } from '../../../lib/cn'
import { roleLabels, type Role } from '../../../lib/roles'
import { useWorkspace } from '../../../lib/workspace'
import { FormError } from '../auth/FormError'
import { actionErrorMessage } from '../settings/ui/hooks'
import { teamKeys } from './queries'
import { assignableRoles, roleDescriptions } from './roles'

type ChangeRoleDialogProps = { member: Membership; open: boolean; onOpenChange: (open: boolean) => void }

export function ChangeRoleDialog({ member, open, onOpenChange }: ChangeRoleDialogProps) {
  const { workspaceId } = useWorkspace()
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const current: Role = member.role ?? 'viewer'
  const [role, setRole] = useState<Role>(current)
  const name = member.user.full_name || member.user.email

  const update = useMutation({
    mutationFn: (next: Role) =>
      unwrap(api.PATCH('/api/v1/workspaces/members/{id}/', { params: { path: { id: member.id } }, body: { role: next } })),
    onSuccess: (updated) => {
      void queryClient.invalidateQueries({ queryKey: teamKeys.all(workspaceId) })
      toast({ title: `Role updated`, description: `${name} is now ${roleLabels[updated.role ?? role]}.`, tone: 'success' })
      onOpenChange(false)
    },
  })

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => !update.isPending && onOpenChange(next)}
      dismissible={!update.isPending}
      size="sm"
      title={`Change role for ${name}`}
      description={member.user.email}
      footer={
        <>
          <Button variant="secondary" disabled={update.isPending} onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button loading={update.isPending} disabled={role === current} onClick={() => update.mutate(role)}>
            Save role
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-3">
        <FormError message={update.isError ? actionErrorMessage(update.error) : undefined} />
        <fieldset className="flex flex-col gap-2">
          <legend className="sr-only">Role</legend>
          {assignableRoles.map((option) => (
            <label
              key={option}
              className={cn(
                'flex cursor-pointer items-start gap-3 rounded-lg border px-3 py-2.5 transition-colors',
                role === option ? 'border-accent bg-accent-soft/40' : 'border-line hover:border-ink/20',
              )}
            >
              <input
                type="radio"
                name="member-role"
                value={option}
                checked={role === option}
                onChange={() => setRole(option)}
                className="mt-1 accent-[var(--color-accent)]"
              />
              <span>
                <span className="block text-sm font-medium text-ink">
                  {roleLabels[option]}
                  {option === current && <span className="ml-1.5 text-[12.5px] font-normal text-muted">Current</span>}
                </span>
                <span className="block text-[13px] text-muted">{roleDescriptions[option]}</span>
              </span>
            </label>
          ))}
        </fieldset>
      </div>
    </Dialog>
  )
}
