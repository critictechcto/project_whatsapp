import { ExternalLink, LogOut } from 'lucide-react'
import { useNavigate } from 'react-router'
import { Avatar, DropdownMenu } from '../../../components/app'
import { site } from '../../../config/site'
import { useLogout, useMe } from '../auth/session'

export function UserMenu() {
  const me = useMe()
  const logout = useLogout()
  const navigate = useNavigate()
  const name = me.data?.full_name || me.data?.email || 'Account'

  return (
    <DropdownMenu
      placement="top-start"
      triggerVariant="ghost"
      triggerClassName="h-auto w-full justify-start gap-2.5 px-2 py-2 text-left"
      menuClassName="w-60"
      header={
        <div className="border-b border-line-2 px-2.5 pb-2 pt-1.5">
          <p className="truncate text-sm font-medium text-ink">{name}</p>
          <p className="truncate text-[12.5px] text-muted">{me.data?.email}</p>
        </div>
      }
      trigger={
        <>
          <Avatar name={name} size="sm" />
          <span className="min-w-0 flex-1 truncate text-sm text-ink">
            <span className="sr-only">Account menu for </span>
            {name}
          </span>
        </>
      }
      items={[
        {
          id: 'help',
          label: 'Contact support',
          icon: <ExternalLink />,
          onSelect: () => window.open(`mailto:${site.email.support}`, '_blank', 'noopener'),
        },
        { type: 'separator', id: 'sep' },
        {
          id: 'logout',
          label: 'Log out',
          icon: <LogOut />,
          onSelect: () => {
            void logout().then(() => navigate('/app/login', { replace: true }))
          },
        },
      ]}
    />
  )
}
