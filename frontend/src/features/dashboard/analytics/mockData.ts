/**
 * Seeded analytics for mock mode and tests: 90 days of Indian demo activity for Sharma Sweets ending
 * today (in the workspace time zone). Every number derives from a per-day record keyed by the date,
 * so all reports agree with each other for any range: the overview totals equal the sums of the
 * messages series, the by-source and by-category rows, the templates table and the commerce report.
 */
import { db } from '../../../mocks/db'
import { ids, seedTemplates } from '../../../mocks/seed'
import { addDays, daysInRange, eachDate, previousRange } from './range'
import type {
  AnalyticsCampaignRow,
  AnalyticsCampaigns,
  AnalyticsCategoryRow,
  AnalyticsCommerce,
  AnalyticsFailureRow,
  AnalyticsMessages,
  AnalyticsOverview,
  AnalyticsPaymentMethod,
  AnalyticsRange,
  AnalyticsSource,
  AnalyticsTeam,
  AnalyticsTemplateRow,
  AnalyticsTemplates,
  AnalyticsTotals,
  DateRange,
  DecimalRate,
} from './types'

/** Days of seeded history, ending today. */
export const SEEDED_DAYS = 90

/** Plan features per workspace in the mock: Sharma Sweets is on the Growth trial with commerce; Kaveri is on Starter. */
export const mockPlanFeatures: Record<string, { analytics: boolean; commerce: boolean }> = {
  [ids.sharmaSweets]: { analytics: true, commerce: true },
  [ids.kaveriClinic]: { analytics: false, commerce: false },
}

type Counts = { sent: number; delivered: number; read: number; failed: number }
type OrderStatus = AnalyticsCommerce['by_status'][number]['status']
type MockOrder = {
  status: OrderStatus
  payment_method: AnalyticsPaymentMethod
  paid: boolean
  total_paise: number
  items: { product: number; quantity: number }[]
}
type TemplateKey = { name: string; language: string; category: string }

type Day = {
  bySource: Record<AnalyticsSource, Counts>
  /** Template messages per template name + language. */
  byTemplate: Map<string, Counts & TemplateKey>
  failures: Record<string, number>
  received: number
  conversationsStarted: number
  contactsAdded: number
  contactsOptedIn: number
  contactsOptedOut: number
  campaignsSent: number
  automationRuns: number
  orders: MockOrder[]
  /** Inbox replies per member index (0 = owner, 1 = admin, 2 = agent). */
  inboxBySender: number[]
  assigned: number[]
  closed: number[]
}

const sources: AnalyticsSource[] = ['inbox', 'campaign', 'automation', 'api', 'commerce']

export const mockProducts = [
  { id: 'd7a1c2e3-4b5f-4a6d-9e8c-000000000101', name: 'Kaju Katli (500 g)', price: 65000 },
  { id: 'd7a1c2e3-4b5f-4a6d-9e8c-000000000102', name: 'Motichoor Laddoo (1 kg)', price: 56000 },
  { id: 'd7a1c2e3-4b5f-4a6d-9e8c-000000000103', name: 'Dry Fruit Gift Box', price: 120000 },
  { id: 'd7a1c2e3-4b5f-4a6d-9e8c-000000000104', name: 'Ghewar (4 pcs)', price: 45000 },
  { id: 'd7a1c2e3-4b5f-4a6d-9e8c-000000000105', name: 'Soan Papdi (500 g)', price: 24000 },
  { id: 'd7a1c2e3-4b5f-4a6d-9e8c-000000000106', name: 'Rasgulla Tin (1 kg)', price: 32000 },
  { id: 'd7a1c2e3-4b5f-4a6d-9e8c-000000000107', name: 'Besan Laddoo (500 g)', price: 38000 },
  { id: 'd7a1c2e3-4b5f-4a6d-9e8c-000000000108', name: 'Mawa Kachori (6 pcs)', price: 36000 },
] as const

/** Template names and the templates app ids they map to (null when the template was deleted). */
const templates = {
  diwali: { name: 'diwali_early_access', language: 'en', category: 'marketing', id: seedTemplates[1].id as string | null },
  festive: { name: 'festive_offer_hi', language: 'hi', category: 'marketing', id: null },
  shipped: { name: 'order_shipped', language: 'en', category: 'utility', id: seedTemplates[0].id as string | null },
  payment: { name: 'payment_reminder_hi', language: 'hi', category: 'utility', id: seedTemplates[2].id as string | null },
  otp: { name: 'login_otp', language: 'en', category: 'authentication', id: null },
}

