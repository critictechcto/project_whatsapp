import type { ReactNode } from 'react'
import { NavLink } from 'react-router'
import { PageHeader } from '../../../../components/app'
import { cn } from '../../../../lib/cn'
import { useWorkspace } from '../../../../lib/workspace'

export function StoreNav() {
  const { workspaceId } = useWorkspace()
  const base = `/app/w/${workspaceId}/store`
  const items = [
    { to: base, label: 'Setup', end: true },
    { to: `${base}/settings`, label: 'Settings', end: false },
    { to: `${base}/payments`, label: 'Payments', end: false },
    { to: `${base}/alerts`, label: 'Alerts', end: false },
    { to: `${base}/notifications`, label: 'Notifications', end: false },
  ]

  return (
    <nav aria-label="Store sections" className="flex gap-1 overflow-x-auto border-b border-line">
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

/** The Store area's page frame: one `Store` heading, the section tabs, then the section. */
export function StoreFrame({ description, actions, children }: { description: ReactNode; actions?: ReactNode; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-6">
      <PageHeader title="Store" description={description} actions={actions} />
      <StoreNav />
      {children}
    </div>
  )
}
