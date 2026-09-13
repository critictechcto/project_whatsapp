import { useId, useRef, useState, type KeyboardEvent, type ReactNode } from 'react'
import { cn } from '../../lib/cn'

export type TabItem = { id: string; label: string; content: ReactNode }

export function Tabs({ items, label }: { items: TabItem[]; label: string }) {
  const [active, setActive] = useState(0)
  const tabRefs = useRef<Array<HTMLButtonElement | null>>([])
  const baseId = useId()

  function onKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    const last = items.length - 1
    const next =
      event.key === 'ArrowRight'
        ? (active + 1) % items.length
        : event.key === 'ArrowLeft'
          ? (active - 1 + items.length) % items.length
          : event.key === 'Home'
            ? 0
            : event.key === 'End'
              ? last
              : null
    if (next === null) return
    event.preventDefault()
    setActive(next)
    tabRefs.current[next]?.focus()
  }

  return (
    <div>
      <div
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
              onClick={() => setActive(i)}
              className={cn(
                'relative shrink-0 whitespace-nowrap px-4 py-3 text-[14px] font-medium transition-colors',
                'after:absolute after:inset-x-3 after:bottom-0 after:h-0.5 after:transition-colors',
                selected ? 'text-ink after:bg-ink' : 'text-muted after:bg-transparent hover:text-ink',
              )}
            >
              {item.label}
            </button>
          )
        })}
      </div>
      {items.map((item, i) => (
        <div
          key={item.id}
          id={`${baseId}-panel-${item.id}`}
          role="tabpanel"
          aria-labelledby={`${baseId}-tab-${item.id}`}
          hidden={i !== active}
          tabIndex={0}
          className="tab-panel pt-10 focus-visible:outline-none"
        >
          {item.content}
        </div>
      ))}
    </div>
  )
}
