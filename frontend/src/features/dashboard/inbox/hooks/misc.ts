import { useEffect, useState, useSyncExternalStore } from 'react'
import { fetchMessageMedia } from '../api'

/** Current time, refreshed every `intervalMs`, for countdowns and relative times. */
export function useNow(intervalMs = 15_000): number {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), intervalMs)
    return () => clearInterval(timer)
  }, [intervalMs])
  return now
}

function subscribeVisibility(listener: () => void) {
  document.addEventListener('visibilitychange', listener)
  return () => document.removeEventListener('visibilitychange', listener)
}

/** True while the tab is visible (read receipts wait until the agent can actually see the thread). */
export function useDocumentVisible(): boolean {
  return useSyncExternalStore(
    subscribeVisibility,
    () => document.visibilityState !== 'hidden',
    () => true,
  )
}

/** Returns `value` once it has stopped changing for `delayMs`. */
export function useDebouncedValue<T>(value: T, delayMs = 300): T {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delayMs)
    return () => clearTimeout(timer)
  }, [value, delayMs])
  return debounced
}

type MediaState = { messageId: string; url?: string; failed?: boolean }

/**
 * Loads a message's media (auth-protected) as an object URL while `enabled`. Revoked on unmount.
 * `url` stays undefined where object URLs aren't supported (tests).
 */
export function useMediaObjectUrl(messageId: string, enabled: boolean) {
  const [state, setState] = useState<MediaState>({ messageId })

  useEffect(() => {
    if (!enabled) return
    const controller = new AbortController()
    let url: string | null = null
    fetchMessageMedia(messageId, controller.signal)
      .then((blob) => {
        if (controller.signal.aborted || typeof URL.createObjectURL !== 'function') return
        url = URL.createObjectURL(blob)
        setState({ messageId, url })
      })
      .catch(() => {
        if (!controller.signal.aborted) setState({ messageId, failed: true })
      })
    return () => {
      controller.abort()
      if (url) URL.revokeObjectURL(url)
    }
  }, [messageId, enabled])

  const current = state.messageId === messageId ? state : { messageId }
  return { url: current.url, failed: Boolean(current.failed), loading: enabled && !current.url && !current.failed }
}

/** Downloads a message's media file through the authenticated client. */
export async function downloadMessageMedia(messageId: string, fileName: string) {
  const blob = await fetchMessageMedia(messageId)
  if (typeof URL.createObjectURL !== 'function') return
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = fileName || 'attachment'
  document.body.appendChild(link)
  link.click()
  link.remove()
  setTimeout(() => URL.revokeObjectURL(url), 10_000)
}
