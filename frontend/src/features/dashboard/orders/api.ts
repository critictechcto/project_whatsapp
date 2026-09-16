import { useQuery, useQueryClient, type InfiniteData, type QueryClient } from '@tanstack/react-query'
import { api, unwrap } from '../../../api/client'
import { useCursorQuery } from '../../../api/pagination'
import { workspaceKeys } from '../../../api/queryKeys'
import type { CursorPage, Schemas } from '../../../api/types'
import { useToast } from '../../../components/app'
import { useRealtimeEvent } from '../../../lib/realtime/hooks'

export type Order = Schemas['Order']
export type OrderListItem = Schemas['OrderListItem']
export type OrderEvent = Schemas['OrderEvent']
export type OrderItem = Schemas['OrderItem']
export type OrderAddress = Schemas['OrderAddress']
export type OrderSummary = Schemas['OrderSummary']
export type OrderStatus = Schemas['OrderStatusEnum']
export type PaymentStatus = Schemas['PaymentStatusEnum']
export type PaymentMethod = Schemas['PaymentMethodEnum']
export type PaymentLinkStatus = Schemas['PaymentLinkStatusEnum']
export type OrderSource = Schemas['OrderSourceEnum']
export type EventType = Schemas['OrderEventTypeEnum']
export type EventActor = Schemas['OrderEventActorEnum']
export type TransitionBody = Schemas['OrderTransitionRequest']
export type CancelBody = Schemas['CancelOrderRequest']

export type OrderListQuery = NonNullable<NonNullable<Parameters<typeof fetchOrders>[0]>>

export const orderKeys = workspaceKeys('orders')

export const summaryKey = (workspaceId: string) => orderKeys.custom(workspaceId, 'summary')
export const eventsKey = (workspaceId: string, orderId: string) => orderKeys.custom(workspaceId, 'events', orderId)

export function fetchOrders(
  query: {
    status?: string
    stage?: 'checkout' | 'open' | 'closed'
    payment_status?: PaymentStatus
    payment_method?: PaymentMethod
    created_after?: string
    created_before?: string
    search?: string
    cursor?: string
  } = {},
  signal?: AbortSignal,
) {
  return unwrap(api.GET('/api/v1/orders/', { params: { query }, signal }))
}

export function useOrders(workspaceId: string, query: Omit<OrderListQuery, 'cursor'>) {
  return useCursorQuery<OrderListItem>({
    queryKey: orderKeys.list(workspaceId, query),
    queryFn: ({ cursor, signal }) => fetchOrders({ ...query, cursor }, signal),
  })
}

export function useOrder(workspaceId: string, id: string) {
  return useQuery({
    queryKey: orderKeys.detail(workspaceId, id),
    queryFn: ({ signal }) => unwrap(api.GET('/api/v1/orders/{id}/', { params: { path: { id } }, signal })),
    enabled: Boolean(id),
  })
}

export function useOrderSummary(workspaceId: string) {
  return useQuery({
    queryKey: summaryKey(workspaceId),
    queryFn: ({ signal }) => unwrap(api.GET('/api/v1/orders/summary/', { signal })),
  })
}

export function useOrderEvents(workspaceId: string, id: string) {
  return useCursorQuery<OrderEvent>({
    queryKey: eventsKey(workspaceId, id),
    queryFn: ({ cursor, signal }) =>
      unwrap(api.GET('/api/v1/orders/{id}/events/', { params: { path: { id }, query: { cursor } }, signal })),
  })
}

const pathOf = (id: string) => ({ params: { path: { id } } })

export const orderMutations = {
  transition: (id: string, body: TransitionBody) => unwrap(api.POST('/api/v1/orders/{id}/transition/', { ...pathOf(id), body })),
  cancel: (id: string, body: CancelBody) => unwrap(api.POST('/api/v1/orders/{id}/cancel/', { ...pathOf(id), body })),
  markCodCollected: (id: string) => unwrap(api.POST('/api/v1/orders/{id}/mark-cod-collected/', pathOf(id))),
  markRefunded: (id: string) => unwrap(api.POST('/api/v1/orders/{id}/mark-refunded/', pathOf(id))),
  updateNotes: (id: string, notes: string) => unwrap(api.PATCH('/api/v1/orders/{id}/', { ...pathOf(id), body: { notes } })),
}

type OrderPages = InfiniteData<CursorPage<OrderListItem>, string | undefined>

function patchLists(queryClient: QueryClient, workspaceId: string, id: string, patch: Partial<OrderListItem>) {
  queryClient.setQueriesData<OrderPages>({ queryKey: orderKeys.lists(workspaceId) }, (data) =>
    data
      ? {
          ...data,
          pages: data.pages.map((page) => ({
            ...page,
            results: page.results.map((order) => (order.id === id ? { ...order, ...patch } : order)),
          })),
        }
      : data,
  )
}

/** Refetches everything an order change can affect: lists (stage membership), summary and the timeline. */
export function invalidateOrder(queryClient: QueryClient, workspaceId: string, id: string) {
  void queryClient.invalidateQueries({ queryKey: orderKeys.lists(workspaceId) })
  void queryClient.invalidateQueries({ queryKey: summaryKey(workspaceId) })
  void queryClient.invalidateQueries({ queryKey: eventsKey(workspaceId, id) })
}

/** Writes an order returned by a mutation into the caches right away, then refetches what depends on it. */
export function storeOrder(queryClient: QueryClient, workspaceId: string, order: Order) {
  queryClient.setQueryData(orderKeys.detail(workspaceId, order.id), order)
  const { status, payment_status, payment_method, updated_at } = order
  patchLists(queryClient, workspaceId, order.id, { status, payment_status, payment_method, updated_at })
  invalidateOrder(queryClient, workspaceId, order.id)
}

/** `order.updated` frames: patch loaded rows in place and refetch the list, detail, timeline and summary. */
export function useOrderUpdates(workspaceId: string) {
  const queryClient = useQueryClient()
  useRealtimeEvent('order.updated', ({ order_id, status, payment_status }) => {
    patchLists(queryClient, workspaceId, order_id, { status, payment_status })
    void queryClient.invalidateQueries({ queryKey: orderKeys.detail(workspaceId, order_id) })
    invalidateOrder(queryClient, workspaceId, order_id)
  })
}

/**
 * `message.status` frames for a buyer notification listed on this order's timeline: refetch the timeline so a
 * delivery failure reported by Meta after sending shows up.
 */
export function useNotificationStatusUpdates(workspaceId: string, orderId: string, messageIds: ReadonlySet<string>) {
  const queryClient = useQueryClient()
  useRealtimeEvent('message.status', ({ message_id }) => {
    if (!messageIds.has(message_id)) return
    void queryClient.invalidateQueries({ queryKey: eventsKey(workspaceId, orderId) })
  })
}

/** `order.created` frames: a toast and a refreshed list and summary. */
export function useNewOrderAlerts(workspaceId: string) {
  const queryClient = useQueryClient()
  const { toast } = useToast()
  useRealtimeEvent('order.created', ({ number }) => {
    toast({ title: `New order ${number}`, tone: 'success' })
    void queryClient.invalidateQueries({ queryKey: orderKeys.lists(workspaceId) })
    void queryClient.invalidateQueries({ queryKey: summaryKey(workspaceId) })
  })
}