/** Campaigns and the day (days before today) each started. The first three share ids with the campaigns mock. */
const campaignSeeds = [
  { id: '6b0e2c4a-8d1f-4e3b-9a5c-7f2d1e0c0001', name: 'Diwali sale 2026', daysAgo: 0, status: 'running', total: 1840, template: 'diwali' },
  { id: '6b0e2c4a-8d1f-4e3b-9a5c-7f2d1e0c0003', name: 'Monsoon offer', daysAgo: 2, status: 'paused', total: 1260, template: 'diwali' },
  { id: '6b0e2c4a-8d1f-4e3b-9a5c-7f2d1e0c0002', name: 'Order shipped update', daysAgo: 6, status: 'completed', total: 420, template: 'shipped' },
  { id: 'f2b8a1c0-5d3e-4f7a-8b9c-00000000a004', name: 'Raksha Bandhan hampers', daysAgo: 14, status: 'completed', total: 2150, template: 'festive' },
  { id: 'f2b8a1c0-5d3e-4f7a-8b9c-00000000a005', name: 'Independence Day tricolour barfi', daysAgo: 27, status: 'completed', total: 1980, template: 'festive' },
  { id: 'f2b8a1c0-5d3e-4f7a-8b9c-00000000a006', name: 'Teej ghewar pre-orders', daysAgo: 41, status: 'completed', total: 1520, template: 'diwali' },
  { id: 'f2b8a1c0-5d3e-4f7a-8b9c-00000000a007', name: 'Payment reminder, July invoices', daysAgo: 55, status: 'completed', total: 310, template: 'payment' },
  { id: 'f2b8a1c0-5d3e-4f7a-8b9c-00000000a008', name: 'Monsoon snacks launch', daysAgo: 68, status: 'completed', total: 1730, template: 'festive' },
  { id: 'f2b8a1c0-5d3e-4f7a-8b9c-00000000a009', name: 'Rath Yatra specials', daysAgo: 83, status: 'cancelled', total: 900, template: 'festive' },
] as const

/** Deterministic 0–1 from a string key (FNV-1a + xorshift). */
function rand(key: string): number {
  let h = 2166136261
  for (let i = 0; i < key.length; i++) {
    h ^= key.charCodeAt(i)
    h = Math.imul(h, 16777619)
  }
  h ^= h >>> 13
  h = Math.imul(h, 0x5bd1e995)
  h ^= h >>> 15
  return (h >>> 0) / 4294967296
}

function between(key: string, min: number, max: number): number {
  return Math.round(min + rand(key) * (max - min))
}

function weekday(date: string): number {
  return new Date(`${date}T00:00:00Z`).getUTCDay()
}

function statusCounts(key: string, sent: number, deliveredShare: number, readShare: number, failShare: number): Counts {
  const failed = Math.round(sent * failShare * (0.6 + rand(`${key}:f`) * 0.8))
  const delivered = Math.min(sent, Math.round(sent * (deliveredShare + rand(`${key}:d`) * 0.02)))
  const read = Math.min(delivered, Math.round(delivered * (readShare + (rand(`${key}:r`) - 0.5) * 0.08)))
  return { sent, delivered, read, failed }
}

function add(target: Counts, value: Counts) {
  target.sent += value.sent
  target.delivered += value.delivered
  target.read += value.read
  target.failed += value.failed
}

const zero = (): Counts => ({ sent: 0, delivered: 0, read: 0, failed: 0 })

function emptyDay(): Day {
  return {
    bySource: { inbox: zero(), campaign: zero(), automation: zero(), api: zero(), commerce: zero() },
    byTemplate: new Map(),
    failures: {},
    received: 0,
    conversationsStarted: 0,
    contactsAdded: 0,
    contactsOptedIn: 0,
    contactsOptedOut: 0,
    campaignsSent: 0,
    automationRuns: 0,
    orders: [],
    inboxBySender: [0, 0, 0],
    assigned: [0, 0, 0],
    closed: [0, 0, 0],
  }
}

