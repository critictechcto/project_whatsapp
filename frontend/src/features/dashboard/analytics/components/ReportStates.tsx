import { CircleAlert, Download } from 'lucide-react'
import { useId, useState, type ReactNode } from 'react'
import { errorMessage } from '../../../../api/errors'
import { Button, Skeleton, useToast } from '../../../../components/app'
import { cn } from '../../../../lib/cn'
import { downloadReportCsv, type AnalyticsReport } from '../api'
import type { DateRange } from '../range'

/** Error box with a retry button, announced to screen readers. */
export function ReportError({ title, error, onRetry }: { title: string; error: unknown; onRetry: () => void }) {
  return (
    <div role="alert" className="flex items-start gap-2.5 rounded-xl border border-signal/25 bg-signal-soft/60 px-4 py-3 text-sm text-signal">
      <CircleAlert className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
      <div className="min-w-0 flex-1">
        <p className="font-medium">{title}</p>
        <p className="mt-0.5 text-ink-2">{errorMessage(error)}</p>
        <Button variant="secondary" size="sm" className="mt-2" onClick={onRetry}>
          Try again
        </Button>
      </div>
    </div>
  )
}

/** Placeholder blocks while a report loads. */
export function ReportSkeleton({ blocks = 2 }: { blocks?: number }) {
  return (
    <div className="flex flex-col gap-4" aria-busy="true" aria-label="Loading report">
      {Array.from({ length: blocks }, (_, i) => (
        <div key={i} className="rounded-xl border border-line bg-card p-5">
          <Skeleton className="h-4 w-40" />
          <Skeleton className="mt-4 h-40 w-full" />
        </div>
      ))}
    </div>
  )
}

/** A titled block inside a report tab. */
export function Panel({
  title,
  description,
  actions,
  children,
  className,
}: {
  title: string
  description?: ReactNode
  actions?: ReactNode
  children: ReactNode
  className?: string
}) {
  const headingId = useId()
  return (
    <section aria-labelledby={headingId} className={cn('flex min-w-0 flex-col gap-3', className)}>
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div className="min-w-0">
          <h3 id={headingId} className="font-display text-base font-semibold tracking-[-0.01em] text-ink">
            {title}
          </h3>
          {description && <p className="mt-0.5 text-[13px] text-muted">{description}</p>}
        </div>
        {actions}
      </div>
      {children}
    </section>
  )
}

/** Heading row of a report tab with its CSV export. */
export function ReportHeader({ title, description, report, range }: { title: string; description: ReactNode; report: AnalyticsReport; range: DateRange }) {
  return (
    <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
      <div className="min-w-0">
        <h2 className="font-display text-lg font-semibold tracking-[-0.01em] text-ink">{title}</h2>
        <p className="mt-0.5 max-w-2xl text-sm text-muted">{description}</p>
      </div>
      <ExportButton report={report} range={range} label={title} />
    </div>
  )
}

/** Downloads the report as CSV through the authenticated client. */
export function ExportButton({ report, range, label }: { report: AnalyticsReport; range: DateRange; label: string }) {
  const [busy, setBusy] = useState(false)
  const { toast } = useToast()

  async function onExport() {
    setBusy(true)
    try {
      await downloadReportCsv(report, range)
    } catch (error) {
      toast({ title: "Couldn't export the CSV", description: errorMessage(error), tone: 'error' })
    } finally {
      setBusy(false)
    }
  }

  return (
    <Button
      variant="secondary"
      size="sm"
      className="h-10 self-start sm:h-8 sm:self-auto"
      icon={<Download className="size-4" aria-hidden="true" />}
      loading={busy}
      onClick={() => void onExport()}
      aria-label={`Export ${label.toLowerCase()} as CSV`}
    >
      Export CSV
    </Button>
  )
}

/** Horizontal share bar for breakdown rows. */
export function ShareBar({ value, max, tone = 'accent' }: { value: number; max: number; tone?: 'accent' | 'signal' }) {
  const width = max > 0 ? Math.max(2, Math.round((value / max) * 100)) : 0
  return (
    <span aria-hidden="true" className="block h-1.5 w-full overflow-hidden rounded-full bg-line-2">
      <span className={cn('block h-full rounded-full', tone === 'accent' ? 'bg-accent' : 'bg-signal')} style={{ width: `${width}%` }} />
    </span>
  )
}
