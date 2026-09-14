import type { RealtimeEventMap, RealtimeEventType, RealtimeFrame } from './events'

export type RealtimeHandler<T extends RealtimeEventType> = (
  data: RealtimeEventMap[T],
  frame: RealtimeFrame<T>,
) => void

type AnyHandler = (data: unknown, frame: RealtimeFrame) => void

const handlers = new Map<RealtimeEventType, Set<AnyHandler>>()

/** Registers a handler for one event type. Returns an unsubscribe function. */
export function subscribe<T extends RealtimeEventType>(type: T, handler: RealtimeHandler<T>): () => void {
  let set = handlers.get(type)
  if (!set) {
    set = new Set()
    handlers.set(type, set)
  }
  const entry = handler as unknown as AnyHandler
  set.add(entry)
  return () => {
    set.delete(entry)
  }
}

/** Delivers a frame to every handler of its type. A throwing handler does not block the others. */
export function dispatch(frame: RealtimeFrame): void {
  const set = handlers.get(frame.type)
  if (!set) return
  for (const handler of [...set]) {
    try {
      handler(frame.data, frame)
    } catch (error) {
      console.error(`[realtime] handler for ${frame.type} failed`, error)
    }
  }
}

/** Test helper. */
export function clearSubscriptions(): void {
  handlers.clear()
}
