import { useId, useState, type ReactNode } from 'react'
import { ChevronDown, CornerUpLeft, ExternalLink, List, MapPin, Package, ShoppingBag, Store } from 'lucide-react'
import { cn } from '../../../lib/cn'
import { formatPaise } from '../../../lib/money'
import type { InteractiveHeader, InteractiveMessage, PreviewProduct, ProductLookup } from './interactive'
import { PreviewBubble, type PreviewBubbleProps } from './PreviewBubble'
import { WhatsAppText } from './WhatsAppMessagePreview'

export type InteractiveMessagePreviewProps = PreviewBubbleProps & {
  message: InteractiveMessage
  /** Names, prices and images for `product`, `product_list` and `catalog_message`, keyed by retailer id (SKU). */
  products?: ProductLookup
}

const actionRow = 'flex w-full items-center justify-center gap-1.5 px-2.5 py-2 text-center text-[13px] font-medium text-[#1f6aa8]'

function Header({ header }: { header?: InteractiveHeader }) {
  if (!header) return null
  if (header.type === 'image') {
    return (
      <img
        src={header.image?.link}
        alt="Header image"
        className="m-1 mb-0 block aspect-[16/9] w-[calc(100%-0.5rem)] rounded-md bg-ink/10 object-cover"
      />
    )
  }
  return header.text ? <p className="px-2.5 pt-2 font-semibold text-ink">{header.text}</p> : null
}

function Body({ text }: { text?: string }) {
  if (!text) return null
  return (
    <p className="whitespace-pre-wrap break-words px-2.5 pt-1.5 text-ink">
      <WhatsAppText text={text} />
    </p>
  )
}

function Footer({ text }: { text?: string }) {
  return text ? <p className="px-2.5 pt-1 text-[12px] text-muted">{text}</p> : null
}

function ActionRow({ icon, children }: { icon: ReactNode; children: ReactNode }) {
  return (
    <p className={cn(actionRow, 'border-t border-ink/5')}>
      {icon}
      {children}
    </p>
  )
}

/** A bubble button that reveals what the buyer sees when tapping it. */
function Disclosure({ label, icon, children }: { label: string; icon: ReactNode; children: ReactNode }) {
  const [open, setOpen] = useState(false)
  const panelId = useId()
  return (
    <div className="border-t border-ink/5">
      <button
        type="button"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((value) => !value)}
        className={cn(actionRow, 'cursor-pointer hover:bg-ink/[0.03]')}
      >
        {icon}
        {label}
        <ChevronDown className={cn('size-3.5 transition-transform', open && 'rotate-180')} aria-hidden="true" />
      </button>
      <div id={panelId} hidden={!open} className="border-t border-ink/5 bg-white/70 px-2.5 py-2">
        {children}
      </div>
    </div>
  )
}

function SectionTitle({ children }: { children: ReactNode }) {
  return <p className="pb-0.5 pt-1.5 font-mono text-[10px] uppercase tracking-[0.12em] text-muted first:pt-0">{children}</p>
}

function ProductImage({ product, alt, className }: { product?: PreviewProduct; alt: string; className: string }) {
  if (product?.imageUrl) return <img src={product.imageUrl} alt={alt} className={cn('bg-ink/10 object-cover', className)} />
  return (
    <div aria-hidden="true" className={cn('grid place-items-center bg-ink/10 text-ink/50', className)}>
      <Package className="size-1/2 max-h-6 max-w-6" />
    </div>
  )
}

function ProductRow({ retailerId, products }: { retailerId: string; products?: ProductLookup }) {
  const product = products?.[retailerId]
  return (
    <li className="flex items-center gap-2 py-1">
      <ProductImage product={product} alt="" className="size-9 shrink-0 rounded" />
      <div className="min-w-0 flex-1">
        {product ? (
          <>
            <p className="truncate text-[13px] text-ink">{product.name}</p>
            <p className="text-[12px] text-muted">{formatPaise(product.pricePaise)}</p>
          </>
        ) : (
          <p className="truncate font-mono text-[12px] text-ink">{retailerId}</p>
        )}
      </div>
    </li>
  )
}

function hostname(url: string): string {
  try {
    return new URL(url).hostname
  } catch {
    return url
  }
}

