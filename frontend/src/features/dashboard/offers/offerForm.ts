import { z } from 'zod'
import { fromZonedParts, toZonedParts } from '../../../lib/datetime'
import { paiseToRupeesString, parseRupeesToPaise } from '../../../lib/money'
import type { OfferAppliesTo, OfferCode, OfferCodeWrite, OfferDiscountType } from './types'

export const CODE_PATTERN = /^[A-Z0-9_-]{2,20}$/
export const MAX_TITLE = 60
export const MAX_REPLY = 900

const optionalRupees = (message: string) =>
  z.string().refine((value) => !value.trim() || parseRupeesToPaise(value) !== null, message)

const optionalWholeNumber = (min: number, message: string) =>
  z.string().refine((value) => {
    if (!value.trim()) return true
    const number = Number(value)
    return Number.isInteger(number) && number >= min
  }, message)

export const offerSchema = z
  .object({
    code: z
      .string()
      .trim()
      .min(1, 'Enter a code.')
      .refine((value) => CODE_PATTERN.test(value), 'Use 2 to 20 letters, digits, - or _.'),
    title: z.string().trim().min(1, 'Enter a title.').max(MAX_TITLE, `Keep it under ${MAX_TITLE} characters.`),
    reply_text: z.string().trim().min(1, 'Enter the reply customers get.').max(MAX_REPLY, `Keep it under ${MAX_REPLY} characters.`),
    discount_type: z.enum(['none', 'percent', 'amount']),
    percent: z.string(),
    amount: z.string(),
    max_discount: optionalRupees('Enter an amount in rupees, like 300.'),
    min_order: optionalRupees('Enter an amount in rupees, like 999.'),
    applies_to: z.enum(['all', 'products', 'services']),
    starts_on: z.string(),
    ends_on: z.string(),
    max_uses: optionalWholeNumber(1, 'Enter a whole number of 1 or more, or leave it empty.'),
    max_uses_per_contact: z.string().refine((value) => {
      const number = Number(value)
      return value.trim() !== '' && Number.isInteger(number) && number >= 1
    }, 'Enter a whole number of 1 or more.'),
    is_active: z.boolean(),
  })
  .superRefine((values, ctx) => {
    if (values.discount_type === 'percent') {
      const pct = Number(values.percent)
      if (!values.percent.trim() || !Number.isInteger(pct) || pct < 1 || pct > 90) {
        ctx.addIssue({ code: 'custom', path: ['percent'], message: 'Enter a whole percent from 1 to 90.' })
      }
    }
    if (values.discount_type === 'amount') {
      const paise = parseRupeesToPaise(values.amount)
      if (paise === null || paise < 100) ctx.addIssue({ code: 'custom', path: ['amount'], message: 'Enter at least ₹1.' })
    }
    if (values.starts_on && values.ends_on && values.ends_on < values.starts_on) {
      ctx.addIssue({ code: 'custom', path: ['ends_on'], message: 'The end date is before the start date.' })
    }
  })

export type OfferFormValues = z.infer<typeof offerSchema>

export function offerToForm(offer: OfferCode | null, timeZone: string): OfferFormValues {
  const day = (iso: string | null) => (iso ? toZonedParts(iso, timeZone).date : '')
  return {
    code: offer?.code ?? '',
    title: offer?.title ?? '',
    reply_text: offer?.reply_text ?? '',
    discount_type: offer?.discount_type ?? 'percent',
    percent: offer?.discount_type === 'percent' ? String(offer.discount_value) : '',
    amount: offer?.discount_type === 'amount' ? paiseToRupeesString(offer.discount_value).replace(/\.00$/, '') : '',
    max_discount: offer?.max_discount_paise ? paiseToRupeesString(offer.max_discount_paise).replace(/\.00$/, '') : '',
    min_order: offer?.min_order_paise ? paiseToRupeesString(offer.min_order_paise).replace(/\.00$/, '') : '',
    applies_to: offer?.applies_to ?? 'all',
    starts_on: day(offer?.starts_at ?? null),
    ends_on: day(offer?.ends_at ?? null),
    max_uses: offer?.max_uses ? String(offer.max_uses) : '',
    max_uses_per_contact: String(offer?.max_uses_per_contact ?? 1),
    is_active: offer?.is_active ?? true,
  }
}

const rupees = (value: string) => (value.trim() ? (parseRupeesToPaise(value) ?? 0) : 0)

/** Form values → API body. Dates cover whole days in the workspace zone. */
export function formToBody(values: OfferFormValues, timeZone: string): OfferCodeWrite {
  const type: OfferDiscountType = values.discount_type
  const discountValue = type === 'percent' ? Number(values.percent) : type === 'amount' ? rupees(values.amount) : 0
  return {
    code: values.code.trim().toUpperCase(),
    title: values.title.trim(),
    reply_text: values.reply_text.trim(),
    discount_type: type,
    discount_value: discountValue,
    max_discount_paise: type === 'percent' && values.max_discount.trim() ? rupees(values.max_discount) : null,
    min_order_paise: type === 'none' ? 0 : rupees(values.min_order),
    applies_to: values.applies_to as OfferAppliesTo,
    starts_at: values.starts_on ? fromZonedParts(values.starts_on, '00:00', timeZone) : null,
    ends_at: values.ends_on ? endOfDay(values.ends_on, timeZone) : null,
    max_uses: values.max_uses.trim() ? Number(values.max_uses) : null,
    max_uses_per_contact: Number(values.max_uses_per_contact),
    is_active: values.is_active,
  }
}

function endOfDay(date: string, timeZone: string): string | null {
  const start = fromZonedParts(date, '23:59', timeZone)
  return start ? new Date(new Date(start).getTime() + 59_999).toISOString() : null
}

/** API field → form field, for server validation errors. */
export function offerFieldMap(discountType: OfferDiscountType): Record<string, string> {
  return {
    discount_value: discountType === 'amount' ? 'amount' : 'percent',
    max_discount_paise: 'max_discount',
    min_order_paise: 'min_order',
    starts_at: 'starts_on',
    ends_at: 'ends_on',
  }
}

export const offerFormFields = [
  'code',
  'title',
  'reply_text',
  'discount_type',
  'percent',
  'amount',
  'max_discount',
  'min_order',
  'applies_to',
  'starts_on',
  'ends_on',
  'max_uses',
  'max_uses_per_contact',
  'is_active',
] as const
