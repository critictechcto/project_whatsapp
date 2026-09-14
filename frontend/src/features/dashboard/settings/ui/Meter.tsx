import { cn } from '../../../../lib/cn'
import { formatNumber } from '../../../../lib/format'

type MeterProps = {
  label: string
  used: number
  /** `null` means unlimited. */
  limit: number | null
  className?: string
}

/** Usage against a plan limit. Amber from 80%, red at the limit. Candidate for `components/app`. */
export function Meter({ label, used, limit, className }: MeterProps) {
  const unlimited = limit === null
  const ratio = unlimited || limit === 0 ? 0 : Math.min(used / limit, 1)
  const percent = Math.round(ratio * 100)
  const tone = unlimited ? 'bg-accent' : used >= (limit ?? 0) ? 'bg-signal' : ratio >= 0.8 ? 'bg-amber' : 'bg-accent'
  const valueText = unlimited ? `${formatNumber(used)} used, unlimited` : `${formatNumber(used)} of ${formatNumber(limit)} used`

  return (
    <div className={cn('flex flex-col gap-1.5', className)}>
      <div className="flex items-baseline justify-between gap-3 text-sm">
        <span className="text-ink">{label}</span>
        <span className="font-mono text-[12.5px] text-muted">
          {formatNumber(used)}
          <span aria-hidden="true"> / </span>
          <span className="sr-only"> of </span>
          {unlimited ? 'Unlimited' : formatNumber(limit)}
        </span>
      </div>
      <div
        role="meter"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={unlimited ? used : (limit ?? 0)}
        aria-valuenow={used}
        aria-valuetext={valueText}
        className="h-1.5 overflow-hidden rounded-full bg-line-2"
      >
        <div className={cn('h-full rounded-full transition-[width]', tone)} style={{ width: unlimited ? '0%' : `${percent}%` }} />
      </div>
    </div>
  )
}
