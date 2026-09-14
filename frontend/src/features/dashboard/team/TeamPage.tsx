import { UserPlus } from 'lucide-react'
import { useState } from 'react'
import { Button, PageHeader, Tabs } from '../../../components/app'
import { roleLabels } from '../../../lib/roles'
import { useWorkspace } from '../../../lib/workspace'
import { SectionCard } from '../settings/ui/SectionCard'
import { InvitationsPanel } from './InvitationsPanel'
import { InviteDialog } from './InviteDialog'
import { MembersPanel } from './MembersPanel'
import { useInvitations } from './queries'
import { roleDescriptions } from './roles'

type TeamTab = 'members' | 'invitations'

const roleOrder = ['owner', 'admin', 'agent', 'viewer'] as const

export function TeamPage() {
  const { workspace, can } = useWorkspace()
  const isAdmin = can('admin')
  const [tab, setTab] = useState<TeamTab>('members')
  const [inviteOpen, setInviteOpen] = useState(false)
  const invitations = useInvitations(isAdmin)

  const openInvite = () => setInviteOpen(true)

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-6">
      <PageHeader
        title="Team"
        description={`People who can work in ${workspace.name} and what each of them can do.`}
        actions={
          isAdmin && (
            <Button icon={<UserPlus className="size-4" aria-hidden="true" />} onClick={openInvite}>
              Invite teammate
            </Button>
          )
        }
      />

      {isAdmin ? (
        <Tabs
          label="Team"
          value={tab}
          onValueChange={setTab}
          items={[
            { value: 'members', label: 'Members' },
            { value: 'invitations', label: 'Invitations', count: invitations.isSuccess ? invitations.items.length : undefined },
          ]}
        >
          {tab === 'members' ? <MembersPanel /> : <InvitationsPanel query={invitations} onInvite={openInvite} />}
        </Tabs>
      ) : (
        <MembersPanel />
      )}

      <SectionCard id="team-roles" title="Roles" description="Roles apply to this workspace only.">
        <dl className="grid gap-x-6 gap-y-3 sm:grid-cols-2">
          {roleOrder.map((role) => (
            <div key={role}>
              <dt className="text-sm font-medium text-ink">{roleLabels[role]}</dt>
              <dd className="text-[13px] text-muted">{roleDescriptions[role]}</dd>
            </div>
          ))}
        </dl>
      </SectionCard>

      {isAdmin && (
        <InviteDialog
          open={inviteOpen}
          onOpenChange={setInviteOpen}
          onInvited={() => setTab('invitations')}
        />
      )}
    </div>
  )
}
