import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Lock, LogOut, MoreHorizontal, Search, ShieldCheck, UserMinus } from 'lucide-react'
import { useState } from 'react'
import { useNavigate } from 'react-router'
import { api, unwrap } from '../../../api/client'
import type { Membership } from '../../../api/types'
import { Avatar, Button, DropdownMenu, EmptyState, Field, Input, Table, Tooltip, useToast, type Column, type MenuEntry } from '../../../components/app'
import { formatDate } from '../../../lib/datetime'
import { useWorkspace } from '../../../lib/workspace'
import { FormError } from '../auth/FormError'
import { useMe } from '../auth/session'
import { ConfirmDialog } from '../settings/ui/ConfirmDialog'
import { actionErrorMessage, useDebouncedValue } from '../settings/ui/hooks'
import { Notice } from '../settings/ui/Notice'
import { exitWorkspace } from '../workspaces/exitWorkspace'
import { ChangeRoleDialog } from './ChangeRoleDialog'
import { teamKeys, useMembers } from './queries'
import { RoleBadge } from './RoleBadge'
import { canChangeRole, canRemove } from './roles'

type Target = { kind: 'role' | 'remove' | 'leave'; member: Membership }

function memberName(member: Membership) {
  return member.user.full_name || member.user.email
}

export function MembersPanel() {
  const { role: actorRole, timeZone } = useWorkspace()
  const me = useMe()
  const [search, setSearch] = useState('')
  const debouncedSearch = useDebouncedValue(search.trim())
  const members = useMembers(debouncedSearch)
  const [target, setTarget] = useState<Target | null>(null)

  const columns: Column<Membership>[] = [
    {
      id: 'member',
      header: 'Member',
      cell: (member) => {
        const isSelf = member.user.id === me.data?.id
        return (
          <div className="flex min-w-0 items-center gap-3">
            <Avatar name={memberName(member)} />
            <div className="min-w-0">
              <p className="truncate font-medium text-ink">
                {memberName(member)}
                {isSelf && <span className="ml-1.5 text-[12.5px] font-normal text-muted">(You)</span>}
              </p>
              <p className="truncate text-[13px] text-muted">{member.user.email}</p>
            </div>
          </div>
        )
      },
    },
    {
      id: 'role',
      header: 'Role',
      cell: (member) => (
        <span className="inline-flex items-center gap-1.5">
          <RoleBadge role={member.role ?? 'viewer'} />
          {member.role === 'owner' && (
            <Tooltip content="The owner's role can't be changed here.">
              <span tabIndex={0} aria-label="Owner role is locked" className="inline-grid rounded text-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/30">
                <Lock className="size-3.5" aria-hidden="true" />
              </span>
            </Tooltip>
          )}
        </span>
      ),
    },
    {
      id: 'joined',
      header: 'Joined',
      hideOnMobile: true,
      cell: (member) => <span className="text-muted">{formatDate(member.created_at, timeZone)}</span>,
    },
    {
      id: 'actions',
      header: <span className="sr-only">Actions</span>,
      align: 'right',
      cell: (member) => {
        const isSelf = member.user.id === me.data?.id
        const subject = { role: member.role ?? 'viewer', isSelf }
        const items: MenuEntry[] = []
        if (canChangeRole(actorRole, subject)) {
          items.push({
            id: 'role',
            label: 'Change role',
            icon: <ShieldCheck className="size-4" aria-hidden="true" />,
            onSelect: () => setTarget({ kind: 'role', member }),
          })
        }
        if (canRemove(actorRole, subject)) {
          items.push({
            id: 'remove',
            label: 'Remove from workspace',
            danger: true,
            icon: <UserMinus className="size-4" aria-hidden="true" />,
            onSelect: () => setTarget({ kind: 'remove', member }),
          })
        }
        if (isSelf) {
          items.push({
            id: 'leave',
            label: 'Leave workspace',
            danger: true,
            icon: <LogOut className="size-4" aria-hidden="true" />,
            onSelect: () => setTarget({ kind: 'leave', member }),
          })
        }
        if (!items.length) return null
        return (
          <DropdownMenu
            trigger={<MoreHorizontal className="size-4" aria-hidden="true" />}
            triggerLabel={`Actions for ${memberName(member)}`}
            triggerVariant="ghost"
            triggerSize="icon-sm"
            placement="bottom-end"
            items={items}
          />
        )
      },
    },
  ]

  return (
    <div className="flex flex-col gap-4">
      <Field label="Search members" hideLabel className="sm:max-w-xs">
        <Input
          type="search"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          placeholder="Search by name or email"
        />
      </Field>

      {members.isError ? (
        <Notice
          tone="danger"
          role="alert"
          title="Couldn't load members"
          action={
            <Button variant="secondary" size="sm" onClick={() => void members.refetch()}>
              Try again
            </Button>
          }
        >
          {actionErrorMessage(members.error)}
        </Notice>
      ) : (
        <Table
          caption="Workspace members"
          columns={columns}
          rows={members.items}
          getRowId={(member) => member.id}
          loading={members.isPending}
          hasNextPage={members.hasNextPage}
          isFetchingNextPage={members.isFetchingNextPage}
          onLoadMore={() => void members.fetchNextPage()}
          empty={
            <EmptyState
              icon={<Search className="size-5" aria-hidden="true" />}
              title={debouncedSearch ? 'No members match your search' : 'No members yet'}
              description={debouncedSearch ? `Nobody here matches “${debouncedSearch}”.` : undefined}
            />
          }
        />
      )}

      {target?.kind === 'role' && (
        <ChangeRoleDialog key={target.member.id} member={target.member} open onOpenChange={(open) => !open && setTarget(null)} />
      )}
      {target?.kind === 'remove' && (
        <RemoveMemberDialog key={target.member.id} member={target.member} onClose={() => setTarget(null)} />
      )}
      {target?.kind === 'leave' && <LeaveWorkspaceDialog member={target.member} onClose={() => setTarget(null)} />}
    </div>
  )
}

