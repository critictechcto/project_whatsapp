import { useState, type ReactNode } from 'react'
import { Menu } from 'lucide-react'
import { NavLink } from 'react-router'
import { Drawer } from '../../../components/app'
import { cn } from '../../../lib/cn'
import { site } from '../../../config/site'
import { useWorkspace } from '../../../lib/workspace'
import { visibleNav } from '../registry'
import { EmailVerificationBanner } from './EmailVerificationBanner'
import { UserMenu } from './UserMenu'
import { WorkspaceSwitcher } from './WorkspaceSwitcher'

function SidebarNav({ onNavigate }: { onNavigate?: () => void }) {
  const { workspaceId, role } = useWorkspace()
  const groups = visibleNav(role)

  return (
    <nav aria-label="Workspace" className="flex flex-col gap-5">
      {groups.map((group) => (
        <div key={group.id}>
          <p className="px-2.5 pb-1.5 font-mono text-[10.5px] uppercase tracking-[0.14em] text-muted">{group.label}</p>
          <ul className="flex flex-col gap-0.5">
            {group.items.map((item) => {
              const Icon = item.icon
              return (
                <li key={item.id}>
                  <NavLink
                    to={item.to ? `/app/w/${workspaceId}/${item.to}` : `/app/w/${workspaceId}`}
                    end={item.end}
                    onClick={onNavigate}
                    className={({ isActive }) =>
                      cn(
                        'flex h-9 items-center gap-2.5 rounded-md px-2.5 text-sm transition-colors',
                        isActive ? 'bg-ink/[0.06] font-medium text-ink' : 'text-ink-2 hover:bg-ink/[0.04] hover:text-ink',
                      )
                    }
                  >
                    <Icon className="size-4 shrink-0 text-muted" aria-hidden="true" />
                    {item.label}
                  </NavLink>
                </li>
              )
            })}
          </ul>
        </div>
      ))}
    </nav>
  )
}

function SidebarContent({ onNavigate }: { onNavigate?: () => void }) {
  return (
    <div className="flex h-full flex-col gap-5">
      <WorkspaceSwitcher onNavigate={onNavigate} />
      <div className="flex-1 overflow-y-auto">
        <SidebarNav onNavigate={onNavigate} />
      </div>
      <div className="border-t border-line-2 pt-2">
        <UserMenu />
      </div>
    </div>
  )
}

/** Responsive shell: fixed sidebar on large screens, top bar + drawer below. */
export function AppShell({ children }: { children: ReactNode }) {
  const [menuOpen, setMenuOpen] = useState(false)
  const { workspace } = useWorkspace()

  return (
    <div className="flex min-h-dvh bg-paper">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:fixed focus:left-3 focus:top-3 focus:z-[80] focus:rounded-md focus:bg-card focus:px-3 focus:py-2 focus:text-sm"
      >
        Skip to content
      </a>

      <aside className="hidden w-64 shrink-0 border-r border-line bg-paper px-3 py-4 lg:sticky lg:top-0 lg:block lg:h-[calc(100dvh-var(--demo-banner-height,0px))]">
        <p className="mb-4 px-2.5 font-display text-lg font-semibold tracking-[-0.02em] text-ink">{site.name}</p>
        <SidebarContent />
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex h-14 items-center gap-3 border-b border-line bg-paper/95 px-4 backdrop-blur lg:hidden">
          <button
            type="button"
            onClick={() => setMenuOpen(true)}
            aria-label="Open navigation"
            className="touch-target grid size-9 place-items-center rounded-md text-ink hover:bg-ink/5"
          >
            <Menu className="size-5" aria-hidden="true" />
          </button>
          <span className="min-w-0 truncate text-sm font-medium text-ink">{workspace.name}</span>
        </header>

        <EmailVerificationBanner />

        <main id="main" tabIndex={-1} className="mx-auto w-full max-w-6xl flex-1 px-4 py-6 focus:outline-none sm:px-8 sm:py-8">
          {children}
        </main>
      </div>

      <Drawer open={menuOpen} onOpenChange={setMenuOpen} side="left" width="max-w-72" title={site.name}>
        <SidebarContent onNavigate={() => setMenuOpen(false)} />
      </Drawer>
    </div>
  )
}
