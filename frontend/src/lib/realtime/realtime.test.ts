import { afterEach, describe, expect, it, vi } from 'vitest'
import { mockRealtime } from '../../mocks/realtime'
import { backoffDelay, RealtimeConnection } from './connection'
import { parseFrame, type RealtimeFrame } from './events'
import { dispatch, subscribe } from './registry'

const conversationUpdated = (workspaceId: string): RealtimeFrame<'conversation.updated'> => ({
  v: 1,
  type: 'conversation.updated',
  workspace_id: workspaceId,
  data: { conversation_id: 'conv-1' },
})

class FakeSocket {
  onopen: ((event: Event) => void) | null = null
  onmessage: ((event: MessageEvent) => void) | null = null
  onclose: ((event: CloseEvent) => void) | null = null
  onerror: ((event: Event) => void) | null = null
  closed = false
  readonly url: string

  constructor(url: string) {
    this.url = url
  }

  close() {
    this.closed = true
  }

  open() {
    this.onopen?.(new Event('open'))
  }

  receive(frame: unknown) {
    this.onmessage?.(new MessageEvent('message', { data: JSON.stringify(frame) }))
  }

  drop() {
    this.onclose?.(new CloseEvent('close'))
  }
}

afterEach(() => {
  vi.useRealTimers()
})

describe('realtime registry', () => {
  it('delivers frames to subscribers of that type until they unsubscribe', () => {
    const onConversation = vi.fn()
    const onStatus = vi.fn()
    const unsubscribe = subscribe('conversation.updated', onConversation)
    subscribe('message.status', onStatus)

    const frame = conversationUpdated('ws-1')
    dispatch(frame)
    expect(onConversation).toHaveBeenCalledWith({ conversation_id: 'conv-1' }, frame)
    expect(onStatus).not.toHaveBeenCalled()

    unsubscribe()
    dispatch(frame)
    expect(onConversation).toHaveBeenCalledTimes(1)
  })

  it('keeps delivering when one handler throws', () => {
    vi.spyOn(console, 'error').mockImplementation(() => {})
    const healthy = vi.fn()
    subscribe('conversation.updated', () => {
      throw new Error('boom')
    })
    subscribe('conversation.updated', healthy)

    dispatch(conversationUpdated('ws-1'))
    expect(healthy).toHaveBeenCalledOnce()
  })
})

describe('parseFrame', () => {
  it('accepts v1 frames of known types only', () => {
    expect(parseFrame(JSON.stringify(conversationUpdated('ws-1')))).toEqual(conversationUpdated('ws-1'))
    expect(parseFrame({ ...conversationUpdated('ws-1'), v: 2 })).toBeNull()
    expect(parseFrame({ ...conversationUpdated('ws-1'), type: 'contact.deleted' })).toBeNull()
    expect(parseFrame('not json')).toBeNull()
  })

  it('accepts the wave-3 commerce frames and dispatches them by type', () => {
    const frames: RealtimeFrame[] = [
      { v: 1, type: 'order.created', workspace_id: 'ws-1', data: { order_id: 'o-1', number: 'SS-1001', status: 'confirmed' } },
      { v: 1, type: 'order.updated', workspace_id: 'ws-1', data: { order_id: 'o-1', status: 'shipped', payment_status: 'cod_pending' } },
      { v: 1, type: 'catalog.sync', workspace_id: 'ws-1', data: { meta_catalog_id: 'mc-1', status: 'synced' } },
      { v: 1, type: 'alert_recipient.updated', workspace_id: 'ws-1', data: { recipient_id: 'r-1', status: 'verified' } },
    ]
    const onOrderUpdated = vi.fn()
    subscribe('order.updated', onOrderUpdated)

    for (const frame of frames) {
      const parsed = parseFrame(JSON.stringify(frame))
      expect(parsed).toEqual(frame)
      if (parsed) dispatch(parsed)
    }
    expect(onOrderUpdated).toHaveBeenCalledOnce()
    expect(onOrderUpdated).toHaveBeenCalledWith({ order_id: 'o-1', status: 'shipped', payment_status: 'cod_pending' }, frames[1])
  })
})

