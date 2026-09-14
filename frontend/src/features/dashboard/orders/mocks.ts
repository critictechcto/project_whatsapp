import type { Schemas } from '../../../api/types'
import { mockRealtime } from '../../../mocks/realtime'
import { ids } from '../../../mocks/seed'
import { authorize, errorResponse, http, mockDelay, notFound, paginate, validationError, type MockErrorResponse } from '../../../mocks/utils'
import type { AreaMockHandlers } from '../registry/types'
import { orderStatusInfo, orderTransitions } from './labels'
import {
  addEvent,
  createMockOrder,
  filterOrders,
  findOrder,
  orderSummary,
  toListItem,
  toOrder,
  type OrderRecord,
} from './mockState'

type OrderStatus = Schemas['OrderStatusEnum']

const transitionTargets: readonly string[] = ['confirmed', 'packed', 'shipped', 'delivered']

function emitUpdated(record: OrderRecord) {
  const { id, status, payment_status } = record.order
  mockRealtime.emit('order.updated', { order_id: id, status, payment_status }, record.workspaceId)
}

function invalidTransition(record: OrderRecord, to: OrderStatus, message?: string): MockErrorResponse {
  const from = record.order.status
  return errorResponse(
    409,
    'invalid_order_transition',
    message ?? `A ${orderStatusInfo[from].label.toLowerCase()} order can't be moved to ${orderStatusInfo[to].label.toLowerCase()}.`,
    { from_status: from, to_status: to, allowed: [...orderTransitions[from]] },
  )
}

function notifyEvent(record: OrderRecord, notify: boolean | undefined, detail: string) {
  if (notify === false) return
  addEvent(record, 'notification_sent', 'system', { detail })
}

type Loaded = { record: OrderRecord; userId: string } | { error: MockErrorResponse }

function load(request: Request, id: string, minRole: 'viewer' | 'agent' | 'admin'): Loaded {
  const ctx = authorize(request, minRole)
  if (ctx instanceof Response) return { error: ctx }
  const record = findOrder(ctx.workspace.id, id)
  return record ? { record, userId: ctx.user.id } : { error: notFound() }
}

const isHttps = (value: string) => {
  try {
    return new URL(value).protocol === 'https:'
  } catch {
    return false
  }
}

