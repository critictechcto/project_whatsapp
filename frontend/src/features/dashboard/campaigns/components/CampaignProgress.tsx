import { cn } from '../../../../lib/cn'
import { formatNumber } from '../../../../lib/format'
import type { CampaignStats, CampaignStatus } from '../api'
import { progressSegments, sendableCount, type ProgressSegment } from '../stats'

const segmentClasses: Record<ProgressSegment['key'], string> = {
  read: 'bg-accent',
  delivered: 'bg-accent/55',
  sent: 'bg-[#2f7fc1]/55',
  failed: 'bg-signal',
}

/** Compact progress bar for list rows, with a text equivalent for screen readers. */
export function CampaignProgress({ stats, status }: { stats: CampaignStats; status: CampaignStatus }) {
  const base = sendableCount(stats)
  if (status === 'draft' || status === 'scheduled' || base === 0) {
    return <span className="text-[13px] text-muted">{status === 'draft' || status === 'scheduled' ? 'Not sent yet' : '—'}</span>
  }
  const segments = progressSegments(stats)

  return (
    <div className="min-w-36">
      <div aria-hidden="true" className="flex h-1.5 overflow-hidden rounded-full bg-line-2">
        {segments.map((segment) =>
          segment.fraction > 0 ? (
            <span key={segment.key} className={cn('h-full', segmentClasses[segment.key])} style={{ width: `${segment.fraction * 100}%` }} />
          ) : null,
        )}
      </div>
      <p aria-hidden="true" className="mt-1 font-mono text-[11.5px] text-muted">
        {formatNumber(stats.sent)}/{formatNumber(base)} sent · {formatNumber(stats.read)} read
      </p>
      <span className="sr-only">
        {`${formatNumber(stats.sent)} of ${formatNumber(base)} sent, ${formatNumber(stats.delivered)} delivered, ${formatNumber(stats.read)} read, ${formatNumber(stats.failed)} failed`}
      </span>
    </div>
  )
}
