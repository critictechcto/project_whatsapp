import { formatPaise } from '../../../lib/money'
import { countDelta, formatNumber, formatRate, rateDelta, type Delta } from './format'
import type { Schemas } from '../../../api/types'

type AnalyticsOverview = Schemas['AnalyticsOverview']

export type Kpi = {
  id: string
  label: string
  value: string
  delta: Delta
  /** Previous value, shown when there is no percent to compare. */
  previous: string
  /** An increase is bad news (failures, opt-outs). */
  upIsBad?: boolean
  hint?: string
}

function countKpi(id: string, label: string, current: number, previous: number, extra: Partial<Kpi> = {}): Kpi {
  return { id, label, value: formatNumber(current), delta: countDelta(current, previous), previous: formatNumber(previous), ...extra }
}

/** KPI cards of the overview; orders and revenue only when the API returns them (commerce plans). */
export function buildKpis({ current, previous }: Pick<AnalyticsOverview, 'current' | 'previous'>): Kpi[] {
  const kpis: Kpi[] = [
    countKpi('sent', 'Messages sent', current.messages_sent, previous.messages_sent),
    {
      id: 'delivery_rate',
      label: 'Delivery rate',
      value: formatRate(current.delivery_rate),
      delta: rateDelta(current.delivery_rate, previous.delivery_rate),
      previous: formatRate(previous.delivery_rate),
      hint: `${formatNumber(current.messages_delivered)} delivered`,
    },
    {
      id: 'read_rate',
      label: 'Read rate',
      value: formatRate(current.read_rate),
      delta: rateDelta(current.read_rate, previous.read_rate),
      previous: formatRate(previous.read_rate),
      hint: `${formatNumber(current.messages_read)} read`,
    },
    countKpi('failed', 'Failed messages', current.messages_failed, previous.messages_failed, { upIsBad: true }),
    countKpi('received', 'Messages received', current.messages_received, previous.messages_received),
    countKpi('conversations', 'Conversations started', current.conversations_started, previous.conversations_started),
    countKpi('contacts_added', 'Contacts added', current.contacts_added, previous.contacts_added),
    countKpi('opted_in', 'Opted in', current.contacts_opted_in, previous.contacts_opted_in),
    countKpi('opted_out', 'Opted out', current.contacts_opted_out, previous.contacts_opted_out, { upIsBad: true }),
    countKpi('campaigns', 'Campaigns sent', current.campaigns_sent, previous.campaigns_sent),
    countKpi('automations', 'Automation runs', current.automation_runs, previous.automation_runs),
  ]
  if (current.orders !== null) kpis.push(countKpi('orders', 'Orders', current.orders, previous.orders ?? 0))
  if (current.revenue_paise !== null) {
    const before = previous.revenue_paise ?? 0
    kpis.push({
      id: 'revenue',
      label: 'Revenue',
      value: formatPaise(current.revenue_paise, { decimals: 0 }),
      delta: countDelta(current.revenue_paise, before),
      previous: formatPaise(before, { decimals: 0 }),
      hint: 'Paid online or cash collected',
    })
  }
  return kpis
}
