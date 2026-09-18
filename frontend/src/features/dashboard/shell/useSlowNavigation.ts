import { useEffect, useState } from 'react'
import { useNavigation } from 'react-router'

/** Quick navigations finish before this and never flash the bar. */
const SHOW_AFTER_MS = 120

/** True while the router loads the next page, once that has taken longer than a moment. */
export function useSlowNavigation() {
  const navigation = useNavigation()
  // Identifies this navigation, so a timer from an earlier one never marks the current one slow.
  const pending = navigation.state === 'idle' ? null : (navigation.location?.key ?? navigation.state)
  const [slowKey, setSlowKey] = useState<string | null>(null)
  useEffect(() => {
    if (pending === null) return
    const timer = window.setTimeout(() => setSlowKey(pending), SHOW_AFTER_MS)
    return () => window.clearTimeout(timer)
  }, [pending])
  return pending !== null && slowKey === pending
}
