import type { ReactNode } from 'react'
import { cn } from '../../lib/cn'

type Tone = 'neutral' | 'green' | 'amber' | 'red' | 'ink'

const tones: Record<Tone, string> = {
  neutral: 'border-line bg-paper-2 text-muted',
  green: 'border-accent/20 bg-accent-soft text-accent-2',
  amber: 'border-amber/20 bg-amber-soft text-amber',
  red: 'border-signal/20 bg-signal-soft text-signal',
  ink: 'border-ink bg-ink text-paper',
}

export function Badge({ tone = 'neutral', className, children }: { tone?: Tone; className?: string; children: ReactNode }) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 whitespace-nowrap rounded border px-1.5 py-0.5 text-[10.5px] font-medium',
        tones[tone],
        className,
      )}
    >
      {children}
    </span>
  )
}
