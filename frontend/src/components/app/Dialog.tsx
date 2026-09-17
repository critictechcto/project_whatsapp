import { useId, type ReactNode, type RefObject } from 'react'
import {
  FloatingFocusManager,
  FloatingOverlay,
  FloatingPortal,
  useDismiss,
  useFloating,
  useInteractions,
  useRole,
} from '@floating-ui/react'
import { X } from 'lucide-react'
import { cn } from '../../lib/cn'

type OverlayProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
  title: ReactNode
  description?: ReactNode
  children?: ReactNode
  /** Buttons row at the bottom. */
  footer?: ReactNode
  /** Element to focus on open; defaults to the first focusable element. */
  initialFocus?: RefObject<HTMLElement | null>
  /** When false, Escape and outside clicks don't close it (e.g. while saving). */
  dismissible?: boolean
}

function useOverlay({ open, onOpenChange, dismissible = true }: Pick<OverlayProps, 'open' | 'onOpenChange' | 'dismissible'>) {
  const {
    refs: { setFloating },
    context,
  } = useFloating({ open, onOpenChange })
  const dismiss = useDismiss(context, { enabled: dismissible, outsidePressEvent: 'mousedown' })
  const role = useRole(context, { role: 'dialog' })
  const { getFloatingProps } = useInteractions([dismiss, role])
  return { setFloating, context, getFloatingProps }
}

function CloseButton({ onClick }: { onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label="Close"
      className="touch-target grid size-8 shrink-0 place-items-center rounded-md text-muted hover:bg-ink/5 hover:text-ink"
    >
      <X className="size-4" aria-hidden="true" />
    </button>
  )
}

const dialogSizes = { sm: 'max-w-sm', md: 'max-w-lg', lg: 'max-w-2xl' } as const

/** Modal dialog: focus is trapped, Escape and outside click close it, focus returns to the trigger. */
export function Dialog({ size = 'md', ...props }: OverlayProps & { size?: keyof typeof dialogSizes }) {
  const { open, onOpenChange, title, description, children, footer, initialFocus, dismissible = true } = props
  const { setFloating, context, getFloatingProps } = useOverlay({ open, onOpenChange, dismissible })
  const titleId = useId()
  const descriptionId = useId()

  if (!open) return null

  return (
    <FloatingPortal>
      <FloatingOverlay lockScroll className="fade-up z-50 grid place-items-center bg-ink/35 p-4">
        <FloatingFocusManager context={context} initialFocus={initialFocus}>
          <div
            ref={setFloating}
            aria-labelledby={titleId}
            aria-describedby={description ? descriptionId : undefined}
            aria-modal="true"
            {...getFloatingProps()}
            className={cn('flex max-h-[calc(100dvh-2rem)] w-full flex-col rounded-xl border border-line bg-card shadow-2xl', dialogSizes[size])}
          >
            <div className="flex items-start justify-between gap-4 px-5 pt-5">
              <div className="min-w-0">
                <h2 id={titleId} className="font-display text-lg font-semibold tracking-[-0.01em] text-ink">
                  {title}
                </h2>
                {description && (
                  <p id={descriptionId} className="mt-1 text-sm text-muted">
                    {description}
                  </p>
                )}
              </div>
              {dismissible && <CloseButton onClick={() => onOpenChange(false)} />}
            </div>
            {children && <div className="overflow-y-auto px-5 py-4">{children}</div>}
            {footer && <div className="flex flex-wrap justify-end gap-2 border-t border-line-2 px-5 py-3.5">{footer}</div>}
          </div>
        </FloatingFocusManager>
      </FloatingOverlay>
    </FloatingPortal>
  )
}

/** Side panel with the same focus and dismiss behaviour as `Dialog`. */
export function Drawer({ side = 'right', width = 'max-w-md', ...props }: OverlayProps & { side?: 'left' | 'right'; width?: string }) {
  const { open, onOpenChange, title, description, children, footer, initialFocus, dismissible = true } = props
  const { setFloating, context, getFloatingProps } = useOverlay({ open, onOpenChange, dismissible })
  const titleId = useId()
  const descriptionId = useId()

  if (!open) return null

  return (
    <FloatingPortal>
      <FloatingOverlay lockScroll className="z-50 bg-ink/35">
        <FloatingFocusManager context={context} initialFocus={initialFocus}>
          <div
            ref={setFloating}
            aria-labelledby={titleId}
            aria-describedby={description ? descriptionId : undefined}
            aria-modal="true"
            {...getFloatingProps()}
            className={cn(
              'fixed inset-y-0 flex w-full flex-col border-line bg-card shadow-2xl',
              side === 'right' ? 'drawer-right right-0 border-l' : 'drawer-left left-0 border-r',
              width,
            )}
          >
            <div className="flex items-start justify-between gap-4 border-b border-line-2 px-5 py-4">
              <div className="min-w-0">
                <h2 id={titleId} className="font-display text-lg font-semibold tracking-[-0.01em] text-ink">
                  {title}
                </h2>
                {description && (
                  <p id={descriptionId} className="mt-1 text-sm text-muted">
                    {description}
                  </p>
                )}
              </div>
              {dismissible && <CloseButton onClick={() => onOpenChange(false)} />}
            </div>
            <div className="flex-1 overflow-y-auto px-5 py-4">{children}</div>
            {footer && <div className="flex flex-wrap justify-end gap-2 border-t border-line-2 px-5 py-3.5">{footer}</div>}
          </div>
        </FloatingFocusManager>
      </FloatingOverlay>
    </FloatingPortal>
  )
}
