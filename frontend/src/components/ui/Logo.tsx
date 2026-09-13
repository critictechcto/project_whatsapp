import { site } from '../../config/site'
import { cn } from '../../lib/cn'

export function Logo({ className }: { className?: string }) {
  return (
    <span className={cn('inline-flex items-center gap-2.5', className)}>
      <svg viewBox="0 0 28 28" className="size-7" aria-hidden="true">
        <rect width="28" height="28" rx="7" className="fill-ink" />
        <path
          d="M10.5 8H17.5A3 3 0 0 1 20.5 11V15A3 3 0 0 1 17.5 18H13L9.5 21V18A2 3 0 0 1 7.5 15V11A3 3 0 0 1 10.5 8Z"
          className="fill-paper"
        />
        <path
          d="M11 13H16.5M14.5 11L16.8 13L14.5 15"
          fill="none"
          className="stroke-ink"
          strokeWidth="1.6"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
      <span className="text-[17px] font-semibold tracking-[-0.02em]">{site.name}</span>
    </span>
  )
}