function addTemplate(day: Day, template: (typeof templates)[keyof typeof templates], counts: Counts) {
  const key = `${template.name}|${template.language}`
  const row = day.byTemplate.get(key) ?? { name: template.name, language: template.language, category: template.category, ...zero() }
  add(row, counts)
  day.byTemplate.set(key, row)
}

const failureCodes = ['131026', '131049', '131047', '131050', '131048', '131056', '130472', '131000', '']
const failureWeights = [30, 22, 16, 10, 6, 5, 4, 4, 3]

function spreadFailures(day: Day, key: string, failed: number, marketing: boolean) {
  for (let i = 0; i < failed; i++) {
    let pick = rand(`${key}:fail:${i}`) * 100
    let index = 0
    while (index < failureWeights.length - 1 && pick >= failureWeights[index]) {
      pick -= failureWeights[index]
      index += 1
    }
    const code = !marketing && (failureCodes[index] === '131049' || failureCodes[index] === '131050') ? '131026' : failureCodes[index]
    day.failures[code] = (day.failures[code] ?? 0) + 1
  }
}

const orderStatuses: OrderStatus[] = ['delivered', 'shipped', 'packed', 'confirmed', 'pending_payment', 'cancelled', 'expired', 'needs_attention']

function buildOrders(key: string, date: string, age: number): MockOrder[] {
  const weekend = [0, 6].includes(weekday(date))
  const count = between(`${key}:orders`, 2, weekend ? 11 : 7)
  return Array.from({ length: count }, (_, i) => {
    const k = `${key}:order:${i}`
    const itemCount = between(`${k}:n`, 1, 3)
    const items = Array.from({ length: itemCount }, (_, j) => ({
      product: Math.min(mockProducts.length - 1, Math.floor(rand(`${k}:p:${j}`) ** 1.4 * mockProducts.length)),
      quantity: between(`${k}:q:${j}`, 1, 3),
    }))
    const total = items.reduce((sum, item) => sum + mockProducts[item.product].price * item.quantity, 0) + (rand(`${k}:ship`) < 0.4 ? 5000 : 0)
    const r = rand(`${k}:status`)
    let status: OrderStatus
    if (r < 0.05) status = 'cancelled'
    else if (r < 0.08) status = 'expired'
    else if (r < 0.1) status = 'needs_attention'
    else if (age <= 1) status = orderStatuses[1 + Math.floor(rand(`${k}:recent`) * 4)]
    else if (age <= 4) status = rand(`${k}:mid`) < 0.5 ? 'shipped' : 'delivered'
    else status = 'delivered'
    const payment_method: AnalyticsPaymentMethod = status === 'pending_payment' ? 'online' : status === 'expired' ? '' : rand(`${k}:pm`) < 0.62 ? 'online' : 'cod'
    const paid =
      payment_method === 'online'
        ? !['pending_payment', 'expired'].includes(status)
        : payment_method === 'cod' && status === 'delivered'
    return { status, payment_method, paid, total_paise: total, items }
  })
}

const cache = new Map<string, Day>()

