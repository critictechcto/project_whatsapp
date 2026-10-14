import { useCallback, useEffect, useId, useLayoutEffect, useRef, useState, useSyncExternalStore, type KeyboardEvent } from 'react'
import {
  FloatingFocusManager,
  FloatingOverlay,
  FloatingPortal,
  useDismiss,
  useFloating,
  useInteractions,
  useRole,
} from '@floating-ui/react'
import { Button } from '../../../../components/app'
import { cn } from '../../../../lib/cn'
import { usePrefersReducedMotion } from '../../../../lib/motion'
import { useWorkspace } from '../../../../lib/workspace'
import { findTarget, LARGE_SCREEN_QUERY, resolveSteps } from './steps'

function subscribeLargeScreen(onChange: () => void) {
  if (typeof window.matchMedia !== 'function') return () => {}
  const query = window.matchMedia(LARGE_SCREEN_QUERY)
  query.addEventListener?.('change', onChange)
  return () => query.removeEventListener?.('change', onChange)
}

function isLargeScreen() {
  return typeof window.matchMedia === 'function' && window.matchMedia(LARGE_SCREEN_QUERY).matches
}

type Rect = { top: number; left: number; width: number; height: number }

const SPOTLIGHT_PADDING = 4
const POPOVER_GAP = 14
const VIEWPORT_MARGIN = 12

/**
 * The tour popover. On large screens each step sits next to its sidebar item with a spotlight cut
 * out of the dimmed page; below `lg` (sidebar in a closed drawer) every step is a centred card.
 */
