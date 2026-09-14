import { Skeleton } from '../../../../components/app'
import { cn } from '../../../../lib/cn'
import { formatNumber } from '../../../../lib/format'
import { formatPaise } from '../../../../lib/money'
import { useOrderSummary } from '../api'

type SummaryStripProps = {
  workspaceId: string
  /** Shows the "Needs attention" tab. */
  onShowAttention?: () => void
}

/** Today's numbers from `GET orders/summary/`. */
export function SummaryStrip({ workspaceId, onShowAttention }: SummaryStripProps) {
  const summary = useOrderSummary(workspaceId)
  const data = summary.data

  const items: { label: string; value: string | undefined; alert?: boolean; action?: boolean }[] = [
    { label: 'Orders today', value: data && formatNumber(data.today_count) },
    { label: 'Revenue today', value: data && formatPaise(data.today_revenue_paise) },
    { label: 'Open', value: data && formatNumber(data.open_count) },
    {
      label: 'Needs attention',
      value: data && formatNumber(data.needs_attention_count),
      alert: Boolean(data?.needs_attention_count),
      action: Boolean(data?.needs_attention_count && onShowAttention),
    },
    { label: 'Awaiting payment', value: data && formatNumber(data.awaiting_payment_count) },
  ]

  return (
    <section aria-label="Order summary">
      {summary.isError ? (
        <p className="text-sm text-muted">Today&apos;s numbers couldn&apos;t be loaded.</p>
      ) : (
        <dl className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
          {items.map((item) => (
            <div
              key={item.label}
              className={cn(
                'flex flex-col justify-between gap-1 rounded-xl border bg-card px-4 py-3',
                item.alert ? 'border-signal/30' : 'border-line',
              )}
            >
              <dt className="text-[12px] text-muted">{item.label}</dt>
              <dd className="flex flex-wrap items-baseline justify-between gap-x-2">
                {item.value === undefined ? (
                  <Skeleton className="my-1 h-6 w-16" />
                ) : (
                  <span className={cn('font-display text-xl font-semibold tabular-nums tracking-[-0.01em]', item.alert ? 'text-signal' : 'text-ink')}>
                    {item.value}
                  </span>
                )}
                {item.action && (
                  <button
                    type="button"
                    onClick={onShowAttention}
                    className="text-[12px] font-medium text-accent-2 underline-offset-4 hover:underline"
                    aria-label="Show orders that need attention"
                  >
                    Review
                  </button>
                )}
              </dd>
            </div>
          ))}
        </dl>
      )}
    </section>
  )
}
