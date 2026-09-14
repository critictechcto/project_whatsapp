import { LazyTrendChart } from '../../../../components/app'
import { formatNumber } from '../../../../lib/format'
import type { CampaignStats } from '../api'
import { deliveryRate, formatRate, funnelStages, rate, readRate, sendableCount } from '../stats'

/** Delivery funnel chart with a visible text equivalent, plus delivery and read rates. */
export function CampaignFunnel({ stats }: { stats: CampaignStats }) {
  const stages = funnelStages(stats)
  const base = sendableCount(stats)
  const summary = stages.map((stage) => `${stage.label} ${formatNumber(stage.value)}`).join(', ')
  // recharts measures its container with ResizeObserver; without it (old browsers, jsdom) the list below stands alone.
  const canChart = base > 0 && typeof ResizeObserver !== 'undefined'

  return (
    <section aria-labelledby="campaign-funnel-heading" className="rounded-xl border border-line bg-card">
      <div className="flex flex-wrap items-baseline justify-between gap-2 border-b border-line-2 px-5 py-3.5">
        <h2 id="campaign-funnel-heading" className="font-display text-base font-semibold tracking-[-0.01em] text-ink">
          Delivery funnel
        </h2>
        <dl className="flex flex-wrap gap-x-5 gap-y-1 text-[13px]">
          <div className="flex gap-1.5">
            <dt className="text-muted">Delivery rate</dt>
            <dd className="font-mono text-ink">{formatRate(deliveryRate(stats))}</dd>
          </div>
          <div className="flex gap-1.5">
            <dt className="text-muted">Read rate</dt>
            <dd className="font-mono text-ink">{formatRate(readRate(stats))}</dd>
          </div>
        </dl>
      </div>

      <div className="px-5 py-4">
        {base === 0 ? (
          <p className="text-sm text-muted">Nothing has been sent yet. The funnel fills in as Meta reports delivery.</p>
        ) : (
          canChart && <LazyTrendChart data={stages.map((stage) => ({ label: stage.label, value: stage.value }))} label={`Delivery funnel: ${summary}`} height={200} />
        )}

        <ol className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-5" aria-label="Funnel stages">
          {stages.map((stage) => (
            <li key={stage.key} className="rounded-lg bg-paper/70 px-3 py-2">
              <p className="text-[12px] text-muted">{stage.label}</p>
              <p className="font-mono text-sm text-ink">
                {formatNumber(stage.value)}
                {stage.key !== 'sendable' && base > 0 && (
                  <span className="ml-1.5 text-[12px] text-muted">{formatRate(rate(stage.value, base))}</span>
                )}
              </p>
            </li>
          ))}
        </ol>
        <p className="mt-3 text-[12.5px] text-muted">
          Rates are shares of the recipients UpChatz sent to. Read counts only include customers who have read receipts turned on in WhatsApp.
        </p>
      </div>
    </section>
  )
}