/** The seeded record of one day; zero outside the 90 seeded days or for workspaces without data. */
export function dayRecord(workspaceId: string, date: string, today: string): Day {
  const age = daysInRange(date, today) - 1
  if (workspaceId !== ids.sharmaSweets || age < 0 || age >= SEEDED_DAYS) return emptyDay()
  const cacheKey = `${workspaceId}|${date}|${today}`
  const cached = cache.get(cacheKey)
  if (cached) return cached

  const key = `${workspaceId}:${date}`
  const day = emptyDay()
  const weekend = [0, 6].includes(weekday(date))
  // Busier towards the festive season (today) than three months ago.
  const growth = 0.7 + 0.3 * (1 - age / SEEDED_DAYS)
  const scale = (base: number, salt: string) => Math.round(base * growth * (weekend ? 1.25 : 1) * (0.8 + rand(`${key}:${salt}`) * 0.4))

  // Inbox replies by the team.
  const inbox = statusCounts(`${key}:inbox`, scale(46, 'inbox'), 0.965, 0.86, 0.012)
  day.bySource.inbox = inbox
  day.inboxBySender = [Math.round(inbox.sent * 0.22), Math.round(inbox.sent * 0.33), 0]
  day.inboxBySender[2] = inbox.sent - day.inboxBySender[0] - day.inboxBySender[1]
  spreadFailures(day, `${key}:inbox`, inbox.failed, false)

  // Automations (keyword and away replies), non-template.
  const automation = statusCounts(`${key}:auto`, scale(24, 'auto'), 0.97, 0.8, 0.01)
  day.bySource.automation = automation
  day.automationRuns = automation.sent
  spreadFailures(day, `${key}:auto`, automation.failed, false)

  // Login OTPs from the website through the API.
  const api = statusCounts(`${key}:api`, scale(12, 'api'), 0.955, 0.55, 0.02)
  day.bySource.api = api
  addTemplate(day, templates.otp, api)
  spreadFailures(day, `${key}:api`, api.failed, false)

  // Orders and the buyer messages they send (confirmation, shipping, payment reminders).
  day.orders = buildOrders(key, date, age)
  const shipped = statusCounts(`${key}:ship`, day.orders.length * 2, 0.97, 0.78, 0.015)
  const reminders = statusCounts(`${key}:pay`, Math.round(day.orders.length * 0.6), 0.96, 0.7, 0.02)
  add(day.bySource.commerce, shipped)
  add(day.bySource.commerce, reminders)
  addTemplate(day, templates.shipped, shipped)
  addTemplate(day, templates.payment, reminders)
  spreadFailures(day, `${key}:ship`, shipped.failed + reminders.failed, false)

  // Campaigns that started on this day send their whole audience that day.
  for (const campaign of campaignSeeds) {
    if (campaign.daysAgo !== age || campaign.status === 'cancelled') continue
    const row = campaignRow(campaign)
    const counts = { sent: row.sent_count, delivered: row.delivered_count, read: row.read_count, failed: row.failed_count }
    add(day.bySource.campaign, counts)
    addTemplate(day, templates[campaign.template], counts)
    spreadFailures(day, `${key}:camp:${campaign.id}`, counts.failed, templates[campaign.template].category === 'marketing')
  }
  day.campaignsSent = campaignSeeds.filter((campaign) => campaign.daysAgo === age).length

  const campaignReplies = Math.round(day.bySource.campaign.read * 0.12)
  day.received = Math.round(inbox.sent * 1.35) + day.orders.length * 3 + campaignReplies
  day.conversationsStarted = Math.round(day.received / 5) + day.orders.length
  day.contactsAdded = scale(7, 'contacts') + Math.round(campaignReplies / 4)
  day.contactsOptedIn = Math.round(day.contactsAdded * (0.62 + rand(`${key}:optin`) * 0.2))
  day.contactsOptedOut = between(`${key}:optout`, 0, 2) + Math.round(day.bySource.campaign.read * 0.004)

  const conversations = day.conversationsStarted
  day.assigned = [Math.round(conversations * 0.15), Math.round(conversations * 0.35), 0]
  day.assigned[2] = conversations - day.assigned[0] - day.assigned[1]
  day.closed = day.assigned.map((count, i) => Math.round(count * (age === 0 ? 0.3 : 0.85 - i * 0.03)))

  cache.set(cacheKey, day)
  return day
}

function rate(numerator: number, denominator: number): DecimalRate {
  return denominator === 0 ? null : (Math.round((numerator / denominator) * 10000) / 10000).toFixed(4)
}

function campaignRow(seed: (typeof campaignSeeds)[number]): Omit<AnalyticsCampaignRow, 'started_at'> {
  const key = `campaign:${seed.id}`
  const sendable = seed.status === 'cancelled' ? Math.round(seed.total * 0.3) : Math.round(seed.total * 0.94)
  const marketing = templates[seed.template].category === 'marketing'
  const counts = statusCounts(key, seed.status === 'running' ? Math.round(sendable * 0.62) : sendable, 0.94, marketing ? 0.64 : 0.8, marketing ? 0.045 : 0.02)
  const replied = Math.round(counts.read * (marketing ? 0.11 : 0.05))
  return {
    id: seed.id,
    name: seed.name,
    status: seed.status,
    total_count: seed.total,
    sent_count: counts.sent,
    delivered_count: counts.delivered,
    read_count: counts.read,
    failed_count: counts.failed,
    replied_count: replied,
    delivery_rate: rate(counts.delivered, counts.sent),
    read_rate: rate(counts.read, counts.delivered),
    reply_rate: rate(replied, counts.delivered),
  }
}

