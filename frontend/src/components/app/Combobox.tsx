import { useId, useMemo, useRef, useState, type KeyboardEvent, type ReactNode } from 'react'
import { autoUpdate, flip, FloatingPortal, offset, size, useDismiss, useFloating, useInteractions } from '@floating-ui/react'
import { Check, ChevronDown, X } from 'lucide-react'
import { cn } from '../../lib/cn'
import { useFieldControl } from './fieldContext'
import { Spinner } from './Spinner'
import { controlClasses, popoverClasses } from './styles'

export type ComboboxOption = {
  value: string
  label: string
  description?: ReactNode
  disabled?: boolean
}

type BaseProps = {
  options: readonly ComboboxOption[]
  placeholder?: string
  disabled?: boolean
  loading?: boolean
  emptyText?: ReactNode
  /** Called when the search text changes; set `filter={false}` when options are filtered server-side. */
  onSearchChange?: (query: string) => void
  filter?: boolean
  id?: string
  'aria-describedby'?: string
  'aria-invalid'?: boolean
  /** Accessible name when not inside a `<Field>`. */
  'aria-label'?: string
  className?: string
  /** Labels for selected values not in `options` (e.g. after a server-side search). */
  selectedLabels?: Record<string, string>
}

type SingleProps = BaseProps & { multiple?: false; value: string | null; onChange: (value: string | null) => void }
type MultiProps = BaseProps & { multiple: true; value: readonly string[]; onChange: (value: string[]) => void }

export type ComboboxProps = SingleProps | MultiProps

/**
 * Searchable select (ARIA 1.2 combobox with listbox popup). Supports single and multi-select.
 * Keys: ArrowDown/ArrowUp open and move, Enter selects, Escape closes, Backspace on an empty
 * input removes the last chip (multi).
 */
