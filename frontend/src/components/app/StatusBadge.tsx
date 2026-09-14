import type { ReactNode } from 'react'
import { cn } from '../../lib/cn'
import { statusInfo, type Tone } from './status'

const tones: Record<Tone, string> = {
  neutral: 'bg-paper-2 text-muted ring-line',
  green: 'bg-accent-soft text-accent-2 ring-accent/20',
  amber: 'bg-amber-soft text-amber ring-amber/20',
  red: 'bg-signal-soft text-signal ring-signal/20',
  blue: 'bg-[#e3ecf5] text-[#1f5a8c] ring-[#1f5a8c]/20',
}

const dots: Record<Tone, string> = {
  neutral: 'bg-muted/60',
  green: 'bg-accent',
  amber: 'bg-amber',
  red: 'bg-signal',
  blue: 'bg-[#2f7fc1]',
}

type StatusBadgeProps =
  | { status: string; tone?: Tone; children?: ReactNode; className?: string }
  | { status?: undefined; tone: Tone; children: ReactNode; className?: string }

/**
 * `<StatusBadge status="APPROVED" />` resolves label and tone from `status.ts`;
 * `<StatusBadge tone="amber">Custom</StatusBadge>` for anything else.
 */
export function StatusBadge({ status, tone, children, className }: StatusBadgeProps) {
  const info = status ? statusInfo(status) : null
  const resolvedTone = tone ?? info?.tone ?? 'neutral'
  return (
    <span
      className={cn(
        'inline-flex h-6 items-center gap-1.5 whitespace-nowrap rounded-full px-2 text-[12px] font-medium ring-1 ring-inset',
        tones[resolvedTone],
        className,
      )}
    >
      <span aria-hidden="true" className={cn('size-1.5 rounded-full', dots[resolvedTone])} />
      {children ?? info?.label}
    </span>
  )
}