function days(workspaceId: string, range: DateRange, today: string): Day[] {
  return eachDate(range.from, range.to).map((date) => dayRecord(workspaceId, date, today))
}

export function rangeOf(range: DateRange, timeZone: string): AnalyticsRange {
  const previous = previousRange(range)
  return { from: range.from, to: range.to, time_zone: timeZone, previous_from: previous.from, previous_to: previous.to }
}

function sourceTotals(list: Day[]): Record<AnalyticsSource, Counts> {
  const totals = { inbox: zero(), campaign: zero(), automation: zero(), api: zero(), commerce: zero() }
  for (const day of list) for (const source of sources) add(totals[source], day.bySource[source])
  return totals
}

function sumBy(list: Day[], pick: (day: Day) => number): number {
  return list.reduce((sum, day) => sum + pick(day), 0)
}

export function totals(workspaceId: string, range: DateRange, today: string): AnalyticsTotals {
  const list = days(workspaceId, range, today)
  const all = zero()
  for (const counts of Object.values(sourceTotals(list))) add(all, counts)
  const commerce = mockPlanFeatures[workspaceId]?.commerce ?? false
  const orders = list.flatMap((day) => day.orders)
  return {
    messages_sent: all.sent,
    messages_delivered: all.delivered,
    messages_read: all.read,
    messages_failed: all.failed,
    messages_received: sumBy(list, (day) => day.received),
    delivery_rate: rate(all.delivered, all.sent),
    read_rate: rate(all.read, all.delivered),
    conversations_started: sumBy(list, (day) => day.conversationsStarted),
    contacts_added: sumBy(list, (day) => day.contactsAdded),
    contacts_opted_in: sumBy(list, (day) => day.contactsOptedIn),
    contacts_opted_out: sumBy(list, (day) => day.contactsOptedOut),
    campaigns_sent: sumBy(list, (day) => day.campaignsSent),
    automation_runs: sumBy(list, (day) => day.automationRuns),
    orders: commerce ? orders.length : null,
    revenue_paise: commerce ? orders.filter((order) => order.paid).reduce((sum, order) => sum + order.total_paise, 0) : null,
  }
}

export function overview(workspaceId: string, range: DateRange, today: string, timeZone: string): AnalyticsOverview {
  return { range: rangeOf(range, timeZone), current: totals(workspaceId, range, today), previous: totals(workspaceId, previousRange(range), today) }
}

export function messages(workspaceId: string, range: DateRange, today: string, timeZone: string): AnalyticsMessages {
  const dates = eachDate(range.from, range.to)
  const list = dates.map((date) => dayRecord(workspaceId, date, today))
  const series = list.map((day, i) => {
    const all = zero()
    for (const source of sources) add(all, day.bySource[source])
    return { date: dates[i], ...all, received: day.received }
  })

  const bySource = Object.entries(sourceTotals(list))
    .filter(([, counts]) => counts.sent + counts.failed > 0)
    .map(([source, counts]) => ({
      source: source as AnalyticsSource,
      ...counts,
      delivery_rate: rate(counts.delivered, counts.sent),
      read_rate: rate(counts.read, counts.delivered),
    }))
    .sort((a, b) => b.sent - a.sent)

  const categories = new Map<string, Counts>()
  const template = templateTotals(list)
  for (const row of template) {
    const counts = categories.get(row.category) ?? zero()
    add(counts, row)
    categories.set(row.category, counts)
  }
  const sourcesAll = sourceTotals(list)
  const nonTemplate = zero()
  add(nonTemplate, sourcesAll.inbox)
  add(nonTemplate, sourcesAll.automation)
  if (nonTemplate.sent + nonTemplate.failed > 0) categories.set('', nonTemplate)
  const byCategory: AnalyticsCategoryRow[] = [...categories.entries()]
    .map(([category, counts]) => ({ category, ...counts }))
    .sort((a, b) => b.sent - a.sent)

  const failures = new Map<string, number>()
  for (const day of list) for (const [code, count] of Object.entries(day.failures)) failures.set(code, (failures.get(code) ?? 0) + count)
  const failureReasons: AnalyticsFailureRow[] = [...failures.entries()]
    .map(([error_code, count]) => ({ error_code, count }))
    .sort((a, b) => b.count - a.count)
    .slice(0, 10)

  return { range: rangeOf(range, timeZone), series, by_source: bySource, by_category: byCategory, failure_reasons: failureReasons }
}

