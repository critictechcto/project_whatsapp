import type { ReactNode } from 'react'
import { Link } from 'react-router'
import { site } from '../../../config/site'

type AuthLayoutProps = {
  title: string
  description?: ReactNode
  children: ReactNode
  footer?: ReactNode
}

export function AuthLayout({ title, description, children, footer }: AuthLayoutProps) {
  return (
    <div className="flex min-h-dvh flex-col bg-paper">
      <header className="px-5 py-5 sm:px-8">
        <a href={import.meta.env.BASE_URL} className="font-display text-lg font-semibold tracking-[-0.02em] text-ink">
          {site.name}
        </a>
      </header>
      <main className="flex flex-1 items-start justify-center px-4 pb-16 pt-6 sm:pt-14">
        <div className="w-full max-w-sm">
          <h1 className="font-display text-2xl font-semibold tracking-[-0.02em] text-ink">{title}</h1>
          {description && <p className="mt-1.5 text-sm text-muted">{description}</p>}
          <div className="mt-7 rounded-xl border border-line bg-card p-5 sm:p-6">{children}</div>
          {footer && <div className="mt-5 text-center text-sm text-muted">{footer}</div>}
        </div>
      </main>
    </div>
  )
}

export function AuthLink({ to, children }: { to: string; children: ReactNode }) {
  return (
    <Link to={to} className="font-medium text-accent-2 underline-offset-2 hover:underline">
      {children}
    </Link>
  )
}
