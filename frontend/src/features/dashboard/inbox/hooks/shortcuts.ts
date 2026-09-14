import { useEffect, useRef } from 'react'
import { isTypingTarget } from '../utils'

type ShortcutOptions = {
  /** Conversation ids in list order. */
  ids: readonly string[]
  activeId: string | undefined
  onNavigate: (id: string) => void
  onFocusSearch: () => void
  onFocusComposer: () => void
  onHelp: () => void
}

/**
 * Inbox shortcuts: `j`/`k` next/previous conversation, `/` search, `r` reply box, `?` help.
 * Ignored while typing, with modifier keys, or when a dialog is open.
 */
export function useInboxShortcuts(options: ShortcutOptions) {
  const ref = useRef(options)
  useEffect(() => {
    ref.current = options
  })

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.defaultPrevented || event.metaKey || event.ctrlKey || event.altKey || isTypingTarget(event.target)) return
      if (document.querySelector('[aria-modal="true"]')) return
      const { ids, activeId, onNavigate, onFocusSearch, onFocusComposer, onHelp } = ref.current

      if (event.key === 'j' || event.key === 'k') {
        if (!ids.length) return
        const index = activeId ? ids.indexOf(activeId) : -1
        const next = event.key === 'j' ? Math.min(ids.length - 1, index + 1) : index <= 0 ? 0 : index - 1
        const id = ids[next]
        if (!id || id === activeId) return
        event.preventDefault()
        onNavigate(id)
        requestAnimationFrame(() => {
          document.querySelector<HTMLElement>(`[data-conversation-id="${id}"]`)?.scrollIntoView({ block: 'nearest' })
        })
      } else if (event.key === '/') {
        event.preventDefault()
        onFocusSearch()
      } else if (event.key === 'r') {
        event.preventDefault()
        onFocusComposer()
      } else if (event.key === '?') {
        event.preventDefault()
        onHelp()
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [])
}
