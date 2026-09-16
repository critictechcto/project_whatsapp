import type { StoryMessage } from '../storyScreens'
import type { StoryTheme } from './theme'

/*
 * 2D canvas drawings for the WebGL story's textures: the chat screens and the cards. Coordinates are
 * design px (the same sizes as the CSS mockups); the caller scales the context to texture resolution.
 * Every drawing clips to a rounded rectangle and leaves the corners transparent, so the meshes can
 * alpha-test them away.
 */

type Ctx = CanvasRenderingContext2D

const LINK_BLUE = '#1f6aa8'
const READ_BLUE = '#2f7fc1'
const KRAFT_ART = '#efe4cf'

export function roundRect(ctx: Ctx, x: number, y: number, w: number, h: number, r: number) {
  const radius = Math.min(r, w / 2, h / 2)
  ctx.beginPath()
  ctx.moveTo(x + radius, y)
  ctx.arcTo(x + w, y, x + w, y + h, radius)
  ctx.arcTo(x + w, y + h, x, y + h, radius)
  ctx.arcTo(x, y + h, x, y, radius)
  ctx.arcTo(x, y, x + w, y, radius)
  ctx.closePath()
}

function setFont(ctx: Ctx, weight: number, size: number, family: string) {
  ctx.font = `${weight} ${size}px ${family}`
}

function text(ctx: Ctx, value: string, x: number, y: number, color: string, align: CanvasTextAlign = 'left') {
  ctx.fillStyle = color
  ctx.textAlign = align
  ctx.textBaseline = 'middle'
  ctx.fillText(value, x, y)
}

/** Greedy word wrap with the current font. */
function wrap(ctx: Ctx, value: string, maxWidth: number) {
  const lines: string[] = []
  let line = ''
  for (const word of value.split(' ')) {
    const next = line ? `${line} ${word}` : word
    if (line && ctx.measureText(next).width > maxWidth) {
      lines.push(line)
      line = word
    } else {
      line = next
    }
  }
  if (line) lines.push(line)
  return lines
}

function tick(ctx: Ctx, x: number, y: number, size: number, color: string, double = false) {
  ctx.strokeStyle = color
  ctx.lineWidth = size * 0.16
  ctx.lineCap = 'round'
  ctx.lineJoin = 'round'
  const marks = double ? [0, size * 0.36] : [0]
  for (const offset of marks) {
    ctx.beginPath()
    ctx.moveTo(x + offset, y + size * 0.5)
    ctx.lineTo(x + offset + size * 0.3, y + size * 0.8)
    ctx.lineTo(x + offset + size * 0.85, y + size * 0.2)
    ctx.stroke()
  }
}

/** A box of kaju katli: diamonds on a kraft tray. */
function productArt(ctx: Ctx, x: number, y: number, w: number, h: number) {
  roundRect(ctx, x, y, w, h, 5)
  ctx.fillStyle = KRAFT_ART
  ctx.fill()
  const size = 9
  const gap = 16
  const startX = x + w / 2 - gap
  const startY = y + h / 2 - gap / 2
  for (let row = 0; row < 2; row++) {
    for (let col = 0; col < 3; col++) {
      ctx.save()
      ctx.translate(startX + col * gap, startY + row * gap)
      ctx.rotate(Math.PI / 4)
      roundRect(ctx, -size / 2, -size / 2, size, size, 1.5)
      ctx.fillStyle = '#f7efe0'
      ctx.fill()
      ctx.strokeStyle = '#c9b58f'
      ctx.lineWidth = 0.8
      ctx.stroke()
      ctx.restore()
    }
  }
}

function card(ctx: Ctx, theme: StoryTheme, w: number, h: number, radius = 12) {
  roundRect(ctx, 0.5, 0.5, w - 1, h - 1, radius)
  ctx.fillStyle = theme.card
  ctx.fill()
  ctx.strokeStyle = theme.line
  ctx.lineWidth = 1
  ctx.stroke()
}

/* ---------- Chat screens ---------- */

const LINE = 14
const PAD_X = 9

type Laid = { w: number; h: number; draw: (x: number, y: number) => void }

