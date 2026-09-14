import { ShoppingCart } from 'lucide-react'
import { formatPaise } from '../../../lib/money'
import {
  cartItemCount,
  cartItemPricePaise,
  cartLineTotalPaise,
  cartTotalPaise,
  type OrderCart,
  type ProductLookup,
} from './interactive'
import { PreviewBubble, type PreviewBubbleProps } from './PreviewBubble'
import { WhatsAppText } from './WhatsAppMessagePreview'

export type OrderCartPreviewProps = PreviewBubbleProps & {
  /** The cart from an inbound `order` message; normalise API data with `toOrderCart`. */
  order: OrderCart
  /** Product names by retailer id (SKU). Lines without a match show the retailer id. */
  products?: ProductLookup
}

/**
 * A cart sent from WhatsApp's native catalog. Totals come from the cart's own prices
 * (`item_price` rupees × quantity) and are display only: checkout re-prices from the catalog.
 */
export function OrderCartPreview({ order, products, direction = 'inbound', ...bubble }: OrderCartPreviewProps) {
  const count = cartItemCount(order)
  const total = cartTotalPaise(order)
  const countLabel = `${count} ${count === 1 ? 'item' : 'items'}`

  return (
    <PreviewBubble {...bubble} direction={direction} caption="Order cart preview">
      <div className="m-1 mb-0 flex items-center gap-2.5 rounded-md bg-ink/[0.05] px-2.5 py-2">
        <div aria-hidden="true" className="grid size-9 shrink-0 place-items-center rounded bg-ink/10 text-ink/60">
          <ShoppingCart className="size-4" />
        </div>
        <div className="min-w-0">
          <p className="font-semibold text-ink">{countLabel}</p>
          <p className="text-[12px] text-muted">{formatPaise(total)} (estimated total)</p>
        </div>
      </div>
      <ul aria-label="Cart items" className="divide-y divide-ink/5 px-2.5 pt-1">
        {order.product_items.map((item, i) => {
          const product = products?.[item.product_retailer_id]
          return (
            <li key={`${item.product_retailer_id}-${i}`} className="flex items-baseline justify-between gap-3 py-1.5">
              <div className="min-w-0">
                {product ? (
                  <p className="truncate text-[13px] text-ink">{product.name}</p>
                ) : (
                  <p className="truncate font-mono text-[12px] text-ink">{item.product_retailer_id}</p>
                )}
                <p className="text-[12px] text-muted">
                  {item.quantity} × {formatPaise(cartItemPricePaise(item))}
                </p>
              </div>
              <p className="shrink-0 text-[13px] tabular-nums text-ink">{formatPaise(cartLineTotalPaise(item))}</p>
            </li>
          )
        })}
      </ul>
      <p className="mx-2.5 flex justify-between border-t border-ink/10 pt-1.5 font-semibold text-ink">
        <span>Total</span>
        <span className="tabular-nums">{formatPaise(total)}</span>
      </p>
      {order.text && (
        <p className="whitespace-pre-wrap break-words px-2.5 pt-1.5 text-ink">
          <WhatsAppText text={order.text} />
        </p>
      )}
    </PreviewBubble>
  )
}
