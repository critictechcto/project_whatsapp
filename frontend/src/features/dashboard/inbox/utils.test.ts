import { describe, expect, it } from 'vitest'
import { validateAttachment } from './api'
import { conversationQuery } from './filters'
import { dayLabel, formatDuration, formatListTime, formatPhone, previewText, windowRemainingMs } from './utils'

const tz = 'Asia/Kolkata'
// Monday 14 Sep 2026, 3:30 PM IST.
const now = Date.parse('2026-09-14T10:00:00Z')

describe('inbox time formatting', () => {
  it('formats list times in the workspace time zone', () => {
    expect(formatListTime('2026-09-14T04:30:00Z', tz, now)).toBe('10:00 AM')
    // 00:30 IST on the 14th is today in India although it is the 13th in UTC.
    expect(formatListTime('2026-09-13T19:00:00Z', tz, now)).toBe('12:30 AM')
    expect(formatListTime('2026-09-13T12:00:00Z', tz, now)).toBe('Yesterday')
    expect(formatListTime('2026-09-11T12:00:00Z', tz, now)).toBe('Fri')
    expect(formatListTime('2026-08-30T12:00:00Z', tz, now)).toBe('30 Aug')
    expect(formatListTime(null, tz, now)).toBe('')
  })

  it('labels day separators', () => {
    expect(dayLabel('2026-09-14T01:00:00Z', tz, now)).toBe('Today')
    expect(dayLabel('2026-09-13T01:00:00Z', tz, now)).toBe('Yesterday')
    expect(dayLabel('2026-09-10T01:00:00Z', tz, now)).toBe('Thursday, 10 Sep')
    expect(dayLabel('2025-12-24T10:00:00Z', tz, now)).toBe('24 Dec 2025')
  })

  it('counts down the service window', () => {
    const open = { window_open: true, service_window_expires_at: new Date(now + 23 * 3_600_000 + 17 * 60_000).toISOString() }
    expect(formatDuration(windowRemainingMs(open, now))).toBe('23h 17m')
    expect(formatDuration(42 * 60_000)).toBe('42m')
    expect(windowRemainingMs({ window_open: false, service_window_expires_at: open.service_window_expires_at }, now)).toBe(0)
    expect(windowRemainingMs({ window_open: true, service_window_expires_at: null }, now)).toBe(0)
  })
})

describe('inbox text helpers', () => {
  it('previews messages by type', () => {
    expect(previewText('text', '  Kal   milte hain ')).toBe('Kal milte hain')
    expect(previewText('image', 'Ye wala box')).toBe('Photo · Ye wala box')
    expect(previewText('audio', '')).toBe('Voice message')
    expect(previewText('unsupported', 'x')).toBe('Unsupported message')
  })

  it('previews native carts by item count', () => {
    const items = [
      { product_retailer_id: 'SS-KAJU-250', quantity: 2, item_price: 220, currency: 'INR' },
      { product_retailer_id: 'SS-SOAN-250', quantity: 1, item_price: 100, currency: 'INR' },
    ]
    expect(previewText('order', 'Cart: 3 items, ₹540.00', { items })).toBe('Cart · 3 items')
    expect(previewText('order', 'Cart: 1 items, ₹220.00')).toBe('Cart · 1 item')
    expect(previewText('order', 'Cart: 12 items, ₹4,450.00')).toBe('Cart · 12 items')
    expect(previewText('order', '')).toBe('Cart')
    expect(previewText('interactive', 'Address shared')).toBe('Address shared')
  })

  it('formats Indian numbers', () => {
    expect(formatPhone('+919829011223')).toBe('+91 98290 11223')
    expect(formatPhone('+14155550100')).toBe('+14155550100')
  })
})

describe('attachment validation', () => {
  it('accepts supported types within the limit', () => {
    expect(validateAttachment({ name: 'box.jpg', type: 'image/jpeg', size: 1_000_000 })).toEqual({ ok: true, kind: 'image' })
    expect(validateAttachment({ name: 'menu.pdf', type: 'application/pdf', size: 20_000_000 })).toEqual({ ok: true, kind: 'document' })
  })

  it('rejects unsupported types and oversized files', () => {
    expect(validateAttachment({ name: 'photo.heic', type: 'image/heic', size: 10 })).toMatchObject({ ok: false })
    const tooBig = validateAttachment({ name: 'clip.mp4', type: 'video/mp4', size: 17 * 1024 * 1024 })
    expect(tooBig).toEqual({ ok: false, reason: 'clip.mp4 is 17 MB. WhatsApp accepts MP4 or 3GP videos up to 16 MB.' })
  })
})

describe('conversation query', () => {
  it('maps views and filters to API params', () => {
    expect(conversationQuery({ view: 'mine', number: '', unread: false, q: '' })).toEqual({
      status: 'open',
      assignee: 'me',
      phone_number: undefined,
      unread: undefined,
      search: undefined,
    })
    expect(conversationQuery({ view: 'unassigned', number: 'p1', unread: true, q: ' priya ' })).toEqual({
      status: 'open',
      assignee: 'none',
      phone_number: 'p1',
      unread: true,
      search: 'priya',
    })
    expect(conversationQuery({ view: 'closed', number: '', unread: false, q: '' })).toMatchObject({ status: 'closed' })
  })
})
