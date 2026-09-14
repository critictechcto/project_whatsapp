import { Fragment, type ReactNode } from 'react'
import { Check, CheckCheck, Clock, CornerUpLeft, ExternalLink, FileText, Image, MapPin, Phone, Video } from 'lucide-react'
import { cn } from '../../../lib/cn'
import type { PreviewMessage } from './template'

type DeliveryStatus = 'queued' | 'sending' | 'sent' | 'delivered' | 'read' | 'failed'

type WhatsAppMessagePreviewProps = {
  message: PreviewMessage
  /** Business (outbound, right, green) or customer (inbound, left, white). */
  direction?: 'outbound' | 'inbound'
  time?: string
  status?: DeliveryStatus
  /** Render on the chat wallpaper (a standalone preview) or just the bubble (inside a thread). */
  framed?: boolean
  className?: string
}

const PLACEHOLDER_SPLIT = /(\{\{\s*[\w.]+\s*\}\})/g

/** Unfilled `{{1}}` placeholders stand out so users notice missing values. */
function withPlaceholders(text: string, keyPrefix: string): ReactNode[] {
  return text.split(PLACEHOLDER_SPLIT).map((part, i) =>
    /^\{\{/.test(part) ? (
      <span key={`${keyPrefix}-${i}`} className="rounded bg-amber-soft px-1 font-mono text-[11px] text-amber">
        {part}
      </span>
    ) : (
      <Fragment key={`${keyPrefix}-${i}`}>{part}</Fragment>
    ),
  )
}

const FORMAT = /(\*[^*\n]+\*|_[^_\n]+_|~[^~\n]+~|```[^`]+```)/g

/** WhatsApp formatting: *bold*, _italic_, ~strikethrough~, ```monospace```. Rendered as elements, never HTML. */
function formatWhatsAppText(text: string): ReactNode[] {
  return text.split(FORMAT).map((part, i) => {
    const key = `f-${i}`
    if (part.startsWith('```') && part.endsWith('```') && part.length > 6) {
      return <code key={key} className="font-mono text-[12px]">{withPlaceholders(part.slice(3, -3), key)}</code>
    }
    if (part.length > 2) {
      const inner = part.slice(1, -1)
      if (part.startsWith('*') && part.endsWith('*')) return <strong key={key}>{withPlaceholders(inner, key)}</strong>
      if (part.startsWith('_') && part.endsWith('_')) return <em key={key}>{withPlaceholders(inner, key)}</em>
      if (part.startsWith('~') && part.endsWith('~')) return <s key={key}>{withPlaceholders(inner, key)}</s>
    }
    return <Fragment key={key}>{withPlaceholders(part, key)}</Fragment>
  })
}

const mediaIcons: Record<string, ReactNode> = {
  IMAGE: <Image className="size-6" aria-hidden="true" />,
  VIDEO: <Video className="size-6" aria-hidden="true" />,
  DOCUMENT: <FileText className="size-6" aria-hidden="true" />,
  LOCATION: <MapPin className="size-6" aria-hidden="true" />,
}

const buttonIcons: Record<string, ReactNode> = {
  URL: <ExternalLink className="size-3.5" aria-hidden="true" />,
  PHONE_NUMBER: <Phone className="size-3.5" aria-hidden="true" />,
  QUICK_REPLY: <CornerUpLeft className="size-3.5" aria-hidden="true" />,
}

function StatusTicks({ status }: { status: DeliveryStatus }) {
  if (status === 'queued' || status === 'sending') return <Clock className="size-3" aria-label="Sending" />
  if (status === 'sent') return <Check className="size-3" aria-label="Sent" />
  if (status === 'failed') return <span className="text-signal">Failed</span>
  return <CheckCheck className={cn('size-3', status === 'read' && 'text-[#2f7fc1]')} aria-label={status === 'read' ? 'Read' : 'Delivered'} />
}

/** Message text with WhatsApp formatting, for inbox bubbles. */
export function WhatsAppText({ text }: { text: string }) {
  return <>{formatWhatsAppText(text)}</>
}

/**
 * A WhatsApp message as the customer will see it. Adapted from the landing page's `ChatBubble`.
 * Use with `templatePreview(template, values)` for templates.
 */
export function WhatsAppMessagePreview({
  message,
  direction = 'outbound',
  time,
  status,
  framed = true,
  className,
}: WhatsAppMessagePreviewProps) {
  const outgoing = direction === 'outbound'
  const { header, body, footer, buttons = [] } = message

  const bubble = (
    <div className={cn('flex', outgoing ? 'justify-end' : 'justify-start')}>
      <div
        className={cn(
          'w-full max-w-[20rem] overflow-hidden rounded-lg text-[13.5px] leading-snug shadow-[0_1px_0_rgba(16,39,31,0.1)]',
          outgoing ? 'rounded-tr-sm bg-bubble' : 'rounded-tl-sm bg-white',
        )}
      >
        {header && header.format !== 'TEXT' && (
          <div className="m-1 mb-0 grid aspect-[16/9] place-items-center rounded-md bg-ink/10 text-ink/50">
            {mediaIcons[header.format] ?? mediaIcons.DOCUMENT}
          </div>
        )}
        {header?.format === 'TEXT' && header.text && (
          <p className="px-2.5 pt-2 font-semibold text-ink">{withPlaceholders(header.text, 'h')}</p>
        )}
        <p className="whitespace-pre-wrap break-words px-2.5 pt-1.5 text-ink">
          {body ? formatWhatsAppText(body) : <span className="text-muted">Message text</span>}
        </p>
        {footer && <p className="px-2.5 pt-1 text-[12px] text-muted">{footer}</p>}
        <p className="flex items-center justify-end gap-1 px-2.5 pb-1.5 pt-0.5 text-[10.5px] text-muted">
          {time}
          {outgoing && status && <StatusTicks status={status} />}
        </p>
        {buttons.length > 0 && (
          <div className="divide-y divide-ink/5 border-t border-ink/5">
            {buttons.map((button, i) => (
              <p key={`${button.text}-${i}`} className="flex items-center justify-center gap-1.5 py-2 text-center text-[13px] font-medium text-[#1f6aa8]">
                {buttonIcons[button.type]}
                {button.text}
              </p>
            ))}
          </div>
        )}
      </div>
    </div>
  )

  if (!framed) return <div className={className}>{bubble}</div>

  return (
    <figure className={cn('rounded-xl border border-line bg-wallpaper p-4', className)}>
      <figcaption className="sr-only">Message preview</figcaption>
      {bubble}
    </figure>
  )
}
