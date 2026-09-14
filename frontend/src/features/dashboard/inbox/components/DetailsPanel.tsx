import { useMemo } from 'react'
import { Keyboard } from 'lucide-react'
import { Avatar } from '../../../../components/app/Avatar'
import { Button } from '../../../../components/app/Button'
import { Combobox } from '../../../../components/app/Combobox'
import { StatusBadge } from '../../../../components/app/StatusBadge'
import { roleLabels } from '../../../../lib/roles'
import { useWorkspace } from '../../../../lib/workspace'
import { useMe } from '../../auth/session'
import type { Conversation } from '../api'
import { useConversationActions, useMembers } from '../hooks/conversations'
import { contactName, formatDuration, formatFullTime, formatPhone, windowRemainingMs } from '../utils'

const UNASSIGNED = '__unassigned__'

function SectionTitle({ children }: { children: string }) {
  return <h3 className="mb-2 font-mono text-[10.5px] uppercase tracking-[0.14em] text-muted">{children}</h3>
}

type DetailsPanelProps = {
  conversation: Conversation
  now: number
  onShowShortcuts: () => void
}

/** Contact and conversation details with assignment. */
export function DetailsPanel({ conversation, now, onShowShortcuts }: DetailsPanelProps) {
  const { can, timeZone } = useWorkspace()
  const canAct = can('agent')
  const me = useMe()
  const members = useMembers(canAct)
  const actions = useConversationActions(conversation.id)
  const name = contactName(conversation.contact)
  const remaining = windowRemainingMs(conversation, now)

  const options = useMemo(
    () => [
      { value: UNASSIGNED, label: 'Unassigned' },
      ...(members.data ?? []).map((member) => ({
        value: member.user.id,
        label: member.user.full_name || member.user.email,
        description: `${roleLabels[member.role ?? 'agent']} · ${member.user.email}`,
      })),
    ],
    [members.data],
  )

  const assignee = conversation.assignee
  const assign = (userId: string | null) => {
    if ((assignee?.id ?? null) === userId) return
    actions.mutate({ action: 'assign', assigneeId: userId })
  }

  return (
    <div className="flex flex-col divide-y divide-line-2 text-sm">
      <section aria-label="Contact" className="flex flex-col items-center px-4 py-5 text-center">
        <Avatar name={name} size="lg" />
        <p className="mt-2 font-display text-base font-semibold tracking-[-0.01em] text-ink">{name}</p>
        <p className="font-mono text-[12px] text-muted">{formatPhone(conversation.contact.phone_e164)}</p>
        <StatusBadge status={conversation.contact.marketing_opt_in_status} className="mt-2" />
      </section>

      <section className="px-4 py-4">
        <SectionTitle>Assignment</SectionTitle>
        {canAct ? (
          <div className="flex flex-col gap-1.5">
            <Combobox
              aria-label="Assignee"
              options={options}
              value={assignee?.id ?? UNASSIGNED}
              onChange={(value) => assign(!value || value === UNASSIGNED ? null : value)}
              loading={members.isLoading || actions.isPending}
              disabled={actions.isPending}
              selectedLabels={assignee ? { [assignee.id]: assignee.full_name || assignee.email } : undefined}
              placeholder="Search members"
            />
            {me.data && assignee?.id !== me.data.id && (
              <Button variant="link" className="self-start text-[13px]" onClick={() => assign(me.data.id)} disabled={actions.isPending}>
                Assign to me
              </Button>
            )}
          </div>
        ) : (
          <p className="text-ink">{assignee?.full_name ?? 'Unassigned'}</p>
        )}
      </section>

      <section className="px-4 py-4">
        <SectionTitle>Conversation</SectionTitle>
        <dl className="grid grid-cols-[minmax(0,6.5rem)_minmax(0,1fr)] gap-x-3 gap-y-2.5 text-[13px]">
          <dt className="text-muted">Status</dt>
          <dd>
            <StatusBadge status={conversation.status} />
          </dd>
          <dt className="text-muted">Service window</dt>
          <dd className="text-ink">
            {remaining > 0 ? `Open · ${formatDuration(remaining)} left` : 'Closed'}
            <span className="block text-[12px] text-muted">
              {remaining > 0 && conversation.service_window_expires_at
                ? `Closes ${formatFullTime(conversation.service_window_expires_at, timeZone)}`
                : conversation.last_inbound_at
                  ? `Customer last wrote ${formatFullTime(conversation.last_inbound_at, timeZone)}`
                  : "The customer hasn't written yet"}
            </span>
          </dd>
          <dt className="text-muted">Business number</dt>
          <dd className="min-w-0 text-ink">
            {conversation.phone_number.verified_name}
            <span className="block font-mono text-[12px] text-muted">{conversation.phone_number.display_phone_number}</span>
          </dd>
          <dt className="text-muted">Started</dt>
          <dd className="text-ink">{formatFullTime(conversation.created_at, timeZone)}</dd>
        </dl>
      </section>

      <section className="flex flex-col gap-2 px-4 py-4 text-[12.5px] text-muted">
        <p>
          Outside the 24-hour customer service window, only templates approved by Meta can be sent. Meta may also cap how many business-initiated
          conversations this number can start.
        </p>
        <Button variant="link" className="self-start text-[13px]" icon={<Keyboard className="size-4" aria-hidden="true" />} onClick={onShowShortcuts}>
          Keyboard shortcuts
        </Button>
      </section>
    </div>
  )
}