function layoutMessage(ctx: Ctx, theme: StoryTheme, message: StoryMessage, areaWidth: number): Laid {
  const maxWidth = Math.round(areaWidth * 0.88)
  const inner = maxWidth - PAD_X * 2
  const out = message.side === 'out'
  const wide = Boolean(message.buttons || message.rows || message.kind === 'product')
  const pinSpace = message.kind === 'address' ? 13 : 0

  setFont(ctx, 600, 10.5, theme.sans)
  const title = message.title ? wrap(ctx, message.title, inner - pinSpace) : []
  let contentWidth = Math.max(0, ...title.map((line) => ctx.measureText(line).width + pinSpace))
  setFont(ctx, 400, 10.5, theme.sans)
  const lines = (message.lines ?? []).flatMap((line) => wrap(ctx, line, inner))
  contentWidth = Math.max(contentWidth, ...lines.map((line) => ctx.measureText(line).width))

  const rows = message.rows ?? []
  const buttons = message.buttons ?? []
  const w = wide ? maxWidth : Math.min(maxWidth, Math.max(contentWidth + PAD_X * 2, out ? 70 : 56))
  const h =
    6 +
    (message.kind === 'product' ? 62 : 0) +
    (title.length + lines.length + rows.length) * LINE +
    (rows.length ? 3 : 0) +
    14 +
    buttons.length * 24

  const draw = (x: number, y: number) => {
    // Bubble with a hairline shadow underneath
    roundRect(ctx, x, y + 1, w, h, 7)
    ctx.fillStyle = 'rgba(16, 39, 31, 0.1)'
    ctx.fill()
    roundRect(ctx, x, y, w, h, 7)
    ctx.fillStyle = out ? theme.bubble : '#ffffff'
    ctx.fill()

    let cy = y + 6
    if (message.kind === 'product') {
      productArt(ctx, x + 5, cy, w - 10, 56)
      cy += 62
    }
    setFont(ctx, 600, 10.5, theme.sans)
    for (const line of title) {
      if (pinSpace && line === title[0]) {
        ctx.fillStyle = theme.accent2
        ctx.beginPath()
        ctx.arc(x + PAD_X + 4, cy + LINE / 2 - 1, 3.6, 0, Math.PI * 2)
        ctx.fill()
      }
      text(ctx, line, x + PAD_X + pinSpace, cy + LINE / 2, theme.ink)
      cy += LINE
    }
    setFont(ctx, 400, 10.5, theme.sans)
    for (const line of lines) {
      text(ctx, line, x + PAD_X, cy + LINE / 2, message.kind === 'address' ? theme.muted : theme.ink)
      cy += LINE
    }
    rows.forEach(([label, amount], i) => {
      const last = i === rows.length - 1
      if (last) {
        ctx.fillStyle = 'rgba(16, 39, 31, 0.1)'
        ctx.fillRect(x + PAD_X, cy + 1, w - PAD_X * 2, 1)
        cy += 3
      }
      setFont(ctx, last ? 600 : 400, 10.5, theme.sans)
      text(ctx, label, x + PAD_X, cy + LINE / 2, theme.ink)
      text(ctx, amount, x + w - PAD_X, cy + LINE / 2, theme.ink, 'right')
      cy += LINE
    })

    setFont(ctx, 400, 8.5, theme.sans)
    const timeRight = x + w - PAD_X - (out ? 13 : 0)
    text(ctx, message.time, timeRight, cy + 7, theme.muted, 'right')
    if (out) tick(ctx, x + w - PAD_X - 11, cy + 2.5, 10, READ_BLUE, true)
    cy += 14

    setFont(ctx, 500, 10.5, theme.sans)
    for (const button of buttons) {
      ctx.fillStyle = 'rgba(16, 39, 31, 0.06)'
      ctx.fillRect(x, cy, w, 1)
      if (message.pressed === button) {
        ctx.save()
        roundRect(ctx, x, y, w, h, 7)
        ctx.clip()
        ctx.fillStyle = 'rgba(31, 106, 168, 0.1)'
        ctx.fillRect(x, cy + 1, w, 23)
        ctx.restore()
      }
      text(ctx, button, x + w / 2, cy + 12.5, LINK_BLUE, 'center')
      cy += 24
    }
  }

  return { w, h, draw }
}

export type ChatHeader = { name: string; subtitle: string; initials: string; clock: string }

const STATUS_H = 26
const HEADER_H = 42
const COMPOSER_H = 44

