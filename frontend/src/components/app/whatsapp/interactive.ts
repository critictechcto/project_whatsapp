/**
 * WhatsApp Cloud API interactive messages (the raw `interactive` object we send) and the inbound
 * `order` cart, as used by the commerce contract (`docs/contracts/wave-3-commerce.md`).
 * Render them with `InteractiveMessagePreview` and `OrderCartPreview`.
 */

export type InteractiveTextHeader = { type: 'text'; text: string }
export type InteractiveImageHeader = { type: 'image'; image: { link: string } }
/** Reply buttons and CTA messages take a text or image header; lists take text only. */
export type InteractiveHeader = InteractiveTextHeader | InteractiveImageHeader

export type InteractiveBody = { text: string }
export type InteractiveFooter = { text: string }

export type InteractiveReplyButton = { type: 'reply'; reply: { id: string; title: string } }

/** 1–3 reply buttons. */
export type InteractiveButtonMessage = {
  type: 'button'
  header?: InteractiveHeader
  body: InteractiveBody
  footer?: InteractiveFooter
  action: { buttons: InteractiveReplyButton[] }
}

export type InteractiveListRow = { id: string; title: string; description?: string }
export type InteractiveListSection = { title?: string; rows: InteractiveListRow[] }

/** A list opened from one button, up to 10 rows in total. */
export type InteractiveListMessage = {
  type: 'list'
  header?: InteractiveTextHeader
  body: InteractiveBody
  footer?: InteractiveFooter
  action: { button: string; sections: InteractiveListSection[] }
}

export type InteractiveCtaUrlMessage = {
  type: 'cta_url'
  header?: InteractiveHeader
  body: InteractiveBody
  footer?: InteractiveFooter
  action: { name: 'cta_url'; parameters: { display_text: string; url: string } }
}

/** A single product from a connected Meta catalog. */
export type InteractiveProductMessage = {
  type: 'product'
  body?: InteractiveBody
  footer?: InteractiveFooter
  action: { catalog_id: string; product_retailer_id: string }
}

export type InteractiveProductSection = { title: string; product_items: { product_retailer_id: string }[] }

/** Several products from a connected Meta catalog, in sections. */
export type InteractiveProductListMessage = {
  type: 'product_list'
  header: InteractiveTextHeader
  body: InteractiveBody
  footer?: InteractiveFooter
  action: { catalog_id: string; sections: InteractiveProductSection[] }
}

export type InteractiveCatalogMessage = {
  type: 'catalog_message'
  body: InteractiveBody
  footer?: InteractiveFooter
  action: { name: 'catalog_message'; parameters?: { thumbnail_product_retailer_id?: string } }
}

/** Asks the buyer for a delivery address (India only). */
export type InteractiveAddressMessage = {
  type: 'address_message'
  body: InteractiveBody
  action: {
    name: 'address_message'
    parameters: { country: 'IN'; values?: Record<string, string>; validation_errors?: Record<string, string> }
  }
}

export type InteractiveMessage =
  | InteractiveButtonMessage
  | InteractiveListMessage
  | InteractiveCtaUrlMessage
  | InteractiveProductMessage
  | InteractiveProductListMessage
  | InteractiveCatalogMessage
  | InteractiveAddressMessage

export type InteractiveType = InteractiveMessage['type']

/** One line of an inbound `order` message. `item_price` is a unit price in rupees (not paise). */
export type OrderCartItem = { product_retailer_id: string; quantity: number; item_price: number; currency: string }

/** The cart a buyer sends from WhatsApp's native catalog. */
export type OrderCart = { catalog_id: string; text?: string; product_items: OrderCartItem[] }

/** What previews show for a catalog product, keyed by `product_retailer_id` (our SKU). */
export type PreviewProduct = { name: string; pricePaise: number; imageUrl?: string | null }
export type ProductLookup = Record<string, PreviewProduct>

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

/** Shallow check of an unknown value (e.g. `Message.interactive` from the API) before rendering it. */
export function isInteractiveMessage(value: unknown): value is InteractiveMessage {
  if (!isRecord(value) || !isRecord(value.action)) return false
  const { action } = value
  switch (value.type) {
    case 'button':
      return isRecord(value.body) && Array.isArray(action.buttons)
    case 'list':
      return isRecord(value.body) && typeof action.button === 'string' && Array.isArray(action.sections)
    case 'cta_url':
      return isRecord(value.body) && isRecord(action.parameters)
    case 'product':
      return typeof action.product_retailer_id === 'string'
    case 'product_list':
      return isRecord(value.header) && isRecord(value.body) && Array.isArray(action.sections)
    case 'catalog_message':
    case 'address_message':
      return isRecord(value.body)
    default:
      return false
  }
}

/**
 * Reads a cart from Meta's `order` object (`product_items`) or the API's `MessageOrder` (`items`).
 * Numeric strings are accepted for quantity and price; malformed lines are dropped.
 */
export function toOrderCart(value: unknown): OrderCart | null {
  if (!isRecord(value)) return null
  const rawItems = Array.isArray(value.product_items) ? value.product_items : Array.isArray(value.items) ? value.items : null
  if (!rawItems) return null
  const product_items = rawItems.filter(isRecord).flatMap((item): OrderCartItem[] => {
    const quantity = Number(item.quantity)
    const itemPrice = Number(item.item_price)
    if (typeof item.product_retailer_id !== 'string' || !Number.isFinite(quantity) || !Number.isFinite(itemPrice)) return []
    return [
      {
        product_retailer_id: item.product_retailer_id,
        quantity,
        item_price: itemPrice,
        currency: typeof item.currency === 'string' ? item.currency : 'INR',
      },
    ]
  })
  return {
    catalog_id: typeof value.catalog_id === 'string' ? value.catalog_id : '',
    ...(typeof value.text === 'string' && value.text ? { text: value.text } : {}),
    product_items,
  }
}

/** Unit price of a cart line in paise. */
export function cartItemPricePaise(item: OrderCartItem): number {
  return Math.round(item.item_price * 100)
}

export function cartLineTotalPaise(item: OrderCartItem): number {
  return cartItemPricePaise(item) * item.quantity
}

export function cartTotalPaise(cart: OrderCart): number {
  return cart.product_items.reduce((sum, item) => sum + cartLineTotalPaise(item), 0)
}

/** Number of items in the cart (the sum of quantities), as WhatsApp counts them. */
export function cartItemCount(cart: OrderCart): number {
  return cart.product_items.reduce((sum, item) => sum + item.quantity, 0)
}
