import { memo, useState, type ReactNode } from 'react'
import { Contact, Download, FileText, Image as ImageIcon, MapPin, Mic, Play, StickyNote, Video } from 'lucide-react'
import { Spinner } from '../../../../components/app/Spinner'
import { InteractiveMessagePreview } from '../../../../components/app/whatsapp/InteractiveMessagePreview'
import { isInteractiveMessage, toOrderCart, type InteractiveMessage, type OrderCart } from '../../../../components/app/whatsapp/interactive'
import { OrderCartPreview } from '../../../../components/app/whatsapp/OrderCartPreview'
import { WhatsAppText, type DeliveryStatus } from '../../../../components/app/whatsapp/WhatsAppMessagePreview'
import { cn } from '../../../../lib/cn'
import { formatBytes, type ConversationNote, type Message, type MessageType } from '../api'
import { downloadMessageMedia, useMediaObjectUrl } from '../hooks/misc'
import type { OutboxEntry } from '../hooks/thread'
import { formatBubbleTime, formatFullTime, previewText } from '../utils'
import { MessageTicks } from './MessageTicks'

type Side = 'inbound' | 'outbound'

const sourceLabels: Record<Message['source'], string> = {
  inbound: '',
  inbox: '',
  campaign: 'Campaign',
  automation: 'Automation',
  api: 'API',
}

function BubbleShell({
  side,
  label,
  footer,
  failed,
  children,
}: {
  side: Side
  label?: ReactNode
  footer: ReactNode
  failed?: ReactNode
  children: ReactNode
}) {
  return (
    <div className={cn('flex', side === 'outbound' ? 'justify-end' : 'justify-start')}>
      <div
        className={cn(
          'max-w-[88%] overflow-hidden rounded-lg text-[13.5px] leading-snug text-ink shadow-[0_1px_0_rgba(16,39,31,0.1)] sm:max-w-[72%]',
          side === 'outbound' ? 'rounded-tr-sm bg-bubble' : 'rounded-tl-sm bg-white',
          failed ? 'ring-1 ring-signal/35' : undefined,
        )}
      >
        {label && <p className="px-2.5 pt-1.5 font-mono text-[10px] uppercase tracking-[0.12em] text-accent-2">{label}</p>}
        {children}
        <p className="flex items-center justify-end gap-1 px-2.5 pb-1.5 pt-0.5 text-[10.5px] text-muted">{footer}</p>
        {failed}
      </div>
    </div>
  )
}

function BodyText({ text }: { text: string }) {
  if (!text) return null
  return (
    <p className="whitespace-pre-wrap break-words px-2.5 pt-1.5">
      <WhatsAppText text={text} />
    </p>
  )
}

function MediaCard({ icon, title, subtitle, action }: { icon: ReactNode; title: ReactNode; subtitle?: ReactNode; action?: ReactNode }) {
  return (
    <div className="m-1 mb-0 flex min-w-52 items-center gap-2.5 rounded-md bg-ink/[0.05] px-2.5 py-2">
      <span className="shrink-0 text-ink/55 [&_svg]:size-6">{icon}</span>
      <div className="min-w-0 flex-1 text-[12.5px]">
        <p className="truncate font-medium text-ink">{title}</p>
        {subtitle && <p className="truncate text-muted">{subtitle}</p>}
      </div>
      {action}
    </div>
  )
}

function ImageMedia({ message, sticker }: { message: Message; sticker?: boolean }) {
  const available = Boolean(message.media?.download_url)
  const { url, failed, loading } = useMediaObjectUrl(message.id, available)
  const alt = sticker ? 'Sticker' : message.text ? `Photo: ${message.text}` : 'Photo'

  if (url) {
    return (
      <img
        src={url}
        alt={alt}
        className={cn('m-1 mb-0 block rounded-md object-cover', sticker ? 'size-32 bg-transparent' : 'max-h-72 w-[calc(100%-0.5rem)] min-w-48')}
      />
    )
  }
  return (
    <div className={cn('m-1 mb-0 grid place-items-center rounded-md bg-ink/[0.06] text-ink/45', sticker ? 'size-32' : 'aspect-[4/3] w-60 max-w-[calc(100%-0.5rem)]')}>
      {loading ? (
        <Spinner size="sm" label={null} />
      ) : (
        <span className="flex flex-col items-center gap-1 text-[12px]">
          <ImageIcon className="size-6" aria-hidden="true" />
          {failed || !available ? `${sticker ? 'Sticker' : 'Photo'} unavailable` : sticker ? 'Sticker' : 'Photo'}
        </span>
      )}
    </div>
  )
}

