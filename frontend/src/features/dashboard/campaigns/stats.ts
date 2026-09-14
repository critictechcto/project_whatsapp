import type { CampaignStats, CampaignStatus } from './api'

/*
 * Stats are read as cumulative counts of recipients that reached each stage, so
 * sent >= delivered >= read (a read message was also sent and delivered). `total` includes
 * skipped recipients. This is the one place that depends on that reading.
 */

/** Recipients that will actually be messaged. */
export function sendableCount(stats: CampaignStats): number {
  return Math.max(0, stats.total - stats.skipped)
}

/** `part / whole` between 0 and 1, or null when there is nothing to divide by. */
export function rate(part: number, whole: number): number | null {
  if (whole <= 0) return null
  return Math.min(1, Math.max(0, part / whole))
}

export function formatRate(value: number | null): string {
  if (value === null) return '—'
  const percent = Math.round(value * 1000) / 10
  return `${Number.isInteger(percent) ? percent : percent.toFixed(1)}%`
}

/** Share of sent messages that Meta reported delivered. */
export function deliveryRate(stats: CampaignStats): number | null {
  return rate(stats.delivered, stats.sent)
}

/** Share of delivered messages reported read (only customers with read receipts on are counted). */
export function readRate(stats: CampaignStats): number | null {
  return rate(stats.read, stats.delivered)
}

export type FunnelStage = { key: 'sendable' | 'sent' | 'delivered' | 'read' | 'replied'; label: string; value: number }

export function funnelStages(stats: CampaignStats): FunnelStage[] {
  return [
    { key: 'sendable', label: 'To send', value: sendableCount(stats) },
    { key: 'sent', label: 'Sent', value: stats.sent },
    { key: 'delivered', label: 'Delivered', value: stats.delivered },
    { key: 'read', label: 'Read', value: stats.read },
    { key: 'replied', label: 'Replied', value: stats.replied },
  ]
}

export type ProgressSegment = { key: 'read' | 'delivered' | 'sent' | 'failed'; value: number; fraction: number }

/** Non-overlapping progress bar segments as fractions of the sendable audience. */
export function progressSegments(stats: CampaignStats): ProgressSegment[] {
  const base = sendableCount(stats)
  const fraction = (value: number) => (base > 0 ? Math.min(1, value / base) : 0)
  const segment = (key: ProgressSegment['key'], value: number): ProgressSegment => {
    const clamped = Math.max(0, value)
    return { key, value: clamped, fraction: fraction(clamped) }
  }
  return [
    segment('read', stats.read),
    segment('delivered', stats.delivered - stats.read),
    segment('sent', stats.sent - stats.delivered),
    segment('failed', stats.failed),
  ]
}

export function isFinished(status: CampaignStatus): boolean {
  return status === 'completed' || status === 'cancelled' || status === 'failed'
}
