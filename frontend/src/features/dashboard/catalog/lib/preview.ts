import type { InteractiveButtonMessage } from '../../../../components/app'
import { formatPaise } from '../../../../lib/money'
import type { ProductKind } from './types'

const BODY_MAX = 1024

export type ProductCardInput = {
  /** Our product id; `null` while creating (a placeholder is used in the reply ids). */
  productId: string | null
  name: string
  pricePaise: number | null
  salePricePaise: number | null
  description: string
  imageUrl: string | null
  /** Services show their length and a *Book* button instead of the cart buttons. */
  kind?: ProductKind
  durationMinutes?: number | null
}

export function priceLine(pricePaise: number | null, salePricePaise: number | null): string {
  if (pricePaise === null) return '₹—'
  if (salePricePaise !== null && salePricePaise < pricePaise) return `~${formatPaise(pricePaise)}~ *${formatPaise(salePricePaise)}*`
  return formatPaise(pricePaise)
}

/** "45 min", "1 hr", "1 hr 30 min". */
export function formatDuration(minutes: number): string {
  const hours = Math.floor(minutes / 60)
  const rest = minutes % 60
  if (!hours) return `${rest} min`
  return rest ? `${hours} hr ${rest} min` : `${hours} hr`
}

/**
 * The bot-mode product card: an image-header reply-buttons message with the reply ids from the
 * contract's grammar (`upc:shop:add|qty:<product_id>`, `upc:shop:browse`). A service is booked one at a
 * time, so its card has *Book* and *Back* only.
 */
export function productCardMessage({
  productId,
  name,
  pricePaise,
  salePricePaise,
  description,
  imageUrl,
  kind = 'product',
  durationMinutes = null,
}: ProductCardInput): InteractiveButtonMessage {
  const id = productId ?? 'new'
  const service = kind === 'service'
  const price = priceLine(pricePaise, salePricePaise)
  const lines = [
    `*${name.trim() || (service ? 'Service name' : 'Product name')}*`,
    service && durationMinutes ? `${price} · ${formatDuration(durationMinutes)}` : price,
  ]
  const text = description.trim() ? `${lines.join('\n')}\n\n${description.trim()}` : lines.join('\n')
  const buttons: InteractiveButtonMessage['action']['buttons'] = service
    ? [
        { type: 'reply', reply: { id: `upc:shop:add:${id}:1`, title: 'Book' } },
        { type: 'reply', reply: { id: 'upc:shop:browse', title: 'Back' } },
      ]
    : [
        { type: 'reply', reply: { id: `upc:shop:add:${id}:1`, title: 'Add to cart' } },
        { type: 'reply', reply: { id: `upc:shop:qty:${id}`, title: 'Change qty' } },
        { type: 'reply', reply: { id: 'upc:shop:browse', title: 'Back' } },
      ]
  return {
    type: 'button',
    ...(imageUrl ? { header: { type: 'image' as const, image: { link: imageUrl } } } : {}),
    body: { text: text.length > BODY_MAX ? `${text.slice(0, BODY_MAX - 1)}…` : text },
    action: { buttons },
  }
}