export function Combobox(rawProps: ComboboxProps) {
  const props = useFieldControl(rawProps)
  const { options, placeholder, disabled, loading, emptyText = 'No matches', onSearchChange, filter = true, className, selectedLabels } = props

  const listboxId = useId()
  const optionIdPrefix = useId()
  const inputRef = useRef<HTMLInputElement>(null)
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [activeIndex, setActiveIndex] = useState(-1)

  const selected: readonly string[] = props.multiple ? props.value : props.value ? [props.value] : []

  const labelFor = (value: string) =>
    options.find((option) => option.value === value)?.label ?? selectedLabels?.[value] ?? value

  const visible = useMemo(() => {
    if (!filter || !query.trim()) return options
    const q = query.trim().toLowerCase()
    return options.filter((option) => option.label.toLowerCase().includes(q))
  }, [options, filter, query])

  const {
    refs: { setReference, setFloating },
    floatingStyles,
    context,
  } = useFloating({
    open,
    onOpenChange: setOpen,
    placement: 'bottom-start',
    whileElementsMounted: autoUpdate,
    middleware: [
      offset(4),
      flip({ padding: 8 }),
      size({
        padding: 8,
        apply({ rects, availableHeight, elements }) {
          Object.assign(elements.floating.style, {
            width: `${rects.reference.width}px`,
            maxHeight: `${Math.min(availableHeight, 288)}px`,
          })
        },
      }),
    ],
  })
  const { getReferenceProps, getFloatingProps } = useInteractions([useDismiss(context)])

  const openList = () => {
    if (disabled) return
    setOpen(true)
  }

  const updateQuery = (next: string) => {
    setQuery(next)
    setActiveIndex(next ? 0 : -1)
    onSearchChange?.(next)
    openList()
  }

  const choose = (option: ComboboxOption) => {
    if (option.disabled) return
    if (props.multiple) {
      const next = selected.includes(option.value)
        ? selected.filter((value) => value !== option.value)
        : [...selected, option.value]
      props.onChange(next)
      updateQuery('')
      inputRef.current?.focus()
    } else {
      props.onChange(option.value)
      setQuery('')
      onSearchChange?.('')
      setOpen(false)
    }
  }

  const remove = (value: string) => {
    if (props.multiple) props.onChange(selected.filter((v) => v !== value))
    else props.onChange(null)
    inputRef.current?.focus()
  }

  const move = (delta: number) => {
    if (!visible.length) return
    // With nothing active, ArrowDown starts at the first option and ArrowUp at the last.
    let next = activeIndex < 0 ? (delta > 0 ? -1 : visible.length) : activeIndex
    for (let i = 0; i < visible.length; i++) {
      next = (next + delta + visible.length) % visible.length
      if (!visible[next].disabled) break
    }
    setActiveIndex(next)
    document.getElementById(`${optionIdPrefix}-${next}`)?.scrollIntoView({ block: 'nearest' })
  }

  const onKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    switch (event.key) {
      case 'ArrowDown':
        event.preventDefault()
        if (!open) {
          openList()
          setActiveIndex(Math.max(0, activeIndex))
        } else move(1)
        break
      case 'ArrowUp':
        event.preventDefault()
        if (!open) openList()
        move(-1)
        break
      case 'Enter':
        if (open && activeIndex >= 0 && visible[activeIndex]) {
          event.preventDefault()
          choose(visible[activeIndex])
        }
        break
      case 'Escape':
        if (open) {
          event.preventDefault()
          event.stopPropagation()
          setOpen(false)
        } else if (query) updateQuery('')
        break
      case 'Backspace':
        if (props.multiple && !query && selected.length) remove(selected[selected.length - 1])
        break
      case 'Tab':
        setOpen(false)
        break
    }
  }

  const singleLabel = !props.multiple && props.value ? labelFor(props.value) : ''
  const activeId = open && activeIndex >= 0 && visible[activeIndex] ? `${optionIdPrefix}-${activeIndex}` : undefined

  return (
    <div className={className}>
      <div
        ref={setReference}
        className={cn(
          controlClasses,
          'flex min-h-10 flex-wrap items-center gap-1.5 py-1.5 pr-9 focus-within:border-accent focus-within:ring-2 focus-within:ring-accent/25',
          'relative cursor-text',
          props['aria-invalid'] && 'border-signal',
          disabled && 'cursor-not-allowed bg-paper-2',
        )}
        onClick={() => inputRef.current?.focus()}
        {...getReferenceProps()}
      >
        {props.multiple &&
          selected.map((value) => (
            <span key={value} className="inline-flex h-6 items-center gap-1 rounded bg-paper-2 pl-2 pr-0.5 text-[13px] text-ink">
              {labelFor(value)}
              <button
                type="button"
                disabled={disabled}
                onClick={(event) => {
                  event.stopPropagation()
                  remove(value)
                }}
                aria-label={`Remove ${labelFor(value)}`}
                className="grid size-5 place-items-center rounded text-muted hover:bg-ink/10 hover:text-ink"
              >
                <X className="size-3" aria-hidden="true" />
              </button>
            </span>
          ))}
        <input
          ref={inputRef}
          id={props.id}
          type="text"
          role="combobox"
          aria-expanded={open}
          aria-controls={listboxId}
          aria-autocomplete="list"
          aria-activedescendant={activeId}
          aria-describedby={props['aria-describedby']}
          aria-invalid={props['aria-invalid'] || undefined}
          aria-label={props['aria-label']}
          autoComplete="off"
          disabled={disabled}
          value={open || props.multiple ? query : singleLabel}
          placeholder={props.multiple && selected.length ? undefined : singleLabel || placeholder}
          onChange={(event) => updateQuery(event.target.value)}
          onFocus={() => {
            if (!props.multiple && singleLabel) setQuery('')
          }}
          onMouseDown={openList}
          onKeyDown={onKeyDown}
          className="h-7 min-w-24 flex-1 bg-transparent text-sm outline-none placeholder:text-muted/80 disabled:cursor-not-allowed"
        />
        <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-muted">
          {loading ? <Spinner size="sm" label={null} /> : <ChevronDown className="size-4" aria-hidden="true" />}
        </span>
      </div>

      {open && (
        <FloatingPortal>
          <ul
            ref={setFloating}
            id={listboxId}
            role="listbox"
            aria-multiselectable={props.multiple || undefined}
            style={floatingStyles}
            className={cn(popoverClasses, 'overflow-y-auto p-1')}
            {...getFloatingProps()}
          >
            {visible.length === 0 && (
              <li role="presentation" className="px-2.5 py-2 text-sm text-muted">
                {loading ? 'Loading…' : emptyText}
              </li>
            )}
            {visible.map((option, index) => {
              const isSelected = selected.includes(option.value)
              return (
                <li
                  key={option.value}
                  id={`${optionIdPrefix}-${index}`}
                  role="option"
                  aria-selected={isSelected}
                  aria-disabled={option.disabled || undefined}
                  onMouseDown={(event) => event.preventDefault()}
                  onMouseEnter={() => setActiveIndex(index)}
                  onClick={() => choose(option)}
                  className={cn(
                    'flex cursor-pointer items-start gap-2 rounded-md px-2.5 py-2 text-sm',
                    index === activeIndex && 'bg-ink/5',
                    option.disabled && 'cursor-not-allowed opacity-40',
                  )}
                >
                  <Check className={cn('mt-0.5 size-4 shrink-0 text-accent', !isSelected && 'invisible')} aria-hidden="true" />
                  <span className="min-w-0">
                    <span className="block text-ink">{option.label}</span>
                    {option.description && <span className="block text-[12.5px] text-muted">{option.description}</span>}
                  </span>
                </li>
              )
            })}
          </ul>
        </FloatingPortal>
      )}
    </div>
  )
}
