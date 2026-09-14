import { useId, useRef, type KeyboardEvent, type ReactNode } from 'react'
import { cn } from '../../lib/cn'

export type TabOption<V extends string> = { value: V; label: ReactNode; count?: number; disabled?: boolean }

type TabsProps<V extends string> = {
  /** Accessible name of the tab list. */
  label: string
  items: readonly TabOption<V>[]
  value: V
  onValueChange: (value: V) => void
  /** Content of the active tab. Omit to render only the tab list (e.g. as a filter bar). */
  children?: ReactNode
  className?: string
}

/** Controlled tabs with roving focus: arrows move, Home/End jump, activation follows focus. */
export function Tabs<V extends string>({ label, items, value, onValueChange, children, className }: TabsProps<V>) {
  const baseId = useId()
  const refs = useRef<Array<HTMLButtonElement | null>>([])
  const enabled = items.filter((item) => !item.disabled)

  function onKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    const index = enabled.findIndex((item) => item.value === value)
    let next: number | null = null
    if (event.key === 'ArrowRight') next = (index + 1) % enabled.length
    else if (event.key === 'ArrowLeft') next = (index - 1 + enabled.length) % enabled.length
    else if (event.key === 'Home') next = 0
    else if (event.key === 'End') next = enabled.length - 1
    if (next === null) return
    event.preventDefault()
    const target = enabled[next]
    onValueChange(target.value)
    refs.current[items.indexOf(target)]?.focus()
  }

  const panelId = `${baseId}-panel`

  return (
    <div className={className}>
      <div role="tablist" aria-label={label} onKeyDown={onKeyDown} className="flex gap-1 overflow-x-auto border-b border-line">
        {items.map((item, i) => {
          const selected = item.value === value
          return (
            <button
              key={item.value}
              ref={(el) => {
                refs.current[i] = el
              }}
              id={`${baseId}-tab-${item.value}`}
              type="button"
              role="tab"
              aria-selected={selected}
              aria-controls={children !== undefined ? panelId : undefined}
              tabIndex={selected ? 0 : -1}
              disabled={item.disabled}
              onClick={() => onValueChange(item.value)}
              className={cn(
                'relative inline-flex h-10 shrink-0 items-center gap-2 px-3 text-sm font-medium transition-colors disabled:opacity-40',
                'after:absolute after:inset-x-2 after:bottom-[-1px] after:h-0.5',
                selected ? 'text-ink after:bg-ink' : 'text-muted after:bg-transparent hover:text-ink',
              )}
            >
              {item.label}
              {item.count !== undefined && (
                <span className="rounded-full bg-paper-2 px-1.5 font-mono text-[11px] text-muted">{item.count}</span>
              )}
            </button>
          )
        })}
      </div>
      {children !== undefined && (
        <div id={panelId} role="tabpanel" aria-labelledby={`${baseId}-tab-${value}`} tabIndex={0} className="pt-5 focus-visible:outline-none">
          {children}
        </div>
      )}
    </div>
  )
}
