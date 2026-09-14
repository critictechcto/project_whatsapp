import { TZDate } from '@date-fns/tz'
import { differenceInCalendarDays, format } from 'date-fns'
import type { Conversation, MessageType } from './api'

const HOUR = 3_600_000
const MINUTE = 60_000

function zoned(iso: string, timeZone: string) {
  return new TZDate(new Date(iso).getTime(), timeZone)
}

/** Calendar days between two instants in the workspace zone (0 = same day). */
function daysBetween(iso: string, now: number, timeZone: string) {
  return differenceInCalendarDays(new TZDate(now, timeZone), zoned(iso, timeZone))
}

/** Conversation list time: "3:05 PM" today, "Yesterday", "Mon" this week, else "3 Sep". */
export function formatListTime(iso: string | null | undefined, timeZone: string, now: number): string {
  if (!iso) return ''
  const days = daysBetween(iso, now, timeZone)
  if (days <= 0) return format(zoned(iso, timeZone), 'h:mm a')
  if (days === 1) return 'Yesterday'
  if (days < 7) return format(zoned(iso, timeZone), 'EEE')
  return format(zoned(iso, timeZone), 'd MMM')
}

/** Bubble time: "3:05 PM". */
export function formatBubbleTime(iso: string, timeZone: string): string {
  return format(zoned(iso, timeZone), 'h:mm a')
}

/** Full timestamp for titles: "10 Sep 2026, 3:05 PM". */
export function formatFullTime(iso: string, timeZone: string): string {
  return format(zoned(iso, timeZone), 'd MMM yyyy, h:mm a')
}

/** Key for grouping messages by calendar day in the workspace zone. */
export function dayKey(iso: string, timeZone: string): string {
  return format(zoned(iso, timeZone), 'yyyy-MM-dd')
}

/** Day separator label: "Today", "Yesterday", "Monday, 8 Sep" or "8 Sep 2025". */
export function dayLabel(iso: string, timeZone: string, now: number): string {
  const days = daysBetween(iso, now, timeZone)
  if (days <= 0) return 'Today'
  if (days === 1) return 'Yesterday'
  const date = zoned(iso, timeZone)
  if (days < 7) return format(date, 'EEEE, d MMM')
  if (date.getFullYear() !== new TZDate(now, timeZone).getFullYear()) return format(date, 'd MMM yyyy')
  return format(date, 'EEE, d MMM')
}

/** Milliseconds left in the customer service window (0 when closed or unknown). */
export function windowRemainingMs(conversation: Pick<Conversation, 'window_open' | 'service_window_expires_at'>, now: number): number {
  if (!conversation.window_open || !conversation.service_window_expires_at) return 0
  return Math.max(0, new Date(conversation.service_window_expires_at).getTime() - now)
}

/** "23h 17m", "42m", "<1m". */
export function formatDuration(ms: number): string {
  if (ms < MINUTE) return '<1m'
  const hours = Math.floor(ms / HOUR)
  const minutes = Math.floor((ms % HOUR) / MINUTE)
  return hours > 0 ? `${hours}h ${String(minutes).padStart(2, '0')}m` : `${minutes}m`
}

/** Short list form: "23h", "42m". */
export function formatDurationShort(ms: number): string {
  if (ms < MINUTE) return '<1m'
  const hours = Math.floor(ms / HOUR)
  return hours > 0 ? `${hours}h` : `${Math.floor(ms / MINUTE)}m`
}

export const WINDOW_WARNING_MS = 2 * HOUR

/** DOM id of the composer textarea (focused by the `r` shortcut). */
export const COMPOSER_ID = 'inbox-composer'

const typeLabels: Record<MessageType, string> = {
  text: 'Message',
  image: 'Photo',
  video: 'Video',
  audio: 'Voice message',
  document: 'Document',
  sticker: 'Sticker',
  location: 'Location',
  contacts: 'Contact card',
  interactive: 'Interactive message',
  button: 'Button reply',
  reaction: 'Reaction',
  template: 'Template',
  unsupported: 'Unsupported message',
}

export function messageTypeLabel(type: MessageType): string {
  return typeLabels[type]
}

/** One-line preview of a message for the list and reply quotes. */
export function previewText(type: MessageType, text: string): string {
  const trimmed = text.replace(/\s+/g, ' ').trim()
  if (type === 'text' || type === 'button' || type === 'interactive') return trimmed || typeLabels[type]
  if (type === 'reaction') return trimmed ? `Reacted ${trimmed}` : 'Reaction'
  if (type === 'unsupported') return typeLabels.unsupported
  return trimmed ? `${typeLabels[type]} · ${trimmed}` : typeLabels[type]
}

/** `+919876543210` → `+91 98765 43210`; other numbers unchanged. */
export function formatPhone(e164: string): string {
  const match = /^\+91(\d{5})(\d{5})$/.exec(e164)
  return match ? `+91 ${match[1]} ${match[2]}` : e164
}

export function contactName(contact: Pick<Conversation['contact'], 'name' | 'phone_e164'>): string {
  return contact.name?.trim() || formatPhone(contact.phone_e164)
}

/** True when an event target is a text field, so single-key shortcuts must not fire. */
export function isTypingTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false
  if (target.isContentEditable) return true
  const tag = target.tagName
  if (tag === 'TEXTAREA' || tag === 'SELECT') return true
  if (tag === 'INPUT') {
    const type = (target as HTMLInputElement).type
    return !['checkbox', 'radio', 'button', 'submit', 'reset'].includes(type)
  }
  return target.getAttribute('role') === 'combobox'
}
