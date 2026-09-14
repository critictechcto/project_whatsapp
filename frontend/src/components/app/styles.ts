import { cn } from '../../lib/cn'

export type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger' | 'link'
export type ButtonSize = 'sm' | 'md' | 'lg' | 'icon' | 'icon-sm'

const buttonVariants: Record<ButtonVariant, string> = {
  primary: 'bg-ink text-paper hover:bg-ink-2 disabled:bg-ink/40',
  secondary: 'border border-line bg-card text-ink hover:border-ink/40 disabled:text-muted',
  ghost: 'text-ink hover:bg-ink/5 disabled:text-muted',
  danger: 'bg-signal text-white hover:bg-[#8a3a19] disabled:bg-signal/40',
  link: 'text-accent-2 underline-offset-4 hover:underline disabled:text-muted',
}

const buttonSizes: Record<ButtonSize, string> = {
  sm: 'h-8 gap-1.5 px-3 text-[13px]',
  md: 'h-10 gap-2 px-4 text-sm',
  lg: 'h-11 gap-2 px-5 text-[15px]',
  icon: 'size-10',
  'icon-sm': 'size-8',
}

/** Button classes, also for router `<Link>`s that should look like buttons. */
export function buttonClasses(variant: ButtonVariant = 'primary', size: ButtonSize = 'md', className?: string) {
  return cn(
    'inline-flex shrink-0 items-center justify-center whitespace-nowrap rounded-md font-medium transition-colors disabled:cursor-not-allowed',
    variant !== 'link' && buttonSizes[size],
    buttonVariants[variant],
    className,
  )
}

/** Shared look of text inputs, textareas and selects. */
export const controlClasses = cn(
  'w-full rounded-md border border-line bg-card px-3 text-sm text-ink placeholder:text-muted/80',
  'transition-colors hover:border-ink/30 focus-visible:border-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/25',
  'disabled:cursor-not-allowed disabled:bg-paper-2 disabled:text-muted',
  'aria-[invalid=true]:border-signal aria-[invalid=true]:focus-visible:ring-signal/25',
)

/** Floating surfaces: menus, popovers, listboxes. */
export const popoverClasses =
  'z-50 rounded-lg border border-line bg-card shadow-[0_1px_0_rgba(16,39,31,0.04),0_18px_40px_-18px_rgba(16,39,31,0.35)]'
