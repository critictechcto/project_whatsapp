import { Building2, ChevronRight, CreditCard, Smartphone, UserRound, UsersRound, type LucideIcon } from 'lucide-react'
import { Link } from 'react-router'
import { PageHeader } from '../../../components/app'
import { timeZoneName } from '../../../lib/datetime'
import { type Role } from '../../../lib/roles'
import { useWorkspace } from '../../../lib/workspace'
import { RoleBadge } from '../team/RoleBadge'

type SettingsLink = { to: string; icon: LucideIcon; title: string; description: string; minRole?: Role }

const links: readonly SettingsLink[] = [
  { to: 'settings/profile', icon: UserRound, title: 'Your profile', description: 'Your name, password and signing out.' },
  { to: 'settings/workspace', icon: Building2, title: 'Workspace', description: 'Workspace name, time zone and deletion.' },
  { to: 'team', icon: UsersRound, title: 'Team', description: 'Members, roles and invitations.' },
  { to: 'whatsapp', icon: Smartphone, title: 'WhatsApp', description: 'Connected numbers, quality rating and messaging limits.' },
  { to: 'billing', icon: CreditCard, title: 'Billing', description: 'Plan, usage, GST details and invoices.', minRole: 'admin' },
]

export function SettingsPage() {
  const { workspace, workspaceId, role, timeZone, can } = useWorkspace()

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-6">
      <PageHeader title="Settings" description="Manage your profile and how this workspace is set up." />

      <dl className="grid gap-4 rounded-xl border border-line bg-card px-5 py-4 text-sm sm:grid-cols-3">
        <div className="min-w-0">
          <dt className="text-[12.5px] text-muted">Workspace</dt>
          <dd className="truncate font-medium text-ink">{workspace.name}</dd>
        </div>
        <div>
          <dt className="text-[12.5px] text-muted">Your role</dt>
          <dd className="mt-0.5">
            <RoleBadge role={role} />
          </dd>
        </div>
        <div className="min-w-0">
          <dt className="text-[12.5px] text-muted">Time zone</dt>
          <dd className="truncate text-ink">
            {timeZone.replace(/_/g, ' ')} <span className="text-muted">({timeZoneName(timeZone)})</span>
          </dd>
        </div>
      </dl>

      <ul className="grid gap-3 sm:grid-cols-2">
        {links
          .filter((link) => can(link.minRole ?? 'viewer'))
          .map(({ to, icon: Icon, title, description }) => (
            <li key={to}>
              <Link
                to={`/app/w/${workspaceId}/${to}`}
                className="group flex h-full items-start gap-3 rounded-xl border border-line bg-card p-4 transition-colors hover:border-ink/30 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/30"
              >
                <span aria-hidden="true" className="grid size-9 shrink-0 place-items-center rounded-lg border border-line-2 bg-paper text-muted">
                  <Icon className="size-4" />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block font-medium text-ink">{title}</span>
                  <span className="mt-0.5 block text-[13px] text-muted">{description}</span>
                </span>
                <ChevronRight className="mt-2 size-4 shrink-0 text-muted transition-transform group-hover:translate-x-0.5" aria-hidden="true" />
              </Link>
            </li>
          ))}
      </ul>
    </div>
  )
}