export function drawChatScreen(
  ctx: Ctx,
  theme: StoryTheme,
  { width: W, height: H, header, messages, business }: {
    width: number
    height: number
    header: ChatHeader
    messages: StoryMessage[]
    /** Avatar in accent green (a business) or ink (the alerts number). */
    business: boolean
  },
) {
  ctx.save()
  roundRect(ctx, 0, 0, W, H, 26)
  ctx.clip()
  ctx.fillStyle = theme.wallpaper
  ctx.fillRect(0, 0, W, H)

  // Messages, newest at the bottom; older ones scroll off the top.
  const top = STATUS_H + HEADER_H
  const bottom = H - COMPOSER_H
  ctx.save()
  ctx.beginPath()
  ctx.rect(0, top, W, bottom - top)
  ctx.clip()
  let y = bottom - 4
  for (let i = messages.length - 1; i >= 0 && y > top; i--) {
    const laid = layoutMessage(ctx, theme, messages[i], W - 16)
    y -= laid.h
    laid.draw(messages[i].side === 'out' ? W - 8 - laid.w : 8, y)
    y -= 7
  }
  ctx.restore()

  // Status bar
  ctx.fillStyle = theme.card
  ctx.fillRect(0, 0, W, STATUS_H)
  setFont(ctx, 500, 9, theme.mono)
  text(ctx, header.clock, 20, 14, theme.ink)
  roundRect(ctx, W / 2 - 28, 7, 56, 14, 7)
  ctx.fillStyle = theme.ink
  ctx.fill()
  for (let bar = 0; bar < 3; bar++) {
    ctx.fillRect(W - 44 + bar * 4, 17 - bar * 2.5, 2.5, 3 + bar * 2.5)
  }
  roundRect(ctx, W - 28, 9, 15, 9, 2)
  ctx.fill()

  // Chat header
  ctx.fillStyle = theme.card
  ctx.fillRect(0, STATUS_H, W, HEADER_H)
  ctx.fillStyle = theme.line2
  ctx.fillRect(0, top - 1, W, 1)
  ctx.strokeStyle = theme.muted
  ctx.lineWidth = 1.6
  ctx.lineCap = 'round'
  ctx.beginPath()
  ctx.moveTo(16, STATUS_H + 15)
  ctx.lineTo(11, STATUS_H + 21)
  ctx.lineTo(16, STATUS_H + 27)
  ctx.stroke()
  ctx.fillStyle = business ? theme.accent : theme.ink
  ctx.beginPath()
  ctx.arc(37, STATUS_H + 21, 14, 0, Math.PI * 2)
  ctx.fill()
  setFont(ctx, 600, 10, theme.sans)
  text(ctx, header.initials, 37, STATUS_H + 21.5, business ? '#ffffff' : theme.paper, 'center')
  setFont(ctx, 600, 11.5, theme.sans)
  text(ctx, header.name, 58, STATUS_H + 15, theme.ink)
  setFont(ctx, 400, 9, theme.sans)
  text(ctx, header.subtitle, 58, STATUS_H + 29, theme.muted)

  // Composer
  roundRect(ctx, 8, H - 36, W - 52, 28, 14)
  ctx.fillStyle = '#ffffff'
  ctx.fill()
  setFont(ctx, 400, 10, theme.sans)
  text(ctx, 'Message', 20, H - 22, theme.muted)
  ctx.fillStyle = theme.accent
  ctx.beginPath()
  ctx.arc(W - 22, H - 22, 14, 0, Math.PI * 2)
  ctx.fill()
  roundRect(ctx, W - 25, H - 29, 6, 11, 3)
  ctx.fillStyle = '#ffffff'
  ctx.fill()

  ctx.restore()
}

/* ---------- Cards ---------- */

function pill(ctx: Ctx, theme: StoryTheme, label: string, x: number, y: number, lit: boolean) {
  setFont(ctx, 400, 9.5, theme.mono)
  const w = ctx.measureText(label).width + 16
  roundRect(ctx, x + 0.5, y + 0.5, w - 1, 19, 9.5)
  ctx.fillStyle = lit ? theme.accentSoft : theme.card
  ctx.fill()
  ctx.strokeStyle = lit ? theme.accent : theme.line
  ctx.lineWidth = 1
  ctx.stroke()
  text(ctx, label, x + w / 2, y + 10.5, lit ? theme.accent2 : theme.muted, 'center')
  return w
}

export const TEMPLATE_CARD = { width: 250, height: 160 }

/** The approved campaign template with its delivery statuses; `statuses` lit (0..3). */
export function drawTemplateCard(ctx: Ctx, theme: StoryTheme, statuses: number) {
  const { width: W, height: H } = TEMPLATE_CARD
  card(ctx, theme, W, H)
  setFont(ctx, 400, 10.5, theme.mono)
  text(ctx, 'diwali_offer', 14, 20, theme.ink)

  setFont(ctx, 400, 9, theme.mono)
  const chip = 'APPROVED'
  const chipWidth = ctx.measureText(chip).width + 26
  roundRect(ctx, W - 14 - chipWidth, 11, chipWidth, 18, 9)
  ctx.fillStyle = theme.accentSoft
  ctx.fill()
  tick(ctx, W - 14 - chipWidth + 7, 15, 9, theme.accent2)
  text(ctx, chip, W - 14 - chipWidth + 18, 20.5, theme.accent2)

  text(ctx, 'MARKETING TEMPLATE', 14, 38, theme.muted)

  setFont(ctx, 400, 11.5, theme.sans)
  wrap(ctx, 'Namaste {{1}}! Fresh Kaju Katli and Soan Papdi, delivered across Jaipur.', W - 28).forEach(
    (line, i) => text(ctx, line, 14, 62 + i * 16, theme.ink),
  )

  let x = 14
  ;['Sent', 'Delivered', 'Read'].forEach((label, i) => {
    x += pill(ctx, theme, label, x, 126, i < statuses) + 6
  })
}

