import { cn } from '../../lib/cn'
import { initials } from './initials'

const palette = ['bg-accent-soft text-accent-2', 'bg-amber-soft text-amber', 'bg-signal-soft text-signal', 'bg-[#e3ecf5] text-[#1f5a8c]', 'bg-paper-2 text-ink-2']

const sizes = { sm: 'size-7 text-[11px]', md: 'size-9 text-[13px]', lg: 'size-12 text-base' } as const


function hash(value: string) {
  let h = 0
  for (let i = 0; i < value.length; i++) h = (h * 31 + value.charCodeAt(i)) | 0
  return Math.abs(h)
}

type AvatarProps = {
  name: string
  size?: keyof typeof sizes
  className?: string
  /** Decorative when the name is shown next to it (default). */
  decorative?: boolean
}

export function Avatar({ name, size = 'md', className, decorative = true }: AvatarProps) {
  return (
    <span
      role={decorative ? undefined : 'img'}
      aria-label={decorative ? undefined : name}
      aria-hidden={decorative || undefined}
      className={cn(
        'inline-grid shrink-0 place-items-center rounded-full font-medium',
        palette[hash(name) % palette.length],
        sizes[size],
        className,
      )}
    >
      {initials(name)}
    </span>
  )
}
