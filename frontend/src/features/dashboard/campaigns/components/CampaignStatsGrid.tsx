import { formatNumber } from '../../../../lib/format'
import type { CampaignStats } from '../api'

const items: { key: keyof CampaignStats; label: string; hint: string }[] = [
  { key: 'total', label: 'Total', hint: 'Contacts in the audience' },
  { key: 'skipped', label: 'Skipped', hint: 'Opted out, no opt-in or invalid' },
  { key: 'queued', label: 'Queued', hint: 'Waiting to be sent' },
  { key: 'sent', label: 'Sent', hint: 'Accepted by Meta' },
  { key: 'delivered', label: 'Delivered', hint: "Reached the customer's phone" },
  { key: 'read', label: 'Read', hint: 'Only when read receipts are on' },
  { key: 'failed', label: 'Failed', hint: 'See the reasons below' },
  { key: 'replied', label: 'Replied', hint: 'Customers who wrote back' },
]

export function CampaignStatsGrid({ stats }: { stats: CampaignStats }) {
  return (
    <section aria-labelledby="campaign-stats-heading">
      <h2 id="campaign-stats-heading" className="sr-only">
        Campaign numbers
      </h2>
      <dl className="grid grid-cols-2 gap-px overflow-hidden rounded-xl border border-line bg-line-2 sm:grid-cols-4">
        {items.map((item) => (
          <div key={item.key} className="flex flex-col bg-card px-4 py-3.5">
            <dt className="font-mono text-[11px] uppercase tracking-[0.12em] text-muted">{item.label}</dt>
            <dd className="mt-1 font-display text-2xl font-semibold tabular-nums tracking-[-0.02em] text-ink" data-stat={item.key}>
              {formatNumber(stats[item.key])}
            </dd>
            <dd className="mt-0.5 text-[12px] text-muted">{item.hint}</dd>
          </div>
        ))}
      </dl>
    </section>
  )
}