export const handlers: AreaMockHandlers = [
  http.get('/api/v1/orders/', ({ request, query, response }) => {
    const ctx = authorize(request)
    if (ctx instanceof Response) return response.untyped(ctx)
    const items = filterOrders(ctx.workspace.id, {
      status: query.get('status'),
      stage: query.get('stage'),
      payment_status: query.get('payment_status'),
      payment_method: query.get('payment_method'),
      contact: query.get('contact'),
      search: query.get('search'),
      created_after: query.get('created_after'),
      created_before: query.get('created_before'),
    }).map(toListItem)
    return response(200).json(paginate(request, items))
  }),

  http.get('/api/v1/orders/summary/', ({ request, response }) => {
    const ctx = authorize(request)
    if (ctx instanceof Response) return response.untyped(ctx)
    return response(200).json(orderSummary(ctx.workspace.id))
  }),

  http.get('/api/v1/orders/{id}/', ({ request, params, response }) => {
    const loaded = load(request, params.id, 'viewer')
    return 'error' in loaded ? response.untyped(loaded.error) : response(200).json(toOrder(loaded.record))
  }),

  http.patch('/api/v1/orders/{id}/', async ({ request, params, response }) => {
    await mockDelay(150)
    const loaded = load(request, params.id, 'agent')
    if ('error' in loaded) return response.untyped(loaded.error)
    const body = (await request.json()) as Partial<Schemas['PatchedOrderNotesRequest']>
    const notes = body.notes ?? ''
    if (notes.length > 2000) return response.untyped(validationError({ notes: ['Ensure this field has no more than 2000 characters.'] }))
    loaded.record.order.notes = notes
    addEvent(loaded.record, 'note', 'dashboard', { detail: 'Updated the seller notes.', userId: loaded.userId })
    return response(200).json(toOrder(loaded.record))
  }),

  http.get('/api/v1/orders/{id}/events/', ({ request, params, response }) => {
    const loaded = load(request, params.id, 'viewer')
    if ('error' in loaded) return response.untyped(loaded.error)
    const events = [...loaded.record.events].sort((a, b) => a.created_at.localeCompare(b.created_at))
    return response(200).json(paginate(request, events))
  }),

  http.post('/api/v1/orders/{id}/transition/', async ({ request, params, response }) => {
    await mockDelay()
    const loaded = load(request, params.id, 'agent')
    if ('error' in loaded) return response.untyped(loaded.error)
    const { record, userId } = loaded
    const order = record.order
    const body = (await request.json()) as Partial<Schemas['OrderTransitionRequest']>
    const to = body.to_status as OrderStatus | undefined

    if (!to || !transitionTargets.includes(to)) {
      return response.untyped(validationError({ to_status: [`"${String(to)}" is not a valid choice.`] }))
    }
    if (!orderTransitions[order.status].includes(to)) return response.untyped(invalidTransition(record, to))

    if (to === 'shipped') {
      const errors: Record<string, string[]> = {}
      if (!body.courier_name?.trim()) errors.courier_name = ['Enter the courier name.']
      if (!body.awb_number?.trim()) errors.awb_number = ['Enter the AWB number.']
      if (body.tracking_url && !isHttps(body.tracking_url)) errors.tracking_url = ['Enter an https:// link.']
      if (Object.keys(errors).length) return response.untyped(validationError(errors))
    }

    const from = order.status
    const now = new Date().toISOString()
    let detail = ''
    if (to === 'confirmed') order.confirmed_at = now
    if (to === 'packed') order.packed_at = now
    if (to === 'delivered') order.delivered_at = now
    if (to === 'shipped') {
      order.courier_name = body.courier_name!.trim()
      order.awb_number = body.awb_number!.trim()
      order.tracking_url = body.tracking_url?.trim() ?? ''
      order.shipped_at = now
      detail = `${order.courier_name}, AWB ${order.awb_number}`
    }
    order.status = to
    addEvent(record, 'status_changed', 'dashboard', { from, to, detail, userId })
    notifyEvent(record, body.notify_buyer, `Told the buyer the order is ${orderStatusInfo[to].label.toLowerCase()}.`)
    emitUpdated(record)
    return response(200).json(toOrder(record))
  }),

  http.post('/api/v1/orders/{id}/cancel/', async ({ request, params, response }) => {
    await mockDelay()
    const loaded = load(request, params.id, 'agent')
    if ('error' in loaded) return response.untyped(loaded.error)
    const { record, userId } = loaded
    const order = record.order
    const body = (await request.json()) as Partial<Schemas['CancelOrderRequest']>
    const reason = body.reason ?? ''

    if (reason.length > 200) return response.untyped(validationError({ reason: ['Ensure this field has no more than 200 characters.'] }))
    if (!orderTransitions[order.status].includes('cancelled')) return response.untyped(invalidTransition(record, 'cancelled'))

    const from = order.status
    order.status = 'cancelled'
    order.cancel_reason = reason
    order.cancelled_at = new Date().toISOString()
    if (order.payment_status === 'cod_pending') order.payment_status = 'unpaid'
    if (order.payment_link && (order.payment_link.status === 'created' || order.payment_link.status === 'creating')) {
      order.payment_link = { ...order.payment_link, status: 'cancelled' }
    }
    addEvent(record, 'status_changed', 'dashboard', { from, to: 'cancelled', detail: reason, userId })
    if (body.restock !== false) addEvent(record, 'stock_released', 'system', { detail: 'Items went back to stock.' })
    notifyEvent(record, body.notify_buyer, 'Told the buyer the order was cancelled.')
    emitUpdated(record)
    return response(200).json(toOrder(record))
  }),

  http.post('/api/v1/orders/{id}/mark-cod-collected/', async ({ request, params, response }) => {
    await mockDelay()
    const loaded = load(request, params.id, 'agent')
    if ('error' in loaded) return response.untyped(loaded.error)
    const { record, userId } = loaded
    const order = record.order
    const eligible = order.payment_method === 'cod' && order.payment_status === 'cod_pending' && ['shipped', 'delivered'].includes(order.status)
    if (!eligible) {
      return response.untyped(invalidTransition(record, order.status, 'Only cash on delivery orders that are shipped or delivered and not yet collected can be marked collected.'))
    }
    order.payment_status = 'cod_collected'
    addEvent(record, 'cod_collected', 'dashboard', { userId })
    emitUpdated(record)
    return response(200).json(toOrder(record))
  }),

  http.post('/api/v1/orders/{id}/mark-refunded/', async ({ request, params, response }) => {
    await mockDelay()
    const loaded = load(request, params.id, 'admin')
    if ('error' in loaded) return response.untyped(loaded.error)
    const { record, userId } = loaded
    const order = record.order
    if (order.payment_status !== 'paid' || !['cancelled', 'needs_attention'].includes(order.status)) {
      return response.untyped(invalidTransition(record, order.status, 'Only paid orders that are cancelled or need attention can be marked refunded.'))
    }
    order.payment_status = 'refunded_manual'
    addEvent(record, 'refunded_manual', 'dashboard', { detail: 'Refunded in the payment gateway.', userId })
    emitUpdated(record)
    return response(200).json(toOrder(record))
  }),
]

// Demo only: a new order arrives about every 45 seconds while the dashboard is open, so the list,
// summary and toasts feel live. Tests create orders explicitly with `createMockOrder`.
const EMITTER_KEY = '__upchatzOrderEmitter'
if (import.meta.env.MODE !== 'test' && typeof window !== 'undefined') {
  const scope = window as unknown as Record<string, number | undefined>
  if (scope[EMITTER_KEY] !== undefined) window.clearInterval(scope[EMITTER_KEY])
  scope[EMITTER_KEY] = window.setInterval(() => {
    if (!mockRealtime.isConnected(ids.sharmaSweets)) return
    const record = createMockOrder(ids.sharmaSweets)
    const { id, number, status } = record.order
    mockRealtime.emit('order.created', { order_id: id, number, status }, ids.sharmaSweets)
  }, 45_000)
}