export const PRODUCT_CARD = { width: 150, height: 196 }

export function drawProductCard(ctx: Ctx, theme: StoryTheme, name: string, price: string) {
  const { width: W, height: H } = PRODUCT_CARD
  card(ctx, theme, W, H)
  productArt(ctx, 10, 10, W - 20, 70)
  setFont(ctx, 600, 11.5, theme.sans)
  text(ctx, name, 12, 98, theme.ink)
  setFont(ctx, 400, 11, theme.sans)
  text(ctx, price, 12, 115, theme.muted)
  roundRect(ctx, 10.5, H - 38.5, W - 21, 26, 6)
  ctx.strokeStyle = theme.line
  ctx.lineWidth = 1
  ctx.stroke()
  setFont(ctx, 500, 10.5, theme.sans)
  text(ctx, 'Add to cart', W / 2, H - 25, LINK_BLUE, 'center')
}

export const PAYMENT_CARD = { width: 230, height: 160 }

/** The seller's payment link for the order, before and after it is paid. */
export function drawPaymentCard(ctx: Ctx, theme: StoryTheme, paid: boolean) {
  const { width: W, height: H } = PAYMENT_CARD
  card(ctx, theme, W, H)
  setFont(ctx, 400, 9.5, theme.mono)
  text(ctx, 'PAYMENT LINK · SHARMA SWEETS', 14, 22, theme.muted)
  setFont(ctx, 600, 30, theme.display)
  text(ctx, '₹540', 13, 56, theme.ink)
  setFont(ctx, 400, 11, theme.sans)
  text(ctx, 'Order SS-1042 · UPI or card', 14, 86, theme.muted)

  roundRect(ctx, 14, 108, W - 28, 36, 7)
  ctx.fillStyle = paid ? theme.accentSoft : theme.ink
  ctx.fill()
  if (paid) {
    setFont(ctx, 600, 11.5, theme.sans)
    const label = 'Paid to the seller'
    const labelWidth = ctx.measureText(label).width
    const start = W / 2 - (labelWidth + 24) / 2
    ctx.fillStyle = theme.accent
    ctx.beginPath()
    ctx.arc(start + 8, 126, 8, 0, Math.PI * 2)
    ctx.fill()
    tick(ctx, start + 3.5, 121.5, 9, '#ffffff')
    text(ctx, label, start + 24, 126.5, theme.accent2)
  } else {
    setFont(ctx, 500, 11.5, theme.sans)
    text(ctx, 'Pay ₹540', W / 2, 126.5, theme.paper, 'center')
  }
}

export const COD_CHIP = { width: 170, height: 40 }

export function drawCodChip(ctx: Ctx, theme: StoryTheme) {
  const { width: W, height: H } = COD_CHIP
  card(ctx, theme, W, H, 12)
  ctx.fillStyle = theme.amber
  ctx.beginPath()
  ctx.arc(18, H / 2, 4, 0, Math.PI * 2)
  ctx.fill()
  setFont(ctx, 500, 11.5, theme.sans)
  text(ctx, 'or Cash on delivery', 30, H / 2 + 0.5, theme.ink)
}

export const PARCEL_LABEL = { width: 112, height: 66 }

export function drawParcelLabel(ctx: Ctx, theme: StoryTheme, shipped: boolean) {
  const { width: W, height: H } = PARCEL_LABEL
  roundRect(ctx, 0, 0, W, H, 6)
  ctx.fillStyle = theme.card
  ctx.fill()
  setFont(ctx, 400, 9, theme.mono)
  text(ctx, 'SS-1042 · Kabir', 9, 15, theme.ink)
  setFont(ctx, 400, 9, theme.sans)
  text(ctx, 'Malviya Nagar, Jaipur', 9, 30, theme.muted)
  setFont(ctx, 500, 9, theme.mono)
  text(ctx, shipped ? 'SHIPPED' : 'PACKED', 9, 50, shipped ? theme.accent2 : theme.amber)
  if (shipped) tick(ctx, 60, 45, 9, theme.accent2)
}

/** A soft white rectangle on transparent (tinted by the material), for the drop-shadow planes. */
export function drawShadow(ctx: Ctx, size: number) {
  const inset = size * 0.22
  ctx.shadowColor = '#ffffff'
  ctx.shadowBlur = size * 0.12
  // Draw the shape off-canvas so only its blurred shadow lands inside.
  ctx.shadowOffsetX = size
  ctx.fillStyle = '#ffffff'
  roundRect(ctx, inset - size, inset, size - inset * 2, size - inset * 2, size * 0.06)
  ctx.fill()
}