function useDeleteMembership() {
  return useMutation({
    mutationFn: (membershipId: string) =>
      unwrap(api.DELETE('/api/v1/workspaces/members/{id}/', { params: { path: { id: membershipId } } })),
  })
}

function RemoveMemberDialog({ member, onClose }: { member: Membership; onClose: () => void }) {
  const { workspace, workspaceId } = useWorkspace()
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const remove = useDeleteMembership()

  return (
    <ConfirmDialog
      open
      onOpenChange={(open) => !open && onClose()}
      title={`Remove ${memberName(member)}?`}
      description={`They will lose access to ${workspace.name} straight away. You can invite them again later.`}
      confirmLabel="Remove"
      loading={remove.isPending}
      onConfirm={() =>
        remove.mutate(member.id, {
          onSuccess: () => {
            void queryClient.invalidateQueries({ queryKey: teamKeys.all(workspaceId) })
            toast({ title: `${memberName(member)} was removed`, tone: 'success' })
            onClose()
          },
        })
      }
    >
      <FormError message={remove.isError ? actionErrorMessage(remove.error) : undefined} />
    </ConfirmDialog>
  )
}

function LeaveWorkspaceDialog({ member, onClose }: { member: Membership; onClose: () => void }) {
  const { workspace, workspaceId } = useWorkspace()
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const { toast } = useToast()
  const leave = useDeleteMembership()

  return (
    <ConfirmDialog
      open
      onOpenChange={(open) => !open && onClose()}
      title={`Leave ${workspace.name}?`}
      description="You'll lose access to its inbox, contacts and campaigns. An admin can invite you again."
      confirmLabel="Leave workspace"
      loading={leave.isPending}
      onConfirm={() =>
        leave.mutate(member.id, {
          onSuccess: () => {
            exitWorkspace(queryClient, navigate, workspaceId)
            toast({ title: `You left ${workspace.name}`, tone: 'success' })
          },
        })
      }
    >
      <FormError message={leave.isError ? actionErrorMessage(leave.error) : undefined} />
    </ConfirmDialog>
  )
}
