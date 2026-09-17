import { ArrowDownRight, ArrowUpRight } from 'lucide-react'
import { Skeleton } from '../../../../components/app'
import { cn } from '../../../../lib/cn'
import { buildKpis, type Kpi } from '../kpis'
import type { Schemas } from '../../../../api/types'

type AnalyticsOverview = Schemas['AnalyticsOverview']

function DeltaLine({ kpi }: { kpi: Kpi }) {
  const { direction, text } = kpi.delta
  if (text === null) {
    return <p className="text-[12px] text-muted">Previous period: {kpi.previous}</p>
  }
  if (direction === 'flat') {
    return <p className="text-[12px] text-muted">No change vs previous period</p>
  }
  const good = kpi.upIsBad ? direction === 'down' : direction === 'up'
  const Icon = direction === 'up' ? ArrowUpRight : ArrowDownRight
  return (
    <p className={cn('flex items-center gap-1 text-[12px] font-medium', good ? 'text-accent-2' : 'text-signal')}>
      <Icon className="size-3.5 shrink-0" aria-hidden="true" />
      <span>
        <span className="sr-only">{direction === 'up' ? 'Up' : 'Down'} </span>
        {text}
        <span className="font-normal text-muted"> vs previous period</span>
      </span>
    </p>
  )
}

/** Overview numbers with the change vs the previous period of the same length. */
export function KpiCards({ overview, loading }: { overview?: Pick<AnalyticsOverview, 'current' | 'previous'>; loading: boolean }) {
  if (loading || !overview) {
    return (
      <div aria-busy="true" aria-label="Loading key numbers" className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-4">
        {Array.from({ length: 8 }, (_, i) => (
          <div key={i} className="rounded-xl border border-line bg-card px-4 py-3">
            <Skeleton className="h-3 w-24" />
            <Skeleton className="mt-3 h-7 w-20" />
            <Skeleton className="mt-2 h-3 w-28" />
          </div>
        ))}
      </div>
    )
  }

  return (
    <section aria-label="Key numbers">
      <dl className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-4">
        {buildKpis(overview).map((kpi) => (
          <div key={kpi.id} className="flex min-w-0 flex-col gap-1 rounded-xl border border-line bg-card px-4 py-3">
            <dt className="text-[12px] text-muted">{kpi.label}</dt>
            <dd className="flex min-w-0 flex-col gap-1">
              <span className="truncate font-display text-xl font-semibold tabular-nums tracking-[-0.01em] text-ink sm:text-2xl">{kpi.value}</span>
              <DeltaLine kpi={kpi} />
              {kpi.hint && <span className="text-[12px] text-muted">{kpi.hint}</span>}
            </dd>
          </div>
        ))}
      </dl>
    </section>
  )
}