describe('RealtimeConnection', () => {
  function setup() {
    vi.useFakeTimers()
    const sockets: FakeSocket[] = []
    const onReconnect = vi.fn()
    const onSessionRevoked = vi.fn()
    const getTicket = vi.fn(async () => ({ ticket: `t/${getTicket.mock.calls.length}` }))
    const connection = new RealtimeConnection({
      workspaceId: 'ws-1',
      wsUrl: 'wss://api.example.com/',
      getTicket,
      createSocket: (url) => {
        const socket = new FakeSocket(url)
        sockets.push(socket)
        return socket
      },
      onReconnect,
      onSessionRevoked,
      backoff: { baseMs: 1000, maxMs: 30_000 },
      random: () => 1,
    })
    return { sockets, onReconnect, onSessionRevoked, getTicket, connection }
  }

  it('connects with a ticket and dispatches frames for its workspace only', async () => {
    const { sockets, connection } = setup()
    const received = vi.fn()
    subscribe('conversation.updated', received)

    connection.start()
    await vi.advanceTimersByTimeAsync(0)
    expect(sockets[0].url).toBe('wss://api.example.com/ws/v1/?ticket=t%2F1')

    sockets[0].open()
    sockets[0].receive(conversationUpdated('ws-2'))
    sockets[0].receive(conversationUpdated('ws-1'))
    expect(received).toHaveBeenCalledTimes(1)
    expect(connection.getStatus()).toBe('open')
    connection.stop()
  })

  it('reconnects with backoff and a fresh ticket, then asks callers to refetch', async () => {
    const { sockets, onReconnect, getTicket, connection } = setup()
    connection.start()
    await vi.advanceTimersByTimeAsync(0)
    sockets[0].open()
    expect(onReconnect).not.toHaveBeenCalled()

    sockets[0].drop()
    expect(connection.getStatus()).toBe('reconnecting')
    await vi.advanceTimersByTimeAsync(999)
    expect(sockets).toHaveLength(1)
    await vi.advanceTimersByTimeAsync(1)
    expect(sockets).toHaveLength(2)
    expect(getTicket).toHaveBeenCalledTimes(2)

    sockets[1].open()
    expect(onReconnect).toHaveBeenCalledOnce()
    connection.stop()
  })

  it('stops on session.revoked', async () => {
    const { sockets, onSessionRevoked, connection } = setup()
    connection.start()
    await vi.advanceTimersByTimeAsync(0)
    sockets[0].open()

    sockets[0].receive({ v: 1, type: 'session.revoked', workspace_id: 'ws-1', data: { reason: 'membership_removed' } })
    expect(onSessionRevoked).toHaveBeenCalledWith('membership_removed')
    expect(sockets[0].closed).toBe(true)
    expect(connection.getStatus()).toBe('closed')

    await vi.advanceTimersByTimeAsync(60_000)
    expect(sockets).toHaveLength(1)
  })

  it('caps the backoff delay', () => {
    expect(backoffDelay(0, 1000, 30_000, () => 1)).toBe(1000)
    expect(backoffDelay(3, 1000, 30_000, () => 1)).toBe(8000)
    expect(backoffDelay(10, 1000, 30_000, () => 1)).toBe(30_000)
    expect(backoffDelay(10, 1000, 30_000, () => 0)).toBe(15_000)
  })
})

describe('mock realtime emitter', () => {
  it('uses the same registry as the real socket', () => {
    const received = vi.fn()
    const onRevoked = vi.fn()
    subscribe('conversation.updated', received)
    const disconnect = mockRealtime.connect('ws-1', onRevoked)

    mockRealtime.emit('conversation.updated', { conversation_id: 'conv-1' }, 'ws-1')
    mockRealtime.emit('conversation.updated', { conversation_id: 'conv-2' }, 'ws-2')
    expect(received).toHaveBeenCalledTimes(1)

    mockRealtime.emit('session.revoked', { reason: 'logged_out' }, 'ws-1')
    expect(onRevoked).toHaveBeenCalledWith('logged_out')
    expect(mockRealtime.isConnected('ws-1')).toBe(false)
    disconnect()
  })
})
