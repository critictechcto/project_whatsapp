import { BatteryFull, ChevronLeft, Mic, Signal, Wifi } from 'lucide-react'
import { cn } from '../../../lib/cn'
import { CHAT_FINAL_STEP } from '../lib/useChatSequence'
import { ChatBubble } from './ChatBubble'

type PhoneMockupProps = {
  className?: string
  /** Current step from `useChatSequence`. Omit for the finished, static conversation. */
  step?: number
}

/**
 * The customer's side of the demo conversation, on a phone. Mirrors `InboxMockup` step for step.
 * Decorative, so hidden from assistive tech.
 */
export function PhoneMockup({ className, step: sequenceStep }: PhoneMockupProps) {
  const step = sequenceStep ?? CHAT_FINAL_STEP
  const pop = sequenceStep === undefined ? undefined : 'chat-pop'

  return (
    <div
      aria-hidden="true"
      className={cn(
        'rounded-[2.1rem] bg-ink p-[6px] shadow-[inset_0_0_0_1px_rgb(255_255_255/0.14),inset_0_1px_0_rgb(255_255_255/0.22)]',
        className,
      )}
    >
      <div className="relative flex h-full flex-col overflow-hidden rounded-[1.75rem] bg-wallpaper">
        <div className="flex h-7 shrink-0 items-center justify-between bg-card px-5 font-mono text-[9px] font-medium">
          <span>10:42</span>
          <span className="absolute left-1/2 top-2 h-3.5 w-14 -translate-x-1/2 rounded-full bg-ink" />
          <span className="flex items-center gap-1">
            <Signal className="size-2.5" />
            <Wifi className="size-2.5" />
            <BatteryFull className="size-3" />
          </span>
        </div>

        <div className="flex shrink-0 items-center gap-2 border-b border-line-2 bg-card px-2 pb-2 pt-1">
          <ChevronLeft className="size-3.5 text-muted" />
          <span className="grid size-7 shrink-0 place-items-center rounded-full bg-accent text-[10px] font-semibold text-white">
            SR
          </span>
          <div className="min-w-0">
            <p className="truncate text-[11.5px] font-semibold leading-tight">Sharma Retail</p>
            <p className={cn('truncate text-[9px] leading-tight', step === 3 ? 'text-accent-2' : 'text-muted')}>
              {step === 3 ? 'typing…' : 'Business account'}
            </p>
          </div>
        </div>

        <div className="flex min-h-0 flex-1 flex-col justify-end gap-2 overflow-hidden px-2 py-2.5">
          {step >= 1 && (
            <ChatBubble className={pop} from="business" view="customer" compact time="18:05" buttons={['Track order']}>
              Hi Priya, your order #SR-20418 has been shipped. Expected delivery: Thursday.
            </ChatBubble>
          )}
          {step >= 2 && (
            <ChatBubble className={pop} from="customer" view="customer" compact time="10:41">
              Hi! Is COD available for Jaipur? I want to order one more.
            </ChatBubble>
          )}
          {step >= 4 && (
            <ChatBubble className={pop} from="business" view="customer" compact time="10:42">
              Yes, Cash on Delivery is available across Jaipur. Sharing the product link now.
            </ChatBubble>
          )}
        </div>

        <div className="flex shrink-0 items-center gap-1.5 px-2 pb-3 pt-1">
          <div className="h-7 flex-1 rounded-full bg-white px-3 text-[10px] leading-7 text-muted">Message</div>
          <span className="grid size-7 shrink-0 place-items-center rounded-full bg-accent text-white">
            <Mic className="size-3" />
          </span>
        </div>
      </div>
    </div>
  )
}
