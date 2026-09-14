import { NavLink } from 'react-router'
import { cn } from '../../../../lib/cn'
import { useWorkspace } from '../../../../lib/workspace'

export function AutomationsNav() {
  const { workspaceId } = useWorkspace()
  const base = `/app/w/${workspaceId}/automations`
  const items = [
    { to: base, label: 'Rules', end: true },
    { to: `${base}/business-hours`, label: 'Business hours', end: false },
    { to: `${base}/runs`, label: 'Run log', end: false },
  ]

  return (
    <nav aria-label="Automation sections" className="flex gap-1 overflow-x-auto border-b border-line">
      {items.map((item) => (
        <NavLink
          key={item.to}
          to={item.to}
          end={item.end}
          className={({ isActive }) =>
            cn(
              'relative inline-flex h-10 shrink-0 items-center px-3 text-sm font-medium transition-colors',
              'after:absolute after:inset-x-2 after:-bottom-px after:h-0.5',
              isActive ? 'text-ink after:bg-ink' : 'text-muted hover:text-ink',
            )
          }
        >
          {item.label}
        </NavLink>
      ))}
    </nav>
  )
}