function PlayableMedia({ message, kind }: { message: Message; kind: 'video' | 'audio' }) {
  const [requested, setRequested] = useState(false)
  const available = Boolean(message.media?.download_url)
  const { url, failed, loading } = useMediaObjectUrl(message.id, requested && available)
  const label = kind === 'video' ? 'Video' : 'Voice message'

  if (url) {
    return kind === 'video' ? (
      <video controls src={url} className="m-1 mb-0 block max-h-72 w-[calc(100%-0.5rem)] min-w-48 rounded-md bg-ink" />
    ) : (
      <audio controls src={url} className="m-1 mb-0 block w-64 max-w-[calc(100%-0.5rem)]" />
    )
  }

  return (
    <MediaCard
      icon={kind === 'video' ? <Video /> : <Mic />}
      title={label}
      subtitle={failed ? "Couldn't load this file" : !available ? 'Not available' : message.media ? formatBytes(message.media.size) : undefined}
      action={
        <button
          type="button"
          onClick={() => setRequested(true)}
          disabled={!available || loading}
          aria-label={`Play ${label.toLowerCase()}`}
          className="grid size-8 shrink-0 place-items-center rounded-full bg-accent text-white hover:bg-accent-2 disabled:bg-ink/25"
        >
          {loading ? <Spinner size="sm" label={null} /> : <Play className="size-3.5 translate-x-px" aria-hidden="true" />}
        </button>
      }
    />
  )
}

function DocumentMedia({ message }: { message: Message }) {
  const [busy, setBusy] = useState(false)
  const [failed, setFailed] = useState(false)
  const name = message.media?.file_name || 'Document'
  const available = Boolean(message.media?.download_url)

  const download = () => {
    setBusy(true)
    setFailed(false)
    downloadMessageMedia(message.id, name)
      .catch(() => setFailed(true))
      .finally(() => setBusy(false))
  }

  return (
    <MediaCard
      icon={<FileText />}
      title={name}
      subtitle={failed ? 'Download failed, try again' : message.media ? formatBytes(message.media.size) : 'Not available'}
      action={
        <button
          type="button"
          onClick={download}
          disabled={!available || busy}
          aria-label={`Download ${name}`}
          className="grid size-8 shrink-0 place-items-center rounded-md text-ink/70 hover:bg-ink/10 hover:text-ink disabled:text-ink/25"
        >
          {busy ? <Spinner size="sm" label={null} /> : <Download className="size-4" aria-hidden="true" />}
        </button>
      }
    />
  )
}

function MessageContent({ message }: { message: Message }) {
  switch (message.type) {
    case 'image':
      return (
        <>
          <ImageMedia message={message} />
          <BodyText text={message.text} />
        </>
      )
    case 'sticker':
      return <ImageMedia message={message} sticker />
    case 'video':
      return (
        <>
          <PlayableMedia message={message} kind="video" />
          <BodyText text={message.text} />
        </>
      )
    case 'audio':
      return <PlayableMedia message={message} kind="audio" />
    case 'document':
      return (
        <>
          <DocumentMedia message={message} />
          <BodyText text={message.text} />
        </>
      )
    case 'location':
      return (
        <MediaCard
          icon={<MapPin className="text-signal" />}
          title={message.text || 'Shared location'}
          subtitle={
            message.text ? (
              <a
                href={`https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(message.text)}`}
                target="_blank"
                rel="noreferrer"
                className="font-medium text-[#1f6aa8] hover:underline"
              >
                Open in Google Maps
              </a>
            ) : undefined
          }
        />
      )
    case 'contacts':
      return <MediaCard icon={<Contact />} title={message.text || 'Contact card'} subtitle="Shared contact" />
    case 'interactive':
      // The webhook parser summarises an inbound address form (`nfm_reply`) as "Address shared".
      if (message.direction === 'inbound' && isAddressShared(message.text)) {
        return <MediaCard icon={<MapPin className="text-accent-2" />} title="Address shared" subtitle="Delivery address from WhatsApp's address form" />
      }
      return <BodyText text={message.text || 'Interactive message'} />
    case 'order':
      return <BodyText text={message.text || 'Cart'} />
    case 'unsupported':
      return <p className="px-2.5 pt-1.5 italic text-muted">This message type can't be shown here yet.</p>
    default:
      return <BodyText text={message.text} />
  }
}

function isAddressShared(text: string): boolean {
  return text.trim().toLowerCase() === 'address shared'
}