function templateTotals(list: Day[]): (Counts & TemplateKey)[] {
  const rows = new Map<string, Counts & TemplateKey>()
  for (const day of list) {
    for (const [key, value] of day.byTemplate) {
      const row = rows.get(key) ?? { name: value.name, language: value.language, category: value.category, ...zero() }
      add(row, value)
      rows.set(key, row)
    }
  }
  return [...rows.values()]
}

export function templatesReport(workspaceId: string, range: DateRange, today: string, timeZone: string): AnalyticsTemplates {
  const results: AnalyticsTemplateRow[] = templateTotals(days(workspaceId, range, today))
    .map((row) => ({
      template_id: Object.values(templates).find((t) => t.name === row.name && t.language === row.language)?.id ?? null,
      name: row.name,
      language: row.language,
      category: row.category,
      sent: row.sent,
      delivered: row.delivered,
      read: row.read,
      failed: row.failed,
      delivery_rate: rate(row.delivered, row.sent),
      read_rate: rate(row.read, row.delivered),
    }))
    .sort((a, b) => b.sent - a.sent)
    .slice(0, 50)
  return { range: rangeOf(range, timeZone), results }
}

export function campaignsReport(workspaceId: string, range: DateRange, today: string, timeZone: string): AnalyticsCampaigns {
  const results =
    workspaceId !== ids.sharmaSweets
      ? []
      : campaignSeeds
          .map((seed) => ({ seed, date: addDays(today, -seed.daysAgo) }))
          .filter(({ seed, date }) => seed.daysAgo < SEEDED_DAYS && date >= range.from && date <= range.to)
          .map(({ seed, date }) => ({ ...campaignRow(seed), started_at: `${date}T${String(4 + (seed.daysAgo % 5)).padStart(2, '0')}:30:00Z` }))
          .sort((a, b) => b.started_at.localeCompare(a.started_at))
          .slice(0, 50)
  return { range: rangeOf(range, timeZone), results }
}

export function teamReport(workspaceId: string, range: DateRange, today: string, timeZone: string): AnalyticsTeam {
  const list = days(workspaceId, range, today)
  const order = ['owner', 'admin', 'agent', 'viewer']
  const members = db.memberships
    .filter((membership) => membership.workspace_id === workspaceId)
    .sort((a, b) => order.indexOf(a.role) - order.indexOf(b.role))
  const results = members
    .map((membership, index) => {
      const user = db.users.find((candidate) => candidate.id === membership.user_id)
      const slot = index < 3 ? index : -1
      const pick = (field: 'inboxBySender' | 'assigned' | 'closed') => (slot < 0 ? 0 : sumBy(list, (day) => day[field][slot]))
      return {
        user_id: membership.user_id,
        name: user?.full_name ?? '',
        email: user?.email ?? '',
        role: membership.role,
        messages_sent: pick('inboxBySender'),
        conversations_assigned: pick('assigned'),
        conversations_closed: pick('closed'),
      }
    })
    .sort((a, b) => b.messages_sent - a.messages_sent || a.name.localeCompare(b.name))
  return { range: rangeOf(range, timeZone), results }
}

