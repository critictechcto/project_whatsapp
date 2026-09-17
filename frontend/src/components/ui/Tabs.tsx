import {
  useEffect,
  useId,
  useRef,
  useState,
  type CSSProperties,
  type FocusEvent,
  type KeyboardEvent,
  type ReactNode,
} from 'react'
import { useOnScreen } from '../../features/landing/lib/useOnScreen'
import { cn } from '../../lib/cn'
import { usePrefersReducedMotion } from '../../lib/motion'
import './Tabs.css'

export type TabItem = { id: string; label: string; content: ReactNode }

type TabsProps = {
  items: TabItem[]
  label: string
  /**
   * Moves to the next tab after this many milliseconds, with a countdown line on the active tab.
   * It runs only while the tabs are on screen, pauses while hovered or focused, and stops for good
   * once the visitor picks a tab. Off with reduced motion.
   */
  autoAdvanceMs?: number
}

type Direction = 'forward' | 'back'

export function Tabs({ items, label, autoAdvanceMs }: TabsProps) {
  const [active, setActive] = useState(0)
  const [direction, setDirection] = useState<Direction>('forward')
  const [userPicked, setUserPicked] = useState(false)
  const [hovered, setHovered] = useState(false)
  const [focused, setFocused] = useState(false)
  const reducedMotion = usePrefersReducedMotion()
  const rootRef = useRef<HTMLDivElement | null>(null)
  const tabRefs = useRef<Array<HTMLButtonElement | null>>([])
  const baseId = useId()
  const onScreen = useOnScreen(rootRef, '0px')

  const autoAdvance = Boolean(autoAdvanceMs) && !userPicked && !reducedMotion && items.length > 1
  const running = autoAdvance && onScreen && !hovered && !focused
  const count = items.length

  // Time left on the active tab's countdown, kept across pauses.
  const remainingRef = useRef(autoAdvanceMs ?? 0)
  useEffect(() => {
    remainingRef.current = autoAdvanceMs ?? 0
  }, [active, autoAdvanceMs])

  useEffect(() => {
    if (!running) return
    const startedAt = Date.now()
    const timer = window.setTimeout(() => {
      setDirection('forward')
      setActive((current) => (current + 1) % count)
    }, remainingRef.current)
    return () => {
      window.clearTimeout(timer)
      remainingRef.current = Math.max(0, remainingRef.current - (Date.now() - startedAt))
    }
  }, [running, active, count])

  // Where the tab strip scrolls sideways (phones), keep the active tab in view as it changes,
  // including when it auto-advances. Only the strip scrolls, never the page.
  const tablistRef = useRef<HTMLDivElement | null>(null)
  useEffect(() => {
    const list = tablistRef.current
    const tab = tabRefs.current[active]
    if (!list || !tab || list.scrollWidth <= list.clientWidth) return
    const listRect = list.getBoundingClientRect()
    const tabRect = tab.getBoundingClientRect()
    const inset = 20
    let delta = 0
    if (tabRect.left < listRect.left + inset) delta = tabRect.left - listRect.left - inset
    else if (tabRect.right > listRect.right - inset) delta = tabRect.right - listRect.right + inset
    if (delta !== 0) {
      list.scrollTo({ left: list.scrollLeft + delta, behavior: reducedMotion ? 'auto' : 'smooth' })
    }
  }, [active, reducedMotion])

  function select(next: Direction | null, index: number) {
    setUserPicked(true)
    if (index === active) return
    setDirection(next ?? (index > active ? 'forward' : 'back'))
    setActive(index)
  }

  function onKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    const last = count - 1
    const move: [Direction, number] | null =
      event.key === 'ArrowRight'
        ? ['forward', (active + 1) % count]
        : event.key === 'ArrowLeft'
          ? ['back', (active - 1 + count) % count]
          : event.key === 'Home'
            ? ['back', 0]
            : event.key === 'End'
              ? ['forward', last]
              : null
    if (move === null) return
    event.preventDefault()
    select(move[0], move[1])
    tabRefs.current[move[1]]?.focus()
  }

  function onBlur(event: FocusEvent<HTMLDivElement>) {
    if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setFocused(false)
  }

  return (
    <div
      ref={rootRef}
      data-auto-advance={autoAdvance ? (running ? 'running' : 'paused') : undefined}
      onPointerEnter={(event) => {
        if (event.pointerType === 'mouse') setHovered(true)
      }}
      onPointerLeave={() => setHovered(false)}
      onFocus={() => setFocused(true)}
      onBlur={onBlur}
    >
      <div
        ref={tablistRef}
        role="tablist"
        aria-label={label}
        onKeyDown={onKeyDown}
        className="-mx-5 flex overflow-x-auto border-b border-line px-5 md:mx-0 md:flex-wrap md:px-0"
      >
        {items.map((item, i) => {
          const selected = i === active
          return (
            <button
              key={item.id}
              ref={(el) => {
                tabRefs.current[i] = el
              }}
              id={`${baseId}-tab-${item.id}`}
              role="tab"
              type="button"
              aria-selected={selected}
              aria-controls={`${baseId}-panel-${item.id}`}
              tabIndex={selected ? 0 : -1}
              onClick={() => select(null, i)}
              className={cn(
                'relative shrink-0 whitespace-nowrap px-4 py-3 text-[14px] font-medium transition-colors max-md:min-h-11',
                'after:absolute after:inset-x-3 after:bottom-0 after:h-0.5 after:transition-colors',
                selected && autoAdvance && 'after:opacity-15',
                selected ? 'text-ink after:bg-ink' : 'text-muted after:bg-transparent hover:text-ink',
              )}
            >
              {item.label}
              {selected && autoAdvance && (
                <span
                  key={active}
                  aria-hidden="true"
                  data-running={running}
                  className="tabs-progress"
                  style={{ '--tabs-duration': `${autoAdvanceMs}ms` } as CSSProperties}
                />
              )}
            </button>
          )
        })}
      </div>
      <div className="tabs-stage">
        {items.map((item, i) => (
          <div
            key={item.id}
            id={`${baseId}-panel-${item.id}`}
            role="tabpanel"
            aria-labelledby={`${baseId}-tab-${item.id}`}
            hidden={i !== active}
            tabIndex={0}
            data-direction={direction}
            className="tabs-panel pt-10 focus-visible:outline-none max-md:pt-8"
          >
            {item.content}
          </div>
        ))}
      </div>
    </div>
  )
}