function typeLabel(type: MessageType, templateName?: string, message?: Pick<Message, 'direction' | 'text'>): ReactNode {
  if (type === 'template') return `Template · ${templateName || 'unknown'}`
  if (type === 'button') return 'Button reply'
  if (type === 'interactive') {
    if (message?.direction === 'inbound') return isAddressShared(message.text) ? undefined : 'Menu reply'
    return 'Interactive'
  }
  return undefined
}

type CommercePayload = { interactive: InteractiveMessage; cart?: never } | { cart: OrderCart; interactive?: never }

/** What a commerce bubble can draw: a valid interactive object, or a native cart with items. */
function commercePayload(message: Message): CommercePayload | null {
  if (isInteractiveMessage(message.interactive)) return { interactive: message.interactive }
  if (message.type !== 'order') return null
  const cart = toOrderCart(message.order)
  return cart && cart.product_items.length > 0 ? { cart } : null
}

function deliveryStatus(status: Message['status']): DeliveryStatus | undefined {
  return status === 'received' ? undefined : status
}

/**
 * Commerce messages drawn with the WhatsApp previews: outbound interactive messages (bot menus,
 * product cards, payment links, address requests) and inbound native carts (`order`, with the
 * prices WhatsApp displayed to the buyer).
 */
function CommerceBubble({ message, payload, sender, timeZone }: { message: Message; payload: CommercePayload; sender: string; timeZone: string }) {
  const side: Side = message.direction
  const time = formatBubbleTime(message.created_at, timeZone)
  const bubble = {
    direction: side,
    time: sender ? `${sender} · ${time}` : time,
    status: side === 'outbound' ? deliveryStatus(message.status) : undefined,
    framed: false,
    className: 'w-full max-w-[88%] sm:max-w-[20rem]',
  } as const

  return (
    <div className={cn('flex flex-col gap-1', side === 'outbound' ? 'items-end' : 'items-start')} title={formatFullTime(message.created_at, timeZone)}>
      {payload.cart ? <OrderCartPreview {...bubble} order={payload.cart} /> : <InteractiveMessagePreview {...bubble} message={payload.interactive} />}
      {message.status === 'failed' && (
        <p className="max-w-[88%] rounded-md bg-signal-soft/70 px-2.5 py-1.5 text-[12px] text-signal sm:max-w-[20rem]">
          Not delivered{message.error_message ? `: ${message.error_message}` : '.'}
          {message.error_code && <span className="font-mono"> ({message.error_code})</span>}
        </p>
      )}
    </div>
  )
}

function ReplyQuote({ replyTo, contactName }: { replyTo: Message | undefined; contactName: string }) {
  return (
    <div className="mx-1 mt-1 rounded-md border-l-[3px] border-accent bg-ink/[0.05] px-2 py-1 text-[12px]">
      {replyTo ? (
        <>
          <p className="font-medium text-accent-2">{replyTo.direction === 'outbound' ? 'You' : contactName}</p>
          <p className="line-clamp-2 text-muted">{previewText(replyTo.type, replyTo.text, replyTo.order)}</p>
        </>
      ) : (
        <p className="text-muted">Reply to an earlier message</p>
      )}
    </div>
  )
}

type MessageBubbleProps = {
  message: Message
  replyTo: Message | undefined
  contactName: string
  timeZone: string
  /** Offered for failed text messages when the viewer can send. Sends a new message (new key). */
  onRetry?: (message: Message) => void
}

