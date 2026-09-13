import type { ReactNode } from 'react'
import { CheckCheck } from 'lucide-react'
import { cn } from '../../../lib/cn'

type ChatBubbleProps = {
  from: 'customer' | 'business'
  time?: string
  label?: string
  buttons?: string[]
  className?: string
  children: ReactNode
}

export function ChatBubble({ from, time, label, buttons, className, children }: ChatBubbleProps) {
  const outgoing = from === 'business'

  return (
    <div className={cn('flex', outgoing ? 'justify-end' : 'justify-start', className)}>
      <div
        className={cn(
          'max-w-[86%] rounded-lg text-[12.5px] leading-snug shadow-[0_1px_0_rgba(16,39,31,0.1)]',
          outgoing ? 'rounded-tr-sm bg-bubble' : 'rounded-tl-sm bg-white',
        )}
      >
        {label && (
          <p className="px-3 pt-2 font-mono text-[9.5px] uppercase tracking-[0.12em] text-accent-2">{label}</p>
        )}
        <p className="px-3 pt-2 text-ink">{children}</p>
        <p className="flex items-center justify-end gap-1 px-3 pb-1.5 pt-1 text-[10px] text-muted">
          {time}
          {outgoing && <CheckCheck className="size-3 text-[#2f7fc1]" />}
        </p>
        {buttons && (
          <div className="divide-y divide-ink/5 border-t border-ink/5">
            {buttons.map((button) => (
              <p key={button} className="py-2 text-center text-[12px] font-medium text-[#1f6aa8]">
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
