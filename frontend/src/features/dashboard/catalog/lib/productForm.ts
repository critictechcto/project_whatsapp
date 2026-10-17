import { z } from 'zod'
import { paiseToRupeesString, parseRupeesToPaise } from '../../../../lib/money'
import type { Product, ProductWriteRequest } from './types'

/** Meta `retailer_id` rules from the contract. */
export const SKU_RE = /^[A-Za-z0-9_-]{1,100}$/
export const NAME_MAX = 200
export const DESCRIPTION_MAX = 1000
export const MIN_PRICE_PAISE = 100
export const MAX_QTY_LIMIT = 99
export const MIN_DURATION_MINUTES = 5
export const MAX_DURATION_MINUTES = 600

const INTEGER_RE = /^\d+$/

export type ProductFormMode = 'create' | 'edit'

export function productSchema(mode: ProductFormMode) {
  return z
    .object({
      kind: z.enum(['product', 'service']),
      sku: z.string().trim(),
      name: z.string().trim().min(1, 'Enter a product name.').max(NAME_MAX, `Use at most ${NAME_MAX} characters.`),
      description: z.string().max(DESCRIPTION_MAX, `Use at most ${DESCRIPTION_MAX} characters.`),
      price: z.string().trim(),
      salePrice: z.string().trim(),
      collectionId: z.string(),
      availability: z.enum(['in_stock', 'out_of_stock']),
      trackStock: z.boolean(),
      stockQty: z.string().trim(),
      duration: z.string().trim(),
      maxQty: z.string().trim(),
      isActive: z.boolean(),
    })
    .superRefine((values, ctx) => {
      if (mode === 'create') {
        if (!values.sku) ctx.addIssue({ code: 'custom', path: ['sku'], message: 'Enter a SKU.' })
        else if (!SKU_RE.test(values.sku)) {
          ctx.addIssue({ code: 'custom', path: ['sku'], message: 'Use letters, numbers, hyphens and underscores only (up to 100).' })
        }
      }

      const price = parseRupeesToPaise(values.price)
      if (!values.price) ctx.addIssue({ code: 'custom', path: ['price'], message: 'Enter a price.' })
      else if (price === null) ctx.addIssue({ code: 'custom', path: ['price'], message: 'Enter an amount in rupees, like 249 or 249.50.' })
      else if (price < MIN_PRICE_PAISE) ctx.addIssue({ code: 'custom', path: ['price'], message: 'The price must be at least ₹1.' })

      if (values.salePrice) {
        const sale = parseRupeesToPaise(values.salePrice)
        if (sale === null) {
          ctx.addIssue({ code: 'custom', path: ['salePrice'], message: 'Enter an amount in rupees, like 199 or 199.50.' })
        } else if (sale < MIN_PRICE_PAISE) {
          ctx.addIssue({ code: 'custom', path: ['salePrice'], message: 'The sale price must be at least ₹1.' })
        } else if (price !== null && sale >= price) {
          ctx.addIssue({ code: 'custom', path: ['salePrice'], message: 'The sale price must be lower than the price.' })
        }
      }

      const service = values.kind === 'service'
      if (service) {
        const duration = Number(values.duration)
        if (!INTEGER_RE.test(values.duration) || duration < MIN_DURATION_MINUTES || duration > MAX_DURATION_MINUTES) {
          ctx.addIssue({ code: 'custom', path: ['duration'], message: `Enter the length in minutes, from ${MIN_DURATION_MINUTES} to ${MAX_DURATION_MINUTES}.` })
        }
      }

      if (!service && values.trackStock && !INTEGER_RE.test(values.stockQty)) {
        ctx.addIssue({ code: 'custom', path: ['stockQty'], message: 'Enter a whole number of 0 or more.' })
      }

      const maxQty = Number(values.maxQty)
      if (!INTEGER_RE.test(values.maxQty) || maxQty < 1 || maxQty > MAX_QTY_LIMIT) {
        ctx.addIssue({ code: 'custom', path: ['maxQty'], message: `Enter a whole number from 1 to ${MAX_QTY_LIMIT}.` })
      }
    })
}

export type ProductFormValues = z.infer<ReturnType<typeof productSchema>>

export function productDefaults(product?: Product): ProductFormValues {
  return {
    kind: product?.kind ?? 'product',
    sku: product?.sku ?? '',
    name: product?.name ?? '',
    description: product?.description ?? '',
    price: product ? paiseToRupeesString(product.price_paise).replace(/\.00$/, '') : '',
    salePrice: product?.sale_price_paise != null ? paiseToRupeesString(product.sale_price_paise).replace(/\.00$/, '') : '',
    collectionId: product?.collection?.id ?? '',
    availability: product?.availability ?? 'in_stock',
    trackStock: product ? product.stock_qty !== null : false,
    stockQty: product?.stock_qty != null ? String(product.stock_qty) : '',
    duration: String(product?.duration_minutes ?? 60),
    maxQty: String(product?.max_qty_per_order ?? 10),
    isActive: product?.is_active ?? true,
  }
}

/** Form values (rupees as typed) → the API body (paise). Call only with values that passed the schema. */
export function toProductBody(values: ProductFormValues, mode: ProductFormMode): ProductWriteRequest {
  const body: ProductWriteRequest = {
    sku: values.sku,
    name: values.name,
    description: values.description,
    price_paise: parseRupeesToPaise(values.price) ?? 0,
    sale_price_paise: values.salePrice ? parseRupeesToPaise(values.salePrice) : null,
    collection_id: values.collectionId || null,
    availability: values.availability,
    kind: values.kind,
    // Services are booked, not stocked: no stock count, and a length instead.
    stock_qty: values.kind === 'product' && values.trackStock ? Number(values.stockQty) : null,
    duration_minutes: values.kind === 'service' ? Number(values.duration) : null,
    max_qty_per_order: Number(values.maxQty),
    is_active: values.isActive,
  }
  if (mode === 'edit') {
    // SKU is read-only after create.
    const { sku: _sku, ...rest } = body
    return rest as ProductWriteRequest
  }
  return body
}

/** API field → form field, for `applyApiErrorToForm`. */
export const productFieldMap: Record<string, string> = {
  price_paise: 'price',
  sale_price_paise: 'salePrice',
  collection_id: 'collectionId',
  stock_qty: 'stockQty',
  duration_minutes: 'duration',
  max_qty_per_order: 'maxQty',
  is_active: 'isActive',
}

export const productFormFields = [
  'sku',
  'name',
  'description',
  'price',
  'salePrice',
  'collectionId',
  'availability',
  'stockQty',
  'duration',
  'kind',
  'maxQty',
  'isActive',
] as const