export const MessageBubble = memo(function MessageBubble({ message, replyTo, contactName, timeZone, onRetry }: MessageBubbleProps) {
  const side: Side = message.direction
  const time = (
    <time dateTime={message.created_at} title={formatFullTime(message.created_at, timeZone)}>
      {formatBubbleTime(message.created_at, timeZone)}
    </time>
  )

  if (message.type === 'reaction') {
    return (
      <div className={cn('flex', side === 'outbound' ? 'justify-end' : 'justify-start')}>
        <p className="inline-flex items-center gap-1.5 rounded-full border border-line bg-card px-2.5 py-1 text-[12px] text-muted">
          {side === 'outbound' ? 'You' : contactName} reacted <span className="text-[14px] leading-none text-ink">{message.text}</span>
          {replyTo && <span className="max-w-40 truncate">to “{previewText(replyTo.type, replyTo.text, replyTo.order)}”</span>}
          <span aria-hidden="true">·</span>
          {time}
        </p>
      </div>
    )
  }

  const sender = side === 'outbound' ? message.sent_by?.full_name.split(' ')[0] || sourceLabels[message.source] : ''

  const payload = commercePayload(message)
  if (payload) return <CommerceBubble message={message} payload={payload} sender={sender} timeZone={timeZone} />

  return (
    <BubbleShell
      side={side}
      label={typeLabel(message.type, message.template?.name, message)}
      footer={
        <>
          {sender && <span>{sender} ·</span>}
          {time}
          {side === 'outbound' && <MessageTicks status={message.status} />}
        </>
      }
      failed={
        message.status === 'failed' ? (
          <div className="border-t border-signal/15 bg-signal-soft/70 px-2.5 py-1.5 text-[12px] text-signal">
            <p>
              Not delivered{message.error_message ? `: ${message.error_message}` : '.'}
              {message.error_code && <span className="font-mono"> ({message.error_code})</span>}
            </p>
            {onRetry && (
              <button type="button" onClick={() => onRetry(message)} className="mt-0.5 font-medium underline-offset-2 hover:underline">
                Retry as a new message
              </button>
            )}
          </div>
        ) : undefined
      }
    >
      {message.reply_to_message_id && <ReplyQuote replyTo={replyTo} contactName={contactName} />}
      <MessageContent message={message} />
    </BubbleShell>
  )
})

const pendingIcons: Partial<Record<MessageType, ReactNode>> = {
  image: <ImageIcon />,
  video: <Video />,
  audio: <Mic />,
  document: <FileText />,
}

type PendingBubbleProps = {
  entry: OutboxEntry
  timeZone: string
  onRetry: (localId: string) => void
  onDiscard: (localId: string) => void
  onUseTemplate: () => void
}

/** Optimistic outbound bubble for a send that isn't in the thread yet. */
export const PendingBubble = memo(function PendingBubble({ entry, timeZone, onRetry, onDiscard, onUseTemplate }: PendingBubbleProps) {
  const { display } = entry
  const status = entry.state === 'failed' ? 'failed' : entry.state === 'sent' ? (entry.serverStatus ?? 'queued') : 'queued'
  const isMedia = display.type in pendingIcons

  return (
    <BubbleShell
      side="outbound"
      label={typeLabel(display.type, display.templateName)}
      footer={
        <>
          <time dateTime={entry.createdAt}>{formatBubbleTime(entry.createdAt, timeZone)}</time>
          <MessageTicks status={status} />
        </>
      }
      failed={
        entry.state === 'failed' && entry.error ? (
          <div role="alert" className="border-t border-signal/15 bg-signal-soft/70 px-2.5 py-1.5 text-[12px] text-signal">
            <p>Not sent. {entry.error.message}</p>
            <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1 font-medium">
              {entry.error.code === 'outside_service_window' ? (
                <button type="button" onClick={onUseTemplate} className="underline-offset-2 hover:underline">
                  Send a template instead
                </button>
              ) : (
                <button type="button" onClick={() => onRetry(entry.localId)} className="underline-offset-2 hover:underline">
                  Retry
                </button>
              )}
              <button type="button" onClick={() => onDiscard(entry.localId)} className="underline-offset-2 hover:underline">
                Discard
              </button>
            </div>
          </div>
        ) : undefined
      }
    >
      {isMedia && (
        <MediaCard
          icon={pendingIcons[display.type]}
          title={display.fileName ?? 'Attachment'}
          subtitle={display.size !== undefined ? formatBytes(display.size) : undefined}
        />
      )}
      <BodyText text={display.text} />
    </BubbleShell>
  )
})

/** Internal note in the thread: only the team sees it. */
export function NoteCard({ note, timeZone }: { note: ConversationNote; timeZone: string }) {
  return (
    <article
      aria-label={`Internal note by ${note.author.full_name || note.author.email}`}
      className="mx-auto w-full max-w-[92%] rounded-lg border border-dashed border-amber/40 bg-amber-soft px-3 py-2 text-[13px] sm:max-w-[78%]"
    >
      <p className="flex flex-wrap items-center gap-x-1.5 font-mono text-[10.5px] uppercase tracking-[0.08em] text-amber">
        <StickyNote className="size-3.5" aria-hidden="true" />
        Internal note · {note.author.full_name || note.author.email} ·
        <time dateTime={note.created_at} title={formatFullTime(note.created_at, timeZone)}>
          {formatBubbleTime(note.created_at, timeZone)}
        </time>
      </p>
      <p className="mt-1 whitespace-pre-wrap break-words text-ink">{note.body}</p>
    </article>
  )
}
