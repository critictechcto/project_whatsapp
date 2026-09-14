import type { ReactNode } from 'react'
import { CheckCheck } from 'lucide-react'
import { cn } from '../../../lib/cn'

type ChatBubbleProps = {
  from: 'customer' | 'business'
  /** Whose screen the chat is on. Messages from that side are outgoing (right, green, ticks). */
  view?: 'customer' | 'business'
  /** Smaller type for device-sized mockups. */
  compact?: boolean
  time?: string
  label?: string
  buttons?: string[]
  className?: string
  children: ReactNode
}

export function ChatBubble({
  from,
  view = 'business',
  compact = false,
  time,
  label,
  buttons,
  className,
  children,
}: ChatBubbleProps) {
  const outgoing = from === view

  return (
    <div className={cn('flex', outgoing ? 'justify-end' : 'justify-start', className)}>
      <div
        className={cn(
          'rounded-lg shadow-[0_1px_0_rgba(16,39,31,0.1)]',
          compact ? 'max-w-[88%] text-[10.5px] leading-[1.35]' : 'max-w-[86%] text-[12.5px] leading-snug',
          outgoing ? 'rounded-tr-sm bg-bubble' : 'rounded-tl-sm bg-white',
        )}
      >
        {label && (
          <p className="px-3 pt-2 font-mono text-[9.5px] uppercase tracking-[0.12em] text-accent-2">{label}</p>
        )}
        <p className={cn('text-ink', compact ? 'px-2.5 pt-1.5' : 'px-3 pt-2')}>{children}</p>
        <p
          className={cn(
            'flex items-center justify-end gap-1 text-muted',
            compact ? 'px-2.5 pb-1 pt-0.5 text-[8.5px]' : 'px-3 pb-1.5 pt-1 text-[10px]',
          )}
        >
          {time}
          {outgoing && <CheckCheck className={cn('text-[#2f7fc1]', compact ? 'size-2.5' : 'size-3')} />}
        </p>
        {buttons && (
          <div className="divide-y divide-ink/5 border-t border-ink/5">
            {buttons.map((button) => (
              <p
                key={button}
                className={cn(
                  'text-center font-medium text-[#1f6aa8]',
                  compact ? 'py-1.5 text-[10.5px]' : 'py-2 text-[12px]',
                )}
              >
                {button}
              </p>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

/** "Agent is typing" indicator on the business side. */
export function TypingBubble({ className }: { className?: string }) {
  return (
    <div className={cn('flex justify-end', className)}>
      <div className="flex items-center gap-1 rounded-lg rounded-tr-sm bg-bubble px-3.5 py-3 shadow-[0_1px_0_rgba(16,39,31,0.1)]">
        {[0, 1, 2].map((dot) => (
          <span
            key={dot}
            className="typing-dot size-1.5 rounded-full bg-accent-2"
            style={{ animationDelay: `${dot * 160}ms` }}
          />
        ))}
      </div>
    </div>
  )
}
