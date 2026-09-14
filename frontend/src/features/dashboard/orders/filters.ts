import { useCallback, useMemo } from 'react'
import { useSearchParams } from 'react-router'
import { fromZonedParts } from '../../../lib/datetime'
import type { OrderListQuery, PaymentMethod, PaymentStatus } from './api'
import { stageStatuses } from './labels'

export type OrderTab = 'all' | 'checkout' | 'open' | 'closed' | 'attention'

export const orderTabs: { value: OrderTab; label: string }[] = [
  { value: 'all', label: 'All' },
  { value: 'checkout', label: 'Checkout' },
  { value: 'open', label: 'Open' },
  { value: 'closed', label: 'Closed' },
  { value: 'attention', label: 'Needs attention' },
]

export const paymentStatusOptions: { value: PaymentStatus; label: string }[] = [
  { value: 'paid', label: 'Paid' },
  { value: 'unpaid', label: 'Unpaid' },
  { value: 'cod_pending', label: 'COD pending' },
  { value: 'cod_collected', label: 'COD collected' },
  { value: 'refunded_manual', label: 'Refunded' },
]

export const paymentMethodOptions: { value: PaymentMethod; label: string }[] = [
  { value: 'online', label: 'Online' },
  { value: 'cod', label: 'Cash on delivery' },
]

export type OrderFilters = {
  tab: OrderTab
  payment: PaymentStatus | ''
  method: PaymentMethod | ''
  /** `yyyy-MM-dd` in the workspace zone, inclusive. */
  from: string
  /** `yyyy-MM-dd` in the workspace zone, inclusive. */
  to: string
  /** Order number, customer name or phone. */
  q: string
}

const DATE = /^\d{4}-\d{2}-\d{2}$/

function nextDay(date: string): string {
  const next = new Date(`${date}T00:00:00Z`)
  next.setUTCDate(next.getUTCDate() + 1)
  return next.toISOString().slice(0, 10)
}

/** Query params of `GET orders/`. "All" means open and closed orders; checkouts in progress have their own tab. */
export function orderListQuery(filters: OrderFilters, timeZone: string): Omit<OrderListQuery, 'cursor'> {
  const byTab: Record<OrderTab, Pick<OrderListQuery, 'status' | 'stage'>> = {
    all: { status: [...stageStatuses.open, ...stageStatuses.closed].join(',') },
    checkout: { stage: 'checkout' },
    open: { stage: 'open' },
    closed: { stage: 'closed' },
    attention: { status: 'needs_attention' },
  }
  const query: Omit<OrderListQuery, 'cursor'> = { ...byTab[filters.tab] }
  if (filters.payment) query.payment_status = filters.payment
  if (filters.method) query.payment_method = filters.method
  if (DATE.test(filters.from)) query.created_after = fromZonedParts(filters.from, '00:00', timeZone) ?? undefined
  if (DATE.test(filters.to)) query.created_before = fromZonedParts(nextDay(filters.to), '00:00', timeZone) ?? undefined
  if (filters.q.trim()) query.search = filters.q.trim()
  return query
}

export function hasActiveFilters(filters: OrderFilters): boolean {
  return Boolean(filters.payment || filters.method || filters.from || filters.to || filters.q.trim())
}

function pick<T extends string>(value: string | null, options: readonly { value: T }[]): T | '' {
  return options.find((option) => option.value === value)?.value ?? ''
}

/**
 * Order filters in the URL: `?tab=open&payment=cod_pending&method=cod&from=2026-09-01&to=2026-09-14&q=ananya`.
 * Defaults are omitted, and updates replace the history entry.
 */
export function useOrderFilters() {
  const [params, setParams] = useSearchParams()

  const filters = useMemo<OrderFilters>(
    () => ({
      tab: pick(params.get('tab'), orderTabs) || 'all',
      payment: pick(params.get('payment'), paymentStatusOptions),
      method: pick(params.get('method'), paymentMethodOptions),
      from: DATE.test(params.get('from') ?? '') ? params.get('from')! : '',
      to: DATE.test(params.get('to') ?? '') ? params.get('to')! : '',
      q: params.get('q') ?? '',
    }),
    [params],
  )

  const setFilters = useCallback(
    (patch: Partial<OrderFilters>) => {
      setParams(
        (current) => {
          const next = new URLSearchParams(current)
          const apply = (key: string, value: string | undefined) => {
            if (value === undefined) return
            if (value) next.set(key, value)
            else next.delete(key)
          }
          apply('tab', patch.tab === 'all' ? '' : patch.tab)
          apply('payment', patch.payment)
          apply('method', patch.method)
          apply('from', patch.from)
          apply('to', patch.to)
          apply('q', patch.q === undefined ? undefined : patch.q.trim() ? patch.q : '')
          return next
        },
        { replace: true },
      )
    },
    [setParams],
  )

  return { filters, setFilters }
}