export default function TourOverlay({ onFinish }: { onFinish: () => void }) {
  const { role } = useWorkspace()
  const largeScreen = useSyncExternalStore(subscribeLargeScreen, isLargeScreen, () => false)
  // Resolved once per run, so the step count stays stable while the tour is open.
  const [steps] = useState(() => resolveSteps(role, isLargeScreen()))
  const [index, setIndex] = useState(0)
  const [measured, setMeasured] = useState<{ rect: Rect; popover: { top: number; left: number } } | null>(null)
  const reducedMotion = usePrefersReducedMotion()
  const nextRef = useRef<HTMLButtonElement>(null)
  const popoverRef = useRef<HTMLDivElement | null>(null)
  const titleId = useId()
  const bodyId = useId()

  const step = steps[index]
  const target = step && largeScreen ? findTarget(step.target) : null
  const isLast = index === steps.length - 1

  useEffect(() => {
    if (steps.length === 0) onFinish()
  }, [steps.length, onFinish])

  // The spotlight and the popover follow the current step's sidebar item. On large screens the
  // sidebar is always on screen with room to its right, so the popover sits there, vertically
  // centred on the item and kept inside the viewport.
  useLayoutEffect(() => {
    if (!target) return
    target.scrollIntoView?.({ block: 'nearest' })
    let frame = 0
    const measure = () => {
      cancelAnimationFrame(frame)
      frame = requestAnimationFrame(() => {
        const rect = target.getBoundingClientRect()
        const height = popoverRef.current?.offsetHeight ?? 0
        const maxTop = Math.max(VIEWPORT_MARGIN, window.innerHeight - height - VIEWPORT_MARGIN)
        setMeasured({
          popover: {
            top: Math.min(Math.max(rect.top + rect.height / 2 - height / 2, VIEWPORT_MARGIN), maxTop),
            left: rect.right + SPOTLIGHT_PADDING + POPOVER_GAP,
          },
          rect: {
            top: rect.top - SPOTLIGHT_PADDING,
            left: rect.left - SPOTLIGHT_PADDING,
            width: rect.width + SPOTLIGHT_PADDING * 2,
            height: rect.height + SPOTLIGHT_PADDING * 2,
          },
        })
      })
    }
    measure()
    window.addEventListener('resize', measure)
    window.addEventListener('scroll', measure, true)
    return () => {
      cancelAnimationFrame(frame)
      window.removeEventListener('resize', measure)
      window.removeEventListener('scroll', measure, true)
    }
  }, [target, index])
  // The previous step's rectangle until the new one is measured, so the spotlight glides over.
  const spotlight = target && measured ? measured.rect : null

  // Focus trap and Escape use a context without the reference: a modal focus manager keeps its
  // reference tabbable, and the nav link must stay behind the overlay.
  const { refs, context } = useFloating({
    open: true,
    onOpenChange: (open) => {
      if (!open) onFinish()
    },
  })
  const dismiss = useDismiss(context, { outsidePress: false })
  const dialogRole = useRole(context, { role: 'dialog' })
  const { getFloatingProps } = useInteractions([dismiss, dialogRole])
  const setFocusTrapped = refs.setFloating

  const setPopover = useCallback(
    (node: HTMLDivElement | null) => {
      popoverRef.current = node
      setFocusTrapped(node)
    },
    [setFocusTrapped],
  )

  // Back on the second step unmounts the Back button; keep focus inside the popover.
  useEffect(() => {
    const popover = popoverRef.current
    const focused = document.activeElement
    if (popover && (focused === popover || !popover.contains(focused))) nextRef.current?.focus()
  }, [index])

  if (!step) return null

  const next = () => (isLast ? onFinish() : setIndex(index + 1))
  const back = () => {
    // The Back button disappears on the first step: hand focus to Next before it unmounts.
    if (index === 1) nextRef.current?.focus()
    setIndex(Math.max(0, index - 1))
  }

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === 'ArrowRight' && !isLast) {
      event.preventDefault()
      next()
    } else if (event.key === 'ArrowLeft' && index > 0) {
      event.preventDefault()
      back()
    }
  }

  const anchored = target !== null
  const motion = !reducedMotion

  return (
    <FloatingPortal>
      <FloatingOverlay lockScroll className={cn('z-[70]', !anchored && 'grid place-items-center bg-ink/40 p-4')}>
        {anchored && spotlight && (
          <div
            aria-hidden="true"
            data-testid="tour-spotlight"
            className={cn('pointer-events-none fixed rounded-lg', motion && 'transition-[top,left,width,height] duration-200 ease-out')}
            style={{
              ...spotlight,
              boxShadow: '0 0 0 2px var(--color-accent), 0 0 0 9999px color-mix(in srgb, var(--color-ink) 40%, transparent)',
            }}
          />
        )}
        {anchored && !spotlight && <div aria-hidden="true" className="fixed inset-0 bg-ink/40" />}
        <FloatingFocusManager context={context} initialFocus={nextRef} modal>
          <div
            ref={setPopover}
            aria-labelledby={titleId}
            aria-describedby={bodyId}
            aria-modal="true"
            data-tour-step={step.id}
            data-tour-anchor={anchored ? step.target : undefined}
            {...getFloatingProps()}
            onKeyDown={onKeyDown}
            style={anchored ? { position: 'fixed', ...(measured?.popover ?? { top: 0, left: 0, visibility: 'hidden' }) } : undefined}
            className={cn(
              'w-[min(22rem,calc(100vw-2rem))] rounded-xl border border-line bg-card p-5 shadow-2xl',
              motion && anchored && 'transition-[top,left] duration-200 ease-out',
            )}
          >
            <div key={index} className={motion ? 'fade-up' : undefined}>
              <p className="font-mono text-[12px] uppercase tracking-[0.12em] text-muted">
                {index + 1} of {steps.length}
              </p>
              <h2 id={titleId} className="mt-1.5 font-display text-lg font-semibold tracking-[-0.01em] text-ink">
                {step.title}
              </h2>
              <p id={bodyId} className="mt-1.5 text-sm leading-relaxed text-ink-2">
                {step.body}
              </p>
              <span className="sr-only" aria-live="polite">
                {`Step ${index + 1} of ${steps.length}: ${step.title}`}
              </span>
              <div className="mt-5 flex items-center gap-2">
                <Button variant="ghost" size="sm" onClick={onFinish}>
                  Skip tour
                </Button>
                <span className="flex-1" />
                {index > 0 && (
                  <Button variant="secondary" size="sm" onClick={back}>
                    Back
                  </Button>
                )}
                <Button ref={nextRef} size="sm" onClick={next}>
                  {isLast ? 'Done' : 'Next'}
                </Button>
              </div>
            </div>
          </div>
        </FloatingFocusManager>
      </FloatingOverlay>
    </FloatingPortal>
  )
}
