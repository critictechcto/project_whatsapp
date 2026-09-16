import type { ReactNode } from 'react'
import { cn } from '../../lib/cn'

// Readable long-form text for the static pages, styled with the landing page's tokens.

export function ProseSection({ id, title, children }: { id: string; title: string; children: ReactNode }) {
  return (
    <section id={id} aria-labelledby={`${id}-title`} className="border-t border-line py-9 first:border-t-0 first:pt-0">
      <h2
        id={`${id}-title`}
        className="font-display text-[1.45rem] font-semibold leading-tight tracking-[-0.02em] md:text-[1.6rem]"
      >
        {title}
      </h2>
      <div className="mt-4 space-y-4 text-[16px] leading-[1.7] text-ink-2">{children}</div>
    </section>
  )
}

export function Subheading({ children }: { children: ReactNode }) {
  return <h3 className="pt-2 text-[16px] font-semibold text-ink">{children}</h3>
}

export function BulletList({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <ul
      className={cn(
        'space-y-2 pl-5 [&>li]:relative [&>li]:before:absolute [&>li]:before:-left-4 [&>li]:before:top-[0.8em] [&>li]:before:h-px [&>li]:before:w-2 [&>li]:before:bg-accent',
        className,
      )}
    >
      {children}
    </ul>
  )
}

export function TextLink({ href, children, external }: { href: string; children: ReactNode; external?: boolean }) {
  return (
    <a
      href={href}
      className="text-accent-2 underline decoration-accent/40 underline-offset-[3px] hover:decoration-accent-2"
      {...(external ? { target: '_blank', rel: 'noreferrer' } : {})}
    >
      {children}
    </a>
  )
}
