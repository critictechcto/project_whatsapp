import { useEffect, useId, useRef, useState } from 'react'
import { Ban, Clock, FileText, Image as ImageIcon, LayoutTemplate, Lock, Mic, Paperclip, SendHorizontal, Video, X } from 'lucide-react'
import { errorMessage } from '../../../../api/errors'
import { Button } from '../../../../components/app/Button'
import { cn } from '../../../../lib/cn'
import { useWorkspace } from '../../../../lib/workspace'
import {
  attachmentAccept,
  formatBytes,
  toSendError,
  uploadMedia,
  validateAttachment,
  type AttachmentKind,
  type Conversation,
  type MediaAsset,
  type SendMessageRequest,
} from '../api'
import { useAddNote } from '../hooks/conversations'
import type { OutboxDisplay } from '../hooks/thread'
import { COMPOSER_ID, formatDuration, formatFullTime, WINDOW_WARNING_MS, windowRemainingMs } from '../utils'

type Attachment = {
  id: string
  file: File
  kind: AttachmentKind
  progress: number
  status: 'uploading' | 'ready' | 'error'
  asset?: MediaAsset
  error?: string
}

const kindIcons: Record<AttachmentKind, typeof ImageIcon> = { image: ImageIcon, video: Video, audio: Mic, document: FileText }

type ComposerProps = {
  conversation: Conversation
  now: number
  send: (request: SendMessageRequest, display: OutboxDisplay) => void
  onOpenTemplate: () => void
}

