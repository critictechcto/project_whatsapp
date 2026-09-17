import { Children, useId, useRef, useState, type ReactNode, type Ref } from 'react'
import { ChevronLeft, ChevronRight } from 'lucide-react'
import { cn } from '../../../lib/cn'
import { prefersReducedMotion } from '../../../lib/motion'
import './SwipeRow.css'

type SwipeRowProps = {
  /** Names the row for assistive technology, e.g. "Use cases". */
  label: string
  /** What one item is called in the prev/next button labels, e.g. "use case". */
  itemName?: string
  as?: 'ul' | 'div'
  /** Classes for the list itself: its md-and-up layout (grid, gap) and look. */
  className?: string
  /** Classes for the wrapper around the list and its phone controls (spacing). */
  wrapperClassName?: string
  children: ReactNode
}

/**
 * Below `md` the items become a horizontal scroll-snap row that peeks at the next item, with
 * previous/next buttons and position dots under it (buttons for keyboard users; the items stay in
 * reading order for screen readers). From `md` up the list keeps whatever layout `className` gives
 * it and the controls are hidden. Layout lives in SwipeRow.css, so nothing reads the viewport while
 * rendering.
 */
export function SwipeRow({ label, itemName = 'card', as = 'ul', className, wrapperClassName, children }: SwipeRowProps) {
  const trackRef = useRef<HTMLElement>(null)
  const [index, setIndex] = useState(0)
  const count = Children.count(children)
  const trackId = useId()
  const List = as as 'ul'

  function items() {
    const track = trackRef.current
    return track ? (Array.from(track.children) as HTMLElement[]) : []
  }

  function onScroll() {
    const track = trackRef.current
    const all = items()
    if (!track || all.length < 2) return
    const stride = all[1].offsetLeft - all[0].offsetLeft
    if (stride <= 0) return
    const atEnd = track.scrollLeft >= track.scrollWidth - track.clientWidth - 2
    const next = atEnd ? all.length - 1 : Math.round(track.scrollLeft / stride)
    setIndex(Math.max(0, Math.min(all.length - 1, next)))
  }

  function go(to: number) {
    const track = trackRef.current
    const all = items()
    const target = Math.max(0, Math.min(count - 1, to))
    if (!track || !all[target]) return
    track.scrollTo?.({
      left: all[target].offsetLeft - all[0].offsetLeft,
      behavior: prefersReducedMotion() ? 'auto' : 'smooth',
    })
    setIndex(target)
  }

  const buttonClass =
    'grid size-11 cursor-pointer place-items-center rounded-full border border-line bg-card text-ink transition-colors hover:border-ink/30 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent disabled:cursor-default disabled:opacity-40'

  return (
    <div role="group" aria-label={label} className={wrapperClassName}>
      <List
        ref={trackRef as Ref<HTMLUListElement>}
        id={trackId}
        onScroll={onScroll}
        className={cn('swipe-track', className)}
      >
        {children}
      </List>
      {count > 1 && (
        <div className="mt-4 flex items-center justify-between gap-4 md:hidden">
          <button
            type="button"
            aria-controls={trackId}
            aria-label={`Previous ${itemName}`}
            disabled={index === 0}
            onClick={() => go(index - 1)}
            className={buttonClass}
          >
            <ChevronLeft className="size-5" aria-hidden="true" />
          </button>
          <div className="flex items-center gap-2" aria-hidden="true">
            {Array.from({ length: count }, (_, i) => (
              <span
                key={i}
                data-active={i === index ? '' : undefined}
                className={cn(
                  'h-1.5 rounded-full transition-[width,background-color] duration-300',
                  i === index ? 'w-5 bg-accent' : 'w-1.5 bg-line',
                )}
              />
            ))}
          </div>
          <p className="sr-only" aria-live="polite">
            {`Showing ${itemName} ${index + 1} of ${count}`}
          </p>
          <button
            type="button"
            aria-controls={trackId}
            aria-label={`Next ${itemName}`}
            disabled={index === count - 1}
            onClick={() => go(index + 1)}
            className={buttonClass}
          >
            <ChevronRight className="size-5" aria-hidden="true" />
          </button>
        </div>
      )}
    </div>
  )
}
