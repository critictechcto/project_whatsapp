/**
 * Response components of `docs/contracts/analytics.md`, mirrored by hand until `backend/openapi.yml`
 * includes analytics. Names match the contract components one to one, so each can later become
 * `Schemas['AnalyticsOverview']` etc. from `api/types`.
 */
import type { Schemas } from '../../../api/types'

/** Decimal 0–1 as a string with up to 4 places (`"0.9612"`), or null when the denominator is 0. */
export type DecimalRate = string | null

export type AnalyticsRange = {
  from: string
  to: string
  time_zone: string
  previous_from: string
  previous_to: string
}

export type AnalyticsTotals = {
  messages_sent: number
  messages_delivered: number
  messages_read: number
  messages_failed: number
  messages_received: number
  delivery_rate: DecimalRate
  read_rate: DecimalRate
  conversations_started: number
  contacts_added: number
  contacts_opted_in: number
  contacts_opted_out: number
  campaigns_sent: number
  automation_runs: number
  orders: number | null
  revenue_paise: number | null
}

export type AnalyticsOverview = {
  range: AnalyticsRange
  current: AnalyticsTotals
  previous: AnalyticsTotals
}

export type AnalyticsMessagePoint = {
  date: string
  sent: number
  delivered: number
  read: number
  failed: number
  received: number
}

/** `MessageSourceEnum` minus `inbound`. */
export type AnalyticsSource = Exclude<Schemas['MessageSourceEnum'], 'inbound'>

export type AnalyticsSourceRow = {
  source: AnalyticsSource
  sent: number
  delivered: number
  read: number
  failed: number
  delivery_rate: DecimalRate
  read_rate: DecimalRate
}

export type AnalyticsCategoryRow = {
  /** `marketing`, `utility`, `authentication`, or `""` for non-template messages. */
  category: string
  sent: number
  delivered: number
  read: number
  failed: number
}

export type AnalyticsFailureRow = {
  /** Meta error code, `""` when unknown. */
  error_code: string
  count: number
}

export type AnalyticsMessages = {
  range: AnalyticsRange
  series: AnalyticsMessagePoint[]
  by_source: AnalyticsSourceRow[]
  by_category: AnalyticsCategoryRow[]
  failure_reasons: AnalyticsFailureRow[]
}

export type AnalyticsTemplateRow = {
  template_id: string | null
  name: string
  language: string
  category: string
  sent: number
  delivered: number
  read: number
  failed: number
  delivery_rate: DecimalRate
  read_rate: DecimalRate
}

export type AnalyticsTemplates = {
  range: AnalyticsRange
  results: AnalyticsTemplateRow[]
}

export type AnalyticsCampaignRow = {
  id: string
  name: string
  status: Schemas['CampaignStatusEnum']
  started_at: string
  total_count: number
  sent_count: number
  delivered_count: number
  read_count: number
  failed_count: number
  replied_count: number
  delivery_rate: DecimalRate
  read_rate: DecimalRate
  reply_rate: DecimalRate
}

export type AnalyticsCampaigns = {
  range: AnalyticsRange
  results: AnalyticsCampaignRow[]
}

export type AnalyticsTeamRow = {
  user_id: string
  name: string
  email: string
  role: string
  messages_sent: number
  conversations_assigned: number
  conversations_closed: number
}

export type AnalyticsTeam = {
  range: AnalyticsRange
  results: AnalyticsTeamRow[]
}

export type AnalyticsCommercePoint = {
  date: string
  orders: number
  revenue_paise: number
}

export type AnalyticsOrderStatusRow = {
  status: Schemas['OrderStatusEnum']
  count: number
}

/** `AnalyticsPaymentMethodEnum`, blank allowed. */
export type AnalyticsPaymentMethod = 'online' | 'cod' | ''

export type AnalyticsPaymentMethodRow = {
  payment_method: AnalyticsPaymentMethod
  orders: number
  revenue_paise: number
}

export type AnalyticsProductRow = {
  product_id: string | null
  name: string
  quantity: number
  revenue_paise: number
}

export type AnalyticsCommerce = {
  range: AnalyticsRange
  series: AnalyticsCommercePoint[]
  orders: number
  paid_orders: number
  revenue_paise: number
  average_order_paise: number | null
  by_status: AnalyticsOrderStatusRow[]
  by_payment_method: AnalyticsPaymentMethodRow[]
  top_products: AnalyticsProductRow[]
}

/** `report` values of `GET export/`. */
export type AnalyticsReport = 'messages' | 'templates' | 'campaigns' | 'team' | 'commerce'

/** The `from`/`to` query of every endpoint (inclusive dates, `YYYY-MM-DD`). */
export type DateRange = { from: string; to: string }
