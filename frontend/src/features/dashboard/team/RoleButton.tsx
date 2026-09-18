import { ChevronDown } from 'lucide-react'
import { roleLabels, type Role } from '../../../lib/roles'
import { RoleBadge } from './RoleBadge'

type RoleButtonProps = {
  role: Role
  /** Who the role belongs to: a member's name or an invited email. */
  subject: string
  onClick: () => void
}

/** The role badge as a button that opens the change-role dialog (shown when the role can be changed). */
export function RoleButton({ role, subject, onClick }: RoleButtonProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={`Change role for ${subject}, currently ${roleLabels[role]}`}
      title="Change role"
      className="touch-target group -mx-1 inline-flex items-center gap-1 rounded-full px-1 py-0.5 text-muted transition-colors hover:bg-ink/5 hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/30"
    >
      <RoleBadge role={role} />
      <ChevronDown className="size-3.5 transition-transform group-hover:translate-y-px" aria-hidden="true" />
    </button>
  )
}
