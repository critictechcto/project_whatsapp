import { z } from 'zod'
import { paiseToRupeesString, parseRupeesToPaise } from '../../../lib/money'
import type { StoreSettings, StoreSettingsPatch } from './api'

export const MAX_MENU_KEYWORDS = 20
export const PINCODE = /^[1-9]\d{5}$/
export const ORDER_PREFIX = /^[A-Z]{2,5}$/

const AMOUNT_MESSAGE = 'Enter an amount in rupees, like 60 or 99.50.'

/** A rupee amount typed by the seller. `optional` amounts may be left empty (sent as null). */
function rupees({ optional }: { optional: boolean }) {
  return z.string().superRefine((value, ctx) => {
    if (!value.trim()) {
      if (!optional) ctx.addIssue({ code: 'custom', message: 'Enter an amount (0 for none).' })
      return
    }
    if (parseRupeesToPaise(value) === null) ctx.addIssue({ code: 'custom', message: AMOUNT_MESSAGE })
  })
}

export const settingsSchema = z.object({
  shop_mode: z.enum(['bot', 'native_catalog']),
  store_name: z.string().trim().min(1, 'Enter your store name.').max(60, 'Use 60 characters or fewer.'),
  welcome_message: z.string().trim().min(1, 'Write a welcome message.').max(1024, 'Use 1,024 characters or fewer.'),
  menu_keywords: z
    .array(z.string())
    .min(1, 'Add at least one word that opens the store menu.')
    .max(MAX_MENU_KEYWORDS, `Use ${MAX_MENU_KEYWORDS} keywords or fewer.`),
  order_prefix: z.string().regex(ORDER_PREFIX, 'Use 2 to 5 capital letters, like SS.'),
  min_order: rupees({ optional: false }),
  shipping_fee: rupees({ optional: false }),
  free_shipping_above: rupees({ optional: true }),
  cod_enabled: z.boolean(),
  cod_fee: rupees({ optional: false }),
  cod_max_order: rupees({ optional: true }),
  serviceable_pincodes: z.array(z.string().regex(PINCODE, 'Pincodes have 6 digits.')),
  support_message: z.string().trim().min(1, 'Write the reply buyers get when they tap Talk to us.').max(1024, 'Use 1,024 characters or fewer.'),
  powered_by_footer: z.boolean(),
  /** Empty uses the workspace default number. */
  phone_number_id: z.string(),
})

export type SettingsFormValues = z.infer<typeof settingsSchema>

/** API field → form field, for mapping 400 errors. */
export const settingsFieldMap: Record<string, keyof SettingsFormValues> = {
  min_order_paise: 'min_order',
  shipping_fee_paise: 'shipping_fee',
  free_shipping_above_paise: 'free_shipping_above',
  cod_fee_paise: 'cod_fee',
  cod_max_order_paise: 'cod_max_order',
}

const amount = (paise: number | null | undefined) => (paise === null || paise === undefined ? '' : paiseToRupeesString(paise).replace(/\.00$/, ''))

export function settingsToForm(settings: StoreSettings): SettingsFormValues {
  return {
    shop_mode: settings.shop_mode ?? 'bot',
    store_name: settings.store_name ?? '',
    welcome_message: settings.welcome_message ?? '',
    menu_keywords: [...(settings.menu_keywords ?? [])],
    order_prefix: settings.order_prefix ?? '',
    min_order: amount(settings.min_order_paise ?? 0),
    shipping_fee: amount(settings.shipping_fee_paise ?? 0),
    free_shipping_above: amount(settings.free_shipping_above_paise),
    cod_enabled: settings.cod_enabled ?? false,
    cod_fee: amount(settings.cod_fee_paise ?? 0),
    cod_max_order: amount(settings.cod_max_order_paise),
    serviceable_pincodes: [...(settings.serviceable_pincodes ?? [])],
    support_message: settings.support_message ?? '',
    powered_by_footer: settings.powered_by_footer ?? true,
    phone_number_id: settings.phone_number_id ?? '',
  }
}

const paise = (value: string) => parseRupeesToPaise(value) ?? 0
const optionalPaise = (value: string) => (value.trim() ? parseRupeesToPaise(value) : null)

export function formToPatch(values: SettingsFormValues): StoreSettingsPatch {
  return {
    shop_mode: values.shop_mode,
    store_name: values.store_name.trim(),
    welcome_message: values.welcome_message.trim(),
    menu_keywords: values.menu_keywords,
    order_prefix: values.order_prefix,
    min_order_paise: paise(values.min_order),
    shipping_fee_paise: paise(values.shipping_fee),
    free_shipping_above_paise: optionalPaise(values.free_shipping_above),
    cod_enabled: values.cod_enabled,
    cod_fee_paise: paise(values.cod_fee),
    cod_max_order_paise: optionalPaise(values.cod_max_order),
    serviceable_pincodes: values.serviceable_pincodes,
    support_message: values.support_message.trim(),
    powered_by_footer: values.powered_by_footer,
    phone_number_id: values.phone_number_id || null,
  }
}
