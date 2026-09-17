import { cn } from '../../lib/cn'

type SnapPagerProps = {
  /** Accessible name per item, e.g. "Growth". Shown as text when `showLabels` is set. */
  labels: string[]
  index: number
  onSelect: (index: number) => void
  /** Name of the button group, e.g. "Show plan". */
  label: string
  showLabels?: boolean
  /** Hide it where the row does not scroll, e.g. `md:hidden`. */
  className?: string
}

/**
 * Buttons that move a snap row (`useSnapRow`) to an item, so the row is usable without swiping
 * (keyboard, switch access). Every target is at least 44 px.
 */
export function SnapPager({ labels, index, onSelect, label, showLabels, className }: SnapPagerProps) {
  return (
    <div role="group" aria-label={label} className={cn('flex flex-wrap justify-center', className)}>
      {labels.map((name, i) => {
        const current = i === index
        return (
          <button
            key={name}
            type="button"
            aria-label={showLabels ? undefined : name}
            aria-current={current ? 'true' : undefined}
            onClick={() => onSelect(i)}
            className={cn(
              'grid min-h-11 min-w-11 place-items-center transition-colors',
              showLabels && 'rounded-md px-3 text-[14px] font-medium',
              showLabels && (current ? 'text-ink' : 'text-muted hover:text-ink'),
            )}
          >
            {showLabels ? (
              <span className={cn('border-b-2 pb-0.5', current ? 'border-ink' : 'border-transparent')}>{name}</span>
            ) : (
              <span
                aria-hidden="true"
                className={cn(
                  'block h-2 rounded-full transition-[width,background-color] duration-300',
                  current ? 'w-5 bg-ink' : 'w-2 bg-ink/25',
                )}
              />
            )}
          </button>
        )
      })}
    </div>
  )
}
