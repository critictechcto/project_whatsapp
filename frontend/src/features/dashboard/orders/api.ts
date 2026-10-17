import { useQuery, useQueryClient, type InfiniteData, type QueryClient } from '@tanstack/react-query'
import { api, apiFetch, unwrap } from '../../../api/client'
import { useCursorQuery } from '../../../api/pagination'
import { workspaceKeys } from '../../../api/queryKeys'
import type { paths } from '../../../api/schema'
import type { CursorPage, Schemas } from '../../../api/types'
import { useToast } from '../../../components/app'
import { useRealtimeEvent } from '../../../lib/realtime/hooks'
import type {
  BookingWindow,
  ConfirmBookingBody,
  EventType,
  Order,
  OrderEvent,
  OrderKind,
  OrderListItem,
  OrderStatus,
  PaymentMethod,
  TransitionBody,
} from './bookingTypes'

export type { BookingWindow, ConfirmBookingBody, EventType, Order, OrderEvent, OrderKind, OrderListItem, OrderStatus, PaymentMethod, TransitionBody }
export type OrderItem = Schemas['OrderItem']
export type OrderAddress = Schemas['OrderAddress']
export type OrderSummary = Schemas['OrderSummary']
export type PaymentStatus = Schemas['PaymentStatusEnum']
export type PaymentLinkStatus = Schemas['PaymentLinkStatusEnum']
export type OrderSource = Schemas['OrderSourceEnum']
export type EventActor = Schemas['OrderEventActorEnum']
export type CancelBody = Schemas['CancelOrderRequest']

export type OrderListQuery = {
  status?: string
  stage?: 'checkout' | 'open' | 'closed'
  kind?: OrderKind
  payment_status?: PaymentStatus
  payment_method?: PaymentMethod
  created_after?: string
  created_before?: string
  search?: string
  cursor?: string
}

export const orderKeys = workspaceKeys('orders')

export const summaryKey = (workspaceId: string) => orderKeys.custom(workspaceId, 'summary')
export const eventsKey = (workspaceId: string, orderId: string) => orderKeys.custom(workspaceId, 'events', orderId)

/*
 * TODO(api:types): `kind`, `pay_at_shop`, the new statuses and the booking/offer fields aren't in the generated
 * schema yet. The casts in this file (each marked) narrow the generated types to `./bookingTypes`; drop them
 * after `npm run api:types`.
 */
type GeneratedOrderQuery = paths['/api/v1/orders/']['get']['parameters']['query']

export async function fetchOrders(query: OrderListQuery = {}, signal?: AbortSignal): Promise<CursorPage<OrderListItem>> {
  // TODO(api:types): `kind` filter and `pay_at_shop` method.
  const page = await unwrap(api.GET('/api/v1/orders/', { params: { query: query as GeneratedOrderQuery }, signal }))
  return page as unknown as CursorPage<OrderListItem> // TODO(api:types)
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
    // TODO(api:types): booking-aware `Order`.
    queryFn: async ({ signal }) => (await unwrap(api.GET('/api/v1/orders/{id}/', { params: { path: { id } }, signal }))) as unknown as Order,
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
    // TODO(api:types): new event types.
    queryFn: async ({ cursor, signal }) =>
      (await unwrap(
        api.GET('/api/v1/orders/{id}/events/', { params: { path: { id }, query: { cursor } }, signal }),
      )) as unknown as CursorPage<OrderEvent>,
  })
}

const pathOf = (id: string) => ({ params: { path: { id } } })

/** TODO(api:types): mutation responses are the booking-aware `Order`. */
const asOrder = async (request: Promise<unknown>): Promise<Order> => (await request) as Order

export const orderMutations = {
  transition: (id: string, body: TransitionBody) =>
    // TODO(api:types): `completed` and `no_show` aren't transition targets in the generated schema yet.
    asOrder(unwrap(api.POST('/api/v1/orders/{id}/transition/', { ...pathOf(id), body: body as Schemas['OrderTransitionRequest'] }))),
  cancel: (id: string, body: CancelBody) => asOrder(unwrap(api.POST('/api/v1/orders/{id}/cancel/', { ...pathOf(id), body }))),
  /** Also "Mark paid at shop" for `pay_at_shop` bookings. */
  markCodCollected: (id: string) => asOrder(unwrap(api.POST('/api/v1/orders/{id}/mark-cod-collected/', pathOf(id)))),
  markRefunded: (id: string) => asOrder(unwrap(api.POST('/api/v1/orders/{id}/mark-refunded/', pathOf(id)))),
  updateNotes: (id: string, notes: string) => asOrder(unwrap(api.PATCH('/api/v1/orders/{id}/', { ...pathOf(id), body: { notes } }))),
  // TODO(api:types): `confirm-booking` isn't in the generated schema yet, so it goes through `apiFetch`.
  confirmBooking: (id: string, body: ConfirmBookingBody) =>
    apiFetch<Order>(`/api/v1/orders/${encodeURIComponent(id)}/confirm-booking/`, { method: 'POST', body: JSON.stringify(body) }),
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