export function commerceReport(workspaceId: string, range: DateRange, today: string, timeZone: string): AnalyticsCommerce {
  const dates = eachDate(range.from, range.to)
  const list = dates.map((date) => dayRecord(workspaceId, date, today))
  const orders = list.flatMap((day) => day.orders)
  const paidOrders = orders.filter((order) => order.paid)
  const revenue = paidOrders.reduce((sum, order) => sum + order.total_paise, 0)

  const statusCountsMap = new Map<OrderStatus, number>()
  for (const order of orders) statusCountsMap.set(order.status, (statusCountsMap.get(order.status) ?? 0) + 1)

  const methods = new Map<AnalyticsPaymentMethod, { orders: number; revenue_paise: number }>()
  for (const order of orders) {
    const row = methods.get(order.payment_method) ?? { orders: 0, revenue_paise: 0 }
    row.orders += 1
    if (order.paid) row.revenue_paise += order.total_paise
    methods.set(order.payment_method, row)
  }

  const products = new Map<number, { quantity: number; revenue_paise: number }>()
  for (const order of paidOrders) {
    for (const item of order.items) {
      const row = products.get(item.product) ?? { quantity: 0, revenue_paise: 0 }
      row.quantity += item.quantity
      row.revenue_paise += mockProducts[item.product].price * item.quantity
      products.set(item.product, row)
    }
  }

  return {
    range: rangeOf(range, timeZone),
    series: list.map((day, i) => ({
      date: dates[i],
      orders: day.orders.length,
      revenue_paise: day.orders.filter((order) => order.paid).reduce((sum, order) => sum + order.total_paise, 0),
    })),
    orders: orders.length,
    paid_orders: paidOrders.length,
    revenue_paise: revenue,
    average_order_paise: paidOrders.length ? Math.floor(revenue / paidOrders.length) : null,
    by_status: [...statusCountsMap.entries()].map(([status, count]) => ({ status, count })).sort((a, b) => b.count - a.count),
    by_payment_method: [...methods.entries()]
      .map(([payment_method, row]) => ({ payment_method, ...row }))
      .sort((a, b) => b.orders - a.orders),
    top_products: [...products.entries()]
      .map(([index, row]) => ({ product_id: mockProducts[index].id, name: mockProducts[index].name, ...row }))
      .sort((a, b) => b.revenue_paise - a.revenue_paise)
      .slice(0, 10),
  }
}

/** Quotes a CSV cell and guards against formula injection like the backend. */
function csvCell(value: string | number | null): string {
  let text = value === null ? '' : String(value)
  if (/^[=+\-@]/.test(text)) text = `'${text}`
  return /[",\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text
}

function rupees(paise: number | null): string {
  return paise === null ? '' : (paise / 100).toFixed(2)
}

export function exportCsv(report: string, workspaceId: string, range: DateRange, today: string, timeZone: string): string | null {
  let header: string[]
  let rows: (string | number | null)[][]
  switch (report) {
    case 'messages': {
      header = ['date', 'sent', 'delivered', 'read', 'failed', 'received']
      rows = messages(workspaceId, range, today, timeZone).series.map((p) => [p.date, p.sent, p.delivered, p.read, p.failed, p.received])
      break
    }
    case 'templates': {
      header = ['name', 'language', 'category', 'sent', 'delivered', 'read', 'failed', 'delivery_rate', 'read_rate']
      rows = templatesReport(workspaceId, range, today, timeZone).results.map((r) => [
        r.name, r.language, r.category, r.sent, r.delivered, r.read, r.failed, r.delivery_rate, r.read_rate,
      ])
      break
    }
    case 'campaigns': {
      header = ['name', 'status', 'started_at', 'total', 'sent', 'delivered', 'read', 'failed', 'replied', 'delivery_rate', 'read_rate', 'reply_rate']
      rows = campaignsReport(workspaceId, range, today, timeZone).results.map((r) => [
        r.name, r.status, r.started_at, r.total_count, r.sent_count, r.delivered_count, r.read_count, r.failed_count, r.replied_count,
        r.delivery_rate, r.read_rate, r.reply_rate,
      ])
      break
    }
    case 'team': {
      header = ['name', 'email', 'role', 'messages_sent', 'conversations_assigned', 'conversations_closed']
      rows = teamReport(workspaceId, range, today, timeZone).results.map((r) => [
        r.name, r.email, r.role, r.messages_sent, r.conversations_assigned, r.conversations_closed,
      ])
      break
    }
    case 'commerce': {
      header = ['date', 'orders', 'revenue_inr']
      rows = commerceReport(workspaceId, range, today, timeZone).series.map((p) => [p.date, p.orders, rupees(p.revenue_paise)])
      break
    }
    default:
      return null
  }
  return [header, ...rows].map((row) => row.map(csvCell).join(',')).join('\r\n') + '\r\n'
}
