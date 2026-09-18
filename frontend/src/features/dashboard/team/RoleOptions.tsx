import { cn } from '../../../lib/cn'
import { roleLabels, type Role } from '../../../lib/roles'
import { assignableRoles, roleDescriptions } from './roles'

type RoleOptionsProps = {
  /** Radio group name; unique per dialog. */
  name: string
  value: Role
  /** The role the member or invitation has now, marked "Current". */
  current: Role
  onChange: (role: Role) => void
  disabled?: boolean
}

/** Radio cards for the roles an admin can hand out, each with a plain-words description. */
export function RoleOptions({ name, value, current, onChange, disabled }: RoleOptionsProps) {
  return (
    <fieldset className="flex flex-col gap-2" disabled={disabled}>
      <legend className="sr-only">Role</legend>
      {assignableRoles.map((option) => (
        <label
          key={option}
          className={cn(
            'flex cursor-pointer items-start gap-3 rounded-lg border px-3 py-2.5 transition-colors',
            value === option ? 'border-accent bg-accent-soft/40' : 'border-line hover:border-ink/20',
          )}
        >
          <input
            type="radio"
            name={name}
            value={option}
            checked={value === option}
            onChange={() => onChange(option)}
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
  )
}
