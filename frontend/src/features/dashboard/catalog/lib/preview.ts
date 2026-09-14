import type { InteractiveButtonMessage } from '../../../../components/app'
import { formatPaise } from '../../../../lib/money'

const BODY_MAX = 1024

export type ProductCardInput = {
  /** Our product id; `null` while creating (a placeholder is used in the reply ids). */
  productId: string | null
  name: string
  pricePaise: number | null
  salePricePaise: number | null
  description: string
  imageUrl: string | null
}

export function priceLine(pricePaise: number | null, salePricePaise: number | null): string {
  if (pricePaise === null) return '₹—'
  if (salePricePaise !== null && salePricePaise < pricePaise) return `~${formatPaise(pricePaise)}~ *${formatPaise(salePricePaise)}*`
  return formatPaise(pricePaise)
}

/**
 * The bot-mode product card: an image-header reply-buttons message with the reply ids from the
 * contract's grammar (`upc:shop:add|qty:<product_id>`, `upc:shop:browse`).
 */
export function productCardMessage({ productId, name, pricePaise, salePricePaise, description, imageUrl }: ProductCardInput): InteractiveButtonMessage {
  const id = productId ?? 'new'
  const lines = [`*${name.trim() || 'Product name'}*`, priceLine(pricePaise, salePricePaise)]
  const text = description.trim() ? `${lines.join('\n')}\n\n${description.trim()}` : lines.join('\n')
  return {
    type: 'button',
    ...(imageUrl ? { header: { type: 'image' as const, image: { link: imageUrl } } } : {}),
    body: { text: text.length > BODY_MAX ? `${text.slice(0, BODY_MAX - 1)}…` : text },
    action: {
      buttons: [
        { type: 'reply', reply: { id: `upc:shop:add:${id}:1`, title: 'Add to cart' } },
        { type: 'reply', reply: { id: `upc:shop:qty:${id}`, title: 'Change qty' } },
        { type: 'reply', reply: { id: 'upc:shop:browse', title: 'Back' } },
      ],
    },
  }
}
