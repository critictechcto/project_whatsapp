import { CircleAlert } from 'lucide-react'
import type { TemplateCategory } from '../../../../api/types'
import { StatusBadge } from '../../../../components/app/StatusBadge'
import { cn } from '../../../../lib/cn'
import { categoryLabels, rejectionInfo } from '../lib/constants'

export function CategoryBadge({ category }: { category: TemplateCategory }) {
  return (
    <span className="inline-flex h-6 items-center whitespace-nowrap rounded-md border border-line bg-paper px-2 font-mono text-[11px] uppercase tracking-[0.08em] text-ink-2">
      {categoryLabels[category]}
    </span>
  )
}

export function QualityBadge({ score }: { score: string }) {
  if (!score || score === 'UNKNOWN') return <span className="text-[13px] text-muted">Not rated</span>
  return <StatusBadge status={score} />
}

/** Meta's rejection reason with a plain-language explanation. `compact` fits a table row. */
export function RejectionNotice({ reason, compact = false, className }: { reason: string; compact?: boolean; className?: string }) {
  const info = rejectionInfo(reason)
  if (compact) {
    return (
      <p className={cn('text-[12.5px] leading-snug text-signal', className)}>
        <span className="font-medium">{info.label}.</span> <span className="text-muted">{info.explanation}</span>
      </p>
    )
  }
  return (
    <div className={cn('flex gap-3 rounded-xl border border-signal/25 bg-signal-soft/50 p-4', className)}>
      <CircleAlert className="mt-0.5 size-5 shrink-0 text-signal" aria-hidden="true" />
      <div className="min-w-0 text-sm">
        <p className="font-medium text-signal">Rejected by Meta: {info.label}</p>
        <p className="mt-1 text-ink-2">{info.explanation}</p>
        {reason && <p className="mt-2 font-mono text-[11px] uppercase tracking-[0.08em] text-muted">Reason code: {reason}</p>}
      </div>
    </div>
  )
}
