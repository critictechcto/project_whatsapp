import { cn } from '../../lib/cn'
import { BrandLoader } from './BrandLoader'

const sizes = { sm: 'size-4', md: 'size-5', lg: 'size-8' } as const

type SpinnerProps = {
  size?: keyof typeof sizes
  /** Accessible label; `null` hides the spinner from assistive tech (e.g. inside a busy button). */
  label?: string | null
  className?: string
}

export function Spinner({ size = 'md', label = 'Loading', className }: SpinnerProps) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      role={label ? 'status' : undefined}
      aria-label={label ?? undefined}
      aria-hidden={label ? undefined : true}
      className={cn('animate-spin text-current', sizes[size], className)}
    >
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeOpacity="0.2" strokeWidth="2.5" />
      <path d="M21 12a9 9 0 0 0-9-9" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" />
    </svg>
  )
}

export function Skeleton({ className }: { className?: string }) {
  return <span aria-hidden="true" className={cn('block animate-pulse rounded-md bg-line-2', className)} />
}

/** Loading state for a page or panel: the animated wordmark, centered. */
export function PageSpinner({ label = 'Loading' }: { label?: string }) {
  return (
    <div className="grid min-h-[40vh] place-items-center">
      <BrandLoader label={label} />
    </div>
  )
}
