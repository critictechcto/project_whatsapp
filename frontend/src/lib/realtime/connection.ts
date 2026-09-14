import { parseFrame, type RealtimeFrame } from './events'
import { dispatch } from './registry'

export type ConnectionStatus = 'idle' | 'connecting' | 'open' | 'reconnecting' | 'closed'

type SocketLike = {
  onopen: ((event: Event) => void) | null
  onmessage: ((event: MessageEvent) => void) | null
  onclose: ((event: CloseEvent) => void) | null
  onerror: ((event: Event) => void) | null
  close(code?: number, reason?: string): void
}

export type RealtimeConnectionOptions = {
  workspaceId: string
  /** Fetches a single-use ticket (`POST /api/v1/inbox/ws-ticket/`). */
  getTicket: (workspaceId: string) => Promise<{ ticket: string; path?: string }>
  /** WebSocket origin, e.g. `wss://api.upchatz.com`. */
  wsUrl: string
  createSocket?: (url: string) => SocketLike
  /** Defaults to the global registry `dispatch`. */
  onFrame?: (frame: RealtimeFrame) => void
  /** Called after a reconnect: events may have been missed, so refetch. */
  onReconnect?: () => void
  /** `session.revoked`: the connection is stopped; refresh memberships. */
  onSessionRevoked?: (reason: string) => void
  onStatusChange?: (status: ConnectionStatus) => void
  backoff?: { baseMs?: number; maxMs?: number }
  random?: () => number
}

/** Delay before reconnect attempt `attempt` (0-based): exponential with jitter, capped. */
export function backoffDelay(attempt: number, baseMs = 1000, maxMs = 30_000, random: () => number = Math.random) {
  const exp = Math.min(maxMs, baseMs * 2 ** attempt)
  return Math.round(exp / 2 + (exp / 2) * random())
}

/**
 * One WebSocket per workspace. Gets a fresh ticket per attempt, reconnects with backoff,
 * and reports reconnects so callers can refetch what they may have missed.
 */
export class RealtimeConnection {
  private readonly options: RealtimeConnectionOptions
  private socket: SocketLike | null = null
  private timer: ReturnType<typeof setTimeout> | null = null
  private attempt = 0
  private hasOpened = false
  private stopped = true
  private status: ConnectionStatus = 'idle'

  constructor(options: RealtimeConnectionOptions) {
    this.options = options
  }

  getStatus() {
    return this.status
  }

  start() {
    if (!this.stopped) return
    this.stopped = false
    if (typeof window !== 'undefined') window.addEventListener('online', this.handleOnline)
    void this.connect()
  }

  stop() {
    this.stopped = true
    if (typeof window !== 'undefined') window.removeEventListener('online', this.handleOnline)
    if (this.timer) clearTimeout(this.timer)
    this.timer = null
    const socket = this.socket
    this.socket = null
    if (socket) {
      socket.onclose = null
      socket.onmessage = null
      socket.close(1000, 'client stop')
    }
    this.setStatus('closed')
  }

  private readonly handleOnline = () => {
    if (this.stopped || this.status === 'open' || this.status === 'connecting') return
    if (this.timer) clearTimeout(this.timer)
    this.timer = null
    void this.connect()
  }

  private setStatus(status: ConnectionStatus) {
    if (this.status === status) return
    this.status = status
    this.options.onStatusChange?.(status)
  }

  private async connect() {
    if (this.stopped) return
    this.setStatus(this.hasOpened ? 'reconnecting' : 'connecting')

    let ticket: { ticket: string; path?: string }
    try {
      ticket = await this.options.getTicket(this.options.workspaceId)
    } catch {
      this.scheduleReconnect()
      return
    }
    if (this.stopped) return

    const path = ticket.path || '/ws/v1/'
    const url = `${this.options.wsUrl.replace(/\/+$/, '')}${path}?ticket=${encodeURIComponent(ticket.ticket)}`
    const create = this.options.createSocket ?? ((target: string) => new WebSocket(target) as SocketLike)

    let socket: SocketLike
    try {
      socket = create(url)
    } catch {
      this.scheduleReconnect()
      return
    }
    this.socket = socket

    socket.onopen = () => {
      const reconnected = this.hasOpened
      this.hasOpened = true
      this.attempt = 0
      this.setStatus('open')
      if (reconnected) this.options.onReconnect?.()
    }

    socket.onmessage = (event) => {
      const frame = parseFrame(event.data)
      if (!frame) return
      if (frame.type === 'session.revoked') {
        ;(this.options.onFrame ?? dispatch)(frame)
        this.stop()
        this.options.onSessionRevoked?.(frame.data.reason)
        return
      }
      if (frame.workspace_id !== this.options.workspaceId) return
      ;(this.options.onFrame ?? dispatch)(frame)
    }

    socket.onerror = () => {
      // `onclose` follows and handles the reconnect.
    }

    socket.onclose = () => {
      if (this.socket === socket) this.socket = null
      if (this.stopped) return
      this.scheduleReconnect()
    }
  }

  private scheduleReconnect() {
    if (this.stopped) return
    const { baseMs, maxMs } = this.options.backoff ?? {}
    const delay = backoffDelay(this.attempt, baseMs, maxMs, this.options.random)
    this.attempt += 1
    this.setStatus('reconnecting')
    this.timer = setTimeout(() => {
      this.timer = null
      void this.connect()
    }, delay)
  }
}
