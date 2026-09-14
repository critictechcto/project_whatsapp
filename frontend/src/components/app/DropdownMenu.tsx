import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import {
  autoUpdate,
  flip,
  FloatingFocusManager,
  FloatingPortal,
  offset,
  shift,
  useClick,
  useDismiss,
  useFloating,
  useInteractions,
  useListNavigation,
  useRole,
  useTypeahead,
  type Placement,
} from '@floating-ui/react'
import { cn } from '../../lib/cn'
import { buttonClasses, popoverClasses, type ButtonSize, type ButtonVariant } from './styles'

export type MenuEntry =
  | { type?: 'item'; id: string; label: string; icon?: ReactNode; onSelect: () => void; disabled?: boolean; danger?: boolean }
  | { type: 'separator'; id: string }
  | { type: 'label'; id: string; label: ReactNode }

type DropdownMenuProps = {
  /** Content of the trigger button. */
  trigger: ReactNode
  /** Accessible name when the trigger has no text. */
  triggerLabel?: string
  triggerVariant?: ButtonVariant
  triggerSize?: ButtonSize
  triggerClassName?: string
  items: readonly MenuEntry[]
  placement?: Placement
  /** Optional header above the items (not focusable). */
  header?: ReactNode
  menuClassName?: string
}

/** Menu button: Enter/Space/ArrowDown open, arrows move, typing jumps, Escape closes and returns focus. */
export function DropdownMenu({
  trigger,
  triggerLabel,
  triggerVariant = 'ghost',
  triggerSize = 'md',
  triggerClassName,
  items,
  placement = 'bottom-end',
  header,
  menuClassName,
}: DropdownMenuProps) {
  const [open, setOpen] = useState(false)
  const [activeIndex, setActiveIndex] = useState<number | null>(null)
  const listRef = useRef<Array<HTMLElement | null>>([])

  // Position of each actionable item among actionable items (separators and labels are skipped).
  const { labels, indexById } = useMemo(() => {
    const actionable = items.filter((item) => item.type === undefined || item.type === 'item')
    return {
      labels: actionable.map((item) => ('label' in item && typeof item.label === 'string' ? item.label : null)),
      indexById: new Map(actionable.map((item, index) => [item.id, index])),
    }
  }, [items])
  const labelsRef = useRef<Array<string | null>>(labels)
  useEffect(() => {
    labelsRef.current = labels
  }, [labels])

  const {
    refs: { setReference, setFloating },
    floatingStyles,
    context,
  } = useFloating({
    open,
    onOpenChange: setOpen,
    placement,
    whileElementsMounted: autoUpdate,
    middleware: [offset(6), flip({ padding: 8 }), shift({ padding: 8 })],
  })

  const { getReferenceProps, getFloatingProps, getItemProps } = useInteractions([
    useClick(context),
    useDismiss(context),
    useRole(context, { role: 'menu' }),
    useListNavigation(context, { listRef, activeIndex, onNavigate: setActiveIndex, loop: true }),
    useTypeahead(context, { listRef: labelsRef, activeIndex, onMatch: open ? setActiveIndex : undefined }),
  ])

  return (
    <>
      <button
        ref={setReference}
        type="button"
        aria-label={triggerLabel}
        className={buttonClasses(triggerVariant, triggerSize, triggerClassName)}
        {...getReferenceProps()}
      >
        {trigger}
      </button>
      {open && (
        <FloatingPortal>
          <FloatingFocusManager context={context} modal={false} initialFocus={0}>
            <div
              ref={setFloating}
              style={floatingStyles}
              className={cn(popoverClasses, 'menu-down min-w-48 p-1 outline-none', menuClassName)}
              {...getFloatingProps()}
            >
              {header}
              {items.map((item) => {
                if (item.type === 'separator') return <div key={item.id} role="separator" className="my-1 h-px bg-line-2" />
                if (item.type === 'label') {
                  return (
                    <div key={item.id} className="px-2.5 pb-1 pt-2 font-mono text-[10.5px] uppercase tracking-[0.12em] text-muted">
                      {item.label}
                    </div>
                  )
                }
                const index = indexById.get(item.id) ?? 0
                return (
                  <button
                    key={item.id}
                    type="button"
                    role="menuitem"
                    disabled={item.disabled}
                    tabIndex={activeIndex === index ? 0 : -1}
                    ref={(node) => {
                      listRef.current[index] = node
                    }}
                    className={cn(
                      'flex w-full items-center gap-2.5 rounded-md px-2.5 py-2 text-left text-sm outline-none disabled:opacity-40',
                      'focus:bg-ink/5 [&_svg]:size-4 [&_svg]:text-muted',
                      item.danger ? 'text-signal' : 'text-ink',
                    )}
                    {...getItemProps({
                      onClick() {
                        item.onSelect()
                        setOpen(false)
                      },
                    })}
                  >
                    {item.icon}
                    {item.label}
                  </button>
                )
              })}
            </div>
          </FloatingFocusManager>
        </FloatingPortal>
      )}
    </>
  )
}
