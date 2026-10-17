/**
 * Store settings with the services-and-offers contract fields (`docs/contracts/services-and-offers.md`).
 *
 * TODO(api:types): the bookings backend is built in parallel, so `schema.d.ts` doesn't have these fields yet.
 * After `npm run api:types` these become plain aliases of `Schemas[...]` and the casts in `api.ts` can go.
 */
import type { Schemas } from '../../../api/types'

/** A booking time window, `HH:MM` in the workspace time zone. */
export type BookingWindow = { label: string; start: string; end: string }

export type BookingTemplateField = 'booking_confirmed_template_id' | 'booking_cancelled_template_id' | 'booking_reminder_template_id'

export type BookingSettingsFields = {
  /** Default true. */
  pay_at_shop_enabled?: boolean
  /** 0–6, Monday = 0. */
  booking_days?: number[]
  /** 1–10 windows. */
  booking_windows?: BookingWindow[]
  /** 1–30, default 7. */
  booking_days_ahead?: number
  /** 0–48, 0 = no reminder. */
  booking_reminder_hours?: number
} & Partial<Record<BookingTemplateField, string | null>>

export type StoreSettings = Schemas['StoreSettings'] & BookingSettingsFields
export type StoreSettingsPatch = Schemas['PatchedStoreSettingsRequest'] & BookingSettingsFields

export const DEFAULT_BOOKING_WINDOWS: readonly BookingWindow[] = [
  { label: 'Morning', start: '09:00', end: '12:00' },
  { label: 'Afternoon', start: '12:00', end: '16:00' },
  { label: 'Evening', start: '16:00', end: '20:00' },
]