function parts(message: InteractiveMessage, products?: ProductLookup): { content: ReactNode; actions?: ReactNode } {
  switch (message.type) {
    case 'button':
      return {
        content: (
          <>
            <Header header={message.header} />
            <Body text={message.body?.text} />
            <Footer text={message.footer?.text} />
          </>
        ),
        actions: (
          <ul aria-label="Reply buttons" className="divide-y divide-ink/5 border-t border-ink/5">
            {message.action.buttons.map((button, i) => (
              <li key={`${button.reply?.id}-${i}`} className={actionRow}>
                <CornerUpLeft className="size-3.5" aria-hidden="true" />
                {button.reply?.title}
              </li>
            ))}
          </ul>
        ),
      }

    case 'list':
      return {
        content: (
          <>
            <Header header={message.header} />
            <Body text={message.body?.text} />
            <Footer text={message.footer?.text} />
          </>
        ),
        actions: (
          <Disclosure label={message.action.button} icon={<List className="size-3.5" aria-hidden="true" />}>
            {message.action.sections.map((section, s) => (
              <div key={`${section.title}-${s}`}>
                {section.title && <SectionTitle>{section.title}</SectionTitle>}
                <ul aria-label={section.title || undefined} className="divide-y divide-ink/5">
                  {section.rows.map((row) => (
                    <li key={row.id} className="py-1.5">
                      <p className="text-[13px] text-ink">{row.title}</p>
                      {row.description && <p className="text-[12px] text-muted">{row.description}</p>}
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </Disclosure>
        ),
      }

    case 'cta_url': {
      const { display_text, url } = message.action.parameters
      return {
        content: (
          <>
            <Header header={message.header} />
            <Body text={message.body?.text} />
            <Footer text={message.footer?.text} />
          </>
        ),
        actions: (
          <p className={cn(actionRow, 'border-t border-ink/5')} title={url}>
            <ExternalLink className="size-3.5" aria-hidden="true" />
            {display_text}
            <span className="sr-only">, opens {hostname(url)}</span>
          </p>
        ),
      }
    }

    case 'product': {
      const retailerId = message.action.product_retailer_id
      const product = products?.[retailerId]
      return {
        content: (
          <>
            <ProductImage product={product} alt={product?.name ?? retailerId} className="m-1 mb-0 block aspect-square w-[calc(100%-0.5rem)] rounded-md" />
            <div className="px-2.5 pt-2">
              {product ? (
                <>
                  <p className="font-semibold text-ink">{product.name}</p>
                  <p className="text-[12.5px] text-ink">{formatPaise(product.pricePaise)}</p>
                </>
              ) : (
                <p className="font-mono text-[12.5px] text-ink">{retailerId}</p>
              )}
            </div>
            <Body text={message.body?.text} />
            <Footer text={message.footer?.text} />
          </>
        ),
        actions: <ActionRow icon={<ShoppingBag className="size-3.5" aria-hidden="true" />}>View</ActionRow>,
      }
    }

    case 'product_list': {
      const count = message.action.sections.reduce((sum, section) => sum + (section.product_items?.length ?? 0), 0)
      return {
        content: (
          <>
            <Header header={message.header} />
            <Body text={message.body?.text} />
            <Footer text={message.footer?.text} />
            <p className="px-2.5 pt-1 text-[12px] text-muted">
              {count} {count === 1 ? 'item' : 'items'}
            </p>
          </>
        ),
        actions: (
          <Disclosure label="View items" icon={<ShoppingBag className="size-3.5" aria-hidden="true" />}>
            {message.action.sections.map((section, s) => (
              <div key={`${section.title}-${s}`}>
                {section.title && <SectionTitle>{section.title}</SectionTitle>}
                <ul aria-label={section.title || undefined} className="divide-y divide-ink/5">
                  {section.product_items.map((item, i) => (
                    <ProductRow key={`${item.product_retailer_id}-${i}`} retailerId={item.product_retailer_id} products={products} />
                  ))}
                </ul>
              </div>
            ))}
          </Disclosure>
        ),
      }
    }

    case 'catalog_message': {
      const thumbnailId = message.action.parameters?.thumbnail_product_retailer_id
      const thumbnail = thumbnailId ? products?.[thumbnailId] : undefined
      return {
        content: (
          <>
            {thumbnail?.imageUrl && (
              <img
                src={thumbnail.imageUrl}
                alt={thumbnail.name}
                className="m-1 mb-0 block aspect-[16/9] w-[calc(100%-0.5rem)] rounded-md bg-ink/10 object-cover"
              />
            )}
            <Body text={message.body?.text} />
            <Footer text={message.footer?.text} />
          </>
        ),
        actions: <ActionRow icon={<Store className="size-3.5" aria-hidden="true" />}>View catalog</ActionRow>,
      }
    }

    case 'address_message':
      return {
        content: <Body text={message.body?.text} />,
        actions: <ActionRow icon={<MapPin className="size-3.5" aria-hidden="true" />}>Provide address</ActionRow>,
      }

    default: {
      const unknown = message as { body?: { text?: string } }
      return { content: <Body text={unknown.body?.text || 'Interactive message'} /> }
    }
  }
}

/**
 * A Cloud API interactive message as the buyer sees it: reply buttons, lists, CTA links, products,
 * product lists, catalog and address requests. List rows and product lists open with a real button.
 */
export function InteractiveMessagePreview({ message, products, ...bubble }: InteractiveMessagePreviewProps) {
  const { content, actions } = parts(message, products)
  return (
    <PreviewBubble {...bubble} caption="Interactive message preview" actions={actions}>
      {content}
    </PreviewBubble>
  )
}