export function Composer({ conversation, now, send, onOpenTemplate }: ComposerProps) {
  const { can, timeZone } = useWorkspace()
  const [mode, setMode] = useState<'reply' | 'note'>('reply')
  const [text, setText] = useState('')
  const [attachment, setAttachment] = useState<Attachment | null>(null)
  const [attachmentError, setAttachmentError] = useState<string | null>(null)
  const [noteError, setNoteError] = useState<string | null>(null)
  const addNote = useAddNote(conversation.id)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const fileRef = useRef<HTMLInputElement>(null)
  const uploadRef = useRef<AbortController | null>(null)
  const closedNoticeId = useId()

  useEffect(() => () => uploadRef.current?.abort(), [])

  if (!can('agent')) {
    return (
      <div className="flex items-center gap-2 border-t border-line bg-card px-4 py-3 text-[13px] text-muted">
        <Lock className="size-4 shrink-0" aria-hidden="true" />
        You have view-only access. Agents, admins and owners can reply to customers.
      </div>
    )
  }

  const remaining = windowRemainingMs(conversation, now)
  const windowOpen = remaining > 0
  const optedOut = conversation.contact.marketing_opt_in_status === 'opted_out'
  const replyBlocked = mode === 'reply' && !windowOpen
  const captionAllowed = attachment?.kind !== 'audio'

  const resize = () => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`
  }

  const startUpload = (file: File) => {
    const check = validateAttachment(file)
    if (!check.ok) {
      setAttachmentError(check.reason)
      return
    }
    setAttachmentError(null)
    uploadRef.current?.abort()
    const controller = new AbortController()
    uploadRef.current = controller
    const id = crypto.randomUUID()
    const update = (changes: Partial<Attachment>) => setAttachment((current) => (current?.id === id ? { ...current, ...changes } : current))
    setAttachment({ id, file, kind: check.kind, progress: 0, status: 'uploading' })
    uploadMedia(file, { signal: controller.signal, onProgress: (progress) => update({ progress }) })
      .then((asset) => update({ status: 'ready', progress: 1, asset }))
      .catch((error: unknown) => {
        if (!controller.signal.aborted) update({ status: 'error', error: toSendError(error).message })
      })
  }

  const removeAttachment = () => {
    uploadRef.current?.abort()
    setAttachment(null)
  }

  const trimmed = text.trim()
  const canSubmit =
    mode === 'note'
      ? trimmed.length > 0 && !addNote.isPending
      : !replyBlocked && (attachment ? attachment.status === 'ready' : trimmed.length > 0)

  const clearText = () => {
    setText('')
    if (textareaRef.current) textareaRef.current.style.height = ''
  }

  const submit = () => {
    if (!canSubmit) return
    if (mode === 'note') {
      addNote.mutate(trimmed, {
        onSuccess: () => {
          clearText()
          setNoteError(null)
        },
        onError: (error) => setNoteError(errorMessage(error)),
      })
      return
    }
    if (attachment?.asset) {
      const caption = captionAllowed ? trimmed : ''
      send(
        { type: 'media', media_id: attachment.asset.id, preview_url: false, ...(caption ? { caption } : {}) },
        { type: attachment.kind, text: caption, fileName: attachment.file.name, mimeType: attachment.file.type, size: attachment.file.size },
      )
      setAttachment(null)
    } else {
      send({ type: 'text', text: trimmed, preview_url: false }, { type: 'text', text: trimmed })
    }
    clearText()
    textareaRef.current?.focus()
  }

  const placeholder =
    mode === 'note'
      ? 'Write a note for your team. Customers never see notes.'
      : replyBlocked
        ? 'Free-form replies are unavailable right now'
        : attachment
          ? captionAllowed
            ? 'Add a caption (optional)'
            : "Voice messages can't have a caption"
          : 'Type a reply'

  const KindIcon = attachment ? kindIcons[attachment.kind] : null

  return (
    <div className="border-t border-line bg-card">
      {optedOut && (
        <div role="note" className="flex items-start gap-2 border-b border-signal/15 bg-signal-soft/60 px-4 py-2 text-[12.5px] text-signal">
          <Ban className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
          <p>
            <strong className="font-semibold">This contact has opted out.</strong> They asked not to receive messages from your business, so
            sends to them may be blocked.
          </p>
        </div>
      )}

      {mode === 'reply' && !windowOpen && (
        <div className="flex flex-col gap-2 border-b border-line-2 bg-paper-2/70 px-4 py-2.5 sm:flex-row sm:items-center">
          <p id={closedNoticeId} className="flex flex-1 items-start gap-2 text-[12.5px] text-ink-2">
            <Lock className="mt-0.5 size-3.5 shrink-0 text-muted" aria-hidden="true" />
            <span>
              WhatsApp only allows template messages 24 hours after the customer's last message. Free-form replies open again when they
              write to you.
            </span>
          </p>
          <Button size="sm" icon={<LayoutTemplate className="size-4" aria-hidden="true" />} onClick={onOpenTemplate}>
            Send template
          </Button>
        </div>
      )}

      <div className="px-3 pb-3 pt-2 sm:px-4">
        <div className="mb-2 flex flex-wrap items-center gap-2">
          <div role="group" aria-label="Composer mode" className="inline-flex rounded-md border border-line bg-paper p-0.5 text-[12.5px]">
            {(
              [
                ['reply', 'Reply'],
                ['note', 'Internal note'],
              ] as const
            ).map(([value, label]) => (
              <button
                key={value}
                type="button"
                aria-pressed={mode === value}
                onClick={() => setMode(value)}
                className={cn(
                  'rounded px-2.5 py-1 font-medium transition-colors',
                  mode === value ? (value === 'note' ? 'bg-amber-soft text-amber' : 'bg-card text-ink shadow-sm') : 'text-muted hover:text-ink',
                )}
              >
                {label}
              </button>
            ))}
          </div>
          {windowOpen ? (
            <span
              title={conversation.service_window_expires_at ? `Closes ${formatFullTime(conversation.service_window_expires_at, timeZone)}` : undefined}
              className={cn(
                'ml-auto inline-flex items-center gap-1 rounded px-1.5 py-0.5 font-mono text-[11px]',
                remaining < WINDOW_WARNING_MS ? 'bg-amber-soft text-amber' : 'bg-accent-soft text-accent-2',
              )}
            >
              <Clock className="size-3" aria-hidden="true" />
              Window open · {formatDuration(remaining)} left
            </span>
          ) : (
            <span className="ml-auto inline-flex items-center gap-1 font-mono text-[11px] text-muted">
              <Lock className="size-3" aria-hidden="true" />
              24h window closed
            </span>
          )}
        </div>

        {attachment && mode === 'reply' && KindIcon && (
          <div className="mb-2 flex items-center gap-2.5 rounded-lg border border-line bg-paper-2/60 px-2.5 py-2">
            <KindIcon className="size-5 shrink-0 text-muted" aria-hidden="true" />
            <div className="min-w-0 flex-1">
              <p className="truncate text-[13px] font-medium text-ink">{attachment.file.name}</p>
              {attachment.status === 'uploading' ? (
                <div
                  role="progressbar"
                  aria-label={`Uploading ${attachment.file.name}`}
                  aria-valuemin={0}
                  aria-valuemax={100}
                  aria-valuenow={Math.round(attachment.progress * 100)}
                  className="mt-1.5 h-1 overflow-hidden rounded-full bg-line"
                >
                  <div className="h-full bg-accent motion-safe:transition-[width]" style={{ width: `${attachment.progress * 100}%` }} />
                </div>
              ) : attachment.status === 'error' ? (
                <p role="alert" className="text-[12px] text-signal">
                  Upload failed. {attachment.error}
                </p>
              ) : (
                <p className="text-[12px] text-muted">{formatBytes(attachment.file.size)} · Ready to send</p>
              )}
            </div>
            {attachment.status === 'error' && (
              <Button size="sm" variant="ghost" onClick={() => startUpload(attachment.file)}>
                Retry upload
              </Button>
            )}
            <Button variant="ghost" size="icon-sm" aria-label={`Remove ${attachment.file.name}`} onClick={removeAttachment}>
              <X className="size-4" aria-hidden="true" />
            </Button>
          </div>
        )}
        {attachmentError && mode === 'reply' && (
          <p role="alert" className="mb-2 text-[12.5px] text-signal">
            {attachmentError}
          </p>
        )}
        {noteError && mode === 'note' && (
          <p role="alert" className="mb-2 text-[12.5px] text-signal">
            Couldn't add the note. {noteError}
          </p>
        )}

        <div
          className={cn(
            'flex items-end gap-1 rounded-lg border px-1.5 py-1.5 focus-within:border-accent focus-within:ring-2 focus-within:ring-accent/25',
            mode === 'note' ? 'border-amber/40 bg-amber-soft/40' : replyBlocked ? 'border-line bg-paper-2' : 'border-line bg-white',
          )}
        >
          {mode === 'reply' && (
            <>
              <Button
                variant="ghost"
                size="icon-sm"
                aria-label="Attach file"
                disabled={replyBlocked}
                onClick={() => fileRef.current?.click()}
              >
                <Paperclip className="size-4" aria-hidden="true" />
              </Button>
              <input
                ref={fileRef}
                type="file"
                accept={attachmentAccept}
                aria-label="Attachment file"
                tabIndex={-1}
                className="hidden"
                onChange={(event) => {
                  const file = event.target.files?.[0]
                  event.target.value = ''
                  if (file) startUpload(file)
                }}
              />
              <Button variant="ghost" size="icon-sm" aria-label="Choose a template" onClick={onOpenTemplate}>
                <LayoutTemplate className="size-4" aria-hidden="true" />
              </Button>
            </>
          )}
          <label htmlFor={COMPOSER_ID} className="sr-only">
            {mode === 'note' ? 'Internal note' : attachment ? 'Caption' : 'Reply'}
          </label>
          <textarea
            ref={textareaRef}
            id={COMPOSER_ID}
            rows={1}
            value={text}
            disabled={replyBlocked || (mode === 'reply' && Boolean(attachment) && !captionAllowed)}
            aria-describedby={replyBlocked ? closedNoticeId : undefined}
            placeholder={placeholder}
            onChange={(event) => {
              setText(event.target.value)
              resize()
            }}
            onKeyDown={(event) => {
              if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
                event.preventDefault()
                submit()
              }
            }}
            className="max-h-40 min-h-9 flex-1 resize-none bg-transparent px-2 py-2 text-sm leading-5 text-ink outline-none placeholder:text-muted/80 disabled:cursor-not-allowed"
          />
          <Button
            size="icon-sm"
            variant={mode === 'note' ? 'secondary' : 'primary'}
            aria-label={mode === 'note' ? 'Add note' : 'Send message'}
            disabled={!canSubmit}
            loading={mode === 'note' && addNote.isPending}
            icon={<SendHorizontal className="size-4" aria-hidden="true" />}
            onClick={submit}
          />
        </div>
        <p className="mt-1.5 hidden text-[11px] text-muted sm:block">
          {mode === 'note' ? 'Notes are visible to your team only. ' : ''}Enter to send · Shift + Enter for a new line
        </p>
      </div>
    </div>
  )
}
