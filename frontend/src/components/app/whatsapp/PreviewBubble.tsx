import type { ReactNode } from 'react'
import { cn } from '../../../lib/cn'
import { StatusTicks, type DeliveryStatus } from './WhatsAppMessagePreview'

/** Bubble options shared by the WhatsApp previews. */
export type PreviewBubbleProps = {
  /** Business (outbound, right, green) or customer (inbound, left, white). */
  direction?: 'outbound' | 'inbound'
  time?: string
  status?: DeliveryStatus
  /** Render on the chat wallpaper (a standalone preview) or just the bubble (inside a thread). */
  framed?: boolean
  className?: string
}

type Props = PreviewBubbleProps & {
  /** Screen-reader caption of the framed preview. */
  caption: string
  /** Rendered below the time, e.g. buttons. */
  actions?: ReactNode
  children: ReactNode
}

/** The bubble shell of `WhatsAppMessagePreview`, for the interactive and order previews. */
export function PreviewBubble({ direction = 'outbound', time, status, framed = true, className, caption, actions, children }: Props) {
  const outgoing = direction === 'outbound'
  const bubble = (
    <div className={cn('flex', outgoing ? 'justify-end' : 'justify-start')}>
      <div
        className={cn(
          'w-full max-w-[20rem] overflow-hidden rounded-lg text-[13.5px] leading-snug shadow-[0_1px_0_rgba(16,39,31,0.1)]',
          outgoing ? 'rounded-tr-sm bg-bubble' : 'rounded-tl-sm bg-white',
        )}
      >
        {children}
        <p className="flex items-center justify-end gap-1 px-2.5 pb-1.5 pt-0.5 text-[10.5px] text-muted">
          {time}
          {outgoing && status && <StatusTicks status={status} />}
        </p>
        {actions}
      </div>
    </div>
  )

  if (!framed) return <div className={className}>{bubble}</div>

  return (
    <figure className={cn('rounded-xl border border-line bg-wallpaper p-4', className)}>
      <figcaption className="sr-only">{caption}</figcaption>
      {bubble}
    </figure>
  )
}
